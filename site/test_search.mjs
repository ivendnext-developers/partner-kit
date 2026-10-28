// site/test_search.mjs — the site's search, run in node against the BUILT index and the script the site ships.
//
//     python3 site/build.py site/_out && node site/test_search.mjs site/_out
//
// Every query of site/search_golden.json must find its cards in the top three needs (or, for an empty list, nothing at all).
// Two planted faults show the check can fail: a card taken out of the index, and a synonym group taken out of the cards' words.
// (The third, the vendored library changed, is test_site.py's hash test.)
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, "_out"));
const MiniSearch = require(path.join(out, "assets/vendor/minisearch-7.2.0/index.js"));
const search = require(path.join(out, "assets/search.js"));
const docs = JSON.parse(readFileSync(path.join(out, "search-index.json"), "utf8"));
const golden = JSON.parse(readFileSync(path.join(here, "search_golden.json"), "utf8")).queries;

const cardId = (r) => r.id.split("/").pop().replace(/\.html$/, "");

function failures(index) {
  const ms = search.create(index, MiniSearch);
  const bad = [];
  for (const g of golden) {
    const results = search.rank(ms, g.q);
    const top = search.grouped(results).need.slice(0, 3).map(cardId);
    if (g.top3.length === 0 ? results.length !== 0 : !g.top3.every((id) => top.includes(id))) {
      bad.push(`${g.class}: "${g.q}" -> ${results.length} results, top three needs [${top.join(", ")}], want [${g.top3.join(", ")}]`);
    }
  }
  return bad;
}

let red = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? "\n  " + detail : ""}`);
  if (!ok) red++;
};

const classes = new Set(golden.map((g) => g.class));
const count = (c) => golden.filter((g) => g.class === c).length;
check("the golden set holds at least 30 queries, 11 distributor, 7 scoper, 5 each of typo, synonym and none",
      golden.length >= 30 && count("distributor") >= 11 && count("scoper") >= 7 && ["typo", "synonym", "none"].every((c) => count(c) >= 5),
      [...classes].map((c) => `${c} ${count(c)}`).join(" · "));

const real = failures(docs);
check(`every golden query finds its cards (${golden.length} queries)`, real.length === 0, real.join("\n  "));

// planted fault 1: the card a query names is taken out of the index
const gone = "needs/stock/merge-count-documents.html";
const planted1 = failures(docs.filter((d) => d.id !== gone));
check("planted: a card removed from the index turns its query red",
      planted1.some((f) => f.includes("Merge several Stock Reconciliations")), planted1.join("\n  "));

// planted fault 2: a synonym group taken out of the cards' words (what an emptied line of synonyms.txt does to the index)
const group = ["buy now pay later", "bnpl", "instalments", "installments", "pay later", "klarna", "afterpay", "tabby", "tamara"];
const words = group.join(" ");               // build.py writes a matched group's words in a row, in the file's order
check("the group is in the index as build.py writes it", docs.some((d) => d.s.includes(words)));
const planted2 = failures(docs.map((d) => ({ ...d, s: d.s.replace(words, "") })));
check("planted: a synonym group removed turns its query red", planted2.some((f) => f.includes('"bnpl"')), planted2.join("\n  "));

const size = readFileSync(path.join(out, "search-index.json")).length;
check(`the index is at most 500 kB before compression (${Math.round(size / 1024)} kB)`, size <= 500 * 1024);

const ms = search.create(docs, MiniSearch);
const inst = (q) => search.instant(search.rank(ms, q), 6);
const needsFirst = (l) => l.every((r, i) => i === 0 || r.k !== "need" || l[i - 1].k === "need");
const kinds = (l) => l.map((r) => r.k).join(" ");
const feed = inst("event feed"), hook = inst("webhook"), nonly = inst("bnpl");
check("the header's list: six at most, needs first, four needs and the two best pages when both match",
      feed.length === 6 && kinds(feed) === "need need need need " + feed.slice(4).map((r) => r.k).join(" ") && feed.slice(4).every((r) => r.k !== "need")
      && hook.length === 6 && needsFirst(hook) && nonly.length === 1 && needsFirst(feed),
      `event feed: ${kinds(feed)} · webhook: ${kinds(hook)} · bnpl: ${kinds(nonly)}`);
// a developer's own words find the pages that answer them (How it all works, One app end to end, Questions developers ask)
// among the header's six; the last four words are on none of those pages, so only their synonym groups find them
const HOW = new Set(["guide/01a_how_it_all_works.html", "guide/01b_one_app_end_to_end.html", "questions.html"]);
const DEV_WORDS = ["docker", "container", "tenant", "multi-tenant", "endpoint", "field", "screen", "data", "conflict", "publish",
                   "image", "cost", "kubernetes", "multitenant", "clash", "callback url"];
const unanswered = (index) => {
  const m = search.create(index, MiniSearch);
  return DEV_WORDS.filter((q) => !search.instant(search.rank(m, q), 6).some((r) => HOW.has(r.id)));
};
const devMiss = unanswered(docs);
check(`a developer's words find How it works, its example or the questions in the header's six (${DEV_WORDS.length} words)`,
      devMiss.length === 0, devMiss.join(", "));
// planted fault 3: the docker group taken out of the pages' words turns "kubernetes" red
const dock = "docker container containerised containerized kubernetes k8s";
const planted3 = unanswered(docs.map((d) => ({ ...d, s: d.s.replace(dock, "") })));
check("planted: the docker synonym group removed turns a developer's word red", planted3.includes("kubernetes"), planted3.join(", "));

const filtered = search.rank(ms, "approval", { area: "till" });
check("a filter narrows the results to needs of that area", filtered.length > 0 && filtered.every((r) => r.k === "need" && r.ar === "till"));
const browse = search.rank(ms, "", { status: "not-possible" });
check("a filter with no words lists every need it matches",
      browse.length === docs.filter((d) => d.st === "not-possible").length && browse.length > 0);

console.log(red ? `${red} FAILED` : "SEARCH GREEN");
process.exit(red ? 1 : 0);
