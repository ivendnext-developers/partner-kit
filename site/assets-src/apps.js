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
  // Ask for it opens the public *Tell us what is missing* page, never the members-only form (a 404 to anyone not
  // yet given access), with the need's words copied to paste into the form it offers (J1-12)
  var ASK_PAGE = "/feedback.html";
  var CLAIM_FORM = "/roadmap.html#claim-a-need";   // the public page that says how to claim, never the members-only form

  // ── the pure parts ──────────────────────────────────────────────────────────────────────────────────────────────

  var WORDS = {
    lede: "Sign in to make, try and publish your apps.",
    signin: "Sign in with GitHub",
    noGitHub: ["No GitHub account? ", "Make a free one", " in two minutes with any e-mail, then come back."],
    m22: "GitHub did not sign you in. Try again.",
    // the checkout opens in its own tab, so this tab keeps its sign-in; the checkout's tab comes back here
    backFromCheckout: ["Back from the checkout: paid. If My apps is open in another tab, carry on there; otherwise sign in here.",
                       "The checkout was closed without paying. If My apps is open in another tab, it still offers it; otherwise sign in here."],
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
    makeToken: "Make a token for a build server", makeTokenBtn: "Make a token",
    forWhich: "For which apps",
    revoke: "Revoke",
    copy: "Copy",
    handOver: "Hand over this app",
    toWhich: "Their company's first word. They must have signed in to My apps once.",
    moves: "They accept on their My apps. The app keeps its name; its versions, sites, secrets and hosting move to them, and their card pays from the next month.",
    deviceWarn: "Enter a code only from a command you ran yourself, just now: it signs that command in as you, for your company.",
    accept: "Accept",
    refuse: "Refuse",
    // the purpose lines and small answers a review asked for
    peopleWhy: "Everyone here can make, try and publish your company's apps. An owner adds and removes people.",
    tokensWhy: "A token lets a build server publish your company's apps without a person signing in.",
    handOverWhy: "For when your customer wants to own this app: it moves to their company on My apps, and their people keep it up to date from then on.",
    commandQ: "Signing in a command?",
    back: "Back"
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
    if (q.has("order")) return { kind: "checkout", left: q.get("left") === "1" };
    return { kind: "none" };
  }

  // J2-02: the first word the company's name suggests (derived, editable): the hosting's own rule (web.code_from).
  function suggestWord(company) {
    var w = ((String(company || "").toLowerCase().split(/\s+/).filter(Boolean)[0]) || "").replace(/[^a-z0-9]/g, "").slice(0, 12);
    return /^[a-z][a-z0-9]{1,11}$/.test(w) ? w : "";
  }

  function wordHint(word) {
    // an empty box shows no …_… (EASY1NOTES): the example appears with the first letter typed
    return "Every app you make starts with it" + (word ? ": " + word + "_…" : "") + ". It is yours once you press Continue.";
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
    ledeNeeds: "These samples meet your customer's needs. Search for another, or tick the ones you want.",
    search: "Search by sample (S23, till guard) or by what your customer asked",
    tabs: [["industry", "By industry"], ["door", "By what it does"], ["recipe", "By recipe"]],
    none: "No sample or need matches these words. Try other words, or ask for it: ",
    ask: "Ask for it", askCopied: "Your need's words are copied: paste them as the form's title.",
    desk: "Set in Desk first: no app needed",
    hand: "Copy by hand: not an app made here",
    cannot: "Cannot be built today: ",
    noSample: "Built as an app, with no sample to start from: ",
    claim: "Claim a need: we hold back from it for 90 days while you build it.",
    noIndustry: "No sample is tagged for this industry yet. Browse by what it does.",
    tick: "Use in my app", tickAdd: "Add to the app", inApp: "In this app", recipe: "Read the recipe",
    tickOne: "Tick one or several samples.", tickAddOne: "Tick the sample to add.", next: "Next", everySample: "Show every sample",
    name: "Name your app", appName: "App name",
    threeWords: "A name is one to three words of letters and digits, each starting with a letter: ACME BINS.",
    change: "Change", yourName: "Its name in Desk", yourNameHint: "Your first word, then one or two words of your own. Installed names never change, so choose with care.",
    make: "Make the app", nextSettings: "Next: its settings",
    noApps: "You have no apps yet.", newApp: "New app",
    blank: "Start blank", blankHint: "No sample matches the need? Start with an empty app: its README lists each kind you can add, " +
      "with an example and its recipe. You can add a sample to it later.", blankTitle: "My app",
    blankCovers: "A blank app: no sample in it yet. Its README.md lists what you can add.",
    blankCarries: "Started blank. It carries: {kinds}.", backToApps: "Back to My apps",
    // J3 CAPTURE: what a person made in Desk on a site, into this app (the kit's capture.py on our side)
    capture: "Capture from a site", fromSite: "From a site",
    fromSiteHint: "Set up fields, approvals, print formats, labels or till rules in Desk on a test site? Read the site, pick " +
      "what to keep, and name your app: it installs them on the customer's site the same way.",
    captureLede: "What a person made in Desk on that site, signed in as themselves (not as Administrator). Untick what to leave " +
      "out. Nothing is written to the site.",
    captureRead: "Read the site", captureTake: "Capture", reading: "Reading the site\u2026",
    renamed: "Renamed to your app", leftOut: "Left out",
    captureNoSite: "Add the site you built it on to My sites first, with a key you make there: Capture reads with that key.",
    captureNone: "Nothing is ticked: tick what to capture, then press Next again.",
    madeEmpty: "Your app is made, with nothing in it yet: {why} Press Capture from a site on it to read the site again.",
    settingsLede: "Your app's own values, the same for every site. A customer's own account (their wallet) goes in the app's " +
      "settings in their Desk.",
    addresses: "Outside addresses", secrets: "Secrets your own service needs",
    required: "Required: publishing waits until it is set", optional: "Optional: the feature behind it stays off until you set it",
    together: "Set both, or neither", notOnSite: "Not yet on any site",
    upload: "Upload a new version", uploadHint: "Choose the app folder's zip. We check it before we keep it.", toBuild: "From its recipe, not a sample: ", extra: "Also in this app: ",
    download: "Download the app folder", addSample: "Add a sample", tryIt: "Try", tryOn: "Try on {site}", addSite: "Add a site", publish: "Publish",
    take: "Take it", notNow: "Not now", covers: "What it covers", versions: "Versions"
  };

  // EASY3a part 3: Try (spec J4-01 to J4-05, J4-11, J5-15, J9-02, §3b; SITEPICK: the developer sees the site and picks
  // any). The words a door answers (Connected, M11 to M14, M17 to M21, Installed on, the shelf key's line, the results,
  // the till lines, who pays) are the hosting's and are shown as given (§0b rule 8).
  var T = {
    request: "Request one", change: "Change", here: "Where this app is now", others: "Your company's other sites", ours: "Your company's sites",
    another: "Another site\u2026", tryThere: "Try there", removeList: "Remove from my list",
    changes: "What installing it changes", wording: "Show the exact wording",
    testAgain: "Test again", tryAgain: "Try again", pay: "Pay with your card", plan: "Per month",
    updates: "What the update changes", choosePlan: "Choose a plan first.", noCharge: "Confirm in Stripe: no charge",
    starting: "Starting on {site}\u2026", wait: "Keep this page open: this takes up to about 4 minutes, and a few more the first time an app goes to a site.",   // W227 F-GR-10
    openDesk: "Open Desk", openTill: "Open the till", appAddress: "Your app's address: "
  };
  // the Try button names its site before the press; with none on the list, it opens the list to add one
  function tryLabel(site) { return site ? G.tryOn.replace("{site}", siteName(site)) : G.addSite; }
  // a site by the label the developer gave it, where it has one (J6f F8: Try on Acme test, not its address)
  function siteName(site) {
    var hit = (((data && data.sites) || {}).company || []).filter(function (x) { return x.site === site; })[0];
    return hit && hit.label ? hit.label : site;
  }
  // MYSITES (J2, KK 11-10): the developer's own list of sites: add any site they administer (with a key made there on
  // their own user, Try installs in one press), label it by customer, test or live, make one their default, remove one;
  // and a sandbox of their own in one press. The words a door answers are the hosting's, shown as given (§0b rule 8).
  var S = {
    title: "My sites", open: "My sites",
    why: "The sites you try your apps on, and your customers' sites. Add any iVendNext site you administer, and label it with the customer's name and test or live.",
    add: "Add a site", checking: "Checking your key on {site}\u2026", address: "Its address", key: "API key", secret: "API secret", addBtn: "Add",
    keyHint: "Make the key on that site under your own user, one with System Manager: open your User record, its Settings tab, API Access, Generate Keys (not on Administrator: making keys there replaces its secret). With the key and its secret, Try installs there in one press. Leave both empty and its administrator installs from the shelf key Try shows.",
    label: "Label", labelHint: "A customer's name and test or live, like Acme test. A label with live, prod or production puts the site on Publish's list, not Try's.",
    save: "Save", makeDefault: "Make default", isDefault: "your default", remove: "Remove from my list",
    how: { ours: "Try installs in one press, with our key", own: "Try installs in one press, with your key",
           shelf: "its administrator installs from the shelf key", live: "a customer's live site: Publish goes there, Try does not" },   // W227 F-OP-10: true for every company
    getSandbox: "Get a sandbox", logins: "Show its logins", loginsNote: "Shown once: keep them now.",
    // one free sandbox per partner company, more by the request form; our own developers take their own
    askSandbox: "Ask for another sandbox", requestSandbox: "Request a sandbox",
    liveTick: "Your customers' live sites", installNow: "Install now", installOn: "Install now on {site}",
    removed: "{site} is off your list, with the key you added for it.",
    stays: "{site} stays on your list: it is one of our sandboxes, given to you or your company. The key you added for it is deleted."
  };
  // what My sites offers for a sandbox, as the hosting says (`sandbox`): Get a sandbox for one of our developers with
  // none of their own; Ask for another sandbox, with the hosting's words, for a partner company that holds its free one;
  // Request a sandbox for a newcomer with sites of its own (with none, the empty list's words already link the page)
  var FORM = "https://www.ivendnext.com/developers/sandbox/";   // the sandbox request form, as it is (K184)
  function sandboxOffer(sites, get) {
    var out = el("div", {});
    if (sites.sandbox === "get") out.appendChild(el("p", {}, button(S.getSandbox, get)));
    if (sites.sandbox === "ask") {
      out.appendChild(p((sites.sandbox_words || "").replace(/\s*https:\S+$/, "")));
      out.appendChild(el("p", {}, el("a", { href: FORM, target: "_blank", rel: "noopener", "class": "site-btn", text: S.askSandbox })));
    }
    if (sites.sandbox === "request" && (sites.company || []).length && !sites.words)
      out.appendChild(el("p", {}, el("a", { href: "/sandbox.html", "class": "site-btn", text: S.requestSandbox })));
    return out;
  }
  // what Remove from my list did: off the list, or (one of ours, given by its grant) still on it without the added key
  function removedWords(site, r) {
    var kept = ((r && r.company) || []).some(function (x) { return x.site === site; });
    return (kept ? S.stays : S.removed).replace("{site}", site);
  }
  // how Try installs on one of the company's sites, in a line
  function siteHow(x) { return x.stale ? x.stale : x.live ? S.how.live : S.how[x.route] || S.how.shelf; }
  // Try's sites: every company site but its customers' live sites (Publish's)
  function trySites(sites) { return ((sites && sites.company) || []).filter(function (x) { return !x.live; }); }
  // W227 F-FA-17: an app's Try goes back to the site it was last tried on, while that site is on the list; a try never
  // moves the default (only Make default does)
  function triedOn(a, sites) {
    var h = a && a.tried_on;
    return h && trySites(sites).some(function (x) { return x.site === h; }) ? h : null;
  }
  // a live site ticked on Publish joins the customer's site addresses (an empty first box is filled, not kept)
  function tickLive(list, site, on) {
    var out = list.filter(function (x) { return x.trim() && x.trim() !== site; });
    if (on) out.push(site);
    return out.length ? out : [""];
  }
  // Install now's state, per site and version: read the words, ask the one press, installing, or done
  function instKey(site, version, app) { return (app || "") + ":" + site + "@" + (version || ""); }   // W227 F-OP-9: per app
  // W227 F-FA-15: a connection point's line by the site's own verdict: Passed green, Inconclusive (nothing to read
  // yet) plain, anything else red
  function pointClass(l) { return /\): Passed\b/.test(l) ? "hosting-ok" : /\): Inconclusive\b/.test(l) ? "" : "hosting-bad"; }
  function installState(inst, installed) {
    if (installed || (inst && inst.done)) return "done";
    if (!inst || (!inst.sha && !inst.step && !inst.reading)) return "read";
    if (inst.step === "installing" || inst.reading) return "wait";
    return "ask";
  }
  // EASY3a part 4: Publish and keep it going (spec J5-01, J5-04, J5-16, J5-19, J6-06, J7-01, J7-07, J10-01, J12-01, J13-03,
  // §3b). The words a door answers (who pays, M15 to M17, M23, M30, M33, the message to send, a site's state, the go-back
  // and cancel lines, a key) are the hosting's and are shown as given (§0b rule 8).
  var U = {
    toCustomer: "To a customer", toEveryone: "To everyone", listedUpdate: "It goes to every site the app is on and to the App library, on the card it has.", sitesLabel: "The customer's site addresses",
    addSite: "+ Add another site", copy: "Copy", copied: " Copied.", whereRuns: "Where it runs", removeSite: "Remove this site",
    remove: "Remove", serviceRuns: "Where the service runs", itsAddress: "Its https address", save: "Save", logs: "Logs",
    search: "Search", downloadLogs: "Download", goBack: "Go back to this version", goBackBtn: "Go back",
    cancel: "Cancel at month end", makeKey: "Make a key", keySite: "The retailer's site address",
    title: "Title", oneLine: "One line", whatItDoes: "What it does", industries: "Industries", price: "Price", free: "Free",
    withKey: "With a key: retailers ask you", setUp: "How to set it up", setUpHint: "The steps the retailer follows first, one per line.",
    guide: "Guide link", guideHint: "Any https page: your repository's README is enough.",
    send: "Send for listing", hours: "The last", pay: "Pay with your card", publishing: "Publishing\u2026", wait: "Keep this page open: this takes about 3 minutes.", anotherSite: "Another customer's site address",
    pictures: "Pictures", picturesHint: "Up to four: PNG, JPEG or WebP. A big one is made smaller for the card.",
    pictureBad: "Not added: {name} is not a PNG, JPEG or WebP picture we could make small enough. Choose another.",
    picturesBusy: "Adding pictures\u2026", picturesOnly: "Only the first {n} were added: a card has up to four.",
    onSandboxOnly: "Tried, not yet published",
    // W227 F-FA-16: each version's own Where it went, from where it was tried as well as published
    triedOn: "Tried on {site}", shelfOf: "On {site}'s shelf for its administrator",
    utc: "Times are UTC.", downloaded: "Downloading {file}: your browser saves it where it keeps downloads."
  };
  // an industry the App library's card takes (its ids, as the hosting gives them), in the words the gallery shows
  function industryWords(id) {
    var w = String(id || "").replace(/-and-/g, " and ").replace(/-/g, " ");
    return INDUSTRIES.filter(function (x) { return x.toLowerCase() === w; })[0] || w.charAt(0).toUpperCase() + w.slice(1);
  }
  // Go back shows only on a version that reached a site and is not the newest such (J12-01); every draft says it is on no
  // site yet
  function canGoBack(vs, v) {
    var sent = (vs || []).filter(function (x) { return (x.sites || []).length; });
    return (v.sites || []).length > 0 && sent.length > 1 && sent[sent.length - 1].version !== v.version;
  }
  function pubRunning(s) { return tryRunning(s); }
  // the checkout's button: our own teams' copies are covered, so theirs says no charge (EASY1NOTES, walk 11-02)
  // a plan goes only where the screen asked for one: a form kept from an earlier look never overrides the plan in force
  // J7-05: a listed app's next version goes to the list too, so its Publish opens there; a form already open keeps its tab
  function pubOpensOn(form, to, c) { return form ? to : (c && c.listed ? "everyone" : "customer"); }
  function pubPlan(asked, form, money) { return (asked ? form.plan : money.plan) || undefined; }
  function payLabel(s) { return s.pay || payWords(); }   // K176: the amount, when the door names one
  function payWords(internal) { return (arguments.length ? internal : who && who.internal) ? T.noCharge : T.pay; }
  // what Send for listing sends: the card's fields (J7-01), each picture as the App library knows it
  function cardBody(cd) {
    return { title: cd.title, summary: cd.summary, what: (cd.what || []).filter(function (x) { return x.trim(); }),
             industries: cd.industries, price: cd.price, setup: cd.setup, guide: cd.guide,
             pictures: (cd.pictures || []).map(function (x) { return { sha256: x.sha256, type: x.type, w: x.w, h: x.h }; }) };
  }
  // J7-01's Pictures, by the App library's own picture rules (its media door): the type and size checked here first
  var PIC_TYPES = { "image/png": "png", "image/jpeg": "jpeg", "image/webp": "webp" };
  function pictureType(file) { return file && file.size > 0 && file.size <= 300 * 1024 ? PIC_TYPES[file.type] || null : null; }
  function logFile(app, lines) { return lines.join("\n") + (lines.length ? "\n" : ""); }
  var SECTIONS = ["New in Desk", "Who can use it", "Changes to what you already have", "Print layouts",
                  "Connects outside your site"];

  // the consent's sections as the hosting drew them from the site's own check (J4-02), in its order, as given (§0b rule 8)
  function consentSections(r) {
    return ((r && r.sections) || []).filter(function (s) { return s && s.title && (s.lines || []).length; });
  }
  // a try still moving: the page asks again until it is done or stopped
  function tryRunning(s) { return !!(s && s.step && s.step !== "done" && s.step !== "stopped"); }
  // a newer draft than the one tried, a try that stopped, or another site picked: Try installs it again (J4-05 after a fix)
  // W227 (the walk after phase E): every Try press tries; only a try still running is shown as it stands. A finished
  // try's "Installed" may be old (the app since uninstalled there): the doors test a site that has the version already
  function offerAgain(s) { return !tryRunning(s); }
  // J4-01's line with no site, its "Request one" a link to the sandbox page
  function noSandboxParts(words) {
    var i = String(words || "").indexOf(T.request);
    return i < 0 ? [String(words || "")] : [words.slice(0, i), T.request, words.slice(i + T.request.length)];
  }

  // the industries (spec J1-05: the App library's twelve)
  var INDUSTRIES = ["Beauty and cosmetics", "Electronics and phones", "Fashion and footwear", "Grocery", "Hardware and DIY", "Hospitality",
                    "Liquor and wine", "Optical", "Pharmacy", "Thrift and resale", "Travel retail", "Distribution and warehousing"];

  // the doors in plain words (spec J1-06; no inside word on the page). A door with no line here shows its own name.
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

  // a need's kind on the shortlist and in the gallery (spec J1-11): set in Desk, cannot be built today, or an app
  var DESK_DOORS = { configure: 1, receipt: 1 };
  function needKind(c) {
    if (!c) return "cannot";
    if (c.status === "not-yet" || c.status === "not-possible" || c.door === "request" || c.door === "none") return "cannot";
    return DESK_DOORS[c.door] ? "desk" : "app";
  }
  var KIND_WORDS = { app: "Built as an app", desk: "Set in Desk", cannot: "Cannot be built today" };

  function plainLine(s) { return String(s || "").replace(/\*\*/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"); }
  // the card's *what to do instead*: its Instead or Today line, else what to tell the customer
  function instead(c) {
    var l = ((c && c.limits) || []).filter(function (x) { return /^\*\*Instead:\*\*|^Today\b/.test(x); })[0];
    return plainLine(l || (c && c.tell) || "");
  }
  // J1-12: the request form, its title filled with the need's words (its own form when the card names one)
  function askUrl(c, words) {
    var f = c && (c.request_forms || [])[0];
    if (f && f.url) return f.url;
    return ASK_PAGE + "#open-a-form";
  }
  function askWords(c, words) { return "Extension-point request: " + ((c && c.asks) || words || ""); }

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

  // a sample offered with a tick: one that can be made into an app (a pack is set in Desk, one with no manifest is copied by hand)
  function tickable(s) { return !s.config_pack && !s.by_hand; }

  // J1-03, J1-04, J1-13: the one search. Samples whose number or name match come first, then the needs every word matches;
  // each sample once, with the needs it was matched for; Configure needs and configuration packs apart, needs that
  // cannot be built apart. No words: every sample.
  function search(index, catalogue, q) {
    var ws = words(q), samples = (index && index.samples) || [], by = {};
    samples.forEach(function (s) { by[s.name] = s; });
    var out = { samples: [], forNeeds: {}, desk: [], packs: [], hand: [], cannot: [], nosample: [], none: false };
    var add = function (n) { if (by[n] && tickable(by[n]) && out.samples.indexOf(by[n]) < 0) out.samples.push(by[n]); };
    var apart = function (s) { if (s.config_pack) out.packs.push(s); else if (s.by_hand) out.hand.push(s); else add(s.name); };
    if (!ws.length) {
      samples.forEach(apart);
      return out;
    }
    var number = ws.length === 1 && /^s\d+$/.test(ws[0]) ? ws[0] : null;
    samples.forEach(function (s) {
      var hit = number ? sampleNumber(s.name).toLowerCase() === number : every(ws, sampleNumber(s.name) + " " + sampleTitle(s) + " " + s.title);
      if (hit) apart(s);
    });
    (catalogue || []).forEach(function (c) {
      if (!every(ws, c.asks + " " + c.title)) return;
      var k = needKind(c);
      if (k === "desk") { out.desk.push(c); return; }
      if (k === "cannot") { out.cannot.push(c); return; }
      var ns = needSamples(c).filter(function (n) { return by[n] && tickable(by[n]); });
      if (!ns.length) { out.nosample.push(c); return; }   // built as an app, from its recipe: no sample to tick
      ns.forEach(function (n) { add(n); (out.forNeeds[n] = out.forNeeds[n] || []).push(c.asks); });
    });
    out.none = !out.samples.length && !out.desk.length && !out.cannot.length && !out.packs.length && !out.hand.length && !out.nosample.length;
    return out;
  }

  // J1-02: the needs a shortlist brings: the samples to tick, the Configure needs to list, the needs that cannot be built
  function fromNeeds(index, catalogue, ids) {
    var by = {}, have = {}, out = { ticks: [], built: [], desk: [], cannot: [], nosample: [] };
    (catalogue || []).forEach(function (c) { by[c.id] = c; });
    ((index && index.samples) || []).forEach(function (s) { have[s.name] = s; });
    (ids || []).forEach(function (id) {
      var c = by[id];
      if (!c) return;
      var k = needKind(c);
      if (k !== "app") { out[k].push(c); return; }
      out.built.push(c);
      var ns = needSamples(c).filter(function (n) { return have[n] && tickable(have[n]); });
      if (!ns.length) out.nosample.push(c);
      ns.forEach(function (n) { if (out.ticks.indexOf(n) < 0) out.ticks.push(n); });
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

  function barText(ticked, mode) {
    if (!ticked.length) return mode === "add" ? G.tickAddOne : G.tickOne;
    return ticked.length + " sample" + (ticked.length > 1 ? "s" : "") + " ticked: " + ticked.map(sampleLabel).join(", ") + ".";
  }

  // J2-06: the app's name is a title in any words; the door makes its technical name (accounts.py `free_name`, one place)
  function defaultTitle(titles) {
    var joined = titles.join(" and ");
    if (joined.length <= 60) return joined;
    var more = titles.length > 1 ? " and " + (titles.length - 1) + " more" : "";
    return titles[0].slice(0, 60 - more.length) + more;
  }
  function appFor(name) { return String(name || "").trim().toLowerCase().replace(/ +/g, "_"); }
  var THREE_WORDS = /^[A-Z][A-Z0-9]*( [A-Z][A-Z0-9]*){0,2}$/;     // the kit's rule (rename.py), said as an expert types
  function recordsStart(prefix) { return "In Desk its records start with " + prefix + "."; }

  // J6f F7: what a blank app carries now, by the manifest's kinds (custom_fields → custom fields)
  function blankCarries(kinds) { return G.blankCarries.replace("{kinds}", kinds.map(function (k) { return k.replace(/_/g, " "); }).join(", ")); }
  // J6f F5: a link to this page itself (the header's and footer's My apps, `apps.html`, while the address reads `/apps` after
  // the sign-in) goes home without a reload, which would sign the person out; an in-page `#` link is its own handler's
  function toThisPage(href, here) {
    if (!href || href.charAt(0) === "#") return false;
    var u = new URL(href, here), h = new URL(here), bare = function (x) { return x.replace(/\.html$/, ""); };
    return u.origin === h.origin && bare(u.pathname) === bare(h.pathname) && !u.hash && !u.search;
  }
  // J6f F3, J6 F19: the messages to forward to a customer's administrator: none for a site where the company holds the
  // key (Install now is its way, installed yet or not), matched by the site's key address, which the message names
  function handOff(s, inst) {
    var held = (s.install_now || []).map(function (x) { return x.key_address || x.site; });
    return (s.send || []).filter(function (m) { return m.message && held.indexOf(m.site) < 0; });
  }
  // J6 F19: the shelf line ("…when their administrator installs it") only while some site waits for its administrator
  function pubLines(s, inst) {
    return (s.lines || []).filter(function (l) { return l !== s.published || handOff(s, inst).length > 0; });
  }
  function making(name, n) { return n ? "Making " + name + " from " + n + " sample" + (n === 1 ? "" : "s") + "…" : "Making " + name + ", a blank app…"; }

  // J2-09: an outside address or a secret, by the setting's name or its purpose
  function isAddress(s) { return /(_URL|_ADDRESS|_HOST|_ENDPOINT)$/.test(s.name) || /\baddress\b/i.test(s.purpose || ""); }
  function settingNote(s) {
    var n = [s.required ? G.required : G.optional];
    if ((s.together || []).length) n.push(G.together);
    return n.join(". ");
  }

  // J11-02: a version's line: its number (a draft when on no site), what was done, who, and how
  var HOW = { page: "on the page", upload: "an upload", ivn: "ivn push", ivn_cmd: "ivn" };
  function versionLine(v) {
    var draft = !(v.sites || []).length;
    var how = HOW[v.how] || v.how;
    return [v.version + (draft ? " (draft)" : ""), v.what, v.by, v.what === v.how || how === "an " + v.what ? "" : how].filter(Boolean).join(" · ");
  }
  // a draft a later version replaced can never reach a site: it leaves the list. The newest draft stays
  function versionsShown(vs) {
    var last = -1;
    var went = function (v) { return (v.sites || []).length || triedHere(v, vs, "tried").length || triedHere(v, vs, "shelved").length; };
    (vs || []).forEach(function (v, i) { if (went(v)) last = i; });
    return (vs || []).filter(function (v, i) { return went(v) || i > last; });
  }
  // W227 F-FA-16: the sites where Try put this version and no later one since (`tried` installed, `shelved` on the
  // site's shelf for its administrator)
  function triedHere(v, vs, field) {
    return (v[field] || []).filter(function (h) {
      return !(vs || []).some(function (x) { return x !== v && (vs || []).indexOf(x) > (vs || []).indexOf(v) &&
                                                       ((x.tried || []).indexOf(h) >= 0 || (x.shelved || []).indexOf(h) >= 0); });
    });
  }
  function whereWent(v, vs) {
    var pub = v.sites || [], on = triedHere(v, vs, "tried").filter(function (h) { return pub.indexOf(h) < 0; }),
        shelf = triedHere(v, vs, "shelved").filter(function (h) { return pub.indexOf(h) < 0 && on.indexOf(h) < 0; }), out = [];
    if (pub.length) out.push(pub.join(", "));
    if (on.length) out.push(U.triedOn.replace("{site}", on.join(", ")));
    shelf.forEach(function (h) { out.push(U.shelfOf.replace("{site}", h)); });
    return out.length ? out.join(" · ") : "On no site yet: a draft, a version on our server that no site has yet.";
  }
  function day(at) { return at ? new Date(at * 1000).toISOString().slice(0, 10) : ""; }

  // J6-12: what the app covers, from the needs it was started from
  function covers(app, catalogue) {
    var by = {};
    (catalogue || []).forEach(function (c) { by[c.id] = c; });
    var n = app.needs || {}, pick = function (ids) { return (ids || []).map(function (i) { return by[i]; }).filter(Boolean); };
    var have = app.samples || [], from = {}, built = pick(n.built);
    var inApp = function (c) { return app.samples ? needSamples(c).filter(function (x) { return have.indexOf(x) >= 0; }) : [1]; };
    built.forEach(function (c) { inApp(c).forEach(function (x) { from[x] = 1; }); });
    return { built: built.filter(function (c) { return inApp(c).length; }), tobuild: built.filter(function (c) { return !inApp(c).length; }),
             extra: built.length || pick(n.desk).length || pick(n.cannot).length ? have.filter(function (x) { return !from[x]; }) : [], desk: pick(n.desk), cannot: pick(n.cannot), asked: n.asked || [] };
  }
  function coversText(app, cv, made) {
    var lines = [G.covers + ": " + appTitle(app.app)];
    cv.built.forEach(function (c) { lines.push("Built in this app: " + c.asks); });
    (cv.tobuild || []).forEach(function (c) { lines.push(G.toBuild + c.asks); });
    (cv.extra || []).forEach(function (n) { lines.push(G.extra + n); });
    cv.desk.forEach(function (c) { lines.push("Set in Desk: " + c.asks); });
    cv.cannot.forEach(function (c) { lines.push("Cannot be built today: " + c.asks + (cv.asked.indexOf(c.id) >= 0 ? " (asked " + made + ")" : "")); });
    return lines.join("\n") + "\n";
  }

  var api = { WORDS: WORDS, PAGE: PAGE, readReturn: readReturn, authorizeUrl: authorizeUrl, challengeOf: challengeOf,
              suggestWord: suggestWord, wordHint: wordHint, scheduleLine: scheduleLine, allApps: allApps, appTitle: appTitle,
              acceptedWords: acceptedWords, G: G, INDUSTRIES: INDUSTRIES, DOOR_WORDS: DOOR_WORDS, doorWords: doorWords,
              needKind: needKind, KIND_WORDS: KIND_WORDS, instead: instead, askUrl: askUrl, sampleNumber: sampleNumber,
              sampleTitle: sampleTitle, sampleLabel: sampleLabel, needSamples: needSamples, search: search,
              fromNeeds: fromNeeds, readStart: readStart, barText: barText, appFor: appFor, recordsStart: recordsStart, tickable: tickable,
              making: making, blankCarries: blankCarries, captureGroups: captureGroups, ticksOff: ticksOff, pubLines: pubLines, toThisPage: toThisPage, handOff: handOff, isAddress: isAddress, settingNote: settingNote, versionLine: versionLine, whereWent: whereWent,
              covers: covers, coversText: coversText, ASK_PAGE: ASK_PAGE, CLAIM_FORM: CLAIM_FORM, T: T,
              SECTIONS: SECTIONS, consentSections: consentSections, tryRunning: tryRunning, offerAgain: offerAgain,
              noSandboxParts: noSandboxParts, U: U, industryWords: industryWords, tryLabel: tryLabel,
              canGoBack: canGoBack, defaultTitle: defaultTitle, versionsShown: versionsShown, logFile: logFile, payWords: payWords, payLabel: payLabel, pubPlan: pubPlan, pubOpensOn: pubOpensOn, pictureType: pictureType, b64: b64, cardBody: cardBody,
              S: S, siteHow: siteHow, trySites: trySites, tickLive: tickLive, instKey: instKey, installState: installState,
              removedWords: removedWords, pointClass: pointClass, triedOn: triedOn };
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
    var b = el("button", { type: "button", "class": ghost ? "site-btn site-btn-ghost" : "site-btn", text: text });
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
    if (screen === "sites") loadSites();
    if (screen === "home") {
      call("GET", "/handovers").then(function (r) { data.handovers = r; render(); }, function () {});
      call("GET", "/apps").then(function (r) { data.apps = r; render(); }, fail);
    }
    if ((screen === "app" || screen === "settings") && data.appId) openApp(data.appId);
  }

  function openApp(app) {
    data.where = null; data.whereAsked = null;   // where it runs is read afresh each time: a try or a publish changes it
    loadSites();
    return call("POST", "/app", { app: app }).then(function (r) { data.app = r; render(); return r; }, fail);
  }
  // the company's sites, any number, and the person's default (their last, else the first): Try's button and its list
  function loadSites() { return call("POST", "/sites", {}).then(function (r) { data.sites = r; render(); }, function () {}); }

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
    if (!cfg.ready) {
      box.appendChild(p("The sign-in could not be reached. Try again in a minute."));
      box.appendChild(button("Try again", function () { root.location.reload(); }, true));
      return box;
    }
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
      call("GET", "/whoami").then(function (w) { who = w; if (!(w.company && arrive())) go("home"); }, fail);
    }, true));
    return box;
  }

  // J2-02
  function vCompany() {
    var box = card(WORDS.company);
    var name = el("input", { type: "text", maxlength: "80", autocomplete: "organization", value: data.coName || "" });
    var word = el("input", { type: "text", maxlength: "12", autocapitalize: "off", spellcheck: "false", value: data.coWord || suggestWord(data.coName) });
    var hint = el("span", { "class": "hint", text: " " + wordHint(word.value) });
    var touched = !!data.coWord;
    name.addEventListener("input", function () {
      data.coName = name.value;
      if (!touched) { word.value = suggestWord(name.value); hint.textContent = " " + wordHint(word.value); }
    });
    word.addEventListener("input", function () { touched = true; data.coWord = word.value; hint.textContent = " " + wordHint(word.value.trim().toLowerCase()); });
    box.appendChild(field(WORDS.companyName, name));
    var w = field(WORDS.firstWord, word);
    w.appendChild(el("br", {})); w.appendChild(hint);
    box.appendChild(w);
    var sched = el("input", { type: "checkbox", id: "a-sched" });
    sched.checked = !!data.coTick;   // a refusal keeps the tick, the name and the word
    sched.addEventListener("change", function () { data.coTick = sched.checked; });
    box.appendChild(el("p", {}, sched, " ", el("label", { "for": "a-sched" },
      el("a", { href: who.schedule_url || "#", target: "_blank", rel: "noopener", text: scheduleLine(who.schedule_version) }))));
    box.appendChild(button(WORDS.cont, function (ev) {
      if (!sched.checked) { say("Tick the App Hosting Schedule first.", true); render(); return; }
      ev.target.disabled = true;
      call("POST", "/company", { name: name.value.trim(), word: word.value.trim().toLowerCase(), schedule_version: who.schedule_version })
        .then(function () { return call("GET", "/whoami"); })
        .then(function (r) { who = r; data = { deviceCode: root.sessionStorage.getItem(CODE) || undefined }; if (!arrive()) go("home"); }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    box.appendChild(root.document.createTextNode(" "));
    box.appendChild(button(WORDS.back, function () { go("home"); }, true));   // back to J2-03's two choices
    return box;
  }

  // J2-05, J6-01: My apps
  function vHome() {
    var box = card(who.name || who.company);
    box.appendChild(p("Signed in as " + who.login + (who.role === "owner" ? ", an owner." : ".")));
    box.appendChild(el("p", {}, button(S.open, function () { go("sites"); }, true), " ",
      button(WORDS.people, function () { go("people"); }, true), " ",
      button(WORDS.tokens, function () { go("tokens"); }, true), " ", button("Sign out", signOut, true)));
    var tail = el("div", {});
    var offers = (data.handovers || {}).offered_to_you || [];
    if (who.role === "owner") offers.forEach(function (o) { box.appendChild(vOffer(o)); });   // J5-14: the receiving OWNER
    ((data.handovers || {}).offered_by_you || []).forEach(function (o) {
      if (o.words) box.appendChild(el("p", { "class": "hosting-bad", text: o.words }));
    });
    var list = card(null);
    var apps = (data.apps || {}).apps;
    if (!data.apps) list.appendChild(p("Reading your apps\u2026"));
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
    var out = el("div", {}, box, list, tail);
    (data.deviceCode ? box : tail).appendChild(vDevice());   // a code brought by the address: at the top, open
    return out;
  }

  // ── New app and Add a sample: the gallery (J1-03 to J1-09, J1-13, J2-05, J6-05) ──

  function startGallery(mode, start) {
    if (mode === "new") { data.newName = null; data.newPrefix = null; data.nameBad = ""; data.nameStart = ""; }
    g = { mode: mode, ticks: [], tab: "all", q: "", pick: "", start: start || null, refused: "", asked: [] };
    screen = "gallery"; say(""); render();
    siteData().then(function () {
      if (start && start.sample) g.ticks = [start.sample].filter(function (n) { return byName(n) && tickable(byName(n)); });
      if (start && start.needs.length) {
        var f = fromNeeds(site.index, site.catalogue, start.needs);
        g.fromNeeds = f; g.ticks = f.ticks.slice();
      }
      dry(); render();
    }, function () { say("The samples could not be read. Try again in a minute.", true); render(); });
  }
  function byName(n) { return ((site.index || {}).samples || []).filter(function (s) { return s.name === n; })[0]; }

  // Start blank: no sample, straight to Name your app; the hosting makes the kit's blank folder (combine with no sample)
  function blankTile() {
    var c = el("div", { "class": "hosting-step gallery-card gallery-blank" });
    c.appendChild(el("h3", { text: G.blank }));
    c.appendChild(el("p", { "class": "hint", text: G.blankHint }));
    c.appendChild(el("p", {}, button(G.blank, startBlank)));
    return c;
  }
  function startBlank() { g.ticks = []; g.blank = true; g.refused = ""; g.checking = false; screen = "name"; say(""); render(); }
  // J3b: From a site reads the site first, then names the app, which is made with what stays ticked: a site with nothing
  // on it never leaves an empty app (as `ivn capture --new`)
  function siteTile() {
    var c = el("div", { "class": "hosting-step gallery-card gallery-blank" });
    c.appendChild(el("h3", { text: G.fromSite }));
    c.appendChild(el("p", { "class": "hint", text: G.fromSiteHint }));
    c.appendChild(el("p", {}, button(G.fromSite, function () {
      if (!data.sites) loadSites();   // the sites Capture can read: none are loaded until an app or My sites is opened
      startBlank(); g.fromSite = { off: {} }; screen = "fromsite"; render();
    })));
    return c;
  }
  function vFromSite() {
    var box = vCapture(null, g.fromSite);
    box.appendChild(button("Back", function () { screen = "gallery"; g.blank = false; g.fromSite = false; say(""); render(); }, true));
    return box;
  }

  // the bar's refusals before Next (M01 to M03, M34, M35): the hosting's dry run, its words as given (spec rule 8)
  function dry() {
    g.refused = "";
    g.checking = g.mode === "new" && g.ticks.length > 0;   // Next waits for the answer: a refusal shows before Next
    if (!g.checking) return;
    var ticks = g.ticks.slice();
    var done = function (words) { if (g && g.ticks.join() === ticks.join()) { g.refused = words; g.checking = false; render(); } };
    call("POST", "/new", { samples: ticks, dry: true }).then(function () { done(""); }, function (e) { done(e.message); });
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
    b.addEventListener("click", function () {
      if (c && g.asked.indexOf(c.id) < 0) g.asked.push(c.id);
      var f = c && (c.request_forms || [])[0];
      if (!(f && f.url) && root.navigator && root.navigator.clipboard) {   // the need's words go with the person
        root.navigator.clipboard.writeText(askWords(c, words)).then(function () { say(G.askCopied); render(); }, function () {});
      }
    });
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
      box.appendChild(el("p", {}, c.asks, recipeLink(c, ": ", " (recipe)")));
    });
    packs.forEach(function (s) {
      box.appendChild(el("p", {}, sampleLabel(s) + (s.recipe ? ": " : ""),
        s.recipe ? el("a", { href: "/" + s.recipe, target: "_blank", rel: "noopener", text: G.recipe }) : null));
    });
    return box;
  }

  function handBox(list) {   // no manifest of its own: its page or recipe says how to copy it
    if (!list.length) return null;
    var box = el("div", { "class": "hosting-step" }, el("p", {}, el("strong", { text: G.hand })));
    list.forEach(function (s) {
      box.appendChild(el("p", {}, sampleLabel(s) + ": ",
        el("a", { href: "/" + (s.recipe || "samples/" + s.name + "/"), target: "_blank", rel: "noopener", text: G.recipe })));
    });
    return box;
  }

  function recipeLink(c, before, after) {   // a need's first recipe, a page of this site or the kit file it names
    var r = (c.recipes || [])[0];
    if (!r || !(r.page || r.url)) return null;
    return el("span", {}, before, el("a", { href: r.page ? "/" + r.page : r.url, target: "_blank", rel: "noopener", text: r.title }), after);
  }
  function noSampleBox(cs) {
    if (!cs.length) return null;
    var box = el("div", { "class": "hosting-step" });
    cs.forEach(function (c) { box.appendChild(el("p", {}, G.noSample + c.asks, recipeLink(c, ". Its recipe: ", ""))); });
    return box;
  }

  function vGallery() {
    var wrap = el("div", {});
    var crumbs = el("p", { "class": "hint" });
    var home = el("a", { href: "#", text: "My apps" });
    home.addEventListener("click", function (ev) { ev.preventDefault(); g = null; go("home"); });
    crumbs.appendChild(home);
    crumbs.appendChild(root.document.createTextNode(g.mode === "add" ? " > " + shownTitle() + " > " + G.addSample : " > " + G.newApp));
    wrap.appendChild(crumbs);
    wrap.appendChild(el("h2", { text: g.mode === "add" ? G.addSample : G.newApp }));
    wrap.appendChild(p(g.mode === "add" ? G.addLede : g.fromNeeds && !g.every ? G.ledeNeeds : G.lede));
    if (g.mode === "new") { wrap.appendChild(blankTile()); wrap.appendChild(siteTile()); }   // J1's first tile, J3's
    if (!site.index) { wrap.appendChild(p("Reading the samples…")); return wrap; }
    var q = el("input", { type: "search", value: g.q, placeholder: "S23, till guard, or no more than 50 of one item", spellcheck: "false" });
    var timer = null;
    q.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        g.q = q.value; if (g.q.trim()) { g.tab = "all"; g.pick = ""; }   // typing searches every sample
        render();
        var f = root.document.getElementById("g-q");
        if (f) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); }
      }, 200);
    });
    var sf = field(G.search, q);
    q.id = "g-q"; sf.querySelector("label").setAttribute("for", "g-q");   // one id, so the box keeps its focus
    wrap.appendChild(sf);
    var tabs = el("p", {});
    G.tabs.forEach(function (t) {
      var b = button(t[1], function () { g.tab = g.tab === t[0] ? "all" : t[0]; g.pick = ""; render(); }, g.tab !== t[0]);
      b.setAttribute("aria-pressed", String(g.tab === t[0]));
      tabs.appendChild(b); tabs.appendChild(root.document.createTextNode(" "));
    });
    wrap.appendChild(tabs);
    var samples = site.index.samples || [];
    if (g.tab === "all") {
      var found = search(site.index, site.catalogue, g.q);
      var fn = g.fromNeeds && !g.q.trim() ? g.fromNeeds : null;
      if (found.none) wrap.appendChild(el("div", { "class": "hosting-step" }, el("p", {}, G.none, askButton(null, g.q))));
      var desk = g.mode === "add" && !g.q.trim() ? null : deskBox(fn ? fn.desk : found.desk, fn ? [] : found.packs);
      var hand = g.mode === "add" && !g.q.trim() ? null : handBox(fn ? [] : found.hand);
      var apart = function () { if (desk) wrap.appendChild(desk); if (hand) wrap.appendChild(hand); };
      if (g.q.trim() || fn) apart();    // what a search or a shortlist asked for first; browsing, the ticks come first (MAKEEASY)
      (fn ? fn.cannot : found.cannot).forEach(function (c) { wrap.appendChild(cannotBox(c)); });
      var ns = noSampleBox(fn ? fn.nosample : found.nosample);
      if (ns) wrap.appendChild(ns);
      var forNeeds = found.forNeeds;
      if (fn) {   // the shortlist's samples first, each with the needs it serves
        forNeeds = {};
        fn.built.forEach(function (c) { needSamples(c).forEach(function (n) { (forNeeds[n] = forNeeds[n] || []).push(c.asks); }); });
        var first = fn.ticks.map(byName).filter(Boolean);
        found.samples = first.concat(g.every || !first.length ? found.samples.filter(function (s) { return first.indexOf(s) < 0; }) : []);
      }
      if (!fn && !g.q.trim()) {   // the samples a sample's page or an earlier tick brought, first
        var ticked0 = g.ticks.map(byName).filter(Boolean);
        found.samples = ticked0.concat(found.samples.filter(function (s) { return ticked0.indexOf(s) < 0; }));
      }
      found.samples.forEach(function (s) { wrap.appendChild(sampleCard(s, forNeeds[s.name])); });
      if (!g.q.trim() && !fn) apart();
      if (fn && !g.every && fn.ticks.length) {   // a shortlist shows its own samples; the other cards wait for this press
        wrap.appendChild(el("p", {}, button(G.everySample, function () { g.every = true; render(); }, true)));
      }
    } else {
      var recipesOf = function (s) { return (s.recipes || []).map(function (r) { return r.path; }); };
      var keys = g.tab === "industry" ? INDUSTRIES :
        g.tab === "door" ? uniq(samples.filter(function (s) { return tickable(s) && s.door; }).map(function (s) { return s.door; })) :
        uniq([].concat.apply([], samples.filter(tickable).map(recipesOf)));
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
          if (!tickable(s)) return false;
          if (g.tab === "industry") return (s.industries || []).indexOf(g.pick) >= 0;
          return g.tab === "door" ? s.door === g.pick : recipesOf(s).indexOf(g.pick) >= 0;
        });
        if (!list.length) wrap.appendChild(p(G.noIndustry));
        list.forEach(function (s) { wrap.appendChild(sampleCard(s)); });
      }
    }
    // the bar at the foot (J2-05): the ticks, the refusal before Next, and Next (or Add)
    var ticked = g.ticks.map(byName).filter(Boolean);
    var bar = el("div", { "class": "hosting-step gallery-bar" + (ticked.length ? " on" : "") });   // it follows the person only once a sample is ticked
    if (g.refused) bar.appendChild(el("p", { "class": "hosting-bad", text: g.refused }));
    bar.appendChild(p(barText(ticked, g.mode)));
    if (g.mode === "add") {
      bar.appendChild(button("Back to " + shownTitle(), function () { g = null; go("app"); }, true));
      bar.appendChild(root.document.createTextNode(" "));
      var add = button(ticked.length ? "Add " + sampleLabel(ticked[0]) : G.addSample, function (ev) { addSample(ev.target, ticked[0].name, false); });
      add.disabled = !ticked.length;
      bar.appendChild(add);
    } else {
      var next = button(G.next, function () { screen = "name"; say(""); render(); });
      next.disabled = !ticked.length || !!g.refused || !!g.checking;
      bar.appendChild(next);
    }
    wrap.appendChild(bar);
    return wrap;
  }
  // what the person called the app, once its row is read; its technical name until then
  function shownTitle() { return (data.app && data.app.app === data.appId && data.app.title) || appTitle(data.appId); }
  function uniq(xs) { return xs.filter(function (x, i) { return xs.indexOf(x) === i; }).sort(); }
  function recipeTitle(path) {
    var t = "";
    ((site.index || {}).samples || []).forEach(function (x) { (x.recipes || []).forEach(function (r) { if (r.path === path && r.title) t = r.title; }); });
    return t || path.replace(/^recipes\//, "").replace(/\.html$/, "").replace(/_/g, " ");
  }

  // J2-06, J2-07: Name your app, then Made. Any words; the door answers its name in Desk as the person types
  function vName() {
    var box = card(G.name);
    var fallback = g.blank ? G.blankTitle : defaultTitle(g.ticks.map(function (n) { return sampleTitle(byName(n)); }));
    var name = el("input", { type: "text", maxlength: "60", value: data.newName === null || data.newName === undefined ? fallback : data.newName });
    var start = el("span", { "class": "hint", text: data.nameStart ? recordsStart(data.nameStart) : "" });
    var bad = el("p", { "class": "hosting-bad", role: "alert", text: data.nameBad || "" });
    bad.hidden = !data.nameBad;
    var own = data.newPrefix === null || data.newPrefix === undefined ? null :
      el("input", { type: "text", maxlength: "40", autocapitalize: "characters", spellcheck: "false", value: data.newPrefix, "data-own-name": "1" });
    var asked = 0;
    var show = function (words) { bad.textContent = words; bad.hidden = !words; data.nameBad = words; };
    var look = function () {     // the door's answer; a late answer to older words is dropped
      var mine = ++asked;
      var answer = own ? call("POST", "/name", { app: appFor(own.value) }).then(function () { return own.value.trim().toUpperCase(); })
        : call("POST", "/name", { title: name.value.trim() || fallback, samples: g.ticks }).then(function (r) { return r.prefix; });
      answer.then(function (prefix) {
        if (mine !== asked) return;
        var past = own && !THREE_WORDS.test(prefix);
        data.nameStart = past ? "" : prefix; start.textContent = past ? "" : recordsStart(prefix);
        show(past ? G.threeWords : "");
      }, function (e) { if (mine === asked) { start.textContent = ""; show(e.message); } });
    };
    var timer = null;
    var soon = function () { clearTimeout(timer); timer = setTimeout(look, 300); };
    name.addEventListener("input", function () { data.newName = name.value; if (!own) soon(); });
    var f = field(G.appName, name);
    f.appendChild(el("br", {})); f.appendChild(start);
    if (!own) {
      var change = el("a", { href: "#", text: G.change });
      change.addEventListener("click", function (ev) {
        ev.preventDefault(); data.newPrefix = data.nameStart || ""; render();
        var opened = root.document.querySelector("[data-own-name]"); if (opened) opened.focus();
      });
      f.appendChild(root.document.createTextNode(" ")); f.appendChild(change);
    }
    box.appendChild(f);
    if (own) {
      own.addEventListener("input", function () { data.newPrefix = own.value; soon(); });
      box.appendChild(field(G.yourName, own, G.yourNameHint));
    }
    box.appendChild(bad);   // a refusal stands under the field it is about
    box.appendChild(button("Back", function () {   // From a site goes back to its list, as it was ticked
      if (g.fromSite) { screen = "fromsite"; data.nameBad = ""; say(""); render(); return; }
      screen = "gallery"; g.blank = false; g.fromSite = false; data.nameBad = ""; say(""); render();
    }, true));
    box.appendChild(root.document.createTextNode(" "));
    var make = button(G.make, function (ev) {
      ev.target.disabled = true; clearTimeout(timer); asked++;
      var n = g.ticks.length, title = name.value.trim() || fallback;
      data.made = { making: making(title, n), title: title }; data.nameBad = ""; say(""); render();
      var fn = g.fromNeeds || { built: [], desk: [], cannot: [] }, ids = function (cs) { return cs.map(function (c) { return c.id; }); };
      var body = { samples: g.ticks, title: title, needs: { built: ids(fn.built), desk: ids(fn.desk), cannot: ids(fn.cannot), asked: g.asked.slice() } };
      if (own) body.name = own.value.trim().toUpperCase();
      call("POST", "/new", body)
        .then(function (r) {
          var from = g && g.fromSite;
          data.made = { making: data.made.making, title: r.title || title, words: r.words }; data.appId = r.app; data.app = null; g = null;
          if (from) {   // J3b: the new app takes what stayed ticked on the site read before it was named
            var opened = function () { data.made = null; screen = "app"; render(); openApp(r.app); };
            call("POST", "/capture/take", { app: r.app, site: from.site, skip: ticksOff(from) })
              .then(function (t) { opened(); say((t.words || []).join(" ")); },
                function (e) { opened(); say(G.madeEmpty.replace("{why}", e.message), true); render(); });
            return;
          }
          screen = "made"; render(); openApp(r.app);
        }, function (e) { data.made = null; screen = "name"; data.nameBad = e.message; render(); });
    });
    make.disabled = !!(data.made && data.made.making);   // a second press would make a second app, under the next number
    box.appendChild(make);
    if (data.made && data.made.making) box.appendChild(p(data.made.making));
    else if (!data.nameBad) look();
    return box;
  }

  function vMade() {
    var box = card(data.made.title || appTitle(data.appId));   // J6f F6: Making… goes once Made shows
    var w = data.made.words || [];
    if (w[0]) box.appendChild(el("p", { "class": "hosting-ok", text: w[0] }));
    w.slice(1).forEach(function (x) { box.appendChild(p(x)); });
    var loaded = data.app && data.app.app === data.appId;   // its settings are known once its row is read: no button before
    if (!loaded) { box.appendChild(p("Reading the app…")); return box; }
    var none = !(data.app.settings || []).length;   // nothing to fill: straight to Try
    var def = (data.sites || {}).default;
    box.appendChild(none ? button(data.sites ? tryLabel(def) : G.tryIt, function () { data.made = null; if (def) openTry(data.appId, def); else { data.pick = data.appId; go("app"); } })
      : button(G.nextSettings, function () { data.made = null; go("settings"); }));
    box.appendChild(root.document.createTextNode(" "));
    box.appendChild(button(G.backToApps, function () { data.made = null; go("home"); }, true));   // J6f F5: a way back
    return box;
  }

  // J2-09: Settings
  function vSettings() {
    var box = card("Settings");
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
        a.set = r.set; say(r.words); render();
      }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    box.appendChild(root.document.createTextNode(" "));
    box.appendChild(button("Back to " + (a.title || appTitle(a.app)), function () { go("app"); }, true));
    box.appendChild(el("p", { "class": "hint", text: G.settingsLede }));   // J2-09: below the fields
    return box;
  }

  // J2-10, J6-01: the app's page
  function vApp() {
    var a = data.app;
    var box = card(shownTitle());
    var crumbs = el("p", { "class": "hint" }), home = el("a", { href: "#", text: "My apps" });
    home.addEventListener("click", function (ev) { ev.preventDefault(); go("home"); });
    crumbs.appendChild(home);
    box.insertBefore(crumbs, box.firstChild);
    if (!a) { box.appendChild(p("Reading the app…")); return box; }
    var vs = a.versions || [], sent = vs.filter(function (v) { return (v.sites || []).length; });
    var w0 = data.where && data.where.app === a.app ? data.where : null;
    var tried = !!w0 && (w0.sites || []).some(function (x) { return !x.customer && x.state; });
    box.appendChild(el("p", {}, el("strong", { text: sent.length ? a.line : !w0 ? "" : tried ? U.onSandboxOnly : G.notOnSite }),
      sent.length ? null : " · " + vs[vs.length - 1].version + " (draft)"));
    var acts = el("p", {});
    // one next step in blue: Try until it is tried, then Publish
    var def = triedOn(a, data.sites) || (data.sites || {}).default;
    var tryB = button(data.sites ? tryLabel(def) : G.tryIt, function () { if (def) openTry(a.app, def); else { data.pick = data.pick === a.app ? null : a.app; render(); } }, tried || sent.length > 0),
      pubB = button(G.publish, function () { openPublish(a.app); }, !(tried || sent.length > 0));
    var changeB = def ? button(T.change, function () { data.pick = data.pick === a.app ? null : a.app; render(); }, true) : null;
    tryB.disabled = !data.sites;   // the site's name comes with the list: a second at most
    // J3-06: Upload a new version, one button; the file box stays out of sight
    var file = el("input", { type: "file", accept: ".zip,application/zip", hidden: "", "aria-label": G.upload });
    file.addEventListener("change", function () { if (file.files[0]) upload(file.files[0]); });
    [tryB, changeB, pubB, button(G.download, download, true), uploadButton(file),
     button(G.addSample, function () { startGallery("add"); }, true),
     button(G.capture, function () { data.capture = data.capture && data.capture.app === a.app ? null : { app: a.app }; render(); }, true),
     button(U.logs, function () { data.logs = null; go("logs"); loadLogs(); }, true),
     (a.settings || []).length ? button("Settings", function () { go("settings"); }, true) : null]
      .forEach(function (b) { if (b) { acts.appendChild(b); acts.appendChild(root.document.createTextNode(" ")); } });
    box.appendChild(acts);
    if (data.pick === a.app) box.appendChild(vPick(a.app));   // one list: where it is, the company's other sites, another
    if (data.capture && data.capture.app === a.app) box.appendChild(vCapture(a.app, data.capture));
    box.appendChild(file);
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
    versionsShown(vs).reverse().forEach(function (v) {
      var went = el("td", { text: whereWent(v, vs) });
      if (canGoBack(vs, v)) {
        went.appendChild(el("br", {}));
        went.appendChild(button(U.goBack, function (ev) { goBack(ev.target, v.version); }, true));
      }
      body.appendChild(el("tr", {}, el("td", { text: versionLine(v) }), el("td", { text: day(v.at) }), went));
    });
    t.appendChild(body);
    vb.appendChild(t);
    if (data.back) vb.appendChild(vBack());
    // What it covers (J6-12)
    var cb = card(G.covers);
    var fill = function () {
      var cv = covers(a, site.catalogue), made = day((vs[0] || {}).at);
      if (!cv.built.length && !cv.tobuild.length && !cv.desk.length && !cv.cannot.length) {
        cb.appendChild(p((a.samples || []).length ? "Built in this app: " + a.samples.map(function (n) { var s = byName(n); return s ? sampleLabel(s) : n; }).join(", ") + "."
          : (a.kinds || []).length ? blankCarries(a.kinds) : G.blankCovers));
        return;
      }
      cv.built.forEach(function (c) {
        var ss = needSamples(c).filter(function (n) { return (a.samples || []).indexOf(n) >= 0; }).map(byName).filter(Boolean);
        cb.appendChild(p("Built in this app: " + c.asks + (ss.length ? " (" + ss.map(sampleLabel).join(", ") + ")" : "")));
      });
      cv.tobuild.forEach(function (c) { cb.appendChild(el("p", {}, G.toBuild + c.asks, recipeLink(c, " (", ")"))); });
      cv.extra = cv.extra.map(function (n) { var s = byName(n); return s ? sampleLabel(s) : n; });
      cv.extra.forEach(function (n) { cb.appendChild(p(G.extra + n + ".")); });
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
    more.appendChild(vKey(a.app));
    if (who.role === "owner") more.appendChild(vHandOver(a.app));
    more.appendChild(vCancel(a.app));
    return el("div", {}, box, vWhere(a.app), vb, cb, more);
  }

  function uploadButton(file) {
    var b = button(G.upload, function () { file.click(); }, true);
    b.title = G.uploadHint;
    return b;
  }

  // one picture: its size read in the browser, then put in the App library by the hosting (J7-01)
  function addPicture(f, cd) {
    var bad = U.pictureBad.replace("{name}", f.name);
    if (!PIC_TYPES[f.type]) return Promise.reject(new Error(bad));
    return root.createImageBitmap(f).then(function (img) {
      // a screenshot too big for the card is made smaller here (2400 pixels a side, WebP), never refused for its size
      var w = img.width, h = img.height, kind = pictureType(f);
      if (kind && w <= 2400 && h <= 2400) return f.arrayBuffer().then(function (buf) { return [kind, buf, w, h]; });
      var k = Math.min(1, 2400 / Math.max(w, h)), cv = root.document.createElement("canvas");
      cv.width = Math.round(w * k); cv.height = Math.round(h * k);
      cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
      var shrink = function (q) {
        return new Promise(function (ok) { cv.toBlob(ok, "image/webp", q); }).then(function (b) {
          if (b && b.size <= 300 * 1024 && b.type === "image/webp") return b.arrayBuffer().then(function (buf) { return ["webp", buf, cv.width, cv.height]; });
          if (q > 0.5) return shrink(q - 0.15);
          throw new Error(bad);
        });
      };
      return shrink(0.85);
    }).then(function (x) {
      return call("POST", "/publish/picture", { app: data.appId, type: x[0], data: b64(new Uint8Array(x[1])), w: x[2], h: x[3] });
    }).then(function (r) { cd.pictures.push({ sha256: r.sha256, type: r.type, w: r.w, h: r.h, name: f.name }); });
  }
  function b64(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i += 8192) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
    return btoa(s);
  }

  function download() {
    call("POST", "/download", { app: data.appId }).then(function (r) {
      say(U.downloaded.replace("{file}", r.file || "the app folder")); render();   // W227: the press says where it went
      root.location.assign(r.url);
    }, fail);
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
    var row = el("div", { "class": "hosting-step" }, p(String(o.words || "").replace(/\s*Accept \/ Refuse\.?\s*$/, "")));
    if (o.pays) row.appendChild(p(o.pays));   // K176: who pays, said before Accept
    row.appendChild(button(WORDS.accept, function (ev) {
      ev.target.disabled = true;
      call("POST", "/handover/accept", { app: o.app }).then(function (r) {
        go("home");   // first: going home clears the last message
        say(acceptedWords(o.app, r));
        render();
      }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    row.appendChild(button(WORDS.refuse, function () {
      call("POST", "/handover/refuse", { app: o.app }).then(function () {
        go("home"); say("You refused " + appTitle(o.app) + ". Nothing moved."); render();
      }, fail);
    }, true));
    return row;
  }

  // Change, one list (any site, any number, read from records). Where this app is now, each with its
  // version; the company's other sites; Another site…, any iVendNext site's address, which joins the list
  // J3: Capture from a site: pick a site, read it, untick what to leave out, capture into the app's next version; with no
  // app (J3b, New app's From a site), Next names the new app, which is made with what stays ticked
  function vCapture(app, c) {
    // only a site Capture can read: one of ours granted to the company, or one added with its key (J3 critic)
    var box = card(app ? G.capture : G.fromSite), sites = ((data.sites || {}).company || []).filter(function (x) { return x.press; });
    box.appendChild(p(G.captureLede));
    var sel = el("select", { "aria-label": "Site" });
    sites.forEach(function (x) { sel.appendChild(el("option", { value: x.site, text: x.label ? x.label + " \u00b7 " + x.site : x.site })); });
    if (c.site) sel.value = c.site;
    box.appendChild(el("p", {}, sel, " ", button(G.captureRead, function (ev) {
      ev.target.disabled = true; c.site = sel.value; c.list = null; c.reading = true; render();
      call("POST", "/capture/list", app ? { app: app, site: c.site } : { site: c.site }).then(function (r) {
        c.reading = false; c.list = r; c.off = {}; render();
      }, function (e) { c.reading = false; fail(e); });
    }, !!c.list || !sites.length)));
    if (!sites.length) box.appendChild(el("p", {}, G.captureNoSite + " ", button(S.open, function () { go("sites"); }, true)));
    if (c.reading) box.appendChild(p(G.reading));
    var l = c.list;
    if (!l) return box;
    if (l.words) box.appendChild(p(l.words));
    captureGroups(l.items).forEach(function (grp) {
      var gb = el("div", { "class": "hosting-step" }, el("h3", { text: grp.type }));
      grp.items.forEach(function (it) {
        var cb = el("input", { type: "checkbox" });
        cb.checked = !c.off[it.id];
        cb.addEventListener("change", function () { c.off[it.id] = !cb.checked; });
        gb.appendChild(el("p", {}, el("label", {}, cb, " " + it.name)));
      });
      box.appendChild(gb);
    });
    if ((l.renamed || []).length) {
      box.appendChild(el("h3", { text: G.renamed }));
      l.renamed.forEach(function (x) { box.appendChild(el("p", { "class": "hint", text: x })); });
    }
    if ((l.left_out || []).length) {
      box.appendChild(el("h3", { text: G.leftOut }));
      l.left_out.forEach(function (x) { box.appendChild(el("p", { "class": "hint", text: x.type + " " + x.name + ": " + x.reason })); });
    }
    if ((l.items || []).length && !app) box.appendChild(el("p", {}, button(G.next, function () {   // name it, then Make the app
      if (ticksOff(c).length < l.items.length) { screen = "name"; say(""); } else say(G.captureNone, true);
      render();
    })));
    if ((l.items || []).length && app) box.appendChild(el("p", {}, button(G.captureTake, function (ev) {
      ev.target.disabled = true;
      call("POST", "/capture/take", { app: app, site: c.site, skip: ticksOff(c) }).then(function (r) {
        data.capture = null; say((r.words || []).join(" ")); openApp(app);
      }, function (e) { ev.target.disabled = false; fail(e); });
    })));
    return box;
  }
  function ticksOff(c) { return Object.keys(c.off || {}).filter(function (k) { return c.off[k]; }); }
  // the capture list, one group per record type, in the order the site answered
  function captureGroups(items) {
    var out = [];
    (items || []).forEach(function (it) {
      var gr = out.filter(function (x) { return x.type === it.type; })[0];
      if (!gr) { gr = { type: it.type, items: [] }; out.push(gr); }
      gr.items.push(it);
    });
    return out;
  }
  function vPick(app) {
    var box = el("div", { "class": "hosting-step" }), sites = data.sites || {}, w = data.where && data.where.app === app ? data.where : null;
    var tryOn = function (site) { return function () { data.pick = null; openTry(app, site); }; };
    var here = ((w && w.sites) || []).filter(function (x) { return x.sandbox; }), named = here.map(function (x) { return x.site; });
    var added = function (site) {   // a site the company added (not one of ours handed to it): Remove from my list
      var x = (sites.company || []).filter(function (y) { return y.site === site; })[0];
      return x && !x.press ? button(T.removeList, function (ev) {
        ev.target.disabled = true;
        call("POST", "/sites/remove", { site: site, mine: true }).then(function (r) { data.sites = r; data.where = null; data.whereAsked = null; render(); },
                                                                     function (e) { ev.target.disabled = false; fail(e); });
      }, true) : null;
    };
    if (here.length) {
      box.appendChild(el("h3", { text: T.here }));
      here.forEach(function (x) { box.appendChild(el("p", {}, button(tryLabel(x.site), tryOn(x.site), true), " " + (x.state || x.version || "") + " ", added(x.site))); });
    }
    var others = trySites(sites).filter(function (x) { return named.indexOf(x.site) < 0; });
    if (others.length) {
      box.appendChild(el("h3", { text: here.length ? T.others : T.ours }));
      others.forEach(function (x) {
        box.appendChild(el("p", {}, button(tryLabel(x.site), tryOn(x.site), true), " " + (x.label ? x.label + " \u00b7 " : "") + siteHow(x) + " ", added(x.site)));
      });
    }
    box.appendChild(el("p", {}, button(S.open, function () { data.pick = null; go("sites"); }, true)));
    if (!(sites.company || []).length && sites.words) {
      var parts = noSandboxParts(sites.words);
      box.appendChild(el("p", {}, parts[0], parts[1] ? el("a", { href: "/sandbox.html", text: parts[1] }) : null, parts[2] || null));
    }
    box.appendChild(el("h3", { text: T.another }));
    var inp = el("input", { type: "text", spellcheck: "false", autocomplete: "off", placeholder: "shop.ivendnext.com", "aria-label": T.another });
    inp.value = data.typed || "";
    inp.addEventListener("input", function () { data.typed = inp.value; });
    box.appendChild(el("p", {}, inp, " ", button(T.tryThere, function () {
      var v = inp.value.trim();
      if (v) { data.pick = null; openTry(app, v); }
    })));
    return box;
  }

  // J4-02 to J4-05, J4-11: Try on ⟨site⟩, one press (free, nothing to tick or choose). The site's own check first, shown
  // as the install goes on, then the steps, one per ask
  function openTry(app, site) {
    data.appId = app; data.tryC = null; data.tryS = null; data.tryPress = false; data.trySite = site || null;
    screen = "try"; say(""); render();
    if (!data.sites) loadSites();
    call("POST", "/try/status", { app: app }).then(function (s) {
      if (s.step) data.tryS = s;
      if (tryRunning(s)) { data.trySite = s.site || data.trySite; render(); pollTry(); return; }
      if (!offerAgain(s)) { render(); return; }
      return startTry(app);
    }).then(null, fail);
  }

  // the site's check, then the install at once with the words it showed
  function startTry(app) {
    return call("POST", "/try", { app: app, site: data.trySite || undefined }).then(function (c) {
      data.tryC = c; data.trySite = c.site; data.tryPress = true; data.typed = ""; render();
      return call("POST", "/try/install", { app: app, sha: c.sha, site: c.site }).then(function (r) {
        data.tryPress = false; data.tryS = r; say(""); render(); pollTry();
      });
    }, function (e) { data.tryS = null; throw e; }).then(null, function (e) { data.tryPress = false; fail(e); });   // refused (M14): the last try's lines are not this one's
  }

  function pollTry(errors) {
    if (screen !== "try" || !tryRunning(data.tryS)) return;
    root.setTimeout(function () {
      if (screen !== "try") return;
      call("POST", "/try/status", { app: data.appId }).then(function (s) {
        data.tryS = s; say(""); render();
        pollTry(0);
      },
        function (e) { if ((errors || 0) >= 3) { fail(e); return; } pollTry((errors || 0) + 1); });   // a passing error: ask again
    }, 3000);
  }

  function vTry() {
    var s = data.tryS, c = data.tryC, site = (s && s.site) || data.trySite;
    var box = card(site ? tryLabel(site) : G.tryIt);
    var crumbs = el("p", { "class": "hint" }), back = el("a", { href: "#", text: shownTitle() });
    back.addEventListener("click", function (ev) { ev.preventDefault(); screen = "app"; say(""); openApp(data.appId); });
    crumbs.appendChild(back);
    box.insertBefore(crumbs, box.firstChild);
    if (data.tryPress) {   // from the press on: no old refusal, and the words say it started
      box.appendChild(p(T.starting.replace("{site}", site || "")));
      box.appendChild(el("p", { "class": "hint", text: T.wait }));
      return box;
    }
    if (s && s.step) {
      if (!s.done) (s.lines || []).forEach(function (l) { box.appendChild(p(l)); });   // the steps go once the result is in
      if (tryRunning(s)) box.appendChild(el("p", { "class": "hint", text: T.wait }));
      if (s.stop) {
        box.appendChild(el("p", { "class": "hosting-bad", text: s.stop }));
        if ((s.build_lines || []).length) box.appendChild(el("pre", { text: s.build_lines.join("\n") }));
        box.appendChild(button(T.tryAgain, function (ev) { ev.target.disabled = true; data.tryS = null; startTry(data.appId); }));
      }
      if (s.done) {
        // where it went, for every app: Installed on ⟨site⟩ (or, on a site its administrator installs, the shelf key and
        // what to do with it, as Publish shows its message), the site's own Desk and till, and the app's own address
        var fin = card(s.installed_on || "");
        if (s.shelf_key) {
          fin.appendChild(el("pre", { text: s.shelf_key, "class": "apps-msg" }));
          fin.appendChild(copyRow(s.shelf_key));
        }
        var links = el("p", {});
        if (s.desk) links.appendChild(el("a", { href: s.desk, target: "_blank", rel: "noopener", "class": "site-btn", text: T.openDesk }));
        links.appendChild(root.document.createTextNode(" "));
        if (s.till_url) links.appendChild(el("a", { href: s.till_url, target: "_blank", rel: "noopener", "class": "site-btn site-btn-ghost", text: T.openTill }));
        fin.appendChild(links);
        if (s.address) fin.appendChild(el("p", { "class": "hint", text: T.appAddress + s.address }));
        box.appendChild(fin);
        if (!s.press) (s.head || []).filter(function (l) { return l !== s.installed_on; }).forEach(function (l) { fin.appendChild(p(l)); });
        var res = card("Connection points");
        (s.head || []).filter(function (l) { return l !== s.installed_on; })
          .forEach(function (l, i) { res.appendChild(el("p", { "class": i ? "" : "hint", text: l })); });
        var ul = el("ul", {});
        (s.results || []).forEach(function (l) { ul.appendChild(el("li", { "class": pointClass(l), text: l })); });
        res.appendChild(ul);
        var pointsOk = (s.results || []).every(function (l) { return pointClass(l) !== "hosting-bad"; });
        res.appendChild(button(T.testAgain, function (ev) {
          ev.target.disabled = true;
          call("POST", "/test", { app: data.appId }).then(function (r) { data.tryS = r; render(); },
                                                        function (e) { ev.target.disabled = false; fail(e); });
        }, pointsOk));
        if (s.press) box.appendChild(res);   // a site its administrator installs tests itself (said above)
        if ((s.till || []).length) {
          var till = card(s.till[0]);
          s.till.slice(1).forEach(function (l) { till.appendChild(p(l)); });
          box.appendChild(till);
        }
        if (pointsOk) box.appendChild(el("p", {}, button(G.publish, function () { openPublish(data.appId); })));
      }
    } else if (!c || (flash && flash.bad)) {
      if (flash && flash.bad) {   // refused: the way on, never a page with nothing to press
        var listed = ((data.sites || {}).company || []).some(function (x) { return x.site === data.trySite; });
        box.appendChild(data.sites && !(data.sites.company || []).length && !data.trySite ? el("p", {}, el("a", { href: "/sandbox.html", "class": "site-btn", text: T.request }))
          : data.trySite && !listed ? button(T.change, function () { data.pick = data.appId; screen = "app"; say(""); openApp(data.appId); })
          : button(T.tryAgain, function (ev) { ev.target.disabled = true; say(""); startTry(data.appId); }));
        return box;
      }
      box.appendChild(p("Reading what installing it changes on " + (site || "the site") + "…"));
      return box;
    }
    if (!c) return box;
    if (!c.press || !consentSections(c).length) {   // its administrator's own install shows it, or the site has it already
      if ((c.money || {}).line) box.appendChild(p(c.money.line));
      return box;
    }
    // what the install changes, as the site's own check drew it, read while it goes on (nothing to tick)
    var what = el("details", {}, el("summary", { text: (c.version ? c.version + ": " : "") + T.changes }));
    what.open = !(s && s.done);
    consentSections(c).forEach(function (sec) {
      what.appendChild(el("h4", { text: sec.title }));
      var ul = el("ul", {});
      sec.lines.forEach(function (l) { ul.appendChild(el("li", { text: l })); });
      what.appendChild(ul);
    });
    if ((c.changes || []).length) {
      what.appendChild(el("h4", { text: T.updates }));
      var cu = el("ul", {});
      c.changes.forEach(function (l) { cu.appendChild(el("li", { text: l })); });
      what.appendChild(cu);
    }
    what.appendChild(el("details", {}, el("summary", { text: T.wording }), el("pre", { text: c.wording || "" })));
    if ((c.money || {}).line) what.appendChild(p(c.money.line));
    box.appendChild(what);
    return box;
  }

  // J5-01 to J5-04, J5-15, J5-19, J6-02, J7-01, J9-01 to J9-03: Publish, then its steps, one per ask (as Try's)
  function openPublish(app) {
    if ((data.pubForm || {}).app !== app) data.pubForm = null;   // one app's form never shows on another's
    data.added = null;   // "Added to a new draft …, on no site yet" is old once the person publishes (walk 11-02)
    data.appId = app; data.pubC = null; data.pubS = null; data.pubPress = false; data.pubTo = data.pubTo || "customer"; screen = "publish"; say(""); render();
    call("POST", "/publish/status", { app: app }).then(function (s) {
      if (pubRunning(s)) { data.pubS = s; render(); pollPub(); return; }
      return call("POST", "/publish/start", { app: app }).then(function (c) { if (s.step) data.pubS = s; data.pubC = c; data.pubTo = pubOpensOn(data.pubForm, data.pubTo, c); render(); });
    }).then(null, fail);
  }

  function pollPub(errors) {
    if (screen !== "publish" || !pubRunning(data.pubS)) return;
    root.setTimeout(function () {
      if (screen !== "publish") return;
      call("POST", "/publish/status", { app: data.appId }).then(function (s) {
        // stopped while watched: the form comes back under the stop's words, so Publish can be pressed again (walk 11-02)
        if (s.stop && !data.pubC) { openPublish(data.appId); return; }
        if (s.done) data.pubForm = null;
        data.pubS = s; say(""); render(); pollPub(0);
      },
        function (e) { if ((errors || 0) >= 3) { fail(e); return; } pollPub((errors || 0) + 1); });
    }, 3000);
  }

  function copyRow(text) {
    var st = el("span", { "class": "hint", "aria-live": "polite" });
    return el("p", {}, button(U.copy, function () {
      root.navigator.clipboard.writeText(text).then(function () { st.textContent = U.copied; });
    }, true), st);
  }

  function crumbsTo(box) {
    var crumbs = el("p", { "class": "hint" }), back = el("a", { href: "#", text: shownTitle() });
    back.addEventListener("click", function (ev) { ev.preventDefault(); screen = "app"; say(""); openApp(data.appId); });
    crumbs.appendChild(back);
    box.insertBefore(crumbs, box.firstChild);
  }

  function vPubSteps(box, s) {
    pubLines(s, data.inst || {}).forEach(function (l) { box.appendChild(p(l)); });
    (s.install_now || []).forEach(function (x) { box.appendChild(vInstallNow(x, s.version)); });   // J6 F19: it leads
    if (pubRunning(s)) {   // never an empty page while it works
      if (!(s.lines || []).length) box.appendChild(p(U.publishing));
      box.appendChild(el("p", { "class": "hint", text: U.wait }));
    }
    if (s.checkout_url) box.appendChild(el("p", {}, el("a", { href: s.checkout_url, target: "_blank", rel: "noopener", "class": "site-btn", text: payLabel(s) })));
    if (s.stop) {
      box.appendChild(el("p", { "class": "hosting-bad", text: s.stop }));
      if ((s.build_lines || []).length) box.appendChild(el("pre", { text: s.build_lines.join("\n") }));
    }
    if (s.public_words) box.appendChild(el("p", { "class": "hosting-ok", text: s.public_words }));
    if (s.card_url) box.appendChild(el("p", {}, el("a", { href: s.card_url, target: "_blank", rel: "noopener", text: s.card_url })));
    (handOff(s, data.inst || {}) || []).forEach(function (m) {
      var sb = card(s.send_head);
      sb.appendChild(el("p", { "class": "hint", text: m.site }));
      sb.appendChild(el("pre", { text: m.message, "class": "apps-msg" }));
      sb.appendChild(copyRow(m.message));
      box.appendChild(sb);
    });
  }

  // MYSITES: Install now on a customer's site where the company holds its own key: the site's own install words, read
  // as the card first draws (as Try does), then one press, then where it stands until it is installed
  function vInstallNow(x, version) {
    var k = instKey(x.site, version, data.appId), inst = (data.inst = data.inst || {})[k] || {};
    var box = card(S.installOn.replace("{site}", x.label || x.site)), state = installState(inst, x.installed);
    var ask = function (body) {
      return call("POST", "/publish/install", Object.assign({ app: data.appId, site: x.site }, body)).then(function (r) {
        data.inst[k] = r; render();
        if (r.step === "installing") root.setTimeout(function () { ask({ sha: inst.sha || r.sha }); }, 3000);
      }, function (e) { delete data.inst[k]; fail(e); });   // refused: the button comes back with the site's words
    };
    if (state === "done") { box.appendChild(el("p", { "class": "hosting-ok", text: inst.words || "Installed." })); return box; }
    if (inst.words) box.appendChild(p(inst.words));
    if (state === "read") {
      data.inst[k] = { reading: true };
      ask({});
      box.appendChild(p("Reading what installing it changes on " + x.site + "\u2026"));
    } else if (state === "ask") {
      consentSections(inst).forEach(function (sec) {
        box.appendChild(el("p", {}, el("strong", { text: sec.title })));
        var ul = el("ul", {});
        sec.lines.forEach(function (l) { ul.appendChild(el("li", { text: l })); });
        box.appendChild(ul);
      });
      box.appendChild(button(S.installNow, function (ev) {
        ev.target.disabled = true;
        data.inst[k] = Object.assign({}, inst, { step: "installing", words: "" });
        ask({ sha: inst.sha });
      }));
    }
    return box;
  }

  function go2settings() { screen = "settings"; say(""); openApp(data.appId); render(); }
  function vPublish() {
    var box = card(G.publish), s = data.pubS, c = data.pubC;
    crumbsTo(box);
    (data.backMessages || []).forEach(function (m) {
      box.appendChild(el("p", {}, el("strong", { text: m.site + ": " }), m.message));
      box.appendChild(copyRow(m.message));
    });
    if (data.pubPress) {   // from the press on: no old refusal, and the words say it started
      box.appendChild(p(U.publishing));
      box.appendChild(el("p", { "class": "hint", text: U.wait }));
      return box;
    }
    // the last message shows while nothing newer waits; a new version's form never sits under an old version's key
    if (s && s.step && (pubRunning(s) || !c || (s.done && s.version === c.version))) {
      vPubSteps(box, s);
      if (!c) return box;
    }
    if (s && s.stop) vPubSteps(box, { stop: s.stop, build_lines: s.build_lines });
    if (!c) { box.appendChild(p("Reading the app…")); return box; }
    var tabs = el("p", {});
    [["customer", U.toCustomer], ["everyone", U.toEveryone]].forEach(function (t) {
      var b = button(t[1], function () { data.pubTo = t[0]; render(); }, data.pubTo !== t[0]);
      b.setAttribute("aria-pressed", String(data.pubTo === t[0]));
      tabs.appendChild(b); tabs.appendChild(root.document.createTextNode(" "));
    });
    box.appendChild(tabs);
    var form = data.pubForm || (data.pubForm = { app: data.appId, sites: [""], own: false, plan: null, card: { title: shownTitle(), what: ["", "", ""], industries: [] } });
    var recheck = function () {};   // set once the button exists: a typed site is something new to publish (walk 11-02)
    if (data.pubTo === "customer") {
      if ((c.sites || []).length && c.goes_to && !c.nothing_new) box.appendChild(p(c.goes_to));
      box.appendChild(el("p", {}, el("strong", { text: (c.sites || []).length ? U.anotherSite : U.sitesLabel })));
      form.sites.forEach(function (v, i) {
        var inp = el("input", { type: "text", spellcheck: "false", autocomplete: "off", placeholder: "retailer.ivendnext.com" });
        inp.value = v;
        inp.addEventListener("input", function () { form.sites[i] = inp.value; recheck(); });
        box.appendChild(el("p", {}, inp));
      });
      box.appendChild(el("p", {}, button(U.addSite, function () { form.sites.push(""); render(); }, true)));
      if ((c.live_sites || []).length) {   // MYSITES: the company's customers' live sites, by label, to tick
        box.appendChild(el("p", {}, el("strong", { text: S.liveTick })));
        c.live_sites.forEach(function (x) {
          var tick = el("input", { type: "checkbox" });
          tick.checked = form.sites.indexOf(x.site) >= 0;
          tick.addEventListener("change", function () { form.sites = tickLive(form.sites, x.site, tick.checked); render(); });
          box.appendChild(el("p", {}, el("label", {}, tick, " " + (x.label ? x.label + " \u00b7 " : "") + x.site)));
        });
      }
      var own = el("input", { type: "checkbox" });
      own.checked = form.own;
      own.addEventListener("change", function () { form.own = own.checked; render(); });
      box.appendChild(el("p", {}, el("label", {}, own, " " + c.own_site)));
      if (!(c.sites || []).length) box.appendChild(p(c.only_these + (c.also_sandbox ? " " + c.also_sandbox : "")));   // "every site" says it for an update
    } else if (c.listed) {
      box.appendChild(p(U.listedUpdate));   // J7-05: the card it has; nothing to retype
    } else {
      var cd = form.card;
      var text = function (label, k, hint) {
        var inp = el("input", { type: "text" });
        inp.value = cd[k] || "";
        inp.addEventListener("input", function () { cd[k] = inp.value; });
        box.appendChild(field(label, inp, hint));
      };
      text(U.title, "title");
      text(U.oneLine, "summary");
      box.appendChild(el("p", {}, el("strong", { text: U.whatItDoes })));
      cd.what.forEach(function (v, i) {
        var inp = el("input", { type: "text" });
        inp.value = v;
        inp.addEventListener("input", function () { cd.what[i] = inp.value; });
        box.appendChild(el("p", {}, inp));
      });
      cd.pictures = cd.pictures || [];
      var pics = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp", multiple: "" });
      pics.disabled = cd.pictures.length >= 4 || !!cd.busy;
      pics.addEventListener("change", function () {
        var all = Array.prototype.slice.call(pics.files || []), room = 4 - cd.pictures.length, files = all.slice(0, room);
        cd.notes = all.length > room ? [U.picturesOnly.replace("{n}", String(room))] : [];
        cd.busy = true; render();
        files.reduce(function (prev, f) {   // one by one; a file refused is said by its name, and the rest still go
          return prev.then(function () {
            return addPicture(f, cd).then(null, function (e) { cd.notes.push(e.message); });
          });
        }, Promise.resolve()).then(function () { cd.busy = false; render(); });
      });
      box.appendChild(field(U.pictures, pics, U.picturesHint));
      if (cd.busy) box.appendChild(el("p", { "class": "hint", text: U.picturesBusy }));
      (cd.notes || []).forEach(function (t) { box.appendChild(el("p", { "class": "hosting-bad", text: t })); });
      cd.pictures.forEach(function (x, i) {
        box.appendChild(el("p", { "class": "hint" }, (i + 1) + ". " + x.name + " (" + x.w + " × " + x.h + ") ",
          button(U.remove, function () { cd.pictures.splice(i, 1); render(); }, true)));
      });
      var fs = el("fieldset", {}, el("legend", { text: U.industries }));
      (c.industries || []).forEach(function (id) {
        var cb = el("input", { type: "checkbox" });
        cb.checked = cd.industries.indexOf(id) >= 0;
        cb.addEventListener("change", function () {
          cd.industries = cd.industries.filter(function (x) { return x !== id; }).concat(cb.checked ? [id] : []);
        });
        fs.appendChild(el("label", {}, cb, " " + industryWords(id) + " "));
      });
      box.appendChild(fs);
      var pr = el("fieldset", {}, el("legend", { text: U.price }));
      [["free", U.free], ["key", U.withKey]].forEach(function (x) {
        var r = el("input", { type: "radio", name: "pub-price", value: x[0] });
        r.checked = cd.price === x[0];
        r.addEventListener("change", function () { cd.price = x[0]; });
        pr.appendChild(el("p", {}, el("label", {}, r, " " + x[1])));
      });
      box.appendChild(pr);
      var steps = el("textarea", { rows: "4" });
      steps.value = (cd.setup || []).join("\n");
      steps.addEventListener("input", function () { cd.setup = steps.value.split("\n").filter(function (x) { return x.trim(); }); });
      box.appendChild(field(U.setUp, steps, U.setUpHint));
      text(U.guide, "guide", U.guideHint);
    }
    var money = c.money || {};
    (money.lines || []).forEach(function (l) { box.appendChild(p(l)); });
    // our own teams order no customer's production: the plan is asked only for the company's own site (J5-03, J5-19)
    var askPlan = (money.plans || []).length && (!money.own_only || (data.pubTo === "customer" && form.own));
    if (askPlan) {
      if (!form.plan && money.suggested) form.plan = money.suggested;   // Starter chosen beforehand (K176)
      var fsp = el("fieldset", {}, el("legend", { text: T.plan }));
      money.plans.forEach(function (x) {
        var r = el("input", { type: "radio", name: "pub-plan", value: x.plan });
        r.checked = form.plan === x.plan;
        r.addEventListener("change", function () { form.plan = x.plan; });
        fsp.appendChild(el("p", {}, el("label", {}, r, " " + x.words)));
      });
      box.appendChild(fsp);
    }
    var stopNow = function () {
      return data.pubTo === "customer" && c.nothing_new && !form.sites.some(function (x) { return x.trim(); }) ? c.nothing_new : c.m16;
    };
    var stop = stopNow();
    var go = button(data.pubTo === "customer" || c.listed ? c.button : U.send, function (ev) {
      if (form.card.busy) return;   // the pictures still going up: Send waits for them
      if (askPlan && !form.plan) { say(T.choosePlan, true); render(); return; }
      data.pubPress = true; say(""); render();
      var body = { app: data.appId, to: data.pubTo, plan: pubPlan(askPlan, form, money) };
      if (data.pubTo === "customer") { body.sites = form.sites.filter(function (x) { return x.trim(); }); body.own = form.own; }
      else if (!c.listed) body.card = cardBody(form.card);   // a listed app keeps its card (J7-05)
      call("POST", "/publish", body).then(function (r) {
        data.pubPress = false;
        if (r.stop) { openPublish(data.appId); return; }   // stopped at once: the form under the stop's words, its addresses kept
        if (r.done) data.pubForm = null;
        data.pubS = r; data.pubC = null; say(""); render(); pollPub();
      }, function (e) { data.pubPress = false; fail(e); });
    });
    var stopLine = el("p", { text: stop || "" });
    if (stop) {
      go.disabled = true; box.appendChild(stopLine);
      if (c.m16 && stop === c.m16) box.appendChild(el("p", {}, button("Settings", function () { go2settings(); }, true)));
    }
    if (form.card.busy) go.disabled = true;
    recheck = function () {
      var now = stopNow();
      go.disabled = !!now || !!form.card.busy;
      stopLine.textContent = now || "";
      if (now && !stopLine.parentNode) box.insertBefore(stopLine, go.parentNode || null);
      if (!now && stopLine.parentNode) stopLine.parentNode.removeChild(stopLine);
    };
    box.appendChild(el("p", {}, go));
    return box;
  }

  // J5-16, J5-12, J13-01, M15, J10-01, J5-11: Where it runs, read when the app's page opens
  function vWhere(app) {
    var box = card(U.whereRuns), w = data.where;
    if (!w || w.app !== app) {
      if (!data.whereAsked || data.whereAsked !== app) {
        data.whereAsked = app;
        call("POST", "/where", { app: app }).then(function (r) { data.where = r; render(); }, function () {});
      }
      box.appendChild(p("Reading where it runs…"));
      return box;
    }
    if (w.state) box.appendChild(el("p", { "class": /not answering/.test(w.state) ? "hosting-bad" : "hosting-ok", text: w.state }));
    var ul = el("ul", {});
    var shown = (w.sites || []).filter(function (s) { return s.customer || s.state || s.version; });   // a connected sandbox with nothing on it runs nothing
    shown.forEach(function (s) {
      var li = el("li", {}, el("strong", { text: s.site }), s.state ? ": " + s.state : (s.version ? ": " + s.version : ""));
      if (s.customer) {
        var d = el("details", {}, el("summary", { text: U.removeSite }), p(s.remove_words));
        d.appendChild(button(U.remove, function (ev) {
          ev.target.disabled = true;
          call("POST", "/sites/remove", { app: app, site: s.site }).then(function (r) { data.where = null; data.whereAsked = null; say(r.words); openApp(app); },
                                                                          function (e) { ev.target.disabled = false; fail(e); });
        }, true));
        li.appendChild(d);
      }
      ul.appendChild(li);
    });
    if (shown.length) box.appendChild(ul);
    if (w.customer_test) box.appendChild(el("p", { "class": "hint", text: w.customer_test }));
    // J5-15: the plan, changed from the next month
    if (w.plans) {
      var pick = w.plan_chosen, fp = el("fieldset", {}, el("legend", { text: T.plan }));
      w.plans.forEach(function (x) {
        var r = el("input", { type: "radio", name: "where-plan", value: x.plan });
        r.checked = x.plan === w.plan_chosen;
        r.addEventListener("change", function () { pick = x.plan; });
        fp.appendChild(el("p", {}, el("label", {}, r, " " + x.words)));
      });
      if (w.plan_line) fp.appendChild(el("p", { "class": "hint", text: w.plan_line }));
      fp.appendChild(button(w.change_plan, function (ev) {
        ev.target.disabled = true;
        call("POST", "/plan", { app: app, plan: pick }).then(function (r) { data.where = null; data.whereAsked = null; say(r.words); render(); },
                                                             function (e) { ev.target.disabled = false; fail(e); });
      }, true));
      box.appendChild(fp);
    }
    // J10-01: where the service runs
    var sv = el("details", {}, el("summary", { text: U.serviceRuns }));
    sv.open = !!w.service;
    var addr = el("input", { type: "url", spellcheck: "false", placeholder: "https://apps.acme.example" });
    addr.value = w.service || "";
    var ours = el("input", { type: "radio", name: "svc" }), mine = el("input", { type: "radio", name: "svc" });
    ours.checked = !w.service; mine.checked = !!w.service;
    sv.appendChild(el("p", {}, el("label", {}, ours, " " + w.service_words[0])));
    sv.appendChild(el("p", {}, el("label", {}, mine, " " + w.service_words[1])));
    var at = field(U.itsAddress, addr);
    at.hidden = !w.service;   // the address only for one's own server
    [ours, mine].forEach(function (r) { r.addEventListener("change", function () { at.hidden = !mine.checked; }); });
    sv.appendChild(at);
    if (w.service) sv.appendChild(el("p", { "class": "hint", text: w.service_line }));
    sv.appendChild(button(U.save, function (ev) {
      ev.target.disabled = true;
      call("POST", "/service", { app: app, own_server: mine.checked ? addr.value.trim() : "" })
        .then(function () { data.where = null; data.whereAsked = null; render(); }, function (e) { ev.target.disabled = false; fail(e); });
    }, true));
    box.appendChild(sv);
    return box;
  }

  // J6-06: Logs, the last hour by default, searched, newest first, downloaded as text
  function loadLogs() {
    var q = data.logQ || "", hours = data.logH || 1;
    call("POST", "/logs", { app: data.appId, q: q, hours: hours }).then(function (r) { data.logs = r; render(); }, fail);
  }
  function vLogs() {
    var box = card(U.logs), r = data.logs;
    crumbsTo(box);
    var q = el("input", { type: "search", spellcheck: "false" });
    q.value = data.logQ || "";
    var hs = el("select", {});
    [1, 6, 24, 168].forEach(function (h) {
      var o = el("option", { value: String(h), text: h === 1 ? "hour" : h + " hours" });
      if ((data.logH || 1) === h) o.selected = true;
      hs.appendChild(o);
    });
    box.appendChild(el("p", {}, U.hours + " ", hs, " ", q, " ", button(U.search, function () {
      data.logQ = q.value.trim(); data.logH = parseInt(hs.value, 10); data.logs = null; render(); loadLogs();
    })));
    if (!r) { box.appendChild(p("Reading the log…")); return box; }
    if (r.words) box.appendChild(p(r.words));
    if ((r.lines || []).length) box.appendChild(el("p", { "class": "hint", text: U.utc }));
    var pre = el("pre", { "class": "log-lines", text: (r.lines || []).join("\n") });   // each line wraps, never cut
    if ((r.lines || []).length) {
      box.appendChild(pre);
      box.appendChild(el("p", {}, button(U.downloadLogs, function () {
        var a = el("a", { href: root.URL.createObjectURL(new root.Blob([logFile(data.appId, r.lines)], { type: "text/plain" })),
                          download: data.appId + "-log.txt" });
        root.document.body.appendChild(a); a.click(); a.remove();
      }, true)));
    }
    return box;
  }

  // J12-01, M30: Go back, its words first, then the message for each administrator
  function goBack(btn, version) {
    btn.disabled = true;
    call("POST", "/rollback", { app: data.appId, to: version }).then(function (r) { data.back = r; render(); },
                                                                       function (e) { btn.disabled = false; fail(e); });
  }
  function vBack() {
    var b = data.back, box = el("div", { "class": "hosting-step" });
    if (b.messages) {
      b.messages.forEach(function (m) { box.appendChild(el("p", {}, el("strong", { text: m.site + ": " }), m.message)); box.appendChild(copyRow(m.message)); });
      return box;
    }
    box.appendChild(p(b.words));
    box.appendChild(button(U.goBackBtn, function (ev) {
      ev.target.disabled = true;
      call("POST", "/rollback", { app: data.appId, to: b.to, go: true }).then(function (r) {
        // the republish's steps run on Publish, followed there; the messages wait there too (review MAJOR 3)
        data.back = null; data.backMessages = r.messages; openPublish(data.appId);
      }, function (e) { ev.target.disabled = false; fail(e); });
    }));
    box.appendChild(root.document.createTextNode(" "));
    box.appendChild(button(G.notNow, function () { data.back = null; render(); }, true));
    return box;
  }

  // J13-03: Cancel at month end, naming the sites still using the service before it asks
  function vCancel(app) {
    var d = el("details", {}, el("summary", { text: U.cancel }));
    var c = data.cancel && data.cancel.app === app ? data.cancel : null;
    d.addEventListener("toggle", function () {
      if (d.open && !c) call("POST", "/cancel", { app: app }).then(function (r) { data.cancel = r; render(); }, fail);
    });
    if (c) {
      d.open = true;
      d.appendChild(p(c.words));
      if (c.button) {
        d.appendChild(button(c.button, function (ev) {
          ev.target.disabled = true;
          call("POST", "/cancel", { app: app, go: true }).then(function (r) { data.cancel = { app: app, words: r.words }; render(); },
                                                             function (e) { ev.target.disabled = false; fail(e); });
        }));
        d.appendChild(root.document.createTextNode(" "));
        d.appendChild(button(c.keep, function () { data.cancel = null; render(); }, true));
      }
    }
    return d;
  }

  // J7-07: Make a key for a retailer's site (a paid listed app)
  function vKey(app) {
    var d = el("details", {}, el("summary", { text: U.makeKey })), site = el("input", { type: "text", spellcheck: "false" });
    d.appendChild(field(U.keySite, site));
    var out = el("div", {});
    d.appendChild(button(U.makeKey, function (ev) {
      ev.target.disabled = true;
      call("POST", "/key", { app: app, site: site.value.trim() }).then(function (r) {
        out.textContent = ""; out.appendChild(p(r.words)); out.appendChild(copyRow(r.words)); ev.target.disabled = false;
      }, function (e) { ev.target.disabled = false; fail(e); });
    }, true));
    d.appendChild(out);
    return d;
  }

  // J5-14: the giving owner's form, on the app's own page
  function vHandOver(app) {
    var box = el("details", {}, el("summary", { text: WORDS.handOver }));
    box.appendChild(p(WORDS.handOverWhy));
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
    var box = el("details", {}, el("summary", { text: WORDS.commandQ }));
    if (data.deviceCode) box.setAttribute("open", "");   // open only when the address brought a code
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
  // MYSITES: the company's sites, one list (Try's Change list reads it too)
  function vSites() {
    var box = card(S.title), sites = data.sites;
    box.appendChild(p(S.why));
    if (!sites) { box.appendChild(p("Reading your sites\u2026")); return box; }
    var done = function (r) { data.sites = r; data.where = null; data.whereAsked = null; if (r.words) say(r.words); render(); };
    if (data.shownLogins) {   // a sandbox's logins, kept nowhere but on this screen, until it is left
      var lg = card(data.shownLogins.site);
      lg.appendChild(p(data.shownLogins.logins_words || S.loginsNote));
      var t = el("table", {}, el("thead", {}, el("tr", {}, el("th", { text: "User" }), el("th", { text: "Till ID" }),
        el("th", { text: "Password" }), el("th", { text: "PIN" }))));
      var tb = el("tbody", {});
      (data.shownLogins.logins || []).forEach(function (x) {
        tb.appendChild(el("tr", {}, el("td", { text: x.user || "" }), el("td", { text: x.username || "" }),
          el("td", {}, el("code", { text: x.password || "" })), el("td", { text: x.pin || "" })));
      });
      t.appendChild(tb); lg.appendChild(t); box.appendChild(lg);
    }
    var offer = sandboxOffer(sites, function (ev) {
      ev.target.disabled = true;   // one press, one sandbox
      call("POST", "/sandbox/get", {}).then(function (r) { if (r.logins) data.shownLogins = r; done(r); },
                                         function (e) { ev.target.disabled = false; fail(e); });
    });
    if (sites.sandbox === "get") box.appendChild(offer);   // J6 F15: one of our developers sees it first, above the demo boxes
    (sites.company || []).forEach(function (x) {
      var row = el("div", { "class": "hosting-step" });
      row.appendChild(el("h3", { text: x.label ? x.label + " \u00b7 " + x.site : x.site }));
      row.appendChild(p(siteHow(x) + (x.site === sites["default"] ? " \u00b7 " + S.isDefault : "")));
      if (x.back_words) row.appendChild(p(x.back_words));   // a pool sandbox nobody signs in to goes back on this date
      var lab = el("input", { type: "text", maxlength: "60", spellcheck: "false", "aria-label": S.label + ": " + x.site });
      lab.value = x.own_label || "";
      var acts = el("p", {}, lab, " ", button(S.save, function (ev) {
        ev.target.disabled = true;
        call("POST", "/sites/label", { site: x.site, label: lab.value.trim() }).then(done, function (e) { ev.target.disabled = false; fail(e); });
      }, true));
      if (!x.live && x.site !== sites["default"]) acts.appendChild(el("span", {}, " ", button(S.makeDefault, function (ev) {
        ev.target.disabled = true;
        call("POST", "/sites/default", { site: x.site }).then(done, function (e) { ev.target.disabled = false; fail(e); });
      }, true)));
      if (!x.ours || x.route === "own") acts.appendChild(el("span", {}, " ", button(S.remove, function (ev) {
        ev.target.disabled = true;
        call("POST", "/sites/remove", { site: x.site, mine: true }).then(function (r) {   // walk W1: say what happened
          r.words = removedWords(x.site, r); done(r);
        }, function (e) { ev.target.disabled = false; fail(e); });
      }, true)));
      if (x.logins) acts.appendChild(el("span", {}, " ", button(S.logins, function (ev) {
        ev.target.disabled = true;
        call("POST", "/sandbox/logins", { site: x.site }).then(function (r) { data.shownLogins = r; done(r); },
                                                           function (e) { ev.target.disabled = false; fail(e); });
      })));
      row.appendChild(acts);
      box.appendChild(row);
    });
    if (!(sites.company || []).length && sites.words) {
      var parts = noSandboxParts(sites.words);
      box.appendChild(el("p", {}, parts[0], parts[1] ? el("a", { href: "/sandbox.html", text: parts[1] }) : null, parts[2] || null));
    }
    if (sites.sandbox !== "get") box.appendChild(offer);
    var add = card(S.add);
    var form = data.addForm = data.addForm || { site: "", key: "", secret: "", label: "" };   // kept through a refusal's redraw
    var addr = el("input", { type: "text", spellcheck: "false", autocomplete: "off", placeholder: "shop.ivendnext.com", "aria-label": S.address });
    var key = el("input", { type: "text", spellcheck: "false", autocomplete: "off", "aria-label": S.key });
    var sec = el("input", { type: "password", autocomplete: "off", "aria-label": S.secret });
    var lab = el("input", { type: "text", maxlength: "60", spellcheck: "false", placeholder: "Acme test", "aria-label": S.label });
    [[addr, "site"], [key, "key"], [sec, "secret"], [lab, "label"]].forEach(function (f) {
      f[0].value = form[f[1]];
      f[0].addEventListener("input", function () { form[f[1]] = f[0].value; });
    });
    add.appendChild(field(S.address, addr));
    add.appendChild(field(S.key, key));
    add.appendChild(field(S.secret, sec, S.keyHint));
    add.appendChild(field(S.label, lab, S.labelHint));   // a customer's live site is labelled live as it is added
    add.appendChild(button(S.addBtn, function (ev) {
      ev.target.disabled = true;
      var busy = el("span", { "class": "hint", text: key.value.trim() ? " " + S.checking.replace("{site}", addr.value.trim()) : "" });
      ev.target.parentNode.insertBefore(busy, ev.target.nextSibling);   // W227: a key's check takes ~8 s
      call("POST", "/sites/add", { site: addr.value.trim(), key: key.value.trim(), secret: sec.value.trim(), label: lab.value.trim() })
        .then(function (r) { data.addForm = null; done(r); }, function (e) { busy.remove(); ev.target.disabled = false; fail(e); });
    }));
    var out = el("div", {}, box, add);
    out.appendChild(button("Back to My apps", function () { data.shownLogins = null; data.addForm = null; go("home"); }, true));
    return out;
  }

  function vPeople() {
    var box = card(WORDS.people);
    box.appendChild(p(WORDS.peopleWhy));
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
    box.appendChild(p(WORDS.tokensWhy));
    var name = el("input", { type: "text", maxlength: "60", spellcheck: "false" });
    var which = el("select", {}, el("option", { value: "", text: allApps(who.name || who.company) }),
      el("option", { value: "one", text: "One app" }));
    var one = el("input", { type: "text", spellcheck: "false", placeholder: (who.word || "acme") + "_…", hidden: "" });
    which.addEventListener("change", function () { one.hidden = which.value !== "one"; });
    box.appendChild(field(WORDS.makeToken, name, "its name"));
    box.appendChild(field(WORDS.forWhich, which));
    box.appendChild(one);
    box.appendChild(button(WORDS.makeTokenBtn, function () {
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
            .then(function (r) { data.tokens = r.tokens; say("Revoked: " + x.name + " no longer works."); render(); }, fail);
        }, true))));
    });
    t.appendChild(body);
    if (body.children.length) box.appendChild(t);   // no empty table
    box.appendChild(button("Back to My apps", function () { data.shown = null; go("home"); }, true));
    return box;
  }

  function signOut() {
    call("POST", "/signout").then(function () {}, function () {}).then(function () { session = null; who = null; data = {}; go("home"); });
  }

  var shown = null;
  // W227 (Distribution's Logs link, Thrift's list): a redraw that lands while a press is under way replaces the button
  // under the pointer, so the press does nothing. It waits for the press to end (at most a second), then runs.
  var pressing = false, pending = false;
  function released() { if (!pressing) return; pressing = false; if (pending) { pending = false; root.setTimeout(render, 0); } }
  if (view && view.addEventListener) {
    view.addEventListener("pointerdown", function () { pressing = true; root.setTimeout(released, 1000); });
    root.document.addEventListener("pointerup", released, true);
    root.document.addEventListener("pointercancel", released, true);
  }

  function render() {
    if (pressing) { pending = true; return; }
    if (shown !== null && shown !== screen && view.getBoundingClientRect().top < 0) view.scrollIntoView();   // a new screen at its top
    shown = screen;
    view.textContent = "";
    view.hidden = false;
    var said = flash ? view.appendChild(el("p", { "class": flash.bad ? "hosting-bad" : "hosting-ok", text: flash.text })) : null;
    if (said && flash.bad && said.scrollIntoView && said.getBoundingClientRect().top < 0) said.scrollIntoView({ block: "nearest" });   // W227 F-HOSP-22
    var lede = view.previousElementSibling;   // "Sign in to…" says nothing once signed in
    if (lede && lede.tagName === "P") lede.hidden = !!session;
    if (!session) { view.appendChild(vSignIn()); return; }
    if (!who.company) { view.appendChild(screen === "company" ? vCompany() : vJoin()); return; }
    var v = { people: vPeople, tokens: vTokens, sites: vSites, gallery: g && vGallery, name: g && vName, made: data.made && data.made.words && vMade,
              fromsite: g && g.fromSite && vFromSite,
              settings: vSettings, app: vApp, "try": vTry, publish: vPublish, logs: vLogs }[screen];
    view.appendChild((v || vHome)());
  }

  // once signed in to a company: the ticks the address brought (a shortlist or a sample's page) open New app (J1-02, J1-14)
  function arrive() {
    var st = JSON.parse(root.sessionStorage.getItem(START) || "null");
    if (st && session && who && who.company) { root.sessionStorage.removeItem(START); startGallery("new", st); return true; }
    return false;
  }

  root.document.addEventListener("click", function (ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest("a[href]") : null;
    if (!a || !session || ev.defaultPrevented || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || a.target) return;
    if (!toThisPage(a.getAttribute("href"), root.location.href)) return;
    ev.preventDefault(); data.made = null; data.pick = null; go("home");   // J6f F5: My apps, still signed in
  });

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
    if (arrival.kind === "checkout") say(WORDS.backFromCheckout[arrival.left ? 1 : 0], arrival.left);
    if (arrival.kind !== "signin") { render(); return; }
    return call("POST", "/signin", { code: arrival.code, verifier: arrival.verifier, redirect_uri: PAGE }).then(function (r) {
      session = r.session; who = r; delete who.session;
      if (!arrive()) { render(); load(); }
    }, function () { say(WORDS.m22, true); render(); });
  }, function () { cfg = { ready: false }; render(); });
})(typeof globalThis !== "undefined" ? globalThis : this);
