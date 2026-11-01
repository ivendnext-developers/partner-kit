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
check("the page's own content policy reaches only the hosting", csp.includes("connect-src https://hosting.ivendnext.app") && !csp.includes("'unsafe"));
check("its one script, none of the site's others", page.includes("assets/apps.js") && !page.includes("assets/search.js") && !page.includes("assets/analytics.js"));
check("without script the page says what it is", page.includes("Sign in to make, try and publish your apps."));

console.log(red ? `${red} FAILED` : "ALL PASS");
process.exit(red ? 1 : 0);
