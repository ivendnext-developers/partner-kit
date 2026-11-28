// S64 — runs the station's page (service/code128.js + service/page.js) under node on a small stand-in for the browser,
// for tests/test_page.py. The stand-in keeps a tree of elements with their text, classes, attributes and click handlers,
// answers the page's calls from opts.answers (a queue per path) and records each window.print() with the tag as it was
// filled at that moment. S59's harness shape (samples/s59_kitchen_screen/tests/page_harness.js), without the layout.
//
//   node page_harness.js '<json options>'   → prints one JSON answer
//   options: {answers: {"/pst/board": [...], ...}, steps: ["tap:<tile words>", "click:<element id>", "hash:<new hash>"],
//             hash, languages, storage ({} or "throws")}
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const SERVICE = path.join(__dirname, "..", "service");

function element(tag) {
  const e = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, attrs: {}, listeners: {}, hidden: false,
    disabled: false, className: "", _text: "", type: "", style: {},
    get firstChild() { return this.children[0] || null; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); },
    set textContent(v) { this.children = []; this._text = String(v); },
    get classList() {
      const self = this, list = () => self.className.split(/\s+/).filter(Boolean);
      return {
        contains: (c) => list().includes(c),
        add: (c) => { if (!list().includes(c)) self.className = list().concat(c).join(" "); },
        remove: (c) => { self.className = list().filter((x) => x !== c).join(" "); },
        toggle: (c, on) => { const has = list().includes(c); if (on === undefined ? !has : on) { if (!has) self.className = list().concat(c).join(" "); } else self.className = list().filter((x) => x !== c).join(" "); },
      };
    },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parentNode = null; return c; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    click() { if (!this.disabled) (this.listeners.click || []).forEach((fn) => fn({})); },
    all() { return this.children.reduce((out, c) => out.concat([c], c.all ? c.all() : []), []); },
    querySelectorAll(sel) {            // ".a, .b": elements with either class
      const alts = sel.split(",").map((s) => s.trim().split(".").filter(Boolean));
      return this.all().filter((c) => c.classList && alts.some((cls) => cls.every((k) => c.classList.contains(k))));
    },
  };
  return e;
}

