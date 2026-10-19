// site/test_analytics.mjs — the visit counter's script (assets/analytics.js), run in node against the BUILT site.
//
//     python3 site/build.py site/_out && node site/test_analytics.mjs site/_out
//
// A page is faked (address, browser settings, the two meta tags read from a built page); the script is loaded for each case and what
// it sends is read from a fake fetch. Every guard is then planted wrong in a copy of the script and must turn a check red.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, "_out"));
const SRC = readFileSync(path.join(out, "assets/analytics.js"), "utf8");
const page = readFileSync(path.join(out, "index.html"), "utf8");
const META = /<meta name="ivn-analytics" content="([^"]+)">/.exec(page)?.[1];
const CSP = /<meta http-equiv="Content-Security-Policy" content="([^"]+)">/.exec(page)?.[1];

let red = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? "\n  " + detail : ""}`);
  if (!ok) red++;
};

// a fake browser; `opts` bends one thing
function browser(opts = {}) {
  const log = { fetches: [], cookieTouched: 0, storageWrites: [], localStorageTouched: 0, listeners: {} };
  const metas = { 'meta[name="ivn-analytics"]': opts.meta === undefined ? META : opts.meta,
                  'meta[http-equiv="Content-Security-Policy"]': opts.csp === undefined ? CSP : opts.csp };
  const doc = {
    referrer: opts.referrer || "",
    querySelector: (sel) => (metas[sel] == null ? null : { getAttribute: () => metas[sel] }),
    addEventListener: (t, fn) => { (log.listeners[t] ||= []).push(fn); },
  };
  Object.defineProperty(doc, "cookie", { get() { log.cookieTouched++; return ""; }, set() { log.cookieTouched++; } });
  const u = new URL(opts.href || "https://developer.ivendnext.com/guide/index.html");
  const win = {
    location: { href: u.href, hostname: u.hostname, protocol: u.protocol, pathname: u.pathname, search: u.search, origin: u.origin },
    navigator: { doNotTrack: opts.dnt ?? null, globalPrivacyControl: opts.gpc ?? false },
    document: doc,
    sessionStorage: { getItem: (k) => opts.flag ?? null, setItem: (k, v) => { log.storageWrites.push([k, v]); } },
    fetch: opts.fetch || ((url, init) => { log.fetches.push({ url, init, body: JSON.parse(init.body) }); return Promise.resolve({}); }),
    URL,
  };
  Object.defineProperty(win, "localStorage", { get() { log.localStorageTouched++; throw new Error("no"); } });
  return { win, log };
}

function load(opts = {}, src = SRC, before = null) {
  const b = browser(opts);
  const sandbox = { URL, JSON, decodeURIComponent, encodeURIComponent };
  Object.assign(sandbox, b.win);                                              // the script reads its page from its global
  if (before) sandbox.ivnTrack = before;                                      // a call queued before the file loaded
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { win: sandbox, log: b.log };
}
const events = (l) => l.log.fetches.map((f) => f.body);
const click = (l, href) => {
  const a = { tagName: "A", getAttribute: () => href, parentNode: null };
  for (const fn of l.log.listeners.click || []) fn({ target: { tagName: "SPAN", parentNode: a } });
};

function all(src, label) {
  const bad = [];
  const t = (name, ok, detail = "") => { if (!ok) bad.push(`${name}${detail ? ": " + detail : ""}`); };

  let l = load({ referrer: "https://www.google.com/" }, src);
  t("a visit sends one page view with the path (a folder for index.html) and the referrer's host only",
    JSON.stringify(events(l)) === JSON.stringify([{ e: "pageview", p: "/guide/", r: "www.google.com" }]), JSON.stringify(events(l)));
  t("it posts to the counter's /e with no cookies and no referrer", l.log.fetches[0]?.url === `${META}/e` && l.log.fetches[0].init.credentials === "omit" &&
    l.log.fetches[0].init.referrerPolicy === "no-referrer" && l.log.fetches[0].init.mode === "cors" && typeof l.log.fetches[0].init.body === "string" && !l.log.fetches[0].init.headers,
    "a cors request with a plain-text body is not preflighted and names the page's origin; no-cors with no-referrer would send Origin: null");
  t("no cookie, no local storage, no storage write", l.log.cookieTouched === 0 && l.log.localStorageTouched === 0 && l.log.storageWrites.length === 0,
    `cookie ${l.log.cookieTouched}, local ${l.log.localStorageTouched}, writes ${JSON.stringify(l.log.storageWrites)}`);
  t("window.ivnTrack is defined", typeof l.win.ivnTrack === "function");

  for (const [what, o] of [["Do Not Track (1)", { dnt: "1" }], ["Do Not Track (yes)", { dnt: "yes" }], ["Global Privacy Control", { gpc: true }],
                           ["?notrack", { href: "https://developer.ivendnext.com/?notrack" }], ["the tab's notrack flag", { flag: "1" }],
                           ["localhost", { href: "http://localhost:8000/" }], ["a .localhost name", { href: "http://a.localhost/" }],
                           ["127.0.0.1", { href: "http://127.0.0.1/" }], ["a file", { href: "file:///tmp/x.html" }],
                           ["no counter named", { meta: null }], ["a counter the policy does not list", { meta: "https://evil.example" }],
                           ["a counter with a path", { meta: `${META}/x` }], ["no content policy", { csp: null }]]) {
    l = load(o, src);
    l.win.ivnTrack("search", { q: "gift", n: 0 }); click(l, "https://library.ivendnext.app/x");
    t(`${what} sends nothing at all (not even a call)`, l.log.fetches.length === 0 && Object.keys(l.log.listeners).length === 0, JSON.stringify(events(l)));
    t(`${what}: ivnTrack still exists and does not throw`, typeof l.win.ivnTrack === "function");
  }
  l = load({ href: "https://developer.ivendnext.com/?notrack" }, src);
  t("?notrack is kept for the tab (the one thing written to the browser, a flag, not an identifier)", JSON.stringify(l.log.storageWrites) === '[["ivnNoTrack","1"]]');

  l = load({}, src); l.log.fetches.length = 0;
  l.win.ivnTrack("search", { q: "  Gift   card ", n: 4 });
  t("a search with results sends one search report", JSON.stringify(events(l)) === JSON.stringify([{ e: "search", q: "Gift card", n: 4 }]), JSON.stringify(events(l)));
  l.log.fetches.length = 0; l.win.ivnTrack("search", { q: "zzqx", n: 0 });
  t("a search with no result sends the search and a no_result", JSON.stringify(events(l).map((b) => b.e)) === '["search","no_result"]', JSON.stringify(events(l)));
  l.log.fetches.length = 0; l.win.ivnTrack("plan_export", { how: "print" }); l.win.ivnTrack("nope", {}); l.win.ivnTrack("search", { q: "" });
  t("plan_export is sent; an unknown name and an empty search are not", JSON.stringify(events(l)) === '[{"e":"plan_export","how":"print"}]', JSON.stringify(events(l)));
  l.log.fetches.length = 0; l.win.ivnTrack("plan_export", { how: "limits" }); l.win.ivnTrack("plan_export", { how: "blueprint" });
  t("the plan page's two copy buttons (limits, blueprint) are reported as copy, the counter's word", JSON.stringify(events(l)) === '[{"e":"plan_export","how":"copy"},{"e":"plan_export","how":"copy"}]', JSON.stringify(events(l)));

  const clicks = [["https://developer.ivendnext.com/sandbox.html", "sandbox_request"], ["../sandbox.html", "sandbox_request"],
                  ["https://www.ivendnext.com/partner/#be-a-partner", "sandbox_request"],
                  ["https://github.com/ivendnext-developers/partner-feedback/issues/new?template=2_point_request.yml&title=Extension-point%20request%3A%20P-CAPTURE2%20%E2%80%94%20x", "request_form"],
                  ["https://library.ivendnext.app/build", "outbound"], ["https://docs.ivendnext.com/a", "outbound"], ["https://www.ivendnext.com/", "outbound"]];
  for (const [href, want] of clicks) {
    l = load({}, src); l.log.fetches.length = 0; click(l, href);
    t(`a click on ${href.slice(0, 60)} is ${want}`, events(l).length === 1 && events(l)[0].e === want, JSON.stringify(events(l)));
  }
  l = load({}, src); l.log.fetches.length = 0; click(l, "https://github.com/ivendnext-developers/partner-feedback/issues/new?title=Extension-point%20request%3A%20P-CAPTURE2%20x");
  t("a request-form click carries the extension point's handle", events(l)[0]?.h === "P-CAPTURE2", JSON.stringify(events(l)));
  l.log.fetches.length = 0; click(l, "https://example.org/"); click(l, "mailto:a@b.c"); click(l, "#top"); click(l, "/guide/x.html");
  t("any other link sends nothing", l.log.fetches.length === 0, JSON.stringify(events(l)));

  let caught = 0;
  const down = load({ fetch: () => ({ catch(fn) { caught++; fn(new Error("down")); return this; } }) }, src);
  down.win.ivnTrack("search", { q: "x", n: 1 });
  t("a counter that is down: its failure is caught, nothing thrown", typeof down.win.ivnTrack === "function" && caught >= 2, `caught ${caught}`);
  let threw = false;
  try { load({ fetch: () => { throw new Error("blocked"); } }, src).win.ivnTrack("search", { q: "x", n: 1 }); } catch (e) { threw = true; }
  t("a fetch that throws breaks nothing", !threw);
  const seen = [];
  const never = load({ fetch: (u, i) => { seen.push(JSON.parse(i.body).e); return new Promise(() => {}); } }, src);
  const back = never.win.ivnTrack("search", { q: "x", n: 1 });
  t("a counter that never answers is not waited for (the call returns at once, nothing awaits the reply)", back === undefined && seen.join() === "pageview,search", seen.join());
  const early = Object.assign(() => {}, { q: [["search", { q: "early", n: 1 }]] });
  const b2 = load({}, src, early);
  t("a call queued before the file loaded is sent once it has", b2.log.fetches.some((f) => f.body.e === "search" && f.body.q === "early"), JSON.stringify(b2.log.fetches.map((f) => f.body)));
  return bad;
}

check("the built home page names the counter and its policy lists it", !!META && !!CSP && CSP.includes(META), `${META}`);
const real = all(SRC, "real");
check("every behaviour of the script holds (a page view, every guard, each event, a counter that is down)", real.length === 0, real.join("\n  "));

// each guard planted wrong in a copy of the script must turn at least one check red
const plants = [
  ["Do Not Track ignored", 'nav.doNotTrack === "1" || nav.doNotTrack === "yes" || win.doNotTrack === "1" || nav.msDoNotTrack === "1"', "false"],
  ["Global Privacy Control ignored", "nav.globalPrivacyControl === true", "false"],
  ["localhost counted", 'h === "localhost" ||', "false ||"],
  ["any counter accepted (the policy not read)", 'return listed.indexOf("https://" + host) >= 0 ? "https://" + host : "";', 'return "https://" + host;'],
  ["a cookie set", 'var queued = win.ivnTrack && win.ivnTrack.q;', 'win.document.cookie = "id=1"; var queued = win.ivnTrack && win.ivnTrack.q;'],
  ["no-cors with no referrer (the request would name Origin: null)", 'mode: "cors", credentials: "omit",', 'mode: "no-cors", credentials: "omit",'],
  ["credentials sent", 'credentials: "omit"', 'credentials: "include"'],
  ["a rejected fetch left unhandled", 'if (p && typeof p.catch === "function") p.catch(function () { /* a counter that is down changes nothing */ });', ""],
  ["a no-result search not reported", "if (n === 0) out.push", "if (false) out.push"],
  ["a copy sent under the plan page's own word", 'how: props.how === "print" ? "print" : "copy"', 'how: text(props.how, 10)'],
  ["every link counted as outbound", "OUT_HOSTS.indexOf(u.hostname.toLowerCase()) >= 0", "true"],
];
for (const [name, from, to] of plants) {
  if (!SRC.includes(from)) { check(`planted fault "${name}" can be applied`, false, "the text to change is not in the script"); continue; }
  const bad = all(SRC.replace(from, to), name);
  check(`planted fault "${name}" turns a check red`, bad.length > 0);
}

process.exit(red ? 1 : 0);
