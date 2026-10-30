// S59 — runs the screen's page (service/fit.js + service/page.js) under node on a small stand-in for the browser, for
// tests/test_page.py. The stand-in keeps a tree of elements with their text, classes, attributes and click handlers.
// With a layout (opts.layout = {board, inner}) it gives each box a height (a line, a heading 20; a button 30; a "still
// to make" dish 10) and stacks the board's tickets in one column from its top, so the page's own folding and paging
// run; without one every box is empty. It proves the page's own rules, never how a screen looks.
//
//   node page_harness.js <scenario> '<json options>'   → prints one JSON answer
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const SERVICE = path.join(__dirname, "..", "service");
let LAYOUT = null, BOARD = null, STRIP = null;
const BASE = { LI: 20, P: 20, H2: 20, BUTTON: 30 };
function heightOf(e) {
  if (!e.tagName || e.hidden) return 0;
  let h = BASE[e.tagName] || 0;
  if (e.parentNode === STRIP || e.className.split(" ").includes("ksc-part-head")) h = Math.max(h, e.parentNode === STRIP ? 10 : 20);
  h += e.children.reduce((sum, c) => sum + heightOf(c), 0);
  const cap = parseFloat(e.style.maxBlockSize);
  return isNaN(cap) ? h : Math.min(h, cap);
}
function topOf(e) {                 // inside the board, a box starts below its earlier siblings, in one column
  if (e === BOARD || !e.parentNode) return 0;
  let top = topOf(e.parentNode);
  for (const c of e.parentNode.children) { if (c === e) break; top += heightOf(c); }
  return top;
}
function inBoard(e) { for (let x = e; x; x = x.parentNode) if (x === BOARD) return true; return false; }
function rectOf(e) {
  if (!LAYOUT) return { top: 0, bottom: 0, height: 0, left: 0, right: 0, width: 0 };
  if (e === BOARD) return { top: 0, bottom: LAYOUT.board, height: LAYOUT.board, left: 0, right: 100, width: 100 };
  const top = inBoard(e) ? topOf(e) : 0, h = heightOf(e);
  return { top, bottom: top + h, height: h, left: 0, right: 100, width: 100 };
}

function element(tag) {
  const e = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, attrs: {}, listeners: {}, hidden: false,
    disabled: false, title: "", className: "", _text: "", style: { setProperty() {}, maxBlockSize: "" },
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
    querySelectorAll(sel) {            // one class, or several joined (".a.b")
      const cls = sel.split(".").filter(Boolean);
      return this.all().filter((c) => c.classList && cls.every((k) => c.classList.contains(k)));
    },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    getBoundingClientRect() { return rectOf(this); },
    get scrollHeight() { return LAYOUT && this === BOARD ? this.children.reduce((h, c) => h + heightOf(c), 0) : 0; },
    get clientHeight() { return LAYOUT && this === BOARD ? LAYOUT.board : 0; },
  };
  return e;
}
function text(t) { return { textContent: String(t), parentNode: null, all: () => [] }; }

function run(opts) {
  const byId = {}, body = element("body");
  LAYOUT = opts.layout || null;
  const html = fs.readFileSync(path.join(SERVICE, "page.html"), "utf8");
  for (const m of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)) { byId[m[2]] = element(m[1]); body.appendChild(byId[m[2]]); }
  BOARD = byId.board; STRIP = byId.waiting;
  const calls = [], answers = opts.answers || {}, winListeners = {}, timers = [];
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
    ivnKit: { applyTheme() {}, applyDir() {}, openDialog(el) { el.open = true; }, closeDialog(el) { el.open = false; } },
    innerHeight: (opts.layout || {}).inner || 0,
    getComputedStyle: () => ({ paddingBottom: "0", paddingTop: "0" }),
    addEventListener(type, fn) { (winListeners[type] = winListeners[type] || []).push(fn); },
    performance: { now: () => clock.t }, URLSearchParams, Date, console,
    setTimeout: (fn, ms) => { timers.push(ms); return 0; }, clearTimeout() {}, setInterval: () => 0, requestAnimationFrame: () => 0, cancelAnimationFrame() {},
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
  return { win, byId, body, calls, store, clock, winListeners, timers };
}
const settle = () => new Promise((r) => setImmediate(r));
async function settled() { for (let i = 0; i < 20; i++) await settle(); }

