// S56 — runs the guest page (service/page.js) under node on a small stand-in for the browser, for tests/test_page.py.
// The stand-in keeps a tree of elements with their text, classes, attributes and click handlers, and answers the page's
// two calls from opts.answers. It proves the page's own rules (sizes together, the total, the retailer's words in <bdi>
// and no guessed direction), never how a screen looks.
//
//   node page_harness.js '<json options>'   → prints one JSON answer
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm");
const SERVICE = path.join(__dirname, "..", "service");

function element(tag) {
  const e = {
    tagName: String(tag).toUpperCase(), children: [], parentNode: null, attrs: {}, listeners: {}, hidden: false,
    disabled: false, className: "", _text: "", dir: "", checked: false,
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); },
    set textContent(v) { this.children = []; this._text = String(v); },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.children.push(c); return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parentNode = null; return c; },
    remove() { if (this.parentNode) this.parentNode.removeChild(this); },
    scrollIntoView() { this.scrolled = (this.scrolled || 0) + 1; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
    click() { (this.listeners.click || []).forEach((fn) => fn({})); },
    all() { return this.children.reduce((out, c) => out.concat([c], c.all()), []); },
    querySelectorAll(sel) { const k = sel.split(".").filter(Boolean); return this.all().filter((c) => k.every((x) => c.className.split(" ").includes(x))); },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
  };
  return e;
}

async function main(opts) {
  const byId = {}, body = element("body"), calls = [], pending = [];
  const html = fs.readFileSync(path.join(SERVICE, "page.html"), "utf8");
  for (const m of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)) { byId[m[2]] = element(m[1]); body.appendChild(byId[m[2]]); }
  const htmlDirs = (html.match(/\sdir=/g) || []).length;
  const win = {
    location: { hash: "#s=bistro.example.com&t=GOR-CODE-00001.1.sig" },
    navigator: { language: opts.language || "en-GB" },
    document: { documentElement: element("html"), getElementById: (id) => byId[id] || null, createElement: element, createTextNode: (t) => { const e = element("#text"); e._text = String(t); return e; },
                addEventListener() {}, querySelector: (s) => body.querySelector(s) },
    fetch: (url, init) => {
      calls.push(Object.assign({ path: url }, JSON.parse(init.body)));
      const queue = opts.answers[url] || [{ state: "unavailable" }];
      const a = queue.length > 1 ? queue.shift() : queue[0];
      return Promise.resolve({ json: () => Promise.resolve(a) });
    },
    crypto: { randomUUID: () => "6f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a" },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    setTimeout: (fn, ms) => { pending.push({ ms, fn }); return pending.length; }, clearTimeout() {},
    Intl, URLSearchParams, Date, Array, Math, JSON, String, Object, Number, Promise, console,
  };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(fs.readFileSync(path.join(SERVICE, "page.js"), "utf8"), win, { filename: "page.js" });
  const settle = () => new Promise((r) => setImmediate(r));
  const settled = async () => { for (let i = 0; i < 20; i++) await settle(); };
  await settled();
  const dish = (name) => byId.menu.querySelectorAll(".dish").find((d) => d.querySelector(".dish-name").textContent === name);
  const steps = [];
  for (const st of opts.steps || []) {
    const d = dish(st.dish);
    if (st.size) d.querySelectorAll(".size").find((b) => b.children[0].textContent === st.size).click();
    if (st.add) d.querySelector(".add").click();
    if (st.again) { pending.splice(0).forEach((t) => t.fn()); }
    if (st.imgerror) { d.querySelector(".photo").children[0].listeners.error.forEach((fn) => fn({})); }
    if (st.plus !== undefined) { byId.lines.querySelectorAll(".qty")[st.plus].children[2].click(); }
    if (st.pick !== undefined) { d.querySelector(".choose").querySelectorAll(".choice")[0].children[0].checked = !!st.pick; d.querySelector(".choose").querySelector(".add").click(); }
    if (st.menuopen) { d.querySelector(".add").click(); }
    await settled();
    steps.push({ total: byId.total.textContent, basket: byId.lines.querySelectorAll(".line-name").map((n) => n.textContent),
                 tile: !!d.querySelector(".tile"), note: byId.note.textContent, noteBdi: byId.note.children[0] ? byId.note.children[0].tagName : "" });
  }
  const dirs = [byId.where, byId.note, ...byId.menu.all(), ...byId.lines.all()].filter((e) => e.dir).length;
  const own = byId.menu.querySelectorAll(".dish-name").concat(byId.menu.querySelectorAll(".size"), byId.lines.querySelectorAll(".line-name"));
  return {
    where: byId.where.textContent, whereBdi: byId.where.children[0] ? byId.where.children[0].tagName : "",
    dishes: byId.menu.querySelectorAll(".dish").map((d) => ({
      name: d.querySelector(".dish-name").textContent, price: (d.querySelector(".dish-head").querySelector(".price") || { textContent: "" }).textContent,
      sizes: d.querySelectorAll(".size").map((b) => b.textContent + (b.className.includes("on") ? "*" : "")),
      img: (d.querySelector(".photo").children[0] || {}).tagName === "IMG" ? d.querySelector(".photo").children[0].src : "",
      tile: !!d.querySelector(".tile"), button: d.querySelector(".add").textContent })),
    bdiWrapped: own.every((e) => e.children[0] && e.children[0].tagName === "BDI"),
    dirs, htmlDirs, steps, calls: calls.map((c) => c.path), timers: pending.map((t) => t.ms),
    scrolled: byId.note.scrolled || 0, picks: byId.menu.querySelectorAll(".size").map((b) => b.className),
  };
}
main(JSON.parse(process.argv[2] || "{}")).then((o) => console.log(JSON.stringify(o)), (e) => { console.error(e); process.exit(1); });
