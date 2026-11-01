// site/assets-src/apps.js — My apps, its first screens (developer.ivendnext.com/apps): Sign in, Your company, the
// choice for a person in no company yet, People, Tokens, a code from the command's login, and a hand-over's offer and
// its Accept / Refuse. The words are the experience spec's (design/PUBLISH_EASY_EXPERIENCE_SPEC_2026-10-31.md rows J2-01
// to J2-04, J2-13, J5-14); a refusal shows the words the hosting's door answers, as it gives them.
//
// It talks to the hosting's web door only (https://hosting.ivendnext.app/v1/web/), as the hosting page does: the same
// GitHub sign-in (PKCE; the code is exchanged on the server, the GitHub token never reaches this page), the session kept
// in this script's memory only (a reload signs out). A token made on Tokens is shown once and kept nowhere.
//
// The pure parts are exported for site/test_apps.mjs; the page itself is checked in a browser.
(function (root) {
  "use strict";

  var API = "https://hosting.ivendnext.app/v1/web";
  var PAGE = "https://developer.ivendnext.com/apps";   // a callback address of the GitHub App
  var PENDING = "ivn-apps-signin";                      // the state and verifier of a sign-in on its way, used once
  var CODE = "ivn-apps-code";                            // a code from the command's login, kept across the sign-in

  // ── the pure parts ──────────────────────────────────────────────────────────────────────────────────────────────

  var WORDS = {
    lede: "Sign in to make, try and publish your apps.",
    signin: "Sign in with GitHub",
    noGitHub: ["No GitHub account? ", "Make a free one", " in two minutes with any e-mail, then come back."],
    m22: "GitHub did not sign you in. Try again.",
    company: "Your company",
    companyName: "Company name",
    firstWord: "Your first word",
    setUp: "Set up my company",
    cont: "Continue",
    people: "People",
    person: "Person",
    login: "GitHub login",
    addPerson: "Add a person",
    theirLogin: "Their GitHub login",
    add: "Add",
    makeOwner: "Make owner",
    remove: "Remove",
    tokens: "Tokens",
    makeToken: "Make a token for a build server",
    forWhich: "For which apps",
    revoke: "Revoke",
    copy: "Copy",
    handOver: "Hand over this app",
    toWhich: "To which company? It must have signed in to My apps once.",
    moves: "They accept on their My apps. The app keeps its name; its versions, sites, secrets and hosting move to them, and their card pays from the next month.",
    deviceWarn: "Enter a code only from a command you ran yourself, just now: it signs that command in as you, for your company.",
    accept: "Accept",
    refuse: "Refuse"
  };

  function b64u(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function randomString(n, cryptoObj) { return b64u((cryptoObj || root.crypto).getRandomValues(new Uint8Array(n))); }

  function challengeOf(verifier, cryptoObj) {   // PKCE S256
    var c = cryptoObj || root.crypto;
    return c.subtle.digest("SHA-256", new TextEncoder().encode(verifier)).then(function (d) { return b64u(new Uint8Array(d)); });
  }

  function authorizeUrl(clientId, state, challenge) {
    return "https://github.com/login/oauth/authorize?" + new URLSearchParams({
      client_id: clientId, redirect_uri: PAGE, state: state, code_challenge: challenge, code_challenge_method: "S256"
    }).toString();
  }

  // What the address says on arrival: GitHub's return (taken only with this tab's state, once), or a code the command
  // printed (`?code=ABCD-EFGH`, J2-11's link), which is not GitHub's.
  function readReturn(search, pending) {
    var q = new URLSearchParams(search || "");
    var code = q.get("code") || "";
    if (/^[A-Za-z]{4}-[A-Za-z]{4}$/.test(code) && !q.has("state")) return { kind: "device", code: code.toUpperCase() };
    if (q.has("code") || q.has("state") || q.has("error")) {
      if (q.has("error") || !pending || !pending.state || pending.state !== q.get("state") || !code) {
        return { kind: "refused", why: WORDS.m22 };
      }
      return { kind: "signin", code: code, verifier: pending.verifier };
    }
    return { kind: "none" };
  }

  // J2-02: the first word the company's name suggests (derived, editable): the hosting's own rule (web.code_from).
  function suggestWord(company) {
    var w = ((String(company || "").toLowerCase().split(/\s+/).filter(Boolean)[0]) || "").replace(/[^a-z0-9]/g, "").slice(0, 12);
    return /^[a-z][a-z0-9]{1,11}$/.test(w) ? w : "";
  }

  function wordHint(word) {
    return "Every app you make starts with it: " + (word || "…") + "_…. It is yours once you press Continue.";
  }

  function scheduleLine(version) { return "I accept the App Hosting Schedule (version " + version + ")"; }

  function allApps(name) { return "All of " + name + "'s apps"; }

  function appTitle(app) { return String(app || "").replace(/_/g, " ").toUpperCase(); }
  // J5-14: after *Accept*, the app is yours, and the hosting it brings asks for your card from the next month
  function acceptedWords(app, answer) {
    var pay = (((answer || {}).hosting || {}).orders || []).filter(function (x) { return x.checkout_url; });
    return appTitle(app) + " is yours." + (pay.length ? " Give your card for its hosting from the next month: " +
      pay.map(function (x) { return x.checkout_url; }).join(" ") : "");
  }

  var api = { WORDS: WORDS, PAGE: PAGE, readReturn: readReturn, authorizeUrl: authorizeUrl, challengeOf: challengeOf,
              suggestWord: suggestWord, wordHint: wordHint, scheduleLine: scheduleLine, allApps: allApps, appTitle: appTitle,
              acceptedWords: acceptedWords };
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }

  // ── the page ────────────────────────────────────────────────────────────────────────────────────────────────────

  if (root.top !== root.self) return;   // never inside another page's frame
  var view = root.document.getElementById("apps-tool");
  if (!view) return;
  var cfg = { ready: false }, session = null, who = null, screen = "home", data = {}, flash = null;

  function el(tag, attrs) {
    var e = root.document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null) continue;
      e.appendChild(typeof c === "string" ? root.document.createTextNode(c) : c);
    }
    return e;
  }
  function p(text) { return el("p", { text: text }); }
  function button(text, fn, ghost) {
    var b = el("button", { type: "button", "class": ghost ? "site-btn ghost" : "site-btn", text: text });
    b.addEventListener("click", fn);
    return b;
  }
  function field(label, input, hint) {
    var id = "a-" + Math.random().toString(36).slice(2, 8);
    input.id = id;
    return el("p", {}, el("label", { "for": id, text: label }), hint ? el("span", { "class": "hint", text: " " + hint }) : null,
      el("br", {}), input);
  }
  function card(title) {
    var box = el("section", { "class": "hosting-step" });
    if (title) box.appendChild(el("h2", { text: title }));
    return box;
  }
  function say(text, bad) { flash = text ? { text: text, bad: !!bad } : null; }

  function call(method, path, body) {
    var h = { "content-type": "application/json" };
    if (session) h.authorization = "Bearer " + session;
    return root.fetch(API + path, { method: method, headers: h, body: method === "POST" ? JSON.stringify(body || {}) : undefined,
                                    credentials: "omit", cache: "no-store" })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok) throw new Error(j.words || "The hosting answered " + r.status + ".");
          return j;
        });
      });
  }
  function fail(e) { say(e.message, true); render(); }

  function signIn() {
    var state = randomString(32), verifier = randomString(48);
    challengeOf(verifier).then(function (ch) {
      root.sessionStorage.setItem(PENDING, JSON.stringify({ state: state, verifier: verifier }));
      root.location.assign(authorizeUrl(cfg.client_id, state, ch));
    });
  }

  function go(next) { screen = next; say(""); render(); load(); }

  function load() {
    if (!session || !who || !who.company) return;
    if (screen === "people") call("GET", "/people").then(function (r) { data.people = r.people; data.you = r.you; render(); }, fail);
    if (screen === "tokens") call("GET", "/tokens").then(function (r) { data.tokens = r.tokens; render(); }, fail);
    if (screen === "home") call("GET", "/handovers").then(function (r) { data.handovers = r; render(); }, function () {});
  }

  // J2-01
  function vSignIn() {
    var box = card(null);
    if (!cfg.ready) { box.appendChild(p("The sign-in could not be reached. Try again in a minute.")); return box; }
    box.appendChild(button(WORDS.signin, signIn));
    box.appendChild(el("p", { "class": "hint" }, WORDS.noGitHub[0],
      el("a", { href: "https://github.com/signup", target: "_blank", rel: "noopener", text: WORDS.noGitHub[1] }), WORDS.noGitHub[2]));
    return box;
  }

  // J2-03
  function vJoin() {
    var box = card(null);
    box.appendChild(p(who.no_company));
    box.appendChild(button(WORDS.setUp, function () { go("company"); }));
    box.appendChild(button("Check again", function () {
      call("GET", "/whoami").then(function (w) { who = w; go("home"); }, fail);
    }, true));
    return box;
  }

  // J2-02
  function vCompany() {
    var box = card(WORDS.company);
    var name = el("input", { type: "text", maxlength: "80", autocomplete: "organization", value: data.coName || "" });
    var word = el("input", { type: "text", maxlength: "12", autocapitalize: "off", spellcheck: "false", value: data.coWord || "" });
    var hint = el("span", { "class": "hint", text: " " + wordHint(word.value) });
    var touched = !!data.coWord;
    name.addEventListener("input", function () {
      data.coName = name.value;
      if (!touched) { word.value = suggestWord(name.value); hint.textContent = " " + wordHint(word.value); }
    });
    word.addEventListener("input", function () { touched = true; data.coWord = word.value; hint.textContent = " " + wordHint(word.value.trim().toLowerCase()); });
    box.appendChild(field(WORDS.companyName, name));
    var w = field(WORDS.firstWord, word);
    w.insertBefore(hint, w.childNodes[1]);
    box.appendChild(w);
    var sched = el("input", { type: "checkbox", id: "a-sched" });
    box.appendChild(el("p", {}, sched, " ", el("label", { "for": "a-sched" },
      el("a", { href: who.schedule_url || "#", target: "_blank", rel: "noopener", text: scheduleLine(who.schedule_version) }))));
    box.appendChild(button(WORDS.cont, function (ev) {
      if (!sched.checked) { say("Tick the App Hosting Schedule first.", true); render(); return; }
      ev.target.disabled = true;
      call("POST", "/company", { name: name.value.trim(), word: word.value.trim().toLowerCase(), schedule_version: who.schedule_version })
        .then(function () { return call("GET", "/whoami"); })
        .then(function (r) { who = r; data = {}; go("home"); }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    return box;
  }

  function vHome() {
    var box = card(who.name || who.company);
    box.appendChild(p("Signed in as " + who.login + (who.role === "owner" ? ", an owner." : ".")));
    box.appendChild(el("p", {}, button(WORDS.people, function () { go("people"); }, true), " ",
      button(WORDS.tokens, function () { go("tokens"); }, true), " ", button("Sign out", signOut, true)));
    var offers = (data.handovers || {}).offered_to_you || [];
    if (who.role === "owner") offers.forEach(function (o) { box.appendChild(vOffer(o)); });   // J5-14: the receiving OWNER
    ((data.handovers || {}).offered_by_you || []).forEach(function (o) {
      if (o.words) box.appendChild(el("p", { "class": "hosting-bad", text: o.words }));
    });
    box.appendChild(vDevice());
    if (who.role === "owner") { box.appendChild(vSandbox()); box.appendChild(vHandOver()); }
    return box;
  }

  // J5-14: the receiving owner's screen
  function vOffer(o) {
    var row = el("div", { "class": "hosting-step" }, p(o.words));
    row.appendChild(button(WORDS.accept, function (ev) {
      ev.target.disabled = true;
      call("POST", "/handover/accept", { app: o.app }).then(function (r) {
        go("home");   // first: going home clears the last message
        say(acceptedWords(o.app, r));
        render();
      }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    row.appendChild(button(WORDS.refuse, function () {
      call("POST", "/handover/refuse", { app: o.app }).then(function () { go("home"); }, fail);
    }, true));
    return row;
  }

  // the company's own sandbox (J4-01's address; its key and Check are EASY3a's panel): the preview shelf carries a
  // hosted app's key there only
  function vSandbox() {
    var box = el("details", {}, el("summary", { text: "Your sandbox" }));
    var addr = el("input", { type: "text", spellcheck: "false", placeholder: "https://acme.sandbox.ivend.co" });
    box.appendChild(field("Your sandbox's address", addr));
    box.appendChild(button("Save", function () {
      call("POST", "/sandbox", { site: addr.value.trim() }).then(function (r) { say("Saved: " + r.sandboxes.join(", ")); render(); }, fail);
    }, true));
    return box;
  }

  // J5-14: the giving owner's form (the app's own page around it is EASY3a's)
  function vHandOver() {
    var box = el("details", {}, el("summary", { text: WORDS.handOver }));
    var app = el("input", { type: "text", placeholder: "acme_member_till", spellcheck: "false" });
    var to = el("input", { type: "text", spellcheck: "false" });
    box.appendChild(field("The app", app));
    box.appendChild(field(WORDS.toWhich, to));
    box.appendChild(p(WORDS.moves));
    box.appendChild(button(WORDS.handOver, function () {
      call("POST", "/handover", { app: app.value.trim(), to: to.value.trim().toLowerCase() })
        .then(function (r) { say(r.words); render(); }, fail);
    }));
    return box;
  }

  // step 3: the command's login, a code typed here
  function vDevice() {
    var box = el("details", { open: data.deviceCode ? "" : null }, el("summary", { text: "A code from your terminal" }));
    var code = el("input", { type: "text", maxlength: "9", value: data.deviceCode || "", autocapitalize: "characters" });
    // a code someone else sends you would sign THEIR command in as you: say so where the code is entered
    box.appendChild(el("p", { "class": "hosting-bad", text: WORDS.deviceWarn }));
    box.appendChild(field("The code the command printed", code));
    box.appendChild(button("Sign the command in", function () {
      call("POST", "/device", { user_code: code.value.trim() }).then(function () {
        data.deviceCode = ""; root.sessionStorage.removeItem(CODE);
        say("Done: go back to your terminal."); render();
      }, fail);
    }));
    if (data.deviceCode === "") box.removeAttribute("open");
    return box;
  }

  // J2-04
  function vPeople() {
    var box = card(WORDS.people);
    var t = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: WORDS.person }), el("th", { text: WORDS.login }), el("th", {}))));
    var body = el("tbody", {});
    (data.people || []).forEach(function (m) {
      var acts = el("td", {});
      if (who.role === "owner") {   // your own row too: the door says "Make someone else an owner first." to the last owner
        if (m.role !== "owner") acts.appendChild(button(WORDS.makeOwner, function () {
          call("POST", "/people/owner", { uid: m.uid }).then(function (r) { data.people = r.people; render(); }, fail);
        }, true));
        acts.appendChild(button(WORDS.remove, function () {
          call("POST", "/people/remove", { uid: m.uid }).then(function (r) { data.people = r.people; render(); }, fail);
        }, true));
      }
      body.appendChild(el("tr", {}, el("td", { text: (m.name || m.login) + (m.role === "owner" ? " (owner)" : "") }), el("td", { text: m.login }), acts));
    });
    t.appendChild(body);
    box.appendChild(t);
    if (who.role === "owner") {
      var login = el("input", { type: "text", spellcheck: "false", placeholder: "their-github-login" });
      box.appendChild(field(WORDS.addPerson, login, WORDS.theirLogin));
      box.appendChild(button(WORDS.add, function () {
        call("POST", "/people/add", { login: login.value.trim() }).then(function (r) { data.people = r.people; say(""); render(); }, fail);
      }));
    }
    box.appendChild(button("Back to My apps", function () { go("home"); }, true));
    return box;
  }

  // J2-13
  function vTokens() {
    var box = card(WORDS.tokens);
    var name = el("input", { type: "text", maxlength: "60", spellcheck: "false" });
    var which = el("select", {}, el("option", { value: "", text: allApps(who.name || who.company) }),
      el("option", { value: "one", text: "One app" }));
    var one = el("input", { type: "text", spellcheck: "false", placeholder: (who.word || "acme") + "_…", hidden: "" });
    which.addEventListener("change", function () { one.hidden = which.value !== "one"; });
    box.appendChild(field(WORDS.makeToken, name, "its name"));
    box.appendChild(field(WORDS.forWhich, which));
    box.appendChild(one);
    box.appendChild(button("Make it", function () {
      var app = which.value === "one" ? one.value.trim() : "";
      call("POST", "/tokens/make", app ? { name: name.value.trim(), app: app } : { name: name.value.trim() }).then(function (r) {
        data.shown = r; return call("GET", "/tokens");
      }).then(function (r) { data.tokens = r.tokens; render(); }, fail);
    }));
    if (data.shown) {   // shown once: kept nowhere but on this screen, until it is left
      var code = el("code", { text: data.shown.token });
      box.appendChild(el("div", { "class": "hosting-step" }, p(data.shown.words), code, " ",
        button(WORDS.copy, function () { root.navigator.clipboard.writeText(data.shown.token); }, true)));
    }
    var t = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "Token" }), el("th", { text: "For" }), el("th", { text: "Made" }), el("th", {}))));
    var body = el("tbody", {});
    (data.tokens || []).filter(function (x) { return x.status === "active"; }).forEach(function (x) {
      body.appendChild(el("tr", {}, el("td", { text: x.name }), el("td", { text: x.apps === "*" ? "all apps" : appTitle(x.apps) }),
        el("td", { text: new Date(x.at * 1000).toISOString().slice(0, 10) }),
        el("td", {}, button(WORDS.revoke, function () {
          call("POST", "/tokens/revoke", { id: x.id }).then(function () { return call("GET", "/tokens"); })
            .then(function (r) { data.tokens = r.tokens; render(); }, fail);
        }, true))));
    });
    t.appendChild(body);
    box.appendChild(t);
    box.appendChild(button("Back to My apps", function () { data.shown = null; go("home"); }, true));
    return box;
  }

  function signOut() {
    call("POST", "/signout").then(function () {}, function () {}).then(function () { session = null; who = null; data = {}; go("home"); });
  }

  function render() {
    view.textContent = "";
    view.hidden = false;
    if (flash) view.appendChild(el("p", { "class": flash.bad ? "hosting-bad" : "hosting-ok", text: flash.text }));
    if (!session) { view.appendChild(vSignIn()); return; }
    if (!who.company) { view.appendChild(screen === "company" ? vCompany() : vJoin()); return; }
    view.appendChild(screen === "people" ? vPeople() : screen === "tokens" ? vTokens() : vHome());
  }

  var arrival = readReturn(root.location.search, JSON.parse(root.sessionStorage.getItem(PENDING) || "null"));
  root.sessionStorage.removeItem(PENDING);
  if (root.location.search) root.history.replaceState(null, "", root.location.pathname);
  if (arrival.kind === "device") root.sessionStorage.setItem(CODE, arrival.code);
  data.deviceCode = root.sessionStorage.getItem(CODE) || undefined;
  call("GET", "/config").then(function (c) {
    cfg = c;
    if (arrival.kind === "refused") say(arrival.why, true);
    if (arrival.kind !== "signin") { render(); return; }
    return call("POST", "/signin", { code: arrival.code, verifier: arrival.verifier, redirect_uri: PAGE }).then(function (r) {
      session = r.session; who = r; delete who.session; render(); load();
    }, function () { say(WORDS.m22, true); render(); });
  }, function (e) { cfg = { ready: false }; say(e.message, true); render(); });
})(typeof globalThis !== "undefined" ? globalThis : this);
