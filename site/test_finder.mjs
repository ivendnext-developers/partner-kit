// site/test_finder.mjs — the Needs page's finder and the Samples page's filters, run in node against the BUILT site and the scripts it ships.
//
//     python3 site/build.py site/_out && node site/test_finder.mjs site/_out
//
// The distributor's three lines (the box's own placeholder) each find their card through the site's own search, and every card's
// own words fit closely; a line the catalogue does not hold gets no verdict and stays out of the plan; a list arrives by ?list= and
// ?q=; "Plan these needs" opens Plan a project with the ids, and Plan a project reads them back; each card's recipes and samples are
// a page of this site or a kit file. The filters narrow the built page's own cards by words, industry and way in, a sample for
// every industry shows under each, and a group's count follows the filter on the page itself.
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, "_out"));
const MiniSearch = require(path.join(out, "assets/vendor/minisearch-7.2.0/index.js"));
const search = require(path.join(out, "assets/search.js"));
const finder = require(path.join(out, "assets/finder.js"));
const samples = require(path.join(out, "assets/samples.js"));
const plan = require(path.join(out, "assets/plan.js"));
const docs = JSON.parse(readFileSync(path.join(out, "search-index.json"), "utf8"));
const catalogue = JSON.parse(readFileSync(path.join(out, "catalogue.json"), "utf8"));
const needsPage = readFileSync(path.join(out, "needs/index.html"), "utf8");
const samplesPage = readFileSync(path.join(out, "samples/index.html"), "utf8");
const home = readFileSync(path.join(out, "index.html"), "utf8");

