// site/test_plan.mjs — Plan a project's shortlist, run in node against the BUILT catalogue and the script the site ships.
//
//     python3 site/build.py site/_out && node site/test_plan.mjs site/_out
//
// Three planted shortlists give the expected build order and each recipe once; the blueprint copy equals what
// `needs.py blueprint` prints for the same ids in the same order; an unknown id in the address is set aside, never an
// error; every limit of the distributor's eleven needs and of seven older ones is in the copy; and 40 needs are worked
// out in well under a second. The page itself (the message, the copy, the print) is checked in a browser.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, "_out"));
const plan = require(path.join(out, "assets/plan.js"));
const catalogue = JSON.parse(readFileSync(path.join(out, "catalogue.json"), "utf8"));
const page = readFileSync(path.join(out, "plan.html"), "utf8");
const unescape = (s) => s.replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const head = unescape(page.match(/data-head="([^"]*)"/)[1]);

let red = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok || !detail ? "" : "\n  " + detail}`);
  if (!ok) red++;
};
const pick = (list) => {
  const got = plan.choose(catalogue, list);
  if (got.unknown.length) throw new Error("not a card: " + got.unknown.join(", "));
  return got.cards;
};
const idsOf = (cards) => cards.map((c) => c.id);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// 1. configure only: one step, in the order chosen; the shared recipe once, serving both needs that cite it
{
  const cards = pick(["reason-codes", "document-numbering", "imei-per-phone-sold"]);
  const steps = plan.steps(cards);
  check("configure only: one step, in the order chosen", steps.length === 1 && same(idsOf(steps[0].cards), ["reason-codes", "document-numbering", "imei-per-phone-sold"]),
        JSON.stringify(steps.map((s) => [s.step, idsOf(s.cards)])));
  const r = plan.proofs(cards).recipes;
  check("configure only: configure_no_code once, for both needs that cite it",
        r.length === 1 && r[0].path === "recipes/configure_no_code.md" && same(idsOf(r[0].needs), ["reason-codes", "imei-per-phone-sold"]),
        JSON.stringify(r.map((p) => [p.path, idsOf(p.needs)])));
}

// 2. a mixed set chosen back to front: configure, then the manifest, then the outside apps, then the till key
{
  const cards = pick(["warranty-check-at-till", "own-crm", "own-online-shop", "own-records-in-desk", "member-price-by-tier"]);
  const want = ["member-price-by-tier", "own-records-in-desk", "own-crm", "own-online-shop", "warranty-check-at-till"];
  check("mixed: built in the ladder's order, the manifest straight after configuration", same(idsOf(plan.order(cards)), want),
        idsOf(plan.order(cards)).join(", "));
  const r = plan.proofs(cards).recipes;
  const shared = r.filter((p) => p.path === "recipes/connected_app.md");
  check("mixed: the shared recipe listed once, with both needs", shared.length === 1 && same(idsOf(shared[0].needs), ["own-crm", "own-online-shop"]),
        JSON.stringify(r.map((p) => [p.path, idsOf(p.needs)])));
  check("mixed: no recipe listed twice", new Set(r.map((p) => p.path)).size === r.length);
  check("mixed: every step says why", plan.steps(cards).every((s) => s.why.length > 20));
}

// 3. a set with a Not yet card and a Not possible one: they come last; the request is filed once, the Instead line kept
{
  const cards = pick(["question-on-quantity-change", "fee-or-surcharge", "line-quantity-cap"]);
  check("not yet: the ready need first, then the request, then the not possible one",
        same(idsOf(plan.order(cards)), ["line-quantity-cap", "question-on-quantity-change", "fee-or-surcharge"]), idsOf(plan.order(cards)).join(", "));
  const rq = plan.requests(cards);
  check("not yet: one request to file, P-CAPTURE3, with its form",
        rq.forms.length === 1 && rq.forms[0].handle === "P-CAPTURE3" && rq.forms[0].url.includes("template=2_point_request.yml"), JSON.stringify(rq.forms));
  check("not possible: its Instead line is in the requests", rq.instead.length === 1 && rq.instead[0].line.startsWith("Instead:"));
}

// two needs that wait on the same extension point: one request to file, naming both
{
  const [one] = pick(["question-on-quantity-change"]);
  const rq = plan.requests([one, { ...one, id: "a-second-need-on-the-same-request" }]);
  check("one handle for two needs: filed once, for both", rq.forms.length === 1 && rq.forms[0].needs.length === 2, JSON.stringify(rq.forms.map((f) => f.handle)));
}

// one sample written two ways is one sample
{
  const [a, b] = pick(["reason-codes", "imei-per-phone-sold"]).map((c) => ({ ...c, samples: c.samples.map((p) => ({ ...p })) }));
  b.samples = [{ ...a.samples[0], path: a.samples[0].path + "/" }];
  check("a trailing slash: the same sample listed once", plan.proofs([a, b]).samples.length === 1, JSON.stringify(plan.proofs([a, b]).samples.map((p) => p.path)));
}

// the address: duplicates dropped, an unknown id set aside
{
  const got = plan.choose(catalogue, plan.ids("?needs=line-quantity-cap,no-such-card,line-quantity-cap,%20reason-codes"));
  check("the address: an unknown id is set aside, a repeat counted once", same(idsOf(got.cards), ["line-quantity-cap", "reason-codes"]) && same(got.unknown, ["no-such-card"]),
        JSON.stringify([idsOf(got.cards), got.unknown]));
  check("the address: no needs is an empty shortlist, not an error", plan.ids("").length === 0 && plan.ids("?needs=").length === 0);
}

// the walk's two sets: no error, every limit in the limits copy and in the blueprint, the copy equal to needs.py's
const SETS = {
  "the distributor's eleven": ["derived-price-list", "stock-and-expiry-alerts", "count-list-totals", "merge-count-documents",
    "invoice-layout-per-customer", "price-list-with-photos", "branch-sees-own-stock", "debtors-statement",
    "products-on-promotion-filter", "customer-history-on-till", "manager-approval-cap-per-day"],
  "the seven older needs": ["member-status-at-till", "member-price-by-tier", "country-tax-rules", "unit-code-at-scan",
    "button-on-desk-record", "store-wallet-at-till", "insurance-co-payment"],
};
const root = path.resolve(here, "..");
for (const [name, list] of Object.entries(SETS)) {
  const cards = pick(list);
  const text = plan.limitsText(cards), md = plan.blueprint(cards, head);
  const missing = cards.flatMap((c) => c.limits.map(plan.plain).filter((l) => !text.includes(l)));
  check(`${name}: every limit in the limits copy`, missing.length === 0, missing.join(" | "));
  const tool = spawnSync("python3", [path.join(root, "tools/needs/needs.py"), "blueprint", ...idsOf(plan.order(cards))], { encoding: "utf8" });
  check(`${name}: the blueprint copy equals needs.py blueprint, row for row`, tool.status === 0 && tool.stdout === md,
        tool.status ? tool.stderr : diff(tool.stdout, md));
}
function diff(a, b) {
  const x = a.split("\n"), y = b.split("\n");
  const i = x.findIndex((l, n) => l !== y[n]);
  return `first difference at line ${i + 1}:\n  needs.py: ${x[i]}\n  plan.js:  ${y[i]}`;
}

// 40 needs: every part of the shortlist worked out, timed
{
  const cards = catalogue.slice(0, 40);
  const t0 = performance.now();
  for (let n = 0; n < 10; n++) {
    plan.steps(cards); plan.proofs(cards); plan.limitsText(cards); plan.requests(cards); plan.blueprint(cards, head);
  }
  const ms = (performance.now() - t0) / 10;
  check(`40 needs: the shortlist worked out in ${ms.toFixed(2)} ms (under 1000)`, ms < 1000);
  check("40 needs: forty blueprint rows", plan.blueprint(cards, head).trim().split("\n").length === 42);
}

console.log(red ? `PLAN RED: ${red} failure(s)` : "PLAN GREEN");
process.exit(red ? 1 : 0);
