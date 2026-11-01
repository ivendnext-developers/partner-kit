// site/assets-src/apps.js — My apps (developer.ivendnext.com/apps). EASY1's first screens: Sign in, Your company, the
// choice for a person in no company yet, People, Tokens, a code from the command's login, and a hand-over's offer and
// its Accept / Refuse (spec rows J2-01 to J2-04, J2-13, J5-14). EASY3a's: the list of apps (J2-05, J6-01), New app's
// gallery with its one search and three tabs (J1-03 to J1-09, J1-12, J1-13), the ticks a shortlist or a sample's page
// brings (J1-02, J1-14), Name your app, Made and Settings (J2-06, J2-07, J2-09), and the app's page: its versions, who
// made each (J2-10, J11-02, J11-04), Download, Upload a new version (J3-01, J3-06), Add a sample and the newer-version
// notice (J6-05, J6-08), and What it covers (J6-12). The words are the experience spec's
// (design/PUBLISH_EASY_EXPERIENCE_SPEC_2026-10-31.md); a refusal shows the words the hosting's door answers, as it gives
// them (its rule 8). The gallery reads the site's own samples index and needs catalogue (samples/index.json,
// catalogue.json); nothing else leaves the page but the hosting's door and an upload's presigned address.
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
  var START = "ivn-apps-start";                          // the ticks a shortlist or a sample's page brought, kept across it
  // the extension-point request form (site/build.py POINT_FORM): Ask for it opens it with the need's words (J1-12)
  var POINT_FORM = "https://github.com/ivendnext-developers/partner-feedback/issues/new?template=2_point_request.yml";
  var CLAIM_FORM = "https://github.com/ivendnext-developers/partner-feedback/issues/new?template=6_claim_a_need.yml";

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


  // ── EASY3a: New app's gallery (pure) ──

  var G = {
    lede: "Every sample is below. Search one by name, or search what your customer asked, or browse. Tick the ones you want.",
    addLede: "The samples already in your app are marked. Your changes are kept.",
    search: "Search by sample (S23, till guard) or by what your customer asked",
    tabs: [["all", "All samples"], ["industry", "By industry"], ["door", "By what it does"], ["recipe", "By recipe"]],
    none: "No sample or need matches these words. Try other words, or ask for it: ",
    ask: "Ask for it",
    desk: "Set in Desk first: no app needed",
    cannot: "Cannot be built today: ",
    claim: "Claim a need: we hold back from it for 90 days while you build it.",
    noIndustry: "No sample is tagged for this industry yet. Browse by what it does.",
    tick: "Use in my app", tickAdd: "Add to the app", inApp: "In this app", recipe: "Read the recipe",
    tickOne: "Tick one or several samples.", next: "Next",
    name: "Name your app", appName: "App name",
    nameHint: ": your first word, then your words. Installed names never change, so choose with care.",
    make: "Make the app", nextSettings: "Next: its settings",
    noApps: "You have no apps yet.", newApp: "New app",
    settingsLede: "Your app's own values, the same for every site. A customer's own account (their wallet) goes in the app's " +
      "settings in their Desk. Connection secrets come from each site: you never type them.",
    addresses: "Outside addresses", secrets: "Secrets your own service needs",
    required: "Required: publishing waits until it is set", optional: "Optional: the feature behind it stays off until you set it",
    together: "Set both, or neither", notOnSite: "Not yet on any site",
    upload: "Upload a new version", uploadHint: "Choose the app folder's zip. We check it before we keep it.",
    download: "Download the app folder", addSample: "Add a sample", tryIt: "Try on my sandbox", publish: "Publish",
    take: "Take it", notNow: "Not now", covers: "What it covers", versions: "Versions"
  };

  // the industries (spec J1-05: the App library's twelve)
  var INDUSTRIES = ["Beauty and cosmetics", "Electronics and phones", "Fashion", "Grocery", "Hardware and DIY", "Hospitality",
                    "Liquor and wine", "Optical", "Pharmacy", "Thrift and resale", "Travel retail", "Distribution and warehousing"];

  // the doors in plain words (spec J1-06; D14: no inside word on the page). A door with no line here shows its own name.
  var DOOR_WORDS = {
    "Check before payment": "A check when the cashier presses Pay",
    "Till key": "A key the cashier taps",
    "Manifest": "Your own lists and forms in Desk",
    "Desk action": "A button in Desk",
    "Event feed": "Something that happens after each sale",
    "Outside app": "Your own service outside iVendNext, reading and writing its records",
    "Capture on an event": "A question during the sale",
    "Field rules": "Fields the till shows, hides or asks for",
    "Save rules": "A check when a record is saved in Desk",
    "Partner page": "Your own page inside iVendNext",
    "Scan source": "What the scanner reads",
    "Document check": "A check on a customer's document at the till",
    "Register books": "A register written as each sale is made",
    "Payer": "Someone else who pays part of a sale",
    "Open check": "An open check at a table",
    "Station ticket": "A ticket sent to a kitchen or a station",
    "Configure": "Settings in Desk, with some of your own lists"
  };
  function doorWords(door) { return DOOR_WORDS[door] || door || ""; }

  // a need's kind on the shortlist and in the gallery (spec J1-11, D2, D3): set in Desk, cannot be built today, or an app
  var DESK_DOORS = { configure: 1, receipt: 1 };
  function needKind(c) {
    if (!c) return "cannot";
    if (c.status === "not-yet" || c.status === "not-possible" || c.door === "request" || c.door === "none") return "cannot";
    return DESK_DOORS[c.door] ? "desk" : "app";
  }
  var KIND_WORDS = { app: "Built as an app", desk: "Set in Desk", cannot: "Cannot be built today" };

  function plainLine(s) { return String(s || "").replace(/\*\*/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"); }
  // the card's *what to do instead* (D3): its Instead or Today line, else what to tell the customer
  function instead(c) {
    var l = ((c && c.limits) || []).filter(function (x) { return /^\*\*Instead:\*\*|^Today\b/.test(x); })[0];
    return plainLine(l || (c && c.tell) || "");
  }
  // J1-12: the request form, its title filled with the need's words (its own form when the card names one)
  function askUrl(c, words) {
    var f = c && (c.request_forms || [])[0];
    if (f && f.url) return f.url;
    return POINT_FORM + "&title=" + encodeURIComponent("Extension-point request: " + ((c && c.asks) || words || ""));
  }

  function sampleNumber(name) { var m = /^s(\d+)/.exec(name || ""); return m ? "S" + m[1] : ""; }
  // a sample's own short title (the samples index's `short`, else its card title without the number)
  function sampleTitle(s) { return (s && (s.short || String(s.title || "").replace(/^S\d+\s*[—-]\s*/, ""))) || ""; }
  function sampleLabel(s) { return sampleNumber(s.name) + " " + sampleTitle(s); }
  function sampleOf(path) { var m = /samples\/(s\d+[a-z0-9_]*)/.exec(path || ""); return m ? m[1] : ""; }
  function needSamples(c) {
    var out = [];
    ((c && c.samples) || []).forEach(function (p) { var n = sampleOf(p.path); if (n && out.indexOf(n) < 0) out.push(n); });
    if (!out.length && c && sampleOf(c.sample)) out.push(sampleOf(c.sample));
    return out;
  }

  function words(q) { return String(q || "").toLowerCase().split(/\s+/).filter(Boolean); }
  function every(ws, text) { text = String(text || "").toLowerCase(); return ws.every(function (w) { return text.indexOf(w) >= 0; }); }

  // J1-03, J1-04, J1-13: the one search. Samples whose number or name match come first, then the needs every word matches;
  // each sample once, with the needs it was matched for; Configure needs and configuration packs apart (D2), needs that
  // cannot be built apart (D3). No words: every sample.
  function search(index, catalogue, q) {
    var ws = words(q), samples = (index && index.samples) || [], by = {};
    samples.forEach(function (s) { by[s.name] = s; });
    var out = { samples: [], forNeeds: {}, desk: [], packs: [], cannot: [], none: false };
    var add = function (n) { if (by[n] && !by[n].config_pack && out.samples.indexOf(by[n]) < 0) out.samples.push(by[n]); };
    if (!ws.length) {
      samples.forEach(function (s) { if (s.config_pack) out.packs.push(s); else out.samples.push(s); });
      return out;
    }
    var number = ws.length === 1 && /^s\d+$/.test(ws[0]) ? ws[0] : null;
    samples.forEach(function (s) {
      var hit = number ? sampleNumber(s.name).toLowerCase() === number : every(ws, sampleNumber(s.name) + " " + sampleTitle(s) + " " + s.title);
      if (!hit) return;
      if (s.config_pack) out.packs.push(s); else add(s.name);
    });
    (catalogue || []).forEach(function (c) {
      if (!every(ws, c.asks + " " + c.title)) return;
      var k = needKind(c);
      if (k === "desk") { out.desk.push(c); return; }
      if (k === "cannot") { out.cannot.push(c); return; }
      needSamples(c).forEach(function (n) {
        add(n);
        if (by[n] && !by[n].config_pack) (out.forNeeds[n] = out.forNeeds[n] || []).push(c.asks);
      });
    });
    out.none = !out.samples.length && !out.desk.length && !out.cannot.length && !out.packs.length;
    return out;
  }

  // J1-02: the needs a shortlist brings: the samples to tick, the Configure needs to list, the needs that cannot be built
  function fromNeeds(index, catalogue, ids) {
    var by = {}, have = {}, out = { ticks: [], built: [], desk: [], cannot: [] };
    (catalogue || []).forEach(function (c) { by[c.id] = c; });
    ((index && index.samples) || []).forEach(function (s) { have[s.name] = s; });
    (ids || []).forEach(function (id) {
      var c = by[id];
      if (!c) return;
      var k = needKind(c);
      if (k !== "app") { out[k].push(c); return; }
      out.built.push(c);
      needSamples(c).forEach(function (n) {
        if (have[n] && !have[n].config_pack && out.ticks.indexOf(n) < 0) out.ticks.push(n);
      });
    });
    return out;
  }

  // what the address brought: ?needs=a,b (the shortlist) or ?sample=s23_till_guard (a sample's page)
  function readStart(search) {
    var q = new URLSearchParams(search || "");
    var needs = (q.get("needs") || "").split(",").map(function (x) { return x.trim(); }).filter(function (x) { return /^[a-z0-9][a-z0-9-]{1,80}$/.test(x); });
    var sample = /^s\d{1,3}(_[a-z0-9_]+)?$/.test(q.get("sample") || "") ? q.get("sample") : "";
    return needs.length || sample ? { needs: needs, sample: sample } : null;
  }

  function barText(ticked) {
    if (!ticked.length) return G.tickOne;
    return ticked.length + " sample" + (ticked.length > 1 ? "s" : "") + " ticked: " + ticked.map(sampleLabel).join(", ") + ".";
  }

  // J2-06: the app's name, as the kit makes it (tools/manifest/validate.py app_for)
  function appFor(name) { return String(name || "").trim().toLowerCase().replace(/ /g, "_"); }
  function nameHint(name, word) { return (appFor(name) || (word || "acme") + "_…") + G.nameHint; }

  function making(name, n) { return "Making " + name + " from " + n + " sample" + (n === 1 ? "" : "s") + "…"; }

  // J2-09: an outside address or a secret, by the setting's name or its purpose
  function isAddress(s) { return /(_URL|_ADDRESS|_HOST|_ENDPOINT)$/.test(s.name) || /\baddress\b/i.test(s.purpose || ""); }
  function settingNote(s) {
    var n = [s.required ? G.required : G.optional];
    if ((s.together || []).length) n.push(G.together);
    return n.join(". ");
  }

  // J11-02: a version's line: its number (a draft when on no site), what was done, who, and how
  var HOW = { page: "on the page", upload: "an upload", ivn: "ivn push" };
  function versionLine(v) {
    var draft = !(v.sites || []).length;
    return [v.version + (draft ? " (draft)" : ""), v.what, v.by, HOW[v.how] || v.how].filter(Boolean).join(" · ");
  }
  function whereWent(v) { return (v.sites || []).length ? v.sites.join(", ") : "On no site yet: a draft, a version on our server that no site has yet."; }
  function day(at) { return at ? new Date(at * 1000).toISOString().slice(0, 10) : ""; }

  // J6-12: what the app covers, from the needs it was started from
  function covers(app, catalogue) {
    var by = {};
    (catalogue || []).forEach(function (c) { by[c.id] = c; });
    var n = app.needs || {}, pick = function (ids) { return (ids || []).map(function (i) { return by[i]; }).filter(Boolean); };
    return { built: pick(n.built), desk: pick(n.desk), cannot: pick(n.cannot), asked: n.asked || [] };
  }
  function coversText(app, cv, made) {
    var lines = [G.covers + ": " + appTitle(app.app)];
    cv.built.forEach(function (c) { lines.push("Built in this app: " + c.asks); });
    cv.desk.forEach(function (c) { lines.push("Set in Desk: " + c.asks); });
    cv.cannot.forEach(function (c) { lines.push("Cannot be built today: " + c.asks + (cv.asked.indexOf(c.id) >= 0 ? " (asked " + made + ")" : "")); });
    return lines.join("\n") + "\n";
  }

  var api = { WORDS: WORDS, PAGE: PAGE, readReturn: readReturn, authorizeUrl: authorizeUrl, challengeOf: challengeOf,
              suggestWord: suggestWord, wordHint: wordHint, scheduleLine: scheduleLine, allApps: allApps, appTitle: appTitle,
              acceptedWords: acceptedWords, G: G, INDUSTRIES: INDUSTRIES, DOOR_WORDS: DOOR_WORDS, doorWords: doorWords,
              needKind: needKind, KIND_WORDS: KIND_WORDS, instead: instead, askUrl: askUrl, sampleNumber: sampleNumber,
              sampleTitle: sampleTitle, sampleLabel: sampleLabel, needSamples: needSamples, search: search,
              fromNeeds: fromNeeds, readStart: readStart, barText: barText, appFor: appFor, nameHint: nameHint,
              making: making, isAddress: isAddress, settingNote: settingNote, versionLine: versionLine, whereWent: whereWent,
              covers: covers, coversText: coversText, POINT_FORM: POINT_FORM, CLAIM_FORM: CLAIM_FORM };
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }

  // ── the page ────────────────────────────────────────────────────────────────────────────────────────────────────

  if (root.top !== root.self) return;   // never inside another page's frame
  var view = root.document.getElementById("apps-tool");
  if (!view) return;
  var cfg = { ready: false }, session = null, who = null, screen = "home", data = {}, flash = null;
  var site = { index: null, catalogue: null };   // the site's samples index and needs catalogue, read once
  var g = null;                                    // the gallery's state: {mode, ticks, tab, q, pick, start, refused, adding}

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
    if (screen === "home") {
      call("GET", "/handovers").then(function (r) { data.handovers = r; render(); }, function () {});
      call("GET", "/apps").then(function (r) { data.apps = r; render(); }, fail);
    }
    if ((screen === "app" || screen === "settings") && data.appId) openApp(data.appId);
  }

  function openApp(app) {
    return call("POST", "/app", { app: app }).then(function (r) { data.app = r; render(); return r; }, fail);
  }

  // the site's samples index and needs catalogue (same origin): read once, for the gallery and What it covers
  function siteData() {
    if (site.index && site.catalogue) return Promise.resolve(site);
    var get = function (u) { return root.fetch(u, { credentials: "omit" }).then(function (r) { if (!r.ok) throw new Error(); return r.json(); }); };
    return Promise.all([get("/samples/index.json"), get("/catalogue.json")]).then(function (x) {
      site.index = x[0]; site.catalogue = x[1]; return site;
    });
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
        .then(function (r) { who = r; data = {}; if (!arrive()) go("home"); }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    return box;
  }

  // J2-05, J6-01: My apps
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
    var list = card(null);
    var apps = (data.apps || {}).apps;
    if (apps && !apps.length) list.appendChild(p(G.noApps));
    (apps || []).forEach(function (a) {
      var row = el("div", { "class": "hosting-step" });
      var link = el("a", { href: "#", text: a.title || appTitle(a.app) });
      link.addEventListener("click", function (ev) { ev.preventDefault(); data.appId = a.app; data.app = null; go("app"); });
      row.appendChild(el("h3", {}, link));
      if (a.line) row.appendChild(p(a.line));
      (a.newer || []).forEach(function (n) { row.appendChild(el("p", { "class": "hint", text: n.text })); });
      list.appendChild(row);
    });
    list.appendChild(button(G.newApp, function () { startGallery("new"); }));
    var out = el("div", {}, box, list);
    box.appendChild(vDevice());
    if (who.role === "owner") box.appendChild(vSandbox());
    return out;
  }

  // ── New app and Add a sample: the gallery (J1-03 to J1-09, J1-13, J2-05, J6-05) ──

  function startGallery(mode, start) {
    g = { mode: mode, ticks: [], tab: "all", q: "", pick: "", start: start || null, refused: "", asked: [] };
    screen = "gallery"; say(""); render();
    siteData().then(function () {
      if (start && start.sample) g.ticks = [start.sample].filter(function (n) { return byName(n); });
      if (start && start.needs.length) {
        var f = fromNeeds(site.index, site.catalogue, start.needs);
        g.fromNeeds = f; g.ticks = f.ticks.slice();
      }
      dry(); render();
    }, function () { say("The samples could not be read. Try again in a minute.", true); render(); });
  }
  function byName(n) { return ((site.index || {}).samples || []).filter(function (s) { return s.name === n; })[0]; }

  // the bar's refusals before Next (M01 to M03, M34, M35): the hosting's dry run, its words as given (spec rule 8)
  function dry() {
    g.refused = "";
    if (g.mode !== "new" || !g.ticks.length) return;
    var ticks = g.ticks.slice();
    call("POST", "/new", { samples: ticks, dry: true }).then(function () {
      if (g && g.ticks.join() === ticks.join()) { g.refused = ""; render(); }
    }, function (e) { if (g && g.ticks.join() === ticks.join()) { g.refused = e.message; render(); } });
  }

  function tick(n, on) {
    if (g.mode === "add") g.ticks = on ? [n] : [];   // one sample is added at a time (its words name it)
    else if (on && g.ticks.indexOf(n) < 0) g.ticks.push(n);
    else if (!on) g.ticks = g.ticks.filter(function (x) { return x !== n; });
    dry(); render();
  }

  function sampleCard(s, forNeeds) {
    var inApp = g.mode === "add" && data.app && (data.app.samples || []).indexOf(s.name) >= 0;
    var c = el("div", { "class": "hosting-step gallery-card" });
    if (s.picture) c.appendChild(el("img", { src: "/" + s.picture, alt: "", loading: "lazy", width: "160" }));
    c.appendChild(el("h3", { text: sampleLabel(s) }));
    if (s.when_to_use) c.appendChild(el("p", { "class": "hint", text: s.when_to_use }));
    if (s.door) c.appendChild(p(doorWords(s.door)));
    if (forNeeds && forNeeds.length) c.appendChild(el("p", { "class": "hint", text: "For: " + forNeeds.join("; ") }));
    if (s.recipe) c.appendChild(el("p", { "class": "hint" }, el("a", { href: "/" + s.recipe, target: "_blank", rel: "noopener", text: G.recipe })));
    if (inApp) { c.appendChild(el("p", { "class": "hosting-ok", text: G.inApp })); return c; }
    var id = "t-" + s.name, box = el("input", { type: "checkbox", id: id });
    box.checked = g.ticks.indexOf(s.name) >= 0;
    box.addEventListener("change", function () { tick(s.name, box.checked); });
    c.appendChild(el("p", {}, box, " ", el("label", { "for": id, text: g.mode === "add" ? G.tickAdd : G.tick })));
    return c;
  }

  function askButton(c, words) {
    var b = el("a", { "class": "site-btn site-btn-ghost", href: askUrl(c, words), target: "_blank", rel: "noopener", text: G.ask });
    b.addEventListener("click", function () { if (c && g.asked.indexOf(c.id) < 0) g.asked.push(c.id); });
    return b;
  }
  function cannotBox(c) {
    var box = el("div", { "class": "hosting-step" }, el("p", {}, el("strong", { text: G.cannot + c.asks + "." }), " " + instead(c)));
    box.appendChild(el("p", {}, askButton(c)));
    if (c.next) box.appendChild(el("p", {}, el("a", { href: CLAIM_FORM, target: "_blank", rel: "noopener", text: G.claim })));
    return box;
  }
  function deskBox(needs, packs) {
    if (!needs.length && !packs.length) return null;
    var box = el("div", { "class": "hosting-step" }, el("p", {}, el("strong", { text: G.desk })));
    needs.forEach(function (c) {
      var r = (c.recipes || [])[0];
      box.appendChild(el("p", {}, c.asks + ": ", r ? el("a", { href: "/" + (r.page || ""), target: "_blank", rel: "noopener", text: r.title }) : null,
        r ? " (recipe)" : null));
    });
    packs.forEach(function (s) {
      box.appendChild(el("p", {}, sampleLabel(s) + (s.recipe ? ": " : ""),
        s.recipe ? el("a", { href: "/" + s.recipe, target: "_blank", rel: "noopener", text: G.recipe }) : null));
    });
    return box;
  }

  function vGallery() {
    var wrap = el("div", {});
    var crumbs = el("p", { "class": "hint" });
    var home = el("a", { href: "#", text: "My apps" });
    home.addEventListener("click", function (ev) { ev.preventDefault(); g = null; go("home"); });
    crumbs.appendChild(home);
    crumbs.appendChild(root.document.createTextNode(g.mode === "add" ? " > " + appTitle(data.appId) + " > " + G.addSample : " > " + G.newApp));
    wrap.appendChild(crumbs);
    wrap.appendChild(el("h2", { text: g.mode === "add" ? G.addSample : G.newApp }));
    wrap.appendChild(p(g.mode === "add" ? G.addLede : G.lede));
    if (!site.index) { wrap.appendChild(p("Reading the samples…")); return wrap; }
    var tabs = el("p", { role: "tablist" });
    G.tabs.forEach(function (t) {
      var b = button(t[1], function () { g.tab = t[0]; g.pick = ""; render(); }, g.tab !== t[0]);
      b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(g.tab === t[0]));
      tabs.appendChild(b); tabs.appendChild(root.document.createTextNode(" "));
    });
    wrap.appendChild(tabs);
    var samples = site.index.samples || [];
    if (g.tab === "all") {
      var q = el("input", { type: "search", value: g.q, placeholder: "S23, till guard, or no more than 50 of one item", spellcheck: "false" });
      var timer = null;
      q.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () { g.q = q.value; render(); var f = root.document.getElementById(q.id); if (f) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); } }, 200);
      });
      wrap.appendChild(field(G.search, q));
      var found = search(site.index, site.catalogue, g.q);
      var fn = g.fromNeeds && !g.q.trim() ? g.fromNeeds : null;
      if (found.none) wrap.appendChild(el("div", { "class": "hosting-step" }, el("p", {}, G.none, askButton(null, g.q))));
      var desk = deskBox(fn ? fn.desk : found.desk, fn ? [] : found.packs);
      if (desk) wrap.appendChild(desk);
      (fn ? fn.cannot : found.cannot).forEach(function (c) { wrap.appendChild(cannotBox(c)); });
      var forNeeds = found.forNeeds;
      if (fn) {   // the shortlist's samples first, each with the needs it serves
        forNeeds = {};
        fn.built.forEach(function (c) { needSamples(c).forEach(function (n) { (forNeeds[n] = forNeeds[n] || []).push(c.asks); }); });
        var first = fn.ticks.map(byName).filter(Boolean);
        found.samples = first.concat(found.samples.filter(function (s) { return first.indexOf(s) < 0; }));
      }
      found.samples.forEach(function (s) { wrap.appendChild(sampleCard(s, forNeeds[s.name])); });
    } else {
      var keys = g.tab === "industry" ? INDUSTRIES :
        g.tab === "door" ? uniq(samples.filter(function (s) { return !s.config_pack && s.door; }).map(function (s) { return s.door; })) :
        uniq(samples.filter(function (s) { return !s.config_pack && s.recipe; }).map(function (s) { return s.recipe; }));
      var nav = el("p", {});
      keys.forEach(function (k) {
        var label = g.tab === "door" ? doorWords(k) : g.tab === "recipe" ? recipeTitle(k) : k;
        var b = button(label, function () { g.pick = k; render(); }, g.pick !== k);
        b.setAttribute("aria-pressed", String(g.pick === k));
        nav.appendChild(b); nav.appendChild(root.document.createTextNode(" "));
      });
      wrap.appendChild(nav);
      if (g.pick) {
        var list = samples.filter(function (s) {
          if (s.config_pack) return false;
          if (g.tab === "industry") return (s.industries || []).indexOf(g.pick) >= 0;
          return g.tab === "door" ? s.door === g.pick : s.recipe === g.pick;
        });
        if (!list.length) wrap.appendChild(p(G.noIndustry));
        list.forEach(function (s) { wrap.appendChild(sampleCard(s)); });
      }
    }
    // the bar at the foot (J2-05): the ticks, the refusal before Next, and Next (or Add)
    var ticked = g.ticks.map(byName).filter(Boolean);
    var bar = el("div", { "class": "hosting-step gallery-bar" });
    if (g.refused) bar.appendChild(el("p", { "class": "hosting-bad", text: g.refused }));
    bar.appendChild(p(barText(ticked)));
    if (g.mode === "add") {
      bar.appendChild(button("Back to " + appTitle(data.appId), function () { g = null; go("app"); }, true));
      bar.appendChild(root.document.createTextNode(" "));
      var add = button(ticked.length ? "Add " + sampleLabel(ticked[0]) : G.addSample, function (ev) { addSample(ev.target, ticked[0].name, false); });
      add.disabled = !ticked.length;
      bar.appendChild(add);
    } else {
      var next = button(G.next, function () { screen = "name"; say(""); render(); });
      next.disabled = !ticked.length || !!g.refused;
      bar.appendChild(next);
    }
    wrap.appendChild(bar);
    return wrap;
  }
  function uniq(xs) { return xs.filter(function (x, i) { return xs.indexOf(x) === i; }).sort(); }
  function recipeTitle(path) {
    var s = ((site.index || {}).samples || []).filter(function (x) { return x.recipe === path && x.recipe_title; })[0];
    return s ? s.recipe_title : path.replace(/^recipes\//, "").replace(/\.html$/, "").replace(/_/g, " ");
  }

  // J2-06, J2-07: Name your app, then Made
  function vName() {
    var box = card(G.name);
    var name = el("input", { type: "text", maxlength: "60", autocapitalize: "characters", spellcheck: "false",
                             value: data.newName || ((who.word || "").toUpperCase() + " ") });
    var hint = el("span", { "class": "hint", text: nameHint(name.value, who.word) });
    name.addEventListener("input", function () { data.newName = name.value; hint.textContent = nameHint(name.value, who.word); });
    var f = field(G.appName, name);
    f.appendChild(el("br", {})); f.appendChild(hint);
    box.appendChild(f);
    box.appendChild(button("Back", function () { screen = "gallery"; say(""); render(); }, true));
    box.appendChild(root.document.createTextNode(" "));
    box.appendChild(button(G.make, function (ev) {
      ev.target.disabled = true;
      var n = g.ticks.length, title = name.value.trim().toUpperCase();
      data.made = { making: making(title, n) }; say(""); render();
      var fn = g.fromNeeds || { built: [], desk: [], cannot: [] }, ids = function (cs) { return cs.map(function (c) { return c.id; }); };
      call("POST", "/new", { samples: g.ticks, name: title,
                             needs: { built: ids(fn.built), desk: ids(fn.desk), cannot: ids(fn.cannot), asked: g.asked.slice() } })
        .then(function (r) {
          data.made = { making: data.made.making, words: r.words }; data.appId = r.app; data.app = null; g = null;
          screen = "made"; render();
        }, function (e) { data.made = null; screen = "name"; fail(e); });
    }));
    if (data.made && data.made.making) box.appendChild(p(data.made.making));
    return box;
  }

  function vMade() {
    var box = card(appTitle(data.appId));
    box.appendChild(p(data.made.making));
    var w = data.made.words || [];
    if (w[0]) box.appendChild(el("p", { "class": "hosting-ok", text: w[0] }));
    w.slice(1).forEach(function (x) { box.appendChild(p(x)); });
    box.appendChild(button(G.nextSettings, function () { data.made = null; go("settings"); }));
    return box;
  }

  // J2-09: Settings
  function vSettings() {
    var box = card("Settings");
    box.appendChild(p(G.settingsLede));
    var a = data.app;
    if (!a) { box.appendChild(p("Reading the app…")); return box; }
    var inputs = {};
    var group = function (title, list) {
      if (!list.length) return;
      box.appendChild(el("h3", { text: title }));
      list.forEach(function (s) {
        var set = (a.set || []).indexOf(s.name) >= 0;
        var i = el("input", { type: isAddress(s) ? "url" : "password", autocomplete: "off", spellcheck: "false",
                              placeholder: set ? "set: type a new value to change it" : "" });
        inputs[s.name] = i;
        box.appendChild(field(s.name, i, (s.purpose ? s.purpose + ". " : "") + settingNote(s) + "."));
      });
    };
    var all = a.settings || [];
    group(G.addresses, all.filter(isAddress));
    group(G.secrets, all.filter(function (s) { return !isAddress(s); }));
    if (!all.length) box.appendChild(p("This app needs no values of yours."));
    else box.appendChild(button("Save", function (ev) {
      var values = {};
      Object.keys(inputs).forEach(function (k) { values[k] = inputs[k].value; });
      ev.target.disabled = true;
      call("POST", "/settings", { app: a.app, values: values }).then(function (r) {
        a.set = r.set; say(r.words, !!r.missing.length); render();
      }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    box.appendChild(root.document.createTextNode(" "));
    box.appendChild(button("Back to " + appTitle(a.app), function () { go("app"); }, true));
    return box;
  }

  // J2-10, J6-01: the app's page
  function vApp() {
    var a = data.app;
    var box = card(appTitle(data.appId));
    var crumbs = el("p", { "class": "hint" }), home = el("a", { href: "#", text: "My apps" });
    home.addEventListener("click", function (ev) { ev.preventDefault(); go("home"); });
    crumbs.appendChild(home);
    box.insertBefore(crumbs, box.firstChild);
    if (!a) { box.appendChild(p("Reading the app…")); return box; }
    var vs = a.versions || [], sent = vs.filter(function (v) { return (v.sites || []).length; });
    box.appendChild(el("p", {}, el("strong", { text: sent.length ? a.line : G.notOnSite }),
      sent.length ? null : " · " + vs[vs.length - 1].version + " (draft)"));
    var acts = el("p", {});
    var tryB = button(G.tryIt, function () {}), pubB = button(G.publish, function () {});
    tryB.disabled = true; pubB.disabled = true;   // parts 3 and 4 of the lane
    [tryB, pubB, button(G.download, download, true), button(G.addSample, function () { startGallery("add"); }, true)]
      .forEach(function (b) { acts.appendChild(b); acts.appendChild(root.document.createTextNode(" ")); });
    box.appendChild(acts);
    // J3-06: Upload a new version
    var file = el("input", { type: "file", accept: ".zip,application/zip" });
    var up = field(G.upload, file, G.uploadHint);
    file.addEventListener("change", function () { if (file.files[0]) upload(file.files[0]); });
    box.appendChild(up);
    box.appendChild(el("p", {}, button("Settings", function () { go("settings"); }, true)));
    // J6-08: the newer-version notice
    (a.newer || []).forEach(function (n) {
      var nb = el("div", { "class": "hosting-step" }, el("p", {}, el("strong", { text: n.text })));
      (n.lines || []).forEach(function (l) { nb.appendChild(el("p", { "class": "hint", text: l })); });
      nb.appendChild(button(G.take, function (ev) { addSample(ev.target, n.sample, true); }));
      nb.appendChild(root.document.createTextNode(" "));
      nb.appendChild(button(G.notNow, function () {
        call("POST", "/newer/hide", { app: a.app, sample: n.sample, version: n.version }).then(function () { openApp(a.app); }, fail);
      }, true));
      box.appendChild(nb);
    });
    if (data.added) {
      var ad = el("div", { "class": "hosting-step" });
      data.added.forEach(function (l, i) { ad.appendChild(el("p", { "class": i ? "" : "hosting-ok", text: l })); });
      box.appendChild(ad);
    }
    // Versions (J11-02, J11-04): who made each and how, newest first
    var vb = card(G.versions);
    var t = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "Version" }), el("th", { text: "Made" }), el("th", { text: "Where it went" }))));
    var body = el("tbody", {});
    vs.slice().reverse().forEach(function (v) {
      body.appendChild(el("tr", {}, el("td", { text: versionLine(v) }), el("td", { text: day(v.at) }), el("td", { text: whereWent(v) })));
    });
    t.appendChild(body);
    vb.appendChild(t);
    // What it covers (J6-12)
    var cb = card(G.covers);
    var fill = function () {
      var cv = covers(a, site.catalogue), made = day((vs[0] || {}).at);
      if (!cv.built.length && !cv.desk.length && !cv.cannot.length) {
        cb.appendChild(p("Built in this app: " + (a.samples || []).map(function (n) { var s = byName(n); return s ? sampleLabel(s) : n; }).join(", ") + "."));
        return;
      }
      cv.built.forEach(function (c) {
        var ss = needSamples(c).filter(function (n) { return (a.samples || []).indexOf(n) >= 0; }).map(byName).filter(Boolean);
        cb.appendChild(p("Built in this app: " + c.asks + (ss.length ? " (" + ss.map(sampleLabel).join(", ") + ")" : "")));
      });
      cv.desk.forEach(function (c) {
        var r = (c.recipes || [])[0];
        cb.appendChild(el("p", {}, "Set in Desk: " + c.asks + (r ? " (" : ""),
          r ? el("a", { href: "/" + r.page, target: "_blank", rel: "noopener", text: r.title }) : null, r ? ")" : null));
      });
      cv.cannot.forEach(function (c) {
        cb.appendChild(p("Cannot be built today: " + c.asks + (cv.asked.indexOf(c.id) >= 0 ? " (asked " + made + ")" : "")));
      });
      var st = el("span", { "class": "hint", "aria-live": "polite" });
      cb.appendChild(el("p", {}, button("Copy for the customer", function () {
        root.navigator.clipboard.writeText(coversText(a, cv, made)).then(function () { st.textContent = " Copied."; });
      }, true), st));
    };
    if (site.catalogue) fill(); else siteData().then(function () { render(); }, function () {});
    // More: Hand over this app (EASY1's door, J5-14)
    var more = card(null);
    if (who.role === "owner") more.appendChild(vHandOver(a.app));
    return el("div", {}, box, vb, cb, more);
  }

  function download() {
    call("POST", "/download", { app: data.appId }).then(function (r) { root.location.assign(r.url); }, fail);
  }

  function upload(f) {
    say("Checking " + f.name + "…"); render();
    call("POST", "/draft/url", { app: data.appId, size: f.size }).then(function (r) {
      return root.fetch(r.url, { method: "PUT", headers: r.headers || {}, body: f, credentials: "omit" }).then(function (x) {
        if (!x.ok) throw new Error("The upload did not reach us (" + x.status + "). Try again.");
        return call("POST", "/draft/keep", { app: data.appId, key: r.key });
      });
    }).then(function (r) { data.added = null; say(r.words); openApp(data.appId); }, fail);
  }

  function addSample(btn, sample, take) {
    btn.disabled = true;
    call("POST", "/add", take ? { app: data.appId, sample: sample, take: true } : { app: data.appId, sample: sample })
      .then(function (r) { data.added = r.words; g = null; screen = "app"; say(""); openApp(data.appId); },
            function (e) { btn.disabled = false; fail(e); });
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

  // J5-14: the giving owner's form, on the app's own page
  function vHandOver(app) {
    var box = el("details", {}, el("summary", { text: WORDS.handOver }));
    var to = el("input", { type: "text", spellcheck: "false" });
    box.appendChild(field(WORDS.toWhich, to));
    box.appendChild(p(WORDS.moves));
    box.appendChild(button(WORDS.handOver, function () {
      call("POST", "/handover", { app: app, to: to.value.trim().toLowerCase() })
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
    var v = { people: vPeople, tokens: vTokens, gallery: g && vGallery, name: g && vName, made: data.made && data.made.words && vMade,
              settings: vSettings, app: vApp }[screen];
    view.appendChild((v || vHome)());
  }

  // once signed in to a company: the ticks the address brought (a shortlist or a sample's page) open New app (J1-02, J1-14)
  function arrive() {
    var st = JSON.parse(root.sessionStorage.getItem(START) || "null");
    if (st && session && who && who.company) { root.sessionStorage.removeItem(START); startGallery("new", st); return true; }
    return false;
  }

  var brought = readStart(root.location.search);
  if (brought) root.sessionStorage.setItem(START, JSON.stringify(brought));   // kept through the sign-in (J1-02, J1-14)
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
      session = r.session; who = r; delete who.session;
      if (!arrive()) { render(); load(); }
    }, function () { say(WORDS.m22, true); render(); });
  }, function (e) { cfg = { ready: false }; say(e.message, true); render(); });
})(typeof globalThis !== "undefined" ? globalThis : this);