const ms = search.create(docs, MiniSearch);
const cards = Object.fromEntries(catalogue.map((c) => [c.page, c]));
const unescape = (s) => s.replace(/&#10;/g, "\n").replace(/&#x0*a;/gi, "\n").replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

let red = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok || !detail ? "" : "\n  " + detail}`);
  if (!ok) red++;
};
const shownFor = (line, choice) => {
  const hits = finder.fits(search, ms, line, cards), pick = finder.picked(hits, choice);
  return pick === finder.NONE ? null : cards[hits[pick].id];
};
const first = (line) => shownFor(line);

// the three lines the box opens with, as its placeholder
const placeholder = unescape(needsPage.match(/<textarea id="finder-list"[^>]*placeholder="([^"]*)"/)?.[1] || "");
const THREE = { "Branch sees only own + HQ stock": "branch-sees-own-stock",
                "Cap manager discount overrides per branch per day": "manager-approval-cap-per-day",
                "Item price list with photos": "price-list-with-photos" };
check("the box opens empty, with the distributor's three lines as its placeholder", placeholder === Object.keys(THREE).join("\n"), JSON.stringify(placeholder));
check("the box holds no text of its own", /<textarea id="finder-list"[^>]*><\/textarea>/.test(needsPage));
for (const [line, id] of Object.entries(THREE)) {
  check(`"${line}" finds ${id}`, first(line)?.id === id, first(line)?.id);
}
check("each line offers up to two more matches", finder.fits(search, ms, Object.keys(THREE)[0], cards).length === 3);

// what a list looks like
check("a list splits by line, blanks and single letters set aside, a semicolon kept",
  JSON.stringify(finder.lines(" a list \r\n\n bb;c d\nx ")) === JSON.stringify(["a list", "bb;c d"]), JSON.stringify(finder.lines(" a list \r\n\n bb;c d\nx ")));
check("a long list is read whole", finder.lines(Array.from({ length: 200 }, (_, i) => "need " + i).join("\n")).length === 200);
check("?list= fills the box, with its line breaks", finder.given("?list=" + encodeURIComponent("one\r\ntwo")) === "one\r\ntwo");
check("?q= fills it too, and ?list= wins", finder.given("?q=abc") === "abc" && finder.given("?q=abc&list=def") === "def" && finder.given("") === "");
check("a line of nonsense finds no need", finder.fits(search, ms, "zzqxv wqkjh", cards).length === 0);

// a line the catalogue does not hold: no verdict, the nearest offered, nothing in the plan until the reader picks one
const OFF = ["Staff rota and shift scheduling", "Payroll for store staff", "Biometric login for cashiers", "Weighing scale items",
             "Monthly report of sales by cashier", "Accounting general ledger", "Multi-currency support"];
for (const line of OFF) check(`"${line}" gets no verdict`, shownFor(line) === null, shownFor(line)?.id);
const off = finder.fits(search, ms, OFF[1], cards);
check("the nearest needs are still offered, and one the reader picks is shown", off.length > 0 && shownFor(OFF[1], 0)?.id === cards[off[0].id].id);
check("None of these sets a close match aside", shownFor(Object.keys(THREE)[0], finder.NONE) === null);
const loose = catalogue.filter((c) => shownFor(c.asks)?.id !== c.id);
check("every card's own words fit closely and find that card", loose.length === 0, loose.map((c) => c.id).slice(0, 5).join(", "));

// Plan these needs, and each card's lists
const ids = Object.values(THREE);
const href = finder.planHref("../", ids);
check("Plan these needs opens plan.html?needs=…", href === "../plan.html?needs=" + ids.join(","), href);
check("Plan a project reads those ids back", JSON.stringify(plan.ids(href.slice(href.indexOf("?")))) === JSON.stringify(ids));
const notPage = catalogue.flatMap((c) => finder.uses(c)).filter((u) => u.page && !existsSync(path.join(out, u.page)));
check("every recipe and sample the finder links is a built page or a kit file", notPage.length === 0, JSON.stringify(notPage[0]));
check("a card with a kit file shows it on GitHub", catalogue.flatMap((c) => finder.uses(c)).some((u) => !u.page && u.url.includes("github.com/ivendnext-developers/partner-kit/")));
check("each card names its door and its area", catalogue.every((c) => c.door_name && c.area_name));

// the page and the home page's box
check("the finder sits under the page's first sentence, hidden until its script shows it",
  /<\/h1>\s*<p class="lead">|<\/h1>\s*<p>/.test(needsPage) && needsPage.indexOf('id="finder"') < needsPage.indexOf('id="new-and-changed"') && /<section id="finder"[^>]* hidden>/.test(needsPage));
check("the script is a file of the site, after search.js", needsPage.includes('<script src="../assets/finder.js" defer></script>') &&
  needsPage.indexOf("assets/search.js") < needsPage.indexOf("assets/finder.js"));
check("the catalogue and the index arrive when the box is first used, not with the page", !/fetch\(/.test(readFileSync(path.join(out, "assets/finder.js"), "utf8").split("function load()")[0]));
check("the home page's box is a plain form to the finder", /<form class="finder-strip" action="needs\/index\.html" method="get">/.test(home) && /<textarea id="home-list" name="list"/.test(home));

// the Samples page's filters, over the built page's own cards
const built = [...samplesPage.matchAll(/<li class="card sample" data-text="([^"]*)" data-door="([^"]*)" data-ind="([^"]*)">/g)]
  .map((m) => ({ text: unescape(m[1]), door: unescape(m[2]), industries: unescape(m[3]).split("|") }));
const index = JSON.parse(readFileSync(path.join(out, "samples/index.json"), "utf8")).samples;
const shown = (f) => built.filter((c) => samples.matches(c, f)).length;
check("every sample has a card with what the filters read", built.length === index.length && built.every((c) => c.text && c.industries.length));
check("no filter shows them all", shown({}) === built.length);
check("words narrow, all of them must match", shown({ words: "bin" }) > 0 && shown({ words: "bin" }) < built.length && shown({ words: "BIN zzqxv" }) === 0);
const someDoor = built.find((c) => c.door).door;
check("a way in narrows to exactly that door", shown({ door: someDoor }) === built.filter((c) => c.door === someDoor).length && shown({ door: someDoor }) < built.length);
const every = built.filter((c) => c.industries.includes("every industry")).length;
const grocery = built.filter((c) => c.industries.includes("Grocery")).length;
check("an industry shows its own samples and those for every industry", every > 0 && grocery > 0 && shown({ industry: "Grocery" }) === every + grocery && shown({ industry: "Grocery" }) < built.length);
const groups = [...samplesPage.matchAll(/<section class="sgroup" data-group="([^"]+)"><h2 id="[^"]+">[^<]*<span class="gcount">(\d+)<\/span>/g)];
check("each group's count is its cards, and the groups hold every sample", groups.length > 1 && groups.reduce((n, g) => n + Number(g[2]), 0) === built.length);

// the filters on the page itself: a small stand-in for the browser's document, holding the built page's own groups and cards
{
  const node = (attrs = {}) => ({ hidden: false, attrs, value: "", textContent: "", listeners: {}, getAttribute(k) { return this.attrs[k]; },
    addEventListener(k, f) { this.listeners[k] = f; } });
  const sections = [...samplesPage.matchAll(/<section class="sgroup" data-group="([^"]+)">(.*?)<\/section>/gs)];
  const groupNodes = sections.map((m) => {
    const cardsIn = [...m[2].matchAll(/<li class="card sample" data-text="([^"]*)" data-door="([^"]*)" data-ind="([^"]*)">/g)]
      .map((c) => node({ "data-text": unescape(c[1]), "data-door": unescape(c[2]), "data-ind": unescape(c[3]) }));
    const g = node({ group: m[1] }), count = node();
    g.cardsIn = cardsIn; g.count = count;
    g.querySelector = () => count;
    g.querySelectorAll = () => cardsIn.filter((c) => !c.hidden);
    return g;
  });
  const ids = Object.fromEntries(["sample-filters", "sf-q", "sf-ind", "sf-door", "sf-count", "sf-none"].map((k) => [k, node()]));
  const all = groupNodes.flatMap((g) => g.cardsIn);
  const doc = { getElementById: (k) => ids[k], querySelectorAll: (s) => (s === ".sgroup" ? groupNodes : all) };
  const run = samples.wire(doc);
  check("the script shows the filters", ids["sample-filters"].hidden === false);
  ids["sf-ind"].value = "Grocery"; run();
  check("the count follows the filter", ids["sf-count"].textContent === `${every + grocery} samples` && groupNodes.every((g) => g.hidden === (g.count.textContent === 0)),
        ids["sf-count"].textContent);
  check("a group's count is the cards it still shows", groupNodes.reduce((n, g) => n + Number(g.count.textContent), 0) === every + grocery);
  ids["sf-q"].value = "zzqxv"; run();
  check("no match: every group hides, and the page says so", groupNodes.every((g) => g.hidden) && ids["sf-none"].hidden === false && ids["sf-count"].textContent === "0 samples");
  ids["sf-q"].value = ""; ids["sf-ind"].value = ""; run();
  check("cleared: every sample again", ids["sf-count"].textContent === `${built.length} samples` && ids["sf-none"].hidden === true && groupNodes.every((g) => !g.hidden));
}

console.log(red ? `FINDER RED: ${red} failure(s)` : "FINDER GREEN");
process.exit(red ? 1 : 0);
