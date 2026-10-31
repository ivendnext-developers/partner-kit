// site/test_hosting.mjs — Host your app from the page (HOSTWEB): the script the site ships, run in node.
//
//     python3 site/build.py site/_out && node site/test_hosting.mjs site/_out
//
// A sign-in's return is taken only with the state this tab sent, once; GitHub's refusal and a foreign state are
// refused; the PKCE challenge is RFC 7636's; the order sends app.json's names and shapes, never a value, and no GitHub
// repository; an upload's version is read from the zip's own app.json; and the page carries its own content policy (only
// the hosting's address and its upload store) and none of the site's other scripts.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { webcrypto } from "node:crypto";
import { deflateRawSync } from "node:zlib";

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
check("the order names no GitHub repository, branch, subject or folder (EASY2: the hosting builds what you upload)",
  !("github" in p) && !JSON.stringify(p).includes("a/b") && !JSON.stringify(p).includes("services/a"));
check("a required plain setting left empty is named, a secret is not",
  JSON.stringify(h.missingRequired({ env: [{ name: "A", required: true }, { name: "B", required: true, secret: true }, { name: "C" }] }, { A: " " })) === '["A"]');
check("a schedule is read as the hosting reads it", h.scheduled({ schedule: { pass: "x" } }) && !h.scheduled({ schedule: {} }) && h.scheduled({ timeout: 0 }));
check("a scheduled app's schedule reaches the hosting, which refuses it",
  "schedule" in h.appSettings({ app: "a", schedule: { pass: "rate(1 minute)" } }) && "timeout" in h.appSettings({ app: "a", timeout: 120 }));
check("a secret's box says whether it has a value, and nothing before the hosting says",
  h.secretState({ secrets_set: ["A"] }, "A").startsWith("Has a value") && h.secretState({ secrets_set: ["A"] }, "B") === "No value yet."
  && h.secretState({}, "A") === "");
check("the scratch flag reaches the hosting", h.appSettings({ app: "a", scratch: true }).scratch === true);
check("the order records the Schedule only when it was accepted, at that version",
  p.schedule_version === "2026-10-21"
  && h.orderPayload({ appJson: "{}", copies: [] }, "order", "2026-10-21").schedule_version === ""
  && h.orderPayload({ appJson: "{}", copies: [], accepted: "2026-10-01" }, "order", "2026-10-21").schedule_version === "");
check("the check sends no command", !("cmd" in h.orderPayload({ appJson: "{}", copies: [] }, "check", "x")));
check("the page no longer looks up repositories or sets Variables",
  !("subjectFor" in h) && !("prefill" in h) && !readFileSync(path.join(out, "assets/hosting.js"), "utf8").includes("/variables"));
check("a removed copy is not said to be running", !/running/.test(h.copyWords({ status: "removed", live_version: "1.1.2" })));
check("an order is settled once every copy is live, or it ended",
  h.settled({ copies: [{ status: "live" }, { status: "live" }] }) && !h.settled({ copies: [{ status: "live" }, { status: "waiting" }] })
  && h.settled({ copies: [{ status: "failed" }] }));
check("an order with a build running is not settled: the page keeps following it",
  !h.settled({ copies: [{ status: "live" }], build: { state: "building" } }) && h.settled({ copies: [{ status: "live" }], build: { state: "built" } }));
check("a version just uploaded is followed until the hosting says how its build ended",
  !h.settled({ copies: [{ status: "live" }], build: { version: "1.0.1", state: "built" } }, "1.0.2")
  && h.settled({ copies: [{ status: "live" }], build: { version: "1.0.2", state: "failed" } }, "1.0.2")
  && !h.settled({ copies: [{ status: "live" }] }, "1.0.2"));
check("a failed build shows the hosting's words, then its last lines",
  JSON.stringify(h.buildLines({ build: { words: "1.0.2 did not build.", lines: ["a", "b"] } })) === '["1.0.2 did not build.","a","b"]'
  && h.buildLines({}).length === 0);

