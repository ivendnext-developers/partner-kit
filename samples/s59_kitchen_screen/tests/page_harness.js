// S59 — runs the screen's page (service/fit.js + service/page.js) under node on a small stand-in for the browser, for
// tests/test_page.py. The stand-in keeps a tree of elements with their text, classes, attributes and click handlers;
// it lays nothing out (every box is empty), so it proves the page's own rules, never how a screen looks.
//
//   node page_harness.js <scenario> '<json options>'   → prints one JSON answer
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const SERVICE = path.join(__dirname, "..", "service");

function element(tag) {
  const e = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, attrs: {}, listeners: {}, hidden: false,
    disabled: false, title: "", className: "", _text: "", style: { setProperty() {} },
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
    replaceChildren(...cs) { this.children = []; this._text = ""; cs.forEach((c) => this.appendChild(c)); },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    click() { (this.listeners.click || []).forEach((fn) => fn({})); },
    all() { return this.children.reduce((out, c) => out.concat([c], c.all ? c.all() : []), []); },
    querySelectorAll(sel) { const cls = sel.replace(/^\./, ""); return this.all().filter((c) => c.classList && c.classList.contains(cls)); },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    getBoundingClientRect() { return { top: 0, bottom: 0, height: 0, left: 0, right: 0, width: 0 }; },
    get scrollHeight() { return 0; }, get clientHeight() { return 0; },
  };
  return e;
}
function text(t) { return { textContent: String(t), parentNode: null, all: () => [] }; }

function run(opts) {
  const byId = {}, body = element("body");
  const html = fs.readFileSync(path.join(SERVICE, "page.html"), "utf8");
  for (const m of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)) { byId[m[2]] = element(m[1]); body.appendChild(byId[m[2]]); }
  const calls = [], answers = opts.answers || {};
  const store = opts.storage === "throws" ? null : Object.assign({}, opts.storage || {});
  const win = {
    location: { hash: opts.hash === undefined ? "#s=bistro.example.com&t=KSC-SCREEN-00001.1.sig" : opts.hash, reload() {} },
    document: {
      body, getElementById: (id) => byId[id] || null, createElement: element, createElementNS: (ns, t) => element(t),
      createTextNode: text, addEventListener() {}, querySelectorAll: (sel) => body.querySelectorAll(sel),
    },
    fetch: (url, init) => {
      const b = JSON.parse(init.body); calls.push(Object.assign({ path: url }, b));
      const queue = answers[url] || [{ state: "unavailable" }];
      const a = queue.length > 1 ? queue.shift() : queue[0];
      return Promise.resolve({ json: () => Promise.resolve(a) });
    },
    ivnKit: { applyTheme() {}, applyDir() {}, openDialog(el) { el.attrs.open = "1"; } },
    getComputedStyle: () => ({ paddingBottom: "0", paddingTop: "0" }),
    addEventListener() {}, performance: { now: () => clock.t }, URLSearchParams, Date, console,
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, requestAnimationFrame: () => 0, cancelAnimationFrame() {},
  };
  const clock = { t: 1000 };
  Object.defineProperty(win, "localStorage", {
    get() {
      if (!store) throw new Error("SecurityError: storage is blocked");
      return { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
    },
  });
  win.window = win;
  vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(SERVICE, "fit.js"), "utf8"), win, { filename: "fit.js" });
  vm.runInContext(fs.readFileSync(path.join(SERVICE, "page.js"), "utf8"), win, { filename: "page.js" });
  return { win, byId, body, calls, store, clock };
}
const settle = () => new Promise((r) => setImmediate(r));
async function settled() { for (let i = 0; i < 20; i++) await settle(); }

const SCENARIOS = {
  // the size the screen opens at, and after A- / A+
  async size(opts) {
    const p = run(opts);
    await settled();
    const out = { first: p.body.getAttribute("data-size") };
    (opts.taps || []).forEach((id) => p.byId[id].click());
    out.after = p.body.getAttribute("data-size");
    out.smallerDisabled = p.byId.smaller.disabled; out.biggerDisabled = p.byId.bigger.disabled;
    out.stored = p.store;
    return out;
  },
  // a cook's tap is refused; a later tap on the same ticket that gets no answer must not take the refusal down
  async held(opts) {
    const p = run(opts);
    await settled();
    const btn = () => p.body.all().find((e) => e.classList && e.classList.contains("ksc-act"));
    const out = { drawn: !!btn() };
    if (!btn()) return out;
    btn().click(); await settled();
    out.afterRefusal = { hidden: p.byId.note.hidden, text: p.byId.note.textContent };
    p.clock.t += 100;
    btn().click(); await settled();
    out.afterSecond = { hidden: p.byId.note.hidden, text: p.byId.note.textContent };
    out.moves = p.calls.filter((c) => c.path === "/ksc/move").length;
    return out;
  },
  // what the page puts on a ticket: the retailer's words in <bdi>, and no element told dir="auto"
  async words(opts) {
    const p = run(opts);
    await settled();
    const all = p.body.all().filter((e) => e.tagName);
    return { bdi: all.filter((e) => e.tagName === "BDI").map((e) => e.textContent),
             dirAuto: all.filter((e) => e.getAttribute("dir") === "auto").length };
  },
};

(async () => {
  const [name, raw] = process.argv.slice(2);
  process.stdout.write(JSON.stringify(await SCENARIOS[name](JSON.parse(raw || "{}"))));
})().catch((e) => { process.stdout.write(JSON.stringify({ error: String(e && e.stack || e) })); });
