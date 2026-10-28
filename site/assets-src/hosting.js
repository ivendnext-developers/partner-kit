// site/assets-src/hosting.js — Host your app from this page: sign in with GitHub, pick your repository and your
// customer, pick a plan and its copies, pay in a new tab, and follow the order to live (developer.ivendnext.com/hosting).
//
// It talks to one place, the hosting itself (https://hosting.ivendnext.app/v1/web/), which the page's own content policy
// is the only address it may reach. Sign-in: GitHub sends the browser back here with a code; this script checks the
// `state` it kept, takes the code and the state out of the address before anything else, and gives the code and its
// PKCE verifier to the hosting, which exchanges them on the server. The session it gets back is kept in this script's
// memory only: a reload signs out. The steps you filled in (never a secret, never the session) are kept for this tab in
// sessionStorage, so a new sign-in picks up where you were. Your GitHub token never reaches this page.
//
// The pure parts are exported for site/test_hosting.mjs; the page itself is checked in a browser.
(function (root) {
  "use strict";

  var API = "https://hosting.ivendnext.app/v1/web";
  var PAGE = "https://developer.ivendnext.com/hosting";   // the GitHub App's one callback address
  var KEEP = "ivn-hosting-steps";                          // this tab's steps (no secret)
  var PENDING = "ivn-hosting-signin";                      // the state and verifier of a sign-in on its way, used once
  var ENVS = ["prod", "staging", "sandbox"];
  var COPY_WORDS = { prod: "production", staging: "staging", sandbox: "sandbox" };

  // ── the pure parts ──────────────────────────────────────────────────────────────────────────────────────────────

  function b64u(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function randomString(n, cryptoObj) {
    return b64u((cryptoObj || root.crypto).getRandomValues(new Uint8Array(n)));
  }

  function challengeOf(verifier, cryptoObj) {   // PKCE S256
    var c = cryptoObj || root.crypto;
    return c.subtle.digest("SHA-256", new TextEncoder().encode(verifier)).then(function (d) { return b64u(new Uint8Array(d)); });
  }

  function authorizeUrl(clientId, state, challenge) {
    return "https://github.com/login/oauth/authorize?" + new URLSearchParams({
      client_id: clientId, redirect_uri: PAGE, state: state, code_challenge: challenge, code_challenge_method: "S256",
      allow_signup: "false"
    }).toString();
  }

  // What the address says on arrival. A code is accepted only with the state this tab sent, once.
  function readReturn(search, pending) {
    var q = new URLSearchParams(search || "");
    if (q.has("code") || q.has("state") || q.has("error")) {
      if (q.has("error")) return { kind: "refused", why: "GitHub did not sign you in. Sign in again when you are ready." };
      if (!pending || !pending.state || pending.state !== q.get("state") || !q.get("code")) {
        return { kind: "refused", why: "This sign-in was not started from this page, or was already used. Sign in again." };
      }
      return { kind: "signin", code: q.get("code"), verifier: pending.verifier };
    }
    if (/^[0-9a-f]{16}$/.test(q.get("order") || "")) return { kind: q.get("left") ? "left" : "back", order: q.get("order") };
    return { kind: "none" };
  }

  function subjectFor(repo, plainName) {
    if (!repo) return "";
    return plainName ? "" : repo.subject || "";   // empty: the hosting trusts repo:<owner>/<name>
  }

  // What of app.json the order sends: names and shapes, never a value (the kit's hosting_order.app_settings).
  function appSettings(m) {
    var keep = ["app", "version", "runs", "size", "port", "health", "handler", "region", "shops", "schedule", "timeout"], out = {};
    keep.forEach(function (k) { if (k in m) out[k] = m[k]; });
    out.env = (m.env || []).filter(function (e) { return e && typeof e === "object"; }).map(function (e) {
      var x = {};
      ["name", "secret", "required"].forEach(function (k) { if (k in e) x[k] = e[k]; });
      return x;
    });
    return out;
  }

  function scheduled(m) {   // as the hosting reads it: a non-empty schedule, or any timeout
    var x = m.schedule;
    var some = !!x && (typeof x !== "object" || Object.keys(x).length > 0);
    return some || "timeout" in m;
  }

  function plainNames(m) {
    return (m.env || []).filter(function (e) { return e && e.name && !e.secret; }).map(function (e) { return e.name; });
  }

  function missingRequired(m, settings) {   // the hosting refuses an order that leaves one of these empty
    return (m.env || []).filter(function (e) {
      return e && e.name && e.required && !e.secret && !String((settings || {})[e.name] || "").trim();
    }).map(function (e) { return e.name; });
  }

  function planCopies(plans, plan) {
    var p = plans && plans.plans && plans.plans[plan];
    return p ? ENVS.filter(function (e) { return p.enforced.envs.indexOf(e) >= 0; }) : [];
  }

  function orderPayload(s, cmd, scheduleVersion) {
    var m = JSON.parse(s.appJson);
    var gh = { repo: s.repo, branch: s.branch || "main" };
    if (s.folder && s.folder !== ".") gh.folder = s.folder;   // a folder only when one was given: never "." over a hand-set one
    if (s.subject) gh.subject = s.subject;
    var plain = {};
    Object.keys(s.settings || {}).forEach(function (k) { if (s.settings[k] !== "") plain[k] = s.settings[k]; });
    var p = { cmd: cmd, app: appSettings(m), plan: s.plan, copies: ENVS.filter(function (e) { return (s.copies || []).indexOf(e) >= 0; }),
              customer: s.forCustomer ? s.customer : "", github: gh, plain_env: plain, invoice: !!s.invoice,
              email: s.invoice ? s.email : "", schedule_version: s.accepted === scheduleVersion ? scheduleVersion : "" };
    if (cmd === "check") delete p.cmd;
    return p;
  }

  function copyWords(c) {
    var st = c.status, w = {
      pending: "waiting for the payment", paid: "paid, being built", building: "being built", waiting: "built, waiting for its secrets and its first version",
      live: "live", held: "held", stopped: "stopped", removing: "being removed", removed: "removed", expired: "not ordered (given back)",
      failed: "failed to build (the payment is refunded)"
    }[st] || st;
    if (st === "building" && c.building) w = { create: "being built", roll: "putting a new version live", stop: "being stopped", remove: "being removed" }[c.building] || w;
    if (c.live_version && ["removed", "expired", "failed", "removing"].indexOf(st) < 0) w += ", running " + c.live_version;
    if (c.held) w += " (" + c.held + ")";
    if (c.waiting_for) w += " (waiting for " + [].concat(c.waiting_for).join(", ") + ")";
    if (c.roll_failed) w += " (version " + c.roll_failed + " did not start)";
    if (c.push_refused) w += " (version " + c.push_refused + " was refused)";
    return w;
  }

  function settled(order) {   // nothing more to wait for: every copy live, or the order ended
    var cs = order.copies || [order];
    return cs.every(function (c) { return c.status === "live" && !c.building; }) ||
      cs.some(function (c) { return ["failed", "expired", "removed", "stopped"].indexOf(c.status) >= 0; });
  }

  function ended(o) {   // every copy has ended, as My apps reads it
    return (o.copies || [o]).every(function (c) { return ["expired", "removed", "failed"].indexOf(c.status) >= 0; });
  }

  // A lookup's answer applied to the steps (pure, tested): GitHub's own spelling of the name wins; a subject the person
  // typed or emptied (subjectSet) is never replaced; one that names an earlier repository is cleared.
  function prefill(s, asked, r) {
    var out = Object.assign({}, s);
    if (out.repo !== asked) return out;                           // the person has moved on: a late answer changes nothing
    var mine = r.found && r.can_push !== false;
    if (mine && r.repo !== asked) out.repo = r.repo;              // renamed, moved, or typed in other letter case
    if (out.subject && !subjectNames(out.subject, out.repo)) { out.subject = ""; out.subjectSet = false; }
    if (mine && !out.subjectSet) out.subject = r.subject;
    out.looked = Object.assign({}, r, { asked: out.repo });
    return out;
  }

  function subjectNames(subject, repo) {   // the subject's owner/name (either form) is this repository
    var m = /^repo:([^@/]+)(?:@\d+)?\/([^@:]+)(?:@\d+)?$/.exec(subject || "");
    return !!m && (m[1] + "/" + m[2]).toLowerCase() === String(repo || "").toLowerCase();
  }

  function checkCommand(s, maker, m) {
    var cmd = "python3 tools/deploy_app/deploy_app.py " + (s.folder || ".");
    if (m && m.runs !== "function") cmd += " --image hosting.ivendnext.app/partner-apps/" + m.app + ":" + m.version;
    return cmd + " --plan " + (s.plan || "starter") + " --partner " + maker;
  }

  function publishCommand(maker) {
    return "python3 <the kit>/tools/publish/publish.py publish . --partner " + maker;
  }

  var api = { b64u: b64u, randomString: randomString, challengeOf: challengeOf, authorizeUrl: authorizeUrl,
              readReturn: readReturn, subjectFor: subjectFor, appSettings: appSettings, plainNames: plainNames, scheduled: scheduled,
              missingRequired: missingRequired, prefill: prefill, subjectNames: subjectNames,
              planCopies: planCopies, orderPayload: orderPayload, copyWords: copyWords, settled: settled,
              checkCommand: checkCommand, publishCommand: publishCommand, PAGE: PAGE, API: API };
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }

  // ── the page ────────────────────────────────────────────────────────────────────────────────────────────────────

  var doc = root.document, tool = doc.getElementById("hosting-tool");
  if (!tool) return;

  // 1. Never inside another site's frame (a meta tag cannot carry frame-ancestors).
  if (root.top !== root.self) {
    tool.hidden = false;
    tool.textContent = "This page does not run inside another page. Open https://developer.ivendnext.com/hosting directly.";
    return;
  }

  // 2. Take the code and the state (or the paid order) out of the address before anything else.
  var FOLLOW = "ivn-hosting-follow";   // an order Stripe sent this tab back for: followed once you sign in here
  var pending = null;
  try { pending = JSON.parse(root.sessionStorage.getItem(PENDING) || "null"); } catch (e) { pending = null; }
  root.sessionStorage.removeItem(PENDING);   // one use, whatever the address says
  var arrival = readReturn(root.location.search, pending);
  if (root.location.search) root.history.replaceState(null, "", root.location.pathname + root.location.hash);

  var session = null, who = null, cfg = null, repos = null, poller = null;
  var s = load();

  function load() {
    try { return JSON.parse(root.sessionStorage.getItem(KEEP) || "null") || { step: "app" }; } catch (e) { return { step: "app" }; }
  }
  function keep() { root.sessionStorage.setItem(KEEP, JSON.stringify(s)); }
  function save() { s.checked = null; keep(); }   // any change to the order's inputs: check it again

  function el(tag, attrs) {
    var n = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") n.textContent = attrs[k];
      else if (k === "on") Object.keys(attrs.on).forEach(function (ev) { n.addEventListener(ev, attrs.on[ev]); });
      else if (k in n && typeof attrs[k] === "boolean") n[k] = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      n.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    }
    return n;
  }
  function p() { return el.apply(null, ["p", {}].concat([].slice.call(arguments))); }
  function code(t) { return el("code", { text: t }); }
  function button(text, fn, ghost) { return el("button", { type: "button", "class": "site-btn" + (ghost ? " site-btn-ghost" : ""), text: text, on: { click: fn } }); }
  function copyable(text) {
    return el("p", { "class": "hosting-copy" }, el("code", { text: text }), " ",
      button("Copy", function () { root.navigator.clipboard.writeText(text); }, true));
  }
  function field(label, input, hint) {
    var id = "h-" + Math.random().toString(36).slice(2);
    input.id = id;
    return el("p", { "class": "hosting-field" }, el("label", { "for": id, text: label }), input, hint ? el("span", { "class": "hosting-hint", text: hint }) : null);
  }

  function call(method, path, body) {
    var h = { "Content-Type": "application/json" };
    if (session) h.Authorization = "Bearer " + session;
    return root.fetch(API + path, { method: method, headers: h, body: body ? JSON.stringify(body) : undefined, credentials: "omit",
                                    referrerPolicy: "no-referrer", cache: "no-store" })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok) {
            if (r.status === 401 && j.refused === "not_signed_in") { session = null; who = null; }
            var err = new Error(j.words || "The hosting did not answer. Nothing is known to be done: try again.");
            err.code = j.refused;
            throw err;
          }
          return j;
        });
      }, function () { throw new Error("The hosting could not be reached. Nothing is known to be done: try again."); });
  }

  var out = el("div", { "class": "hosting-out", "aria-live": "polite" });
  function say(text, bad) { out.textContent = ""; if (text) out.appendChild(el("p", { "class": bad ? "hosting-bad" : "hosting-ok", text: text })); }
  function fail(e) { say(e.message, true); redraw(); }
  function redraw() { if (!busy()) render(); }   // an answer that arrives by itself never wipes what is being typed

  // ── sign-in ──

  function signIn() {
    var state = randomString(32), verifier = randomString(48);
    challengeOf(verifier).then(function (ch) {
      root.sessionStorage.setItem(PENDING, JSON.stringify({ state: state, verifier: verifier }));
      root.location.assign(authorizeUrl(cfg.client_id, state, ch));
    });
  }

  function fresh() { stopPolling(); current = null; mine = null; s = { step: "app" }; keep(); }

  function signOut() {
    call("POST", "/signout").then(function () { return true; }, function () { return false; }).then(function (ok) {
      session = null; who = null; repos = null; fresh();
      say(ok ? "Signed out. Your GitHub sign-in for this page has ended too." : "Signed out of this page.");
      render();
    });
  }

  function ownSteps() {
    if (s.maker !== who.maker || s.login !== who.login) { fresh(); s.maker = who.maker; s.login = who.login; keep(); }
  }

  function signInPanel() {
    var box = el("div", { "class": "hosting-step" }, el("h3", { text: "Sign in with GitHub" }));
    if (!cfg.ready) {
      box.appendChild(p(cfg.failed ? "The hosting could not be reached. Try again in a minute." :
        "Signing in with GitHub opens on this page soon. Until then, order with the kit's command: guide 14b, Order and pay online."));
      return box;
    }
    if (!session) {
      box.appendChild(p("Sign in with the GitHub account you use in the iVendNext Developers organisation. It tells us who you are; your hosting account (set up by iVendNext when your company signed) says which company you order for and what it pays."));
      box.appendChild(button("Sign in with GitHub", signIn));
      return box;
    }
    box.appendChild(p("Signed in as ", el("strong", { text: who.login }),
      who.maker ? " for " + (who.name || who.maker) + " (" + who.maker + ")." : "."));
    if (who.makers.length > 1) {
      var sel = el("select", {});
      who.makers.forEach(function (m) { sel.appendChild(el("option", { value: m, text: m })); });
      if (who.maker) sel.value = who.maker;
      box.appendChild(field("You order for", sel, "Your GitHub account is linked to more than one hosting account. What you pay is that account's."));
      box.appendChild(button("Use this one", function () {
        call("POST", "/choose", { maker: sel.value }).then(function (w) { who = w; ownSteps(); say(""); render(); refreshApps(); loadRepos(); }, fail);
      }, true));
    }
    if (who.maker) {
      box.appendChild(p("Your hosting account holds " + who.apps_held + " of its " + who.max_apps + " apps." +
        (who.open ? "" : " Self-serve hosting is open only to iVendNext's own teams while it is tested.")));
    }
    box.appendChild(button("Sign out", signOut, true));
    return box;
  }

  // ── before you start, then step 1: your app ──

  function beforeYouStart() {
    var kit = "https://github.com/ivendnext-developers/partner-kit/blob/main/";
    return el("details", { "class": "hosting-before", open: !s.repo },
      el("summary", { text: "Before you start: four things to have ready" }),
      el("ol", {},
        el("li", {}, "Your app, made with the kit: a sample started with ", code("tools/manifest/start.py"), " or the ",
          el("a", { href: kit + "tools/app_template/README.md", text: "app template" }),
          ". Its folder holds ", code("app.json"), ", which this page asks for."),
        el("li", {}, "Your app in a GitHub repository, with the kit's ", code("tools/deploy_app/hosting-workflow.yml"),
          " copied to ", code(".github/workflows/"), " in it."),
        el("li", {}, "The ", el("a", { href: cfg.install_url, text: "iVendNext App Hosting GitHub App" }),
          " installed on that repository. Then this page lists it, finds its sign-in subject and sets its Variables for you. It writes the repository's Actions variables and nothing else: it never reads your code."),
        el("li", {}, "The values of your app's settings (the plain ones in ", code("app.json"), "), and for a customer's app, the customer's code.")),
      p("The whole page, screen by screen, with a real sample: ",
        el("a", { href: "recipes/host_from_the_web_page.html", text: "Host your app from the web page" }), "."));
  }

  function appStep() {
    var box = el("div", { "class": "hosting-step" }, el("h3", { text: "1. Your app" }));
    var repoIn = el("input", { type: "text", value: s.repo || "", placeholder: "owner/name", autocomplete: "off", spellcheck: "false" });
    var list = el("select", {}, el("option", { value: "", text: repos ? "Choose from your list" : "Loading your list" }));
    (repos || []).forEach(function (r) { list.appendChild(el("option", { value: r.repo, text: r.repo + (r.private ? " (private)" : "") })); });
    list.value = (repos || []).some(function (r) { return r.repo === s.repo; }) ? s.repo : "";
    list.addEventListener("change", function () {
      var r = pick(list.value);
      if (r) { s.repo = r.repo; s.branch = r.branch; }
      save(); render();
    });
    repoIn.addEventListener("change", function () {
      s.repo = repoIn.value.trim(); s.subject = ""; s.subjectSet = false; s.looked = null; save(); render(); lookUp(true);
    });
    box.appendChild(field("Repository", list));
    box.appendChild(field("Or type it", repoIn, "The repository your GitHub workflow pushes each version from."));
    var branch = el("input", { type: "text", value: s.branch || "main", spellcheck: "false" });
    branch.addEventListener("change", function () { s.branch = branch.value.trim(); save(); });
    box.appendChild(field("Branch", branch));
    var folder = el("input", { type: "text", value: s.folder || ".", spellcheck: "false" });
    folder.addEventListener("change", function () { s.folder = folder.value.trim() || "."; save(); });
    box.appendChild(field("Folder that holds app.json", folder));

    var r = pick(s.repo);
    if (r) {
      var plain = el("input", { type: "checkbox", checked: !!s.plainSubject });
      plain.addEventListener("change", function () { s.plainSubject = plain.checked; s.subject = subjectFor(r, s.plainSubject); save(); render(); });
      s.subject = subjectFor(r, s.plainSubject);
      box.appendChild(p("GitHub signs your workflow in as ", code(s.subject || "repo:" + r.repo),
        ". A repository made since 2025 uses the first form, with its ids, and then a repository deleted and made again under the same name can never push your app."));
      box.appendChild(el("p", {}, el("label", {}, plain, " This repository signs in with its plain name (an older repository)")));
      box.appendChild(p("Not sure? Ask GitHub: ", code("gh api repos/" + r.repo + "/actions/oidc/customization/sub --jq .sub_claim_prefix"),
        " prints the first form if your repository uses it."));
    } else if (s.repo) {
      var lk = s.looked && s.looked.asked === s.repo ? s.looked : null;
      if (!lk) {
        box.appendChild(p("Looking for ", code(s.repo), " on GitHub."));
      } else if (lk.found && lk.can_push === false) {
        box.appendChild(el("p", { "class": "hosting-bad", text: "You cannot push to " + lk.repo + " on GitHub: check the repository's name. An order trusts only the repository you push your app from." }));
      } else if (lk.found) {
        box.appendChild(p("Found ", code(lk.repo), " on GitHub. Its sign-in subject is filled in below."));
      } else {
        box.appendChild(p("This page cannot see ", code(s.repo), ". Check the name. If the repository is private, ",
          el("a", { href: cfg.install_url, text: "install the GitHub App on it" }), " and press Look again, or paste below the line this command prints on your computer:"));
        box.appendChild(copyable("gh api repos/" + s.repo + "/actions/oidc/customization/sub --jq .sub_claim_prefix"));
      }
      box.appendChild(button("Look again", function () { s.looked = null; keep(); render(); lookUp(true); }, true));
      var subj = el("input", { type: "text", value: s.subject || "", spellcheck: "false", placeholder: "repo:owner@id/name@id" });
      subj.addEventListener("change", function () { s.subject = subj.value.trim(); s.subjectSet = true; save(); });
      box.appendChild(field("Its sign-in subject", subj, "How GitHub signs your workflow in: repo: then the owner and the repository, each with its number. Empty means the plain name, for a repository made before 2025."));
    }

    var file = el("input", { type: "file", accept: ".json,application/json" });
    var text = el("textarea", { rows: "6", spellcheck: "false" });
    text.value = s.appJson || "";
    file.addEventListener("change", function () {
      var f = file.files[0];
      if (f) f.text().then(function (t) { s.appJson = t; save(); render(); });
    });
    text.addEventListener("change", function () { s.appJson = text.value; save(); render(); });
    box.appendChild(field("app.json (drop the file in, or paste it)", file));
    box.appendChild(field("app.json", text));
    var m = parsed();
    if (m === false) box.appendChild(el("p", { "class": "hosting-bad", text: "That app.json is not JSON." }));
    if (m) {
      if (scheduled(m)) {
        box.appendChild(el("p", { "class": "hosting-bad", text: "An app that runs on a schedule is put live by CitiXsys, not ordered online yet: ask through your partner contact (guide 14b, A function on a schedule)." }));
      }
      box.appendChild(p(el("strong", { text: (m.app || "?") + " " + (m.version || "?") }), ", " +
        (m.runs === "function" ? "a function (it answers presses)" : "a container (its service)") + ", size " + (m.size || "?") + "."));
      var names = plainNames(m);
      s.settings = s.settings || {};
      var need = (m.env || []).filter(function (e) { return e && e.required; }).map(function (e) { return e.name; });
      names.forEach(function (n) {
        var v = el("input", { type: "text", value: s.settings[n] || "", spellcheck: "false" });
        v.addEventListener("change", function () { s.settings[n] = v.value; save(); render(); });
        var about = ((m.env || []).filter(function (e) { return e && e.name === n; })[0] || {}).about;
        box.appendChild(field("Setting " + n + (need.indexOf(n) >= 0 ? " (required)" : ""), v,
          (about ? about + " " : "") + (need.indexOf(n) >= 0 ? "Your app needs a value here to start." : "Leave it empty to leave it out.")));
      });
      var gap = missingRequired(m, s.settings);
      if (gap.length) box.appendChild(el("p", { "class": "hosting-bad", text: "Give a value for " + gap.join(", ") + ": your app.json marks it required." }));
      box.appendChild(p("The page checks app.json with the hosting. The Dockerfile, the licence files and the package need your repository: check them on your computer first, as the hosting will."));
      box.appendChild(copyable(checkCommand(s, who.maker, m)));
    }
    var lkd = s.looked && s.looked.asked === s.repo ? s.looked : null;
    var notYours = lkd && lkd.found && lkd.can_push === false;
    var waiting = s.repo && !pick(s.repo) && !lkd;   // the lookup has not answered yet
    box.appendChild(nav(null, (s.repo && m && !scheduled(m) && !missingRequired(m, s.settings).length && !notYours && !waiting) ? "customer" : null));
    return box;
  }

  function lookUp(again) {   // a typed repository: its sign-in subject, found by the hosting with your own GitHub access
    if (!s.repo || pick(s.repo) || (!again && s.looked && s.looked.asked === s.repo)) return;
    var asked = s.repo;
    call("POST", "/repo", { repo: asked }).then(function (r) {
      if (s.repo !== asked) return;
      s = prefill(s, asked, r); keep(); redraw();
    }, function (e) { if (s.repo === asked) { s.looked = { asked: asked, found: false, failed: true }; keep(); } fail(e); });
  }

  function pick(name) { return (repos || []).filter(function (r) { return r.repo === name; })[0] || null; }
  function parsed() {
    if (!s.appJson) return null;
    try { var m = JSON.parse(s.appJson); return m && typeof m === "object" ? m : false; } catch (e) { return false; }
  }

  // ── step 2: your customer ──

  function customerStep() {
    var box = el("div", { "class": "hosting-step" }, el("h3", { text: "2. Your customer" }));
    var no = el("input", { type: "radio", name: "h-cust", checked: !s.forCustomer });
    var yes = el("input", { type: "radio", name: "h-cust", checked: !!s.forCustomer });
    var codeIn = el("input", { type: "text", value: s.customer || "", spellcheck: "false", placeholder: "the customer's code" });
    no.addEventListener("change", function () { s.forCustomer = false; save(); render(); });
    yes.addEventListener("change", function () { s.forCustomer = true; save(); render(); });
    codeIn.addEventListener("change", function () { s.customer = codeIn.value.trim().toLowerCase(); save(); render(); });
    box.appendChild(el("p", {}, el("label", {}, no, " Not for a customer")));
    box.appendChild(el("p", {}, el("label", {}, yes, " Built for a customer: "), codeIn));
    box.appendChild(p("The customer's code is the one its Made for you shelf in the App library goes by: the same code you name when you publish to that customer. Lower-case letters, digits and hyphens, like ",
      code("acme-stores"), ". Ask your account team if you do not have it."));
    box.appendChild(p("Whoever orders the hosting pays: you, or the customer the app is built for when that customer orders it."));
    box.appendChild(nav("app", (!s.forCustomer || /^[a-z][a-z0-9-]{1,30}$/.test(s.customer || "")) ? "plan" : null));
    return box;
  }

  // ── step 3: plan, copies and terms ──

  function planStep() {
    var box = el("div", { "class": "hosting-step" }, el("h3", { text: "3. Plan, copies and terms" }));
    var plans = cfg.plans.plans;
    s.plan = s.plan in plans ? s.plan : Object.keys(plans)[0];
    Object.keys(plans).forEach(function (k) {
      var r = el("input", { type: "radio", name: "h-plan", checked: s.plan === k });
      r.addEventListener("change", function () { s.plan = k; s.copies = null; s.checked = null; save(); render(); });
      box.appendChild(el("p", {}, el("label", {}, r, " " + k.charAt(0).toUpperCase() + k.slice(1) + ": USD " + plans[k].price_usd_month +
        " per app per month, copies: " + planCopies(cfg.plans, k).map(function (e) { return COPY_WORDS[e]; }).join(", "))));
    });
    var offered = planCopies(cfg.plans, s.plan);
    s.copies = s.copies || offered.slice();
    var noProd = who.internal && s.forCustomer;
    if (noProd) s.copies = s.copies.filter(function (e) { return e !== "prod"; });
    offered.forEach(function (e) {
      var c = el("input", { type: "checkbox", checked: s.copies.indexOf(e) >= 0, disabled: noProd && e === "prod" });
      c.addEventListener("change", function () {
        s.copies = offered.filter(function (x) { return x === e ? c.checked : s.copies.indexOf(x) >= 0; });
        s.checked = null; save(); render();
      });
      box.appendChild(el("p", {}, el("label", {}, c, " " + COPY_WORDS[e] + " copy (https://" + appName() + (e === "prod" ? "" : "-" + e) + ".ivendnext.app)")));
    });
    box.appendChild(p("One order runs these copies at the plan's one price." + (noProd ? " Production for this customer is ordered by the customer, through the account team." : "")));
    var card = el("input", { type: "radio", name: "h-pay", checked: !s.invoice });
    var inv = el("input", { type: "radio", name: "h-pay", checked: !!s.invoice });
    var email = el("input", { type: "email", value: s.email || "", placeholder: "where the invoices go" });
    card.addEventListener("change", function () { s.invoice = false; save(); render(); });
    inv.addEventListener("change", function () { s.invoice = true; save(); render(); });
    email.addEventListener("change", function () { s.email = email.value.trim(); save(); render(); });
    box.appendChild(el("p", {}, el("label", {}, card, " Pay monthly by card")));
    box.appendChild(el("p", {}, el("label", {}, inv, " An invoice with payment terms, to "), email));
    var accept = el("input", { type: "checkbox", checked: s.accepted === cfg.schedule_version });
    accept.addEventListener("change", function () { s.accepted = accept.checked ? cfg.schedule_version : null; save(); render(); });
    box.appendChild(el("p", {}, el("label", {}, accept, " I accept the "),
      el("a", { href: cfg.schedule_url, text: "App Hosting Schedule" }),
      " (Schedule 1 of the iVendNext Developer Terms, dated " + cfg.schedule_version + "). The order records it."));
    var ready = s.copies.length && s.accepted === cfg.schedule_version && (!s.invoice || /@/.test(s.email || ""));
    box.appendChild(button("Check the order", function () {
      call("POST", "/check", orderPayload(s, "check", cfg.schedule_version)).then(function (r) {
        s.checked = r; keep(); say(""); render();
      }, function (e) { s.checked = null; fail(e); });
    }));
    if (!ready) box.lastChild.disabled = true;
    if (s.checked) {
      box.appendChild(p("The hosting takes it: " + s.checked.app + ", " + s.checked.addresses.join(", ") + ". " +
        (s.checked.pays_usd === 0 ? "No charge to you." : "USD " + s.checked.pays_usd + " a month, for every copy together.")));
    }
    box.appendChild(nav("customer", s.checked ? "pay" : null));
    return box;
  }

  function appName() { var m = parsed(); return (m && m.app) || "your-app"; }

  // ── step 4: pay ──

  function payStep() {
    var box = el("div", { "class": "hosting-step" }, el("h3", { text: "4. Pay" }));
    if (s.order && current && current.order === s.order && ended(current)) {
      box.appendChild(p("Order ", code(s.order), " has ended (" + current.status + "). Start a new one."));
      box.appendChild(button("A new order", newOrder));
      return box;
    }
    if (!s.order && s.accepted !== cfg.schedule_version) {
      box.appendChild(p("Accept the App Hosting Schedule first (step 3)."));
    } else if (!s.order) {
      box.appendChild(p("Ordering reserves the app's names and your account's place, then " +
        (s.invoice ? "sends an invoice to " + s.email + "." : "opens Stripe's checkout to pay by card, in a new tab. This page follows the order while you pay.")));
      box.appendChild(button("Order", function (ev) {
        ev.target.disabled = true;
        call("POST", "/order", orderPayload(s, "order", cfg.schedule_version)).then(function (r) {
          s.order = r.order; s.checkout = r.checkout_url || null; keep(); say(""); render(); follow(); refreshApps();
        }, function (e) { ev.target.disabled = false; fail(e); });
      }));
    } else {
      if (s.checkout) {
        box.appendChild(p(el("a", { "class": "site-btn", href: s.checkout, target: "_blank", rel: "noopener noreferrer", text: "Pay by card" }),
          " Stripe opens in a new tab. When it says paid, come back here: the order moves on by itself."));
      } else if (s.invoice) {
        box.appendChild(p("An invoice with payment terms goes to " + s.email + ". The app is built once it is paid."));
      }
      box.appendChild(p("Your order is ", code(s.order), "."));
    }
    box.appendChild(nav(s.order ? null : "plan", s.order ? "follow" : null));
    return box;
  }

  // ── step 5: follow it ──

  var current = null, since = 0;

  // Someone is typing on the page (a secret, a setting): a poll keeps the order's state but does not redraw.
  function busy() {
    var a = doc.activeElement;
    if (a && tool.contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) return true;
    return [].some.call(tool.querySelectorAll("input[type=password]"), function (x) { return x.value !== ""; });
  }

  function follow(again) {
    stopPolling();
    if (!s.order || !session) return;
    if (!again) since = Date.now();
    if (doc.hidden) { poller = root.setTimeout(function () { follow(true); }, 5000); return; }   // a hidden tab asks nothing
    call("POST", "/order", { cmd: "status", order: s.order }).then(function (o) {
      current = o;
      redraw();
      // every 5 seconds for two minutes, then every 30: a build takes minutes, an invoice days
      if (!settled(o)) poller = root.setTimeout(function () { follow(true); }, Date.now() - since < 120000 ? 5000 : 30000);
      else refreshApps();
    }, function (e) {
      if (e.code === "no_order") {   // not this account's order: let it go, and say where orders are
        s.order = null; s.step = "app"; current = null; keep();
        say("That order is not one of this hosting account's. Your orders are under My apps.", true); render(); return;
      }
      if (e.code !== "not_signed_in") poller = root.setTimeout(function () { follow(true); }, 30000);
      fail(e);
    });
  }
  function stopPolling() { if (poller) root.clearTimeout(poller); poller = null; }

  function followStep() {
    var box = el("div", { "class": "hosting-step" }, el("h3", { text: "5. Follow it to live" }));
    var o = current;
    if (!o) { box.appendChild(p("Reading the order.")); return box; }
    box.appendChild(p(el("strong", { text: o.name || o.id }), " on " + o.plan + (o.customer ? ", for " + o.customer : "") + "."));
    var ul = el("ul", {});
    (o.copies || [o]).forEach(function (c) {
      ul.appendChild(el("li", {}, COPY_WORDS[c.env] + ": " + copyWords(c) + " ", el("a", { href: c.address, text: c.address })));
    });
    box.appendChild(ul);
    if (o.checkout_url) {
      box.appendChild(p(el("a", { "class": "site-btn", href: o.checkout_url, target: "_blank", rel: "noopener noreferrer", text: "Pay by card" }),
        " Not paid yet: Stripe opens in a new tab."));
    }
    var paid = (o.copies || [o]).some(function (c) { return c.status !== "pending" && c.status !== "expired"; });
    if (paid) box.appendChild(variablesPanel(o));
    if (paid && o.secrets && o.secrets.length) box.appendChild(secretsPanel(o));
    if ((o.copies || [o]).every(function (c) { return c.status === "live"; })) {
      box.appendChild(p("It is live. Put it on your customer's shelf: publish it from the App library's Publish page, or with the kit's command where your signing key and recipient.pem live" +
        (o.customer ? ", naming " + o.customer + " in your deliveries." : ".")));
      box.appendChild(el("p", { "class": "hero-cta" }, el("a", { "class": "site-btn", href: tool.getAttribute("data-publish"), text: "Publish" })));
      box.appendChild(copyable(publishCommand(who.maker)));
      box.appendChild(p("This page does not publish: the App library takes only what you sign."));
    }
    box.appendChild(nav(null, null, true));
    return box;
  }

  function variablesPanel(o) {
    var box = el("div", {}, el("h4", { text: "Your GitHub workflow" }));
    var roles = JSON.stringify((o.copies || [o]).map(function (c) { return c.upload.github_role; }));
    box.appendChild(p("Copy ", code("tools/deploy_app/hosting-workflow.yml"), " to ", code(".github/workflows/"),
      " in your repository, and give it these Variables."));
    box.appendChild(button("Set them on your repository", function (ev) {
      ev.target.disabled = true;
      call("POST", "/variables", { order: o.order }).then(function (r) {
        s.variables = r; keep(); say(r.set.length ? "Set on " + r.repo + ": " + r.set.join(", ") + "." : ""); render();
      }, function (e) { ev.target.disabled = false; fail(e); });
    }, true));
    var left = s.variables ? s.variables.to_set_by_hand : null;
    if (left && Object.keys(left).length) {
      box.appendChild(p("This page could not set these (install the GitHub App on the repository, or ask someone who can change its settings). Set them under Settings > Secrets and variables > Actions > Variables:"));
      Object.keys(left).forEach(function (k) { box.appendChild(copyable(k + " = " + left[k])); });
    } else if (!s.variables) {
      box.appendChild(p("Or set them yourself:"));
      var want = o.variables || { IVN_HOSTING_ROLES: roles };   // the hosting's list for this order
      Object.keys(want).forEach(function (k) { box.appendChild(copyable(k + " = " + want[k])); });
    }
    box.appendChild(p("Then push to " + ((o.github || {}).branch || "main") + " on " + ((o.github || {}).repo || "your repository") +
      ": each copy gets the version in your app.json."));
    return box;
  }

  function secretsPanel(o) {
    var box = el("div", {}, el("h4", { text: "Your app's secrets" }));
    box.appendChild(p("Each copy has its own values. A value is sent once to that copy's own secret store and never shown again, here or anywhere."));
    (o.copies || [o]).forEach(function (c) {
      if (["waiting", "live"].indexOf(c.status) < 0) return;
      o.secrets.forEach(function (name) {
        var v = el("input", { type: "password", autocomplete: "off" });
        box.appendChild(field(COPY_WORDS[c.env] + ": " + name, v));
        box.appendChild(button("Set", function () {
          var value = v.value;
          v.value = "";
          call("POST", "/order", { cmd: "secret", order: o.order, env: c.env, name: name, value: value }).then(function () {
            say(name + " is set on the " + COPY_WORDS[c.env] + " copy."); follow();
          }, fail);
        }, true));
      });
    });
    return box;
  }

  // ── My apps ──

  function loadRepos() {
    call("GET", "/repos").then(function (x) { repos = x.repos; redraw(); lookUp(); }, function () { repos = []; redraw(); lookUp(); });
  }

  var mine = null;
  function refreshApps() {
    if (!session || !who || !who.maker) return;
    call("GET", "/whoami").then(function (w) { who = w; redraw(); }, function () {});
    call("POST", "/order", { cmd: "status" }).then(function (r) { mine = r.orders; redraw(); }, function () {});
  }

  function appsPanel() {
    var box = el("div", { "class": "hosting-step" }, el("h3", { text: "My apps" }));
    if (!mine) { box.appendChild(p("Reading your hosting.")); return box; }
    if (!mine.length) { box.appendChild(p("No hosting yet.")); return box; }
    var ul = el("ul", {}), old = el("ul", {});
    mine.forEach(function (o) {
      var gone = (o.copies || [o]).every(function (c) { return ["expired", "removed", "failed"].indexOf(c.status) >= 0; });
      var li = el("li", {}, el("strong", { text: o.name || o.id }), " on " + o.plan + (o.customer ? ", for " + o.customer : "") +
        (o.stops_at ? ", stops at the end of the paid month (" + new Date(o.stops_at * 1000).toISOString().slice(0, 10) + ")" : "") + ": " +
        (o.copies || [o]).map(function (c) { return COPY_WORDS[c.env] + " " + copyWords(c); }).join("; ") + " ");
      li.appendChild(button("Follow", function () {
        toTop(); s.order = o.order; s.checkout = null; s.invoice = o.kind === "invoice"; s.variables = null; s.step = "follow";
        keep(); current = null; render(); follow();
      }, true));
      var unpaid = o.status === "pending";
      if (!o.stops_at && ["expired", "removed", "failed", "stopped"].indexOf(o.status) < 0) {
        li.appendChild(button(unpaid ? "Cancel this unpaid order" : "Cancel at month end", function () {
          if (!root.confirm(unpaid ? "Cancel " + (o.name || o.id) + "? Nothing was paid; its names are given back at once."
                                   : "Stop " + (o.name || o.id) + ", every copy, at the end of the month you paid for?")) return;
          call("POST", "/order", { cmd: "cancel", order: o.order }).then(function () {
            say(unpaid ? "Cancelled: its names are free again." : "Cancelled: it stops at the end of the paid month."); refreshApps();
          }, fail);
        }, true));
      }
      (gone ? old : ul).appendChild(li);
    });
    if (ul.childNodes.length) box.appendChild(ul); else box.appendChild(p("Nothing running or on order."));
    if (old.childNodes.length) box.appendChild(el("details", {}, el("summary", { text: "Ended orders (" + old.childNodes.length + ")" }), old));
    box.appendChild(button("A new order", newOrder, true));
    return box;
  }

  // ── the frame ──

  function nav(back, next, last) {
    var row = el("p", { "class": "hosting-nav" });
    if (back) row.appendChild(button("Back", function () { s.step = back; keep(); render(); toTop(); }, true));
    if (next) row.appendChild(button("Next", function () { s.step = next; keep(); render(); toTop(); if (next === "follow") follow(); }));
    if (last) row.appendChild(button("Back to the order's steps", function () { s.step = "pay"; keep(); render(); toTop(); }, true));
    return row;
  }

  function toTop() { tool.scrollIntoView({ block: "start" }); }   // a shorter step must not leave the reader below the form

  function newOrder() {   // a fresh order: the repository and its folder stay, the rest starts again
    s = { step: "app", maker: s.maker, login: s.login, repo: s.repo, branch: s.branch, folder: s.folder, subject: s.subject,
          subjectSet: s.subjectSet, plainSubject: s.plainSubject };
    current = null; stopPolling(); keep(); render(); toTop(); lookUp(true);
  }

  var view = el("div", {});
  function render() {
    view.textContent = "";
    view.appendChild(signInPanel());
    if (session && who && who.maker && who.open) {
      var step = { app: appStep, customer: customerStep, plan: planStep, pay: payStep, follow: followStep }[s.step] || appStep;
      if (step === appStep) view.appendChild(beforeYouStart());
      view.appendChild(step());
      view.appendChild(appsPanel());
    }
  }

  tool.hidden = false;
  tool.appendChild(out);
  tool.appendChild(view);

  call("GET", "/config").then(function (c) {
    cfg = c;
    if (arrival.kind === "refused") say(arrival.why, true);
    if (arrival.kind === "back" || arrival.kind === "left") root.sessionStorage.setItem(FOLLOW, arrival.order);
    if (arrival.kind === "back") say("Stripe sent you back for order " + arrival.order + ". Go back to the tab you ordered in, or sign in here: this page then shows whether the payment arrived and follows the order to live.");
    if (arrival.kind === "left") say("You left Stripe's checkout for order " + arrival.order + " without paying. Pay or cancel it under My apps once you sign in, or with the kit's deploy_app.py cancel.");
    if (arrival.kind !== "signin") { render(); return; }
    say("Signing you in.");
    return call("POST", "/signin", { code: arrival.code, verifier: arrival.verifier, redirect_uri: PAGE }).then(function (r) {
      session = r.session; who = r; delete who.session; say("");
      if (who.maker) ownSteps();
      var back = root.sessionStorage.getItem(FOLLOW);
      if (back && who.maker) { root.sessionStorage.removeItem(FOLLOW); s.order = back; s.step = "follow"; keep(); }
      render();
      if (who.maker) {
        refreshApps();
        loadRepos();
        if (s.order) follow();   // the saved order's state, so an order that has ended offers a new one
      }
    }, fail);
  }, function (e) { cfg = { ready: false, failed: true }; say(e.message, true); render(); });
})(typeof globalThis !== "undefined" ? globalThis : this);