function snapshot(p) {
  const slips = p.byId.board.children.filter((c) => c.classList.contains("ksc-slip"));
  const vis = (e) => !!e && !e.hidden;
  const nums = p.byId.board.querySelectorAll("ksc-num").filter((n) => !n.classList.contains("ksc-num-more"));
  return {
    numbers: { shown: nums.filter(vis).length, more: p.byId.board.querySelectorAll(".ksc-num-more").map((n) => n.textContent) },
    shown: slips.filter(vis).map((s) => s.getAttribute("data-key")),
    slips: slips.filter(vis).map((s) => ({
      key: s.getAttribute("data-key"), height: heightOf(s), tall: s.classList.contains("is-tall"),
      more: vis(s.querySelector(".ksc-more")) ? s.querySelector(".ksc-more").textContent : "",
      act: vis(s.querySelector(".ksc-act")), actOn: !!s.querySelector(".ksc-act") && !s.querySelector(".ksc-act").disabled,
      hiddenLines: s.querySelectorAll(".ksc-line").filter((x) => x.hidden).length,
      voidPart: s.querySelectorAll(".ksc-part").filter((x) => x.classList.contains("is-void"))
        .map((x) => ({ shown: vis(x), lines: x.querySelectorAll(".ksc-line").filter(vis).length })),
    })),
    pager: { more: vis(p.byId.more) ? p.byId.more.textContent : "", prev: vis(p.byId.prev) && !p.byId.prev.disabled,
             next: vis(p.byId.next) && !p.byId.next.disabled },
    late: p.byId.next.classList.contains("is-late"), note: vis(p.byId.note) ? p.byId.note.textContent : "",
    strip: { dishes: p.byId.waiting.querySelectorAll(".ksc-wait").filter(vis).length, height: heightOf(p.byId.waiting),
             rest: vis(p.byId.waiting.querySelector(".ksc-wait-more")) ? p.byId.waiting.querySelector(".ksc-wait-more").textContent : "" },
  };
}

const SCENARIOS = {
  // the page's own fitting, with a layout: what is shown, folded and paged; then the taps asked for
  async fit(opts) {
    const p = run(opts);
    await settled();
    const out = { first: snapshot(p), timers: p.timers.slice() };
    out.moves = 0;
    for (const step of opts.steps || []) {
      if (step === "next" || step === "prev") { p.byId[step].click(); out[step] = snapshot(p); }
      if (step === "read") { (p.winListeners.online || []).forEach((fn) => fn()); await settled(); out.read = snapshot(p); }
      if (step.startsWith("wait:")) p.clock.t += Number(step.slice(5));
      if (step === "tap") {             // the first shown ticket's own button (Start, Ready, Bump)
        const slip = p.byId.board.children.find((c) => c.classList.contains("ksc-slip") && !c.hidden);
        slip.querySelector(".ksc-act").click(); await settled();
        out.moves = p.calls.filter((c) => c.path === "/ksc/move").length;
        out.taps = (out.taps || []).concat([out.moves]);
      }
      if (step.startsWith("more:")) {
        const slip = p.byId.board.children.find((c) => c.getAttribute("data-key") === step.slice(5));
        slip.querySelector(".ksc-more").click();
        const b = p.byId["ticket-body"];
        out.dialog = { open: !!p.byId["ticket-dialog"].open, voidBanner: b.querySelectorAll(".ksc-void").length,
                       voidBox: b.children.some((c) => c.classList && c.classList.contains("is-void")),
                       lines: b.querySelectorAll(".ksc-line").length };
      }
    }
    return out;
  },
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
