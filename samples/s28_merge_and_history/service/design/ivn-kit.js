/* ivn-kit 0.1.0 — optional behaviour for the iVendNext partner design kit.
 * No dependencies, no build step, and NO network call of its own: link search calls a
 * function YOUR page supplies. Everything hangs off one global: window.ivnKit.
 *   ivnKit.applyTheme(theme)          tenant theme from the page context → allow-listed CSS variables
 *   ivnKit.applyDir(lang)             "ar", "he", "fa", "ur" (any region) → dir="rtl"
 *   ivnKit.openDialog(el) / closeDialog(el)
 *   ivnKit.toast(message, {kind, timeout})
 *   ivnKit.linkSearch(inputEl, {search, onPick})
 */
(function () {
  "use strict";
  var VERSION = "0.1.0";
  var root = document.documentElement;

  /* ── Theme ────────────────────────────────────────────────────────────────
   * theme = { mode: "light" | "dark", vars: { "--ivn-primary": "#0b4d69", ... } }
   * Only the variables below may be set, and only with a value of the right kind.
   * Anything else is skipped and reported back, never applied. */
  var COLOUR = "colour", LENGTH = "length", SCALE = "scale";
  var THEME_VARS = {
    "--ivn-bg": COLOUR, "--ivn-surface": COLOUR, "--ivn-border": COLOUR,
    "--ivn-text": COLOUR, "--ivn-text-muted": COLOUR,
    "--ivn-primary": COLOUR, "--ivn-primary-strong": COLOUR, "--ivn-on-primary": COLOUR,
    "--ivn-focus": COLOUR,
    "--ivn-radius": LENGTH, "--ivn-radius-lg": LENGTH,
    "--ivn-font-scale": SCALE
  };
  /* The names the product's page context sends (a partner page's `theme.vars`, the till's own
   * tokens) map onto the kit's: card → surface, ink → text, muted → text-muted, line → border,
   * accent → primary (and the primary button's ground). The kit's own names still work. */
  var CONTEXT_NAMES = {
    "--ivn-card": ["--ivn-surface"], "--ivn-ink": ["--ivn-text"], "--ivn-muted": ["--ivn-text-muted"],
    "--ivn-line": ["--ivn-border"], "--ivn-accent": ["--ivn-primary", "--ivn-primary-strong"]
  };
  var RE_HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
  var RE_FUNC = /^(?:rgb|rgba|hsl|hsla)\(\s*[0-9.%\s,\/+-]+\)$/i;
  var RE_LENGTH = /^(?:0|\d{1,3}(?:\.\d{1,3})?(?:px|rem|em))$/;
  var RE_SCALE = /^\d(?:\.\d{1,3})?$/;
  var FORBIDDEN = /url\(|;|\}|\{|expression|\\|<|>/i;

  function validValue(kind, raw) {
    if (typeof raw === "number") raw = String(raw);
    if (typeof raw !== "string") return null;
    var v = raw.trim();
    if (!v || v.length > 64 || FORBIDDEN.test(v)) return null;
    if (kind === COLOUR) return RE_HEX.test(v) || RE_FUNC.test(v) ? v : null;
    if (kind === LENGTH) return RE_LENGTH.test(v) ? v : null;
    if (kind === SCALE) {
      var n = parseFloat(v);
      return RE_SCALE.test(v) && n >= 0.75 && n <= 1.5 ? v : null;
    }
    return null;
  }

  function applyTheme(theme) {
    var result = { applied: [], rejected: [] };
    if (!theme || typeof theme !== "object") return result;
    if (theme.mode === "dark" || theme.mode === "light") root.setAttribute("data-theme", theme.mode);
    var vars = theme.vars && typeof theme.vars === "object" ? theme.vars : {};
    var own = function (n) { return Object.prototype.hasOwnProperty.call(vars, n); };
    Object.keys(vars).forEach(function (name) {
      var targets = Object.prototype.hasOwnProperty.call(CONTEXT_NAMES, name) ? CONTEXT_NAMES[name] : [name];
      var kind = Object.prototype.hasOwnProperty.call(THEME_VARS, targets[0]) ? THEME_VARS[targets[0]] : null;
      var value = kind ? validValue(kind, vars[name]) : null;
      if (value === null) { result.rejected.push(name); return; }
      targets.forEach(function (t) {
        if (t !== name && own(t)) return;   // a kit name given beside its context name wins
        root.style.setProperty(t, value);
      });
      result.applied.push(name);
    });
    return result;
  }

  /* ── Direction ──────────────────────────────────────────────────────────── */
  var RTL_LANGS = ["ar", "he", "fa", "ur"];
  function applyDir(lang) {
    var primary = String(lang || "").toLowerCase().split(/[-_]/)[0];
    var dir = RTL_LANGS.indexOf(primary) >= 0 ? "rtl" : "ltr";
    root.setAttribute("dir", dir);
    if (/^[a-z]{2,3}$/.test(primary)) root.setAttribute("lang", String(lang).replace("_", "-"));
    return dir;
  }

  /* ── Dialog: the browser's own modal <dialog> does Esc and keeps focus inside the page. ── */
  var FOCUSABLE = "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";
  function openDialog(el) {
    if (!el || el.open) return;
    wireDialog(el);
    el._ivnOpener = document.activeElement;
    el.showModal();
    var first = el.querySelector("[autofocus]") || el.querySelector(".ivn-dialog-body " + FOCUSABLE) || el.querySelector(FOCUSABLE);
    if (first) first.focus();
  }
  function closeDialog(el, value) {
    if (el && el.open) el.close(value || "");
  }
  function trapTab(e) {   // keep Tab inside the dialog instead of leaving for the browser bar
    var dlg = e.currentTarget;
    if (e.key !== "Tab") return;
    var items = Array.prototype.filter.call(dlg.querySelectorAll(FOCUSABLE), function (n) { return n.offsetParent !== null; });
    if (!items.length) return;
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
  }
  function wireDialog(dlg) {
    if (dlg._ivnWired) return;
    dlg._ivnWired = true;
    dlg.addEventListener("keydown", trapTab);
    dlg.addEventListener("close", function () {
      if (dlg._ivnOpener && dlg._ivnOpener.focus) dlg._ivnOpener.focus();
    });
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg) closeDialog(dlg, "backdrop");             // click outside the box
      var closer = e.target.closest("[data-ivn-close]");
      if (closer) closeDialog(dlg, closer.getAttribute("data-ivn-close"));
    });
  }
  function wireDialogs(scope) {
    Array.prototype.forEach.call((scope || document).querySelectorAll("dialog.ivn-dialog"), wireDialog);
    Array.prototype.forEach.call((scope || document).querySelectorAll("[data-ivn-open]"), function (btn) {
      if (btn._ivnWired) return;
      btn._ivnWired = true;
      btn.addEventListener("click", function () { openDialog(document.getElementById(btn.getAttribute("data-ivn-open"))); });
    });
  }

  /* ── Toast: text only (never HTML), one polite live region. ─────────────── */
  function toast(message, opts) {
    opts = opts || {};
    var region = document.querySelector(".ivn-toasts");
    if (!region) {
      region = document.createElement("div");
      region.className = "ivn-toasts";
      region.setAttribute("role", "status");
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    var t = document.createElement("div");
    t.className = "ivn-toast" + (opts.kind ? " ivn-toast-" + String(opts.kind).replace(/[^a-z]/g, "") : "");
    t.textContent = String(message);
    region.appendChild(t);
    var ms = typeof opts.timeout === "number" ? opts.timeout : 4000;
    if (ms > 0) setTimeout(function () { hideToast(t); }, ms);
    return t;
  }
  function hideToast(t) { if (t && t.parentNode) t.parentNode.removeChild(t); }

  /* ── Link search ──────────────────────────────────────────────────────────
   * opts.search(text) → Promise of [{value, label, description}] — YOUR function, YOUR backend.
   * opts.onPick(item) is called when the user picks a row (click or Enter). */
  var seq = 0;
  function linkSearch(input, opts) {
    var id = "ivn-ls-" + (++seq);
    var list = document.createElement("ul");
    list.className = "ivn-results"; list.id = id; list.hidden = true;
    list.setAttribute("role", "listbox");
    input.parentNode.appendChild(list);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", id);
    input.setAttribute("autocomplete", "off");
    var items = [], active = -1, timer = null, asked = 0;

    function show(open) { list.hidden = !open; input.setAttribute("aria-expanded", open ? "true" : "false"); }
    function mark(i) {
      active = i;
      Array.prototype.forEach.call(list.children, function (li, n) { li.setAttribute("aria-selected", n === i ? "true" : "false"); });
      if (i >= 0 && list.children[i]) { input.setAttribute("aria-activedescendant", list.children[i].id); list.children[i].scrollIntoView({ block: "nearest" }); }
      else input.removeAttribute("aria-activedescendant");
    }
    function render(rows) {
      items = Array.isArray(rows) ? rows.slice(0, 20) : [];
      list.textContent = "";
      if (!items.length) {
        var none = document.createElement("li");
        none.className = "ivn-results-empty"; none.textContent = opts.emptyText || "No matches";
        list.appendChild(none);
      }
      items.forEach(function (it, n) {
        var li = document.createElement("li");
        li.id = id + "-" + n; li.setAttribute("role", "option");
        li.textContent = String(it.label != null ? it.label : it.value);
        if (it.description) {
          var sub = document.createElement("span");
          sub.className = "ivn-result-sub"; sub.textContent = String(it.description);
          li.appendChild(sub);
        }
        li.addEventListener("mousedown", function (e) { e.preventDefault(); pick(n); });
        list.appendChild(li);
      });
      mark(items.length ? 0 : -1);
      show(true);
    }
    function pick(n) {
      var it = items[n];
      if (!it) return;
      input.value = String(it.label != null ? it.label : it.value);
      show(false);
      if (opts.onPick) opts.onPick(it);
    }
    function ask() {
      var mine = ++asked;
      Promise.resolve(opts.search(input.value.trim())).then(function (rows) {
        if (mine === asked) render(rows);              // drop answers that arrive out of order
      }, function () { if (mine === asked) render([]); });
    }
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(ask, 200); });
    input.addEventListener("focus", function () { if (!input.value) ask(); });
    input.addEventListener("blur", function () { show(false); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { if (list.hidden) { ask(); } else { mark(Math.min(active + 1, items.length - 1)); } e.preventDefault(); }
      else if (e.key === "ArrowUp") { mark(Math.max(active - 1, 0)); e.preventDefault(); }
      else if (e.key === "Enter" && !list.hidden && active >= 0) { pick(active); e.preventDefault(); }
      else if (e.key === "Escape" && !list.hidden) { show(false); e.preventDefault(); e.stopPropagation(); }
    });
    return { close: function () { show(false); } };
  }

  window.ivnKit = {
    version: VERSION, themeVars: Object.keys(THEME_VARS),
    applyTheme: applyTheme, applyDir: applyDir,
    openDialog: openDialog, closeDialog: closeDialog, wireDialogs: wireDialogs,
    toast: toast, hideToast: hideToast, linkSearch: linkSearch
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { wireDialogs(); });
  else wireDialogs();
})();
