// site/test_hosting.mjs — Host your app from the page (HOSTWEB): the script the site ships, run in node.
//
//     python3 site/build.py site/_out && node site/test_hosting.mjs site/_out
//
// A sign-in's return is taken only with the state this tab sent, once; GitHub's refusal and a foreign state are
// refused; the PKCE challenge is RFC 7636's; the order sends app.json's names and shapes, never a value; and the page
// carries its own content policy (only the hosting's address) and none of the site's other scripts.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { webcrypto } from "node:crypto";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, "_out"));
const h = require(path.join(out, "assets/hosting.js"));
const page = readFileSync(path.join(out, "hosting.html"), "utf8");

let red = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok || !detail ? "" : "\n  " + detail}`);
  if (!ok) red++;
};

// 1. the return from GitHub
const pending = { state: "s".repeat(43), verifier: "v".repeat(64) };
let r = h.readReturn(`?code=abc12345&state=${pending.state}`, pending);
check("a code with this tab's state is taken, with its verifier", r.kind === "signin" && r.code === "abc12345" && r.verifier === pending.verifier);
check("a code with another state is refused", h.readReturn("?code=abc12345&state=other", pending).kind === "refused");
check("a code when no sign-in was started (or it was used) is refused", h.readReturn(`?code=abc12345&state=${pending.state}`, null).kind === "refused");
check("GitHub's refusal is refused", h.readReturn("?error=access_denied&state=x", pending).kind === "refused");
check("Stripe's return names the order and claims no payment", h.readReturn("?order=0123456789abcdef", null).kind === "back");
check("leaving Stripe's checkout is told apart", h.readReturn("?order=0123456789abcdef&left=1", null).kind === "left");
check("a plain visit is nothing", h.readReturn("", null).kind === "none");

// 2. PKCE: RFC 7636 appendix B
const ch = await h.challengeOf("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk", webcrypto);
check("the S256 challenge is RFC 7636's example", ch === "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", ch);
const v = h.randomString(48, webcrypto);
check("a verifier is 64 URL-safe characters", /^[A-Za-z0-9_-]{64}$/.test(v), v);
const u = new URL(h.authorizeUrl("Iv1.x", "st", ch));
check("the sign-in goes to GitHub with the page as its return", u.origin === "https://github.com" &&
  u.searchParams.get("redirect_uri") === "https://developer.ivendnext.com/hosting" && u.searchParams.get("code_challenge_method") === "S256");

// 3. the order
const app = { app: "cxs-points", version: "1.0.0", size: "small", port: 8080, health: "/health",
              env: [{ name: "TOKEN", secret: true, required: true, value: "never" }, { name: "LOG_LEVEL", value: "debug" }] };
const p = h.orderPayload({ appJson: JSON.stringify(app), repo: "a/b", branch: "main", subject: "repo:a@1/b@2", plan: "starter",
                           copies: ["sandbox", "prod"], forCustomer: true, customer: "pp-demo", settings: { LOG_LEVEL: "info", X: "" },
                           invoice: false, email: "x@y.z", folder: "services/a", accepted: "2026-10-21" }, "order", "2026-10-21");
check("the order sends no value from app.json", !JSON.stringify(p.app).includes("never") && !JSON.stringify(p.app).includes("debug"));
check("copies go production first", JSON.stringify(p.copies) === '["prod","sandbox"]');
check("an empty setting is left out; a card order sends no e-mail", JSON.stringify(p.plain_env) === '{"LOG_LEVEL":"info"}' && p.email === "");
check("the order carries the folder it is built from", p.github.folder === "services/a");
check("no folder given, none sent (never \".\" over one set by hand)",
  !("folder" in h.orderPayload({ appJson: "{}", copies: [], folder: "." }, "order", "x").github));
check("a required plain setting left empty is named, a secret is not",
  JSON.stringify(h.missingRequired({ env: [{ name: "A", required: true }, { name: "B", required: true, secret: true }, { name: "C" }] }, { A: " " })) === '["A"]');
{
  const s0 = { repo: "acme/apps", subject: "", subjectSet: true };                       // the person emptied the box
  const found = { found: true, can_push: true, repo: "acme/apps", subject: "repo:acme@1/apps@2" };
  check("an emptied subject (the plain name) is never refilled", h.prefill(s0, "acme/apps", found).subject === "");
  check("an empty, untouched subject is filled in", h.prefill({ repo: "acme/apps" }, "acme/apps", found).subject === "repo:acme@1/apps@2");
  const moved = h.prefill({ repo: "acme/old", subject: "repo:acme@1/old@2", subjectSet: true }, "acme/old",
                          { found: true, can_push: true, repo: "acme/new", subject: "repo:acme@1/new@3" });
  check("a renamed repository takes GitHub's name and drops the old one's subject", moved.repo === "acme/new" && moved.subject === "repo:acme@1/new@3");
  check("GitHub's letter case wins", h.prefill({ repo: "Acme/Apps" }, "Acme/Apps", found).repo === "acme/apps");
  const stranger = h.prefill({ repo: "x/apps" }, "x/apps", { found: true, can_push: false, repo: "x/apps", subject: "repo:x@9/apps@8" });
  check("someone else's repository is not filled in", stranger.subject === undefined || stranger.subject === "");
  check("GitHub saying nothing about access is not read as cannot", h.prefill({ repo: "a/b" }, "a/b", { found: true, repo: "a/b", subject: "repo:a@1/b@2" }).subject === "repo:a@1/b@2");
  check("a late answer for another repository changes nothing", h.prefill({ repo: "a/c" }, "a/b", found).repo === "a/c");
  check("a subject names its repository in either form", h.subjectNames("repo:a@1/b@2", "A/B") && h.subjectNames("repo:a/b", "a/b") && !h.subjectNames("repo:a@1/c@2", "a/b"));
}
check("a schedule is read as the hosting reads it", h.scheduled({ schedule: { pass: "x" } }) && !h.scheduled({ schedule: {} }) && h.scheduled({ timeout: 0 }));
check("a scheduled app's schedule reaches the hosting, which refuses it",
  "schedule" in h.appSettings({ app: "a", schedule: { pass: "rate(1 minute)" } }) && "timeout" in h.appSettings({ app: "a", timeout: 120 }));
check("the order records the Schedule only when it was accepted, at that version",
  p.schedule_version === "2026-10-21"
  && h.orderPayload({ appJson: "{}", copies: [] }, "order", "2026-10-21").schedule_version === ""
  && h.orderPayload({ appJson: "{}", copies: [], accepted: "2026-10-01" }, "order", "2026-10-21").schedule_version === "");
check("the check sends no command", !("cmd" in h.orderPayload({ appJson: "{}", copies: [] }, "check", "x")));
check("a repository from the list signs in with its ids unless told otherwise",
  h.subjectFor({ subject: "repo:a@1/b@2" }, false) === "repo:a@1/b@2" && h.subjectFor({ subject: "repo:a@1/b@2" }, true) === "");
check("a removed copy is not said to be running", !/running/.test(h.copyWords({ status: "removed", live_version: "1.1.2" })));
check("an order is settled once every copy is live, or it ended",
  h.settled({ copies: [{ status: "live" }, { status: "live" }] }) && !h.settled({ copies: [{ status: "live" }, { status: "waiting" }] })
  && h.settled({ copies: [{ status: "failed" }] }));
check("the customer field offers the customers earlier orders named, once each",
  JSON.stringify(h.customersFrom([{ customer: "b-shop" }, { customer: "" }, {}, { customer: "a-stores" }, { customer: "b-shop" }])) === '["a-stores","b-shop"]'
  && h.customersFrom(null).length === 0);

// 4. the page
const policies = page.match(/<meta http-equiv="Content-Security-Policy" content="([^"]*)">/g) || [];
check("one content policy on the page", policies.length === 1, String(policies.length));
check("it reaches only the hosting", /connect-src https:\/\/hosting\.ivendnext\.app;/.test(policies[0] || ""), policies[0]);
check("no inline script is allowed", !/unsafe-inline[^;]*/.test((policies[0] || "").split("script-src")[1].split(";")[0]));
check("no other script on the page (the search data block runs nothing)", (page.match(/<script(?! type="application\/ld\+json")[^>]*>/g) || []).length === 1 && page.includes("assets/hosting.js"));
check("no referrer leaves the page", page.includes('<meta name="referrer" content="no-referrer">'));
check("the Publish button stays on the page", page.includes('href="https://library.ivendnext.app/publish"'));
check("the button shown after live goes to the same page", page.includes('data-publish="https://library.ivendnext.app/publish"'));
check("no inline style is allowed either", !/'unsafe-inline'/.test(policies[0] || ""));

console.log(red ? `${red} FAILED` : "ALL PASS");
process.exit(red ? 1 : 0);