// 3b. an upload's zip: the version is the one its own app.json holds
function zipOf(files, deflate) {   // a minimal zip writer: local headers, then the central directory
  const enc = new TextEncoder(), parts = [], central = [];
  let at = 0;
  for (const [name, text] of Object.entries(files)) {
    const n = enc.encode(name), raw = enc.encode(text), data = deflate ? new Uint8Array(deflateRawSync(raw)) : raw;
    const loc = new Uint8Array(30 + n.length), lv = new DataView(loc.buffer);
    lv.setUint32(0, 0x04034b50, true); lv.setUint16(8, deflate ? 8 : 0, true); lv.setUint32(18, data.length, true);
    lv.setUint32(22, raw.length, true); lv.setUint16(26, n.length, true); loc.set(n, 30);
    const cen = new Uint8Array(46 + n.length), cv = new DataView(cen.buffer);
    cv.setUint32(0, 0x02014b50, true); cv.setUint16(10, deflate ? 8 : 0, true); cv.setUint32(20, data.length, true);
    cv.setUint32(24, raw.length, true); cv.setUint16(28, n.length, true); cv.setUint32(42, at, true); cen.set(n, 46);
    parts.push(loc, data); central.push(cen); at += loc.length + data.length;
  }
  const size = central.reduce((a, c) => a + c.length, 0), end = new Uint8Array(22), ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, central.length, true); ev.setUint16(10, central.length, true);
  ev.setUint32(12, size, true); ev.setUint32(16, at, true);
  const all = new Uint8Array(at + size + 22);
  let o = 0;
  for (const x of [...parts, ...central, end]) { all.set(x, o); o += x.length; }
  return all;
}
const appJson = JSON.stringify({ app: "acme-points", version: "1.0.2" });
check("the version is read from a deflated zip's app.json", (await h.zipAppJson(zipOf({ "app.json": appJson, "Dockerfile": "FROM x" }, true))).version === "1.0.2");
check("and from a stored one made of the folder itself", (await h.zipAppJson(zipOf({ "acme_rules/app.json": appJson }, false))).version === "1.0.2");
{
  const big = zipOf({ "app.json": appJson, "big.bin": "x".repeat(300000) }, false), asked = [];
  const reader = { size: big.length, read: (a, b) => { asked.push(b - a); return Promise.resolve(big.subarray(a, b)); } };
  const m = await h.zipAppJson(reader);
  check("only the zip's end and its app.json are read, never the whole file",
    m.version === "1.0.2" && asked.length === 3 && asked.every((n) => n < big.length), JSON.stringify(asked));
}
const refused = async (bytes) => { try { await h.zipAppJson(bytes); return ""; } catch (e) { return e.message; } };
check("a zip with no app.json at its top is refused in words", /no app\.json at its top/.test(await refused(zipOf({ "a/b/app.json": appJson }, true))));
check("a file that is not a zip is refused in words", /not a zip/.test(await refused(new TextEncoder().encode("hello"))));
check("an app.json with no version is refused", /no version/.test(await refused(zipOf({ "app.json": "{}" }, true))));
check("the customer field offers the customers earlier orders named, once each",
  JSON.stringify(h.customersFrom([{ customer: "b-shop" }, { customer: "" }, {}, { customer: "a-stores" }, { customer: "b-shop" }])) === '["a-stores","b-shop"]'
  && h.customersFrom(null).length === 0);

// 4. the page
const policies = page.match(/<meta http-equiv="Content-Security-Policy" content="([^"]*)">/g) || [];
check("one content policy on the page", policies.length === 1, String(policies.length));
check("it reaches only the hosting and its upload store",
  /connect-src https:\/\/hosting\.ivendnext\.app https:\/\/ivn-selfserve-work-416648266684\.s3\.us-east-1\.amazonaws\.com;/.test(policies[0] || ""), policies[0]);
check("the page's upload store is the one its policy allows", (policies[0] || "").includes(h.STORE.replace(/\/$/, "") + ";"));
check("no inline script is allowed", !/unsafe-inline[^;]*/.test((policies[0] || "").split("script-src")[1].split(";")[0]));
check("no other script on the page (the search data block runs nothing)", (page.match(/<script(?! type="application\/ld\+json")[^>]*>/g) || []).length === 1 && page.includes("assets/hosting.js"));
check("no referrer leaves the page", page.includes('<meta name="referrer" content="no-referrer">'));
check("the Publish button stays on the page", page.includes('href="https://library.ivendnext.app/publish"'));
check("the button shown after live goes to the same page", page.includes('data-publish="https://library.ivendnext.app/publish"'));
check("no inline style is allowed either", !/'unsafe-inline'/.test(policies[0] || ""));

console.log(red ? `${red} FAILED` : "ALL PASS");
process.exit(red ? 1 : 0);
