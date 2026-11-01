// site/test_apps.mjs — My apps' first screens (EASY1): the script the site ships, run in node.
//
//     python3 site/build.py site/_out && node site/test_apps.mjs site/_out
//
// The screens' words are the experience spec's rows (J2-01 to J2-04, J2-13, J5-14), word for word; a GitHub return is
// taken only with this tab's state, once, and GitHub's refusal reads M22; a code the command printed is told apart from
// GitHub's; the first word is suggested by the hosting's own rule; and the page carries the hosting page's own content
// policy (only the hosting's door) and none of the site's other scripts.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, "_out"));
const a = require(path.join(out, "assets/apps.js"));
const page = readFileSync(path.join(out, "apps.html"), "utf8");

let red = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok || !detail ? "" : "\n  " + detail}`);
  if (!ok) red++;
};

// 1. the words, as the rows write them
const W = a.WORDS;
check("J2-01: the lede, the button and the line under it", W.lede === "Sign in to make, try and publish your apps." &&
  W.signin === "Sign in with GitHub" && W.noGitHub.join("") === "No GitHub account? Make a free one in two minutes with any e-mail, then come back.");
check("J8-22 (M22)", W.m22 === "GitHub did not sign you in. Try again.");
check("J2-02: the labels, the hint and the schedule line", W.company === "Your company" && W.companyName === "Company name" &&
  W.firstWord === "Your first word" && a.wordHint("acme") === "Every app you make starts with it: acme_…. It is yours once you press Continue." &&
  a.scheduleLine("3") === "I accept the App Hosting Schedule (version 3)" && W.cont === "Continue");
check("J2-03: the button (its words come from the hosting's door, with the person's login)", W.setUp === "Set up my company");
check("J2-04", W.addPerson === "Add a person" && W.makeOwner === "Make owner" && W.remove === "Remove");
check("J2-13", W.makeToken === "Make a token for a build server" && W.forWhich === "For which apps" &&
  a.allApps("Acme") === "All of Acme's apps" && W.revoke === "Revoke" && W.copy === "Copy");
check("J5-14", W.handOver === "Hand over this app" && W.toWhich === "To which company? It must have signed in to My apps once." &&
  W.moves === "They accept on their My apps. The app keeps its name; its versions, sites, secrets and hosting move to them, and their card pays from the next month." &&
  W.accept === "Accept" && W.refuse === "Refuse" && a.appTitle("acme_member_till") === "ACME MEMBER TILL");

// 2. the return from GitHub, and a code from the terminal
const pending = { state: "s".repeat(43), verifier: "v".repeat(64) };
let r = a.readReturn(`?code=abc12345&state=${pending.state}`, pending);
check("a code with this tab's state is taken, with its verifier", r.kind === "signin" && r.verifier === pending.verifier);
check("a code with another state is refused in M22's words", a.readReturn("?code=abc12345&state=x", pending).why === W.m22);
check("GitHub's refusal reads M22", a.readReturn("?error=access_denied&state=x", pending).why === W.m22);
r = a.readReturn("?code=bcdf-ghjk", null);
check("a code the command printed is the command's, not GitHub's", r.kind === "device" && r.code === "BCDF-GHJK");
check("a plain visit is nothing", a.readReturn("", null).kind === "none");
check("the sign-in returns to My apps", new URL(a.authorizeUrl("Iv1.x", "st", "ch")).searchParams.get("redirect_uri") === "https://developer.ivendnext.com/apps");

// 3. J2-02: the word the name suggests (web.code_from's rule)
check("derived from the name's first word", a.suggestWord("Acme Retail Solutions") === "acme");
check("letters and digits only, at most 12", a.suggestWord("Über-Store 9 Ltd") === "berstore" && a.suggestWord("abcdefghijklmnop x") === "abcdefghijkl");
check("nothing when it cannot start with a letter", a.suggestWord("9to5 Stores") === "");

// 4. the page: its own policy, its one script
const csp = (page.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/) || [])[1] || "";
check("the page's own content policy reaches only this site and the hosting", csp.includes("connect-src 'self' https://hosting.ivendnext.app") && !csp.includes("'unsafe"));
check("its one script, none of the site's others", page.includes("assets/apps.js") && !page.includes("assets/search.js") && !page.includes("assets/analytics.js"));
check("without script the page says what it is", page.includes("Sign in to make, try and publish your apps."));
// J5-14: after Accept the app is yours, with its hosting's checkout; going home must not clear it (walk, 2026-11-01)
check("Accept says the app is yours, with its hosting's checkout",
  a.acceptedWords("acme_member_till", { hosting: { orders: [{ checkout_url: "https://checkout.stripe.com/c/pay/x" }] } }) ===
    "ACME MEMBER TILL is yours. Give your card for its hosting from the next month: https://checkout.stripe.com/c/pay/x" &&
  a.acceptedWords("acme_member_till", { hosting: { orders: [] } }) === "ACME MEMBER TILL is yours.");
const src = readFileSync(path.join(out, "assets/apps.js"), "utf8");
check("Accept's words are said after going home, which clears the last message",
  /go\("home"\);[^\n]*\n\s*say\(acceptedWords\(o\.app, r\)\);\s*\n\s*render\(\);/.test(src));


// ── EASY3a: the list, New app's gallery, Name, Made, Settings, the app's page ──
const G = a.G;
const index = JSON.parse(readFileSync(path.join(out, "samples/index.json"), "utf8"));
const catalogue = JSON.parse(readFileSync(path.join(out, "catalogue.json"), "utf8"));
const plan = require(path.join(out, "assets/plan.js"));
const by = Object.fromEntries(index.samples.map((s) => [s.name, s]));

check("J2-05: the empty list and New app", G.noApps === "You have no apps yet." && G.newApp === "New app");
check("J1-03: the search's label and the three tabs", G.search === "Search by sample (S23, till guard) or by what your customer asked" &&
  JSON.stringify(G.tabs.map((t) => t[1])) === JSON.stringify(["By industry", "By what it does", "By recipe"]));
check("J1-05: the App library's twelve industries", a.INDUSTRIES.length === 12 && a.INDUSTRIES.includes("Distribution and warehousing"));
check("J1-06: the doors' plain words, as the row's examples", a.doorWords("Check before payment") === "A check when the cashier presses Pay" &&
  a.doorWords("Till key") === "A key the cashier taps" && a.doorWords("Manifest") === "Your own lists and forms in Desk" &&
  a.doorWords("Desk action") === "A button in Desk" && a.doorWords("Event feed") === "Something that happens after each sale");
const doors = [...new Set(index.samples.filter((s) => !s.config_pack && s.door).map((s) => s.door))];
check("J1-06: every door a sample has is said in plain words (D14)", doors.every((d) => a.DOOR_WORDS[d]), doors.filter((d) => !a.DOOR_WORDS[d]).join(", "));

let f = a.search(index, catalogue, "S23");
check("J1-13: S23 is first, once", f.samples[0].name === "s23_till_guard" && f.samples.filter((s) => s.name === "s23_till_guard").length === 1);
f = a.search(index, catalogue, "till guard");
check("J1-13: till guard finds S23 first", f.samples[0] && f.samples[0].name === "s23_till_guard");
f = a.search(index, catalogue, "no more than 50 of one item");
check("J1-04: a need in the customer's words finds its sample, with the need it serves", f.samples.length > 0 &&
  Object.values(f.forNeeds).flat().some((n) => /50/.test(n)), JSON.stringify(f.samples.map((s) => s.name)));
check("J1-04: each sample once", f.samples.length === new Set(f.samples.map((s) => s.name)).size);
f = a.search(index, catalogue, "zzqx flibbertigibbet");
check("J1-03: no match says so, with Ask for it", f.none && G.none + G.ask === "No sample or need matches these words. Try other words, or ask for it: Ask for it");
f = a.search(index, catalogue, "");
check("J1-08: with no words every sample is a card, the configuration packs apart, never ticked",
  f.samples.length === index.samples.filter((s) => !s.config_pack).length && f.packs.every((s) => s.config_pack) && f.packs.length >= 2);
const desk = catalogue.find((c) => c.door === "configure");
f = a.search(index, catalogue, desk.asks);
check("J1-08 (D2): a Configure need is listed under Set in Desk first, never a card", f.desk.some((c) => c.id === desk.id) && G.desk === "Set in Desk first: no app needed");
const nope = catalogue.find((c) => c.status === "not-yet");
f = a.search(index, catalogue, nope.asks);
check("J1-09 (D3): a need not yet possible is under Cannot be built today", f.cannot.some((c) => c.id === nope.id) && G.cannot === "Cannot be built today: ");
check("J1-09: Claim a need's words", G.claim === "Claim a need: we hold back from it for 90 days while you build it.");
check("J1-12: Ask for it opens the request form, its title the need's words", a.askUrl(nope).startsWith(a.POINT_FORM + "&title=") &&
  decodeURIComponent(a.askUrl(nope)).endsWith(nope.asks));
const formed = catalogue.find((c) => (c.request_forms || []).length);
check("J1-12: a need whose card names its form opens that form", a.askUrl(formed) === formed.request_forms[0].url);
check("J1-11: the shortlist and the gallery label a need the same way, every card",
  catalogue.every((c) => plan.needKind(c) === a.needKind(c)) && JSON.stringify(plan.KIND_WORDS) === JSON.stringify(a.KIND_WORDS) &&
  JSON.stringify(Object.values(a.KIND_WORDS)) === JSON.stringify(["Built as an app", "Set in Desk", "Cannot be built today"]));
check("J1-02: the shortlist's button and the line beside it", plan.START === "Start an app from these needs" &&
  plan.START_HINT === "Opens New app on My apps with these samples ticked. Needs set in Desk are listed, not added." &&
  plan.startHref([{ id: "a-b" }, { id: "c" }]) === "apps.html?needs=a-b,c");
check("J1-09 on the shortlist: the line, as the row", plan.cannotLine(nope) === "Cannot be built today: " + nope.asks + ". " + plan.instead(nope));

const built = catalogue.find((c) => a.needKind(c) === "app" && a.needSamples(c).some((n) => by[n] && !by[n].config_pack));
const fn = a.fromNeeds(index, catalogue, [built.id, desk.id, nope.id, "no-such-need"]);
check("J1-02: the shortlist's needs tick their samples, list the Desk one, keep the one that cannot be built apart",
  fn.ticks.length > 0 && fn.desk[0].id === desk.id && fn.cannot[0].id === nope.id && fn.built[0].id === built.id);
check("J1-02, J1-14: what the address brought", JSON.stringify(a.readStart("?needs=a-b,cc")) === JSON.stringify({ needs: ["a-b", "cc"], sample: "" }) &&
  a.readStart("?sample=s23_till_guard").sample === "s23_till_guard" && a.readStart("?sample=../x") === null && a.readStart("") === null);
check("J2-05: the bar's words", a.barText([by.s23_till_guard, by.s22_customer_loyalty]) ===
  "2 samples ticked: S23 Till guard rules, S22 Customer-owned loyalty." && a.barText([]) === "Tick one or several samples.");
check("J2-06: the name and its line", G.name === "Name your app" && G.appName === "App name" && G.make === "Make the app" &&
  a.nameHint("ACME MEMBER TILL", "acme") === "acme_member_till: your first word, then your words. Installed names never change, so choose with care.");
check("J2-07: Making, and the next step", a.making("ACME MEMBER TILL", 2) === "Making ACME MEMBER TILL from 2 samples…" && G.nextSettings === "Next: its settings");
check("J2-09: the settings' words", G.settingsLede === "Your app's own values, the same for every site. A customer's own account (their wallet) goes in the app's settings in their Desk. Connection secrets come from each site: you never type them." &&
  G.addresses === "Outside addresses" && G.secrets === "Secrets your own service needs" &&
  a.settingNote({ required: true, together: ["X"] }) === "Required: publishing waits until it is set. Set both, or neither" &&
  a.settingNote({ required: false, together: [] }) === "Optional: the feature behind it stays off until you set it" &&
  a.isAddress({ name: "HKD_WALLET_URL" }) && !a.isAddress({ name: "HKD_WALLET_SECRET", purpose: "the key your wallet provider gave you" }));
check("J2-10: the app's four buttons and Not yet on any site", G.tryIt === "Try on my sandbox" && G.publish === "Publish" &&
  G.download === "Download the app folder" && G.addSample === "Add a sample" && G.notOnSite === "Not yet on any site");
check("J3-06: Upload's words", G.upload === "Upload a new version" && G.uploadHint === "Choose the app folder's zip. We check it before we keep it.");
check("J11-02: a version names what, who and how", a.versionLine({ version: "1.1.0", what: "S11 added", by: "Priya", how: "page", sites: [] }) ===
  "1.1.0 (draft) · S11 added · Priya · on the page" &&
  a.versionLine({ version: "1.0.1", what: "upload", by: "dev", how: "ivn", sites: [] }) === "1.0.1 (draft) · upload · dev · ivn push");
check("D14: every draft says it is on no site yet", /no site yet/.test(a.whereWent({ sites: [] })));
check("J6-08: Take it and Not now", G.take === "Take it" && G.notNow === "Not now");
const cv = a.covers({ app: "acme_x", needs: { built: [built.id], desk: [desk.id], cannot: [nope.id], asked: [nope.id] } }, catalogue);
check("J6-12: What it covers, from the needs the app was started from", cv.built[0].id === built.id && cv.desk[0].id === desk.id &&
  a.coversText({ app: "acme_x" }, cv, "2026-11-01").includes("Cannot be built today: " + nope.asks + " (asked 2026-11-01)"));
check("the samples index names each sample by its own title, and each recipe", by.s23_till_guard.short === "Till guard rules" &&
  index.samples.filter((s) => s.recipe).every((s) => s.recipe_title && !/the recipe$/.test(s.recipe_title)));

// the review's folds: the shortlist search runs; the gallery's search keeps its id; a buildable need with no sample shows
const planSrc = readFileSync(path.join(out, "assets/plan.js"), "utf8");
check("the shortlist's search appends its own label element, never the label() function",
  /lab\.htmlFor = box\.id;[\s\S]{0,120}li\.appendChild\(lab\);/.test(planSrc) && !/li\.appendChild\(label\)/.test(planSrc));
check("the gallery's search box has one id, so it keeps its focus", src.includes('q.id = "g-q"') && src.includes('getElementById("g-q")'));
const nos = catalogue.filter((c) => a.needKind(c) === "app" && !a.needSamples(c).some((n) => by[n] && !by[n].config_pack));
check("a need built as an app with no sample is found by its own words, never 'no match'",
  nos.length > 0 && nos.every((c) => { const r = a.search(index, catalogue, c.asks); return !r.none && r.nosample.some((x) => x.id === c.id); }),
  nos.filter((c) => a.search(index, catalogue, c.asks).none).map((c) => c.id).join(", "));
const D14 = /event feed|\bcontainer\b|byte for byte|extension point|internal coupon|signature accepted|CHECK GREEN|\bmanifest\b/i;
check("D14: no inside word in a card's When to use it, or in a need's what to do instead",
  index.samples.every((s) => !D14.test(s.when_to_use || "")) && catalogue.filter((c) => a.needKind(c) === "cannot").every((c) => !D14.test(a.instead(c))));
check("the samples' short titles start with a capital", index.samples.every((s) => /^[A-Z0-9"]/.test(s.short)));
check("By recipe: every recipe a sample's needs cite", index.samples.every((s) => Array.isArray(s.recipes) && (!s.recipe || s.recipes[0].path === s.recipe)));
check("EASY1NOTES: purposes, the folded command code, a way back", W.peopleWhy && W.tokensWhy && W.handOverWhy && W.commandQ === "Signing in a command?" &&
  !src.includes('{ open: data.deviceCode ? "" : null }'));

// the walk's folds (2026-11-01)
check("J2-06: the first word alone reads as the name will start", a.nameHint("CXSINT ", "cxsint").startsWith("cxsint_\u2026: your first word"));
check("a plain button carries the site's plain style", src.includes('"site-btn site-btn-ghost"') && !src.includes('"site-btn ghost"'));
// EASY3a part 3: Try on my sandbox (J4-01, J4-02, J4-05, §3b); the doors' own words are the hosting's tests
const T = a.T;
check("J4-01: the panel's labels and the Desk clicks", T.address === "Your sandbox's address" &&
  T.keyLabel === "An administrator's key and secret" && T.check === "Check" &&
  T.keyHint === "In your sandbox's Desk: your name (top right) > My Settings > API Access > Generate Keys. The secret is shown once: paste it here.");
const parts = a.noSandboxParts("No sandbox yet? Request one. Everything else here works without it.");
check("J4-01: with no sandbox, Request one is the link", parts.join("") === "No sandbox yet? Request one. Everything else here works without it." &&
  parts[1] === "Request one");
check("J4-02: the sections as the hosting drew them, in order, each with its lines", a.SECTIONS.join("|") ===
  "New in Desk|Who can use it|Changes to what you already have|Print layouts|Connects outside your site" &&
  a.consentSections({ sections: [{ title: "Who can use it", lines: [] }, { title: "New in Desk", lines: ["x"] }, { title: "Other", lines: ["y"] }] })
    .map((x) => x.title).join() === "New in Desk,Other" &&
  T.changes === "What installing it changes" && T.wording === "Show the exact wording" && T.installTry === "Install and try");
check("J4-05: Test again; a try is asked again until done or stopped", T.testAgain === "Test again" &&
  a.tryRunning({ step: "build" }) && !a.tryRunning({ step: "done" }) && !a.tryRunning({ step: "stopped" }) && !a.tryRunning({}));
check("J4-05 after a fix: a newer draft than the one tried is offered again; a finished try of the latest is not",
  a.offerAgain({ step: "done", version: "1.0.0", latest: "1.0.1" }) && !a.offerAgain({ step: "done", version: "1.0.1", latest: "1.0.1" }) &&
  a.offerAgain({ step: "stopped" }) && a.offerAgain(null) && !a.offerAgain({ step: "build" }));
check("J5-15: the plan's lines as the row writes them, nothing added", !src.includes("perMonth") && T.plan === "Per month");
check("J2-10: Try on my sandbox is on; Publish waits for part 4", src.includes('button(G.tryIt, function () { openTry(a.app); })') &&
  src.includes("pubB.disabled = true"));

check("J4-01: what was typed stays through a refusal, and is forgotten once connected (walk 2026-11-01)",
  src.includes("data.sbTyped || (data.sbTyped =") && src.includes("data.sbTyped = null"));
check("J4-03: the consent goes once Install and try starts (walk 2026-11-01)", src.includes("data.tryS = r; data.tryC = null;"));
console.log(red ? `${red} FAILED` : "ALL PASS");
process.exit(red ? 1 : 0);