async function run(opts) {
  const byId = {}, body = element("body"), html = element("html");
  const src = fs.readFileSync(path.join(SERVICE, "page.html"), "utf8");
  const inner = src.slice(src.indexOf("<body"), src.indexOf("</body>"));   // the page's own tree, nested as written
  const stack = [body], VOID = new Set(["META", "LINK", "INPUT", "BR", "IMG"]);
  for (const m of inner.matchAll(/<(\/?)(\w+)([^>]*)>/g)) {
    const tag = m[2].toUpperCase();
    if (tag === "BODY" || tag === "SCRIPT") continue;
    if (m[1]) { if (stack.length > 1) stack.pop(); continue; }
    const e = element(tag), id = /\bid="([^"]+)"/.exec(m[3]), cls = /\bclass="([^"]+)"/.exec(m[3]);
    if (cls) e.className = cls[1];
    if (/\shidden(\s|$|>)/.test(m[3] + " ")) e.hidden = true;
    if (id) byId[id[1]] = e;
    stack[stack.length - 1].appendChild(e);
    if (!VOID.has(tag)) stack.push(e);
  }
  const calls = [], prints = [], rules = [], answers = opts.answers || {}, timers = [], pendingTimers = [];
  const store = opts.storage === "throws" ? null : Object.assign({}, opts.storage || {});
  const doc = {
    body, documentElement: html, title: "Production station",
    getElementById: (id) => byId[id] || null, createElement: element, createElementNS: (ns, t) => element(t),
    querySelectorAll: (sel) => body.querySelectorAll(sel),
    styleSheets: [{ href: "https://p.example/ivn-kit.css", cssRules: [] },
                  { href: "https://p.example/page.css", cssRules: [], insertRule(r) { rules.push(r); this.cssRules.push(r); } }],
  };
  const win = {
    location: { hash: opts.hash === undefined ? "#s=thrift.example.com&t=PST-S-00001.1.sig" : opts.hash, reload() {} },
    navigator: { languages: opts.languages || ["en-US"], language: (opts.languages || ["en-US"])[0] },
    document: doc, URLSearchParams, Intl, console, Promise, JSON, Math, Number, String, Object, Array,
    performance: { now: () => clock.t },
    setTimeout: (fn, ms) => { timers.push(ms); pendingTimers.push({ ms, fn }); return timers.length; }, clearTimeout() {},
    addEventListener() {},
    fetch: (url, init) => {
      const b = JSON.parse(init.body); calls.push(Object.assign({ path: url }, b));
      const q = answers[url] || [{ state: "unavailable" }];
      const a = q.length > 1 ? q.shift() : q[0];
      return Promise.resolve({ json: () => Promise.resolve(a) });
    },
    print: () => {
      const bars = byId["tag-bars"].children[0];
      prints.push({ title: doc.title, price: byId["tag-price"].textContent, what: byId["tag-what"].textContent,
                    digits: byId["tag-digits"].textContent, bars: bars ? bars.children.length : 0,
                    viewBox: bars ? bars.getAttribute("viewBox") : "", width: byId.tag.style.width, height: byId.tag.style.height });
    },
    ivnKit: { openDialog(el) { el.open = true; }, closeDialog(el) { el.open = false; } },
  };
  const clock = { t: 1000 };
  Object.defineProperty(win, "localStorage", {
    get() {
      if (!store) throw new Error("SecurityError: storage is blocked");
      return { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
    },
  });
  win.window = win; win.self = win;
  vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(SERVICE, "code128.js"), "utf8"), win, { filename: "code128.js" });
  vm.runInContext(fs.readFileSync(path.join(SERVICE, "page.js"), "utf8"), win, { filename: "page.js" });
  const settle = async () => { for (let i = 0; i < 8; i++) await new Promise((r) => setImmediate(r)); };
  await settle();
  const tiles = () => body.querySelectorAll(".pst-tile").filter((t) => !hiddenUp(t));
  const hiddenUp = (e) => { for (let x = e; x; x = x.parentNode) if (x.hidden) return true; return false; };
  const steps = [];
  for (const s of opts.steps || []) {
    const [kind, ...rest] = s.split(":"), what = rest.join(":");
    if (kind === "tap") {
      const t = tiles().find((x) => x.textContent === what);
      if (!t) throw new Error("no tile " + what + " among " + JSON.stringify(tiles().map((x) => x.textContent)));
      t.click();
    } else if (kind === "double") {                 // two taps before any answer arrives
      const t = tiles().find((x) => x.textContent === what);
      t.click(); t.click();
    } else if (kind === "click") byId[what].click();
    else if (kind === "advance") clock.t += Number(what);
    else if (kind === "timer") { const i = pendingTimers.findIndex((t) => t.ms === Number(what)); if (i >= 0) pendingTimers.splice(i, 1)[0].fn(); }
    await settle();
    steps.push({ step: s, note: byId.note.hidden ? "" : byId.note.textContent });
  }
  const shown = (id) => (hiddenUp(byId[id]) ? null : byId[id].textContent);
  return {
    calls, prints, rules, steps, store, timers,
    note: byId.note.hidden ? "" : byId.note.textContent, noteGood: byId.note.classList.contains("is-good"),
    title: byId.title.textContent, colour: byId.colour.textContent, who: shown("who"), count: shown("count"),
    tiles: tiles().map((t) => ({ text: t.textContent, on: t.classList.contains("is-on"), dir: t.getAttribute("dir"), disabled: t.disabled })),
    workersTitle: shown("workers-title"), dialogOpen: !!byId["places-dialog"].open, lang: html.getAttribute("lang"),
    printed: body.getAttribute("data-printed"), docTitle: doc.title,
    words: { undo: byId.undo.textContent, full: byId.full.textContent, change: byId.change.textContent },
  };
}

run(JSON.parse(process.argv[2] || "{}")).then((out) => process.stdout.write(JSON.stringify(out)),
  (e) => process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) })));
