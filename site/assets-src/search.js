/* site/assets-src/search.js — the partner site's one search.
 *
 * The index is search-index.json, written by site/build.py from the needs cards and the guide, recipe and sample pages. The
 * ranking library is MiniSearch, vendored unchanged in assets/vendor/ (its hash is pinned by site/test_site.py) and loaded the
 * first time a visitor uses the box. A card's words in the customer's own phrasing (its "asks" line) and their synonyms
 * (site/synonyms.txt) count most, then its title, then its limits and what to tell the customer, then the rest; a card outranks
 * a page of equal score. A one-letter slip still finds the word, and a word is found as it is typed.
 *
 *   - every page: the header box shows at most six results as you type, needs first (at most four when a page matches too);
 *     Enter opens search.html;
 *   - search.html: every result, needs first, with filters by area, door and verdict (the filters narrow the needs);
 *   - each search calls window.ivnTrack("search", {q, n}) if the page has one (n = 0 is a search with no result).
 *
 * Without script the header box opens needs/all.html, every card on one page for the browser's own find.
 * site/test_search.mjs loads this file in node and runs the golden queries of site/search_golden.json against the built index.
 */
(function (root) {
  "use strict";
  var VENDOR = "assets/vendor/minisearch-7.2.0/index.js";
  var INDEX = "search-index.json";
  var KINDS = ["need", "recipe", "sample", "guide"];
  var KIND_NAME = { need: "Need", recipe: "Recipe", sample: "Sample", guide: "Guide" };
  var STOP = {};
  ("a an and are as at be by can do does for from has have how i in is it its me my of on or our so that the their them " +
   "this to us we what when which who will with you your").split(" ").forEach(function (w) { STOP[w] = true; });

  function stem(t) {                       // a plural and an "-ing" set aside, the same way for the index and the query
    if (t.length > 6 && /ing$/.test(t)) return t.slice(0, -3);
    if (t.length > 4 && /(ch|sh|x|z|ss)es$/.test(t)) return t.slice(0, -2);
    if (t.length > 4 && /ies$/.test(t)) return t.slice(0, -3) + "y";
    if (t.length > 3 && /s$/.test(t) && !/ss$/.test(t)) return t.slice(0, -1);
    return t;
  }

  function processTerm(term) {
    var t = term.toLowerCase();
    return (t.length < 2 || STOP[t]) ? null : stem(t);
  }

  var OPTIONS = {
    fields: ["a", "s", "t", "tp", "l", "c", "b"],
    storeFields: ["k", "t", "a", "u", "v", "ar", "d", "st", "tp"],
    processTerm: processTerm,
    searchOptions: {
      boost: { a: 4, s: 3, t: 2.5, tp: 1.5, l: 1.2, c: 1.2, b: 1 },
      prefix: function (term) { return term.length >= 3; },
      fuzzy: function (term) { return term.length >= 7 ? 2 : term.length >= 4 ? 1 : false; },
      combineWith: "OR",
      boostDocument: function (id, term, stored) { return stored && stored.k === "need" ? 1.5 : 1; }
    }
  };

  function create(docs, MiniSearch) {
    var ms = new (MiniSearch || root.MiniSearch)(OPTIONS);
    ms.addAll(docs);
    return ms;
  }

  function narrowed(f) { return !!(f && (f.area || f.door || f.status)); }

  /* Every result for the query, best first. With a filter set, needs only, and those that match it; with no words but a
   * filter, every need that matches it. */
  function rank(ms, q, f) {
    var opts = {};
    if (narrowed(f)) {
      opts.filter = function (r) {
        return r.k === "need" && (!f.area || r.ar === f.area) && (!f.door || r.d === f.door) && (!f.status || r.st === f.status);
      };
    }
    q = (q || "").trim();
    if (!q) return narrowed(f) ? ms.search(ms.constructor.wildcard, opts) : [];
    return ms.search(swapped(ms, q), opts);
  }

  /* Two letters swapped ("alret", "stcok") are two changes to the fuzzy match, which a short word is not allowed. So a word
   * that finds nothing at all, not even as the start of a word, is searched again with each pair of neighbouring letters
   * swapped back; a word that finds something is left alone, so a correct word never gathers lookalikes. */
  function swapped(ms, q) {
    var extra = [];
    q.split(/[\s\p{P}]+/u).forEach(function (w) {
      var t = processTerm(w);
      if (!t || t.length < 4 || ms.search(w, { fuzzy: false, prefix: true }).length) return;
      for (var i = 0; i < w.length - 1; i++) extra.push(w.slice(0, i) + w[i + 1] + w[i] + w.slice(i + 2));
    });
    return extra.length ? q + " " + extra.join(" ") : q;
  }

  function grouped(results) {
    var g = { need: [], recipe: [], sample: [], guide: [] };
    results.forEach(function (r) { (g[r.k] || g.guide).push(r); });
    return g;
  }

  /* The header's list: at most n (six), needs first. Needs take n - 2 places when pages match too, so the best recipe, sample
   * or guide page is never pushed out by a seventh need; either side fills the other's empty places. */
  function instant(results, n) {
    n = n || 6;
    var needs = results.filter(function (r) { return r.k === "need"; });
    var pages = results.filter(function (r) { return r.k !== "need"; });
    var k = Math.max(n - Math.min(2, pages.length), 0);
    return needs.slice(0, k).concat(pages).slice(0, n).concat(needs.slice(k)).slice(0, n)
      .sort(function (a, b) { return (a.k === "need" ? 0 : 1) - (b.k === "need" ? 0 : 1); });
  }

  // engine(document, root) loads the library and the index once and resolves to the ranker; Plan a project uses it too.
  var api = { create: create, rank: rank, grouped: grouped, instant: instant, processTerm: processTerm, OPTIONS: OPTIONS,
              engine: engine };

  // ── the page ──────────────────────────────────────────────────────────────────────────────────────────────────────
  function track(q, n) {
    try { if (typeof root.ivnTrack === "function") root.ivnTrack("search", { q: q, n: n }); } catch (e) { /* never break search */ }
  }

  function el(doc, tag, cls, text) {
    var e = doc.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  var loading = null;
  function engine(doc, base) {
    if (loading) return loading;
    var lib = root.MiniSearch ? Promise.resolve() : new Promise(function (ok, fail) {
      var s = doc.createElement("script");
      s.src = base + VENDOR;
      s.onload = ok;
      s.onerror = fail;
      doc.head.appendChild(s);
    });
    loading = Promise.all([lib, fetch(base + INDEX).then(function (r) { return r.json(); })])
      .then(function (both) { return create(both[1]); });
    loading.catch(function () { loading = null; });
    return loading;
  }

  function searchUrl(base, q) { return base + "search.html" + (q ? "?q=" + encodeURIComponent(q) : ""); }

  function wireHeader(doc) {
    var form = doc.querySelector("form.site-search");
    if (!form) return;
    var base = form.getAttribute("data-root") || "";
    var input = form.querySelector("input");
    var pop = form.querySelector(".search-pop");
    var active = -1, timer = null, sent = null, pending = null;
    function flush() {                              // count the search now, before the visitor leaves for a result
      clearTimeout(sent);
      if (pending) track(pending[0], pending[1]);
      pending = null;
    }
    var said = el(doc, "span", "vh");               // read out by a screen reader: how many results the list holds
    said.setAttribute("aria-live", "polite");
    form.appendChild(said);

    function options() { return pop.querySelectorAll("[role=option]"); }
    function close() {
      pop.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }
    function mark(i) {
      var opts = options();
      if (!opts.length) return;
      active = (i + opts.length) % opts.length;
      for (var j = 0; j < opts.length; j++) opts[j].classList.toggle("is-active", j === active);
      input.setAttribute("aria-activedescendant", opts[active].id);
    }
    function option(href, main, sub) {
      var li = el(doc, "li");
      li.setAttribute("role", "option");
      li.id = "q-top-opt-" + options().length;
      var a = el(doc, "a");
      a.href = href;
      a.tabIndex = -1;
      a.appendChild(el(doc, "span", "pop-main", main));
      if (sub) a.appendChild(el(doc, "span", "pop-sub", sub));
      li.appendChild(a);
      pop.appendChild(li);
    }
    function show(q, results) {
      pop.textContent = "";
      active = -1;
      input.removeAttribute("aria-activedescendant");
      if (!q) { close(); return; }
      var top = instant(results, 6);
      top.forEach(function (r) {
        option(base + r.u, r.t, KIND_NAME[r.k] + (r.v ? " · " + r.v : ""));
      });
      if (top.length) {
        option(searchUrl(base, q), "All " + results.length + " results for “" + q + "”", "");
        option(base + "feedback/point_request.html", "Not what the customer needs?", "Tell us the need: we read every request");
      } else option(base + "feedback/point_request.html", "Nothing matches “" + q + "”", "Tell us the need: we read every request");
      pop.hidden = false;
      input.setAttribute("aria-expanded", "true");
      said.textContent = results.length ? results.length + " results, " + top.length + " shown" : "No result";
      clearTimeout(sent);
      pending = [q, results.length];
      sent = setTimeout(flush, 1200);
    }
    function run() {
      var q = input.value.trim();
      if (!q) { close(); return; }
      engine(doc, base).then(function (ms) { if (input.value.trim() === q) show(q, rank(ms, q)); }, close);
    }
    input.addEventListener("focus", function () { engine(doc, base); });
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(run, 90); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (pop.hidden) { run(); return; }
        e.preventDefault();
        mark(active + (e.key === "ArrowDown" ? 1 : -1));
      } else if (e.key === "Escape") {
        if (!pop.hidden) { e.preventDefault(); close(); } else { input.value = ""; }
      } else if (e.key === "Enter" && active >= 0 && !pop.hidden) {
        e.preventDefault();
        flush();
        root.location.href = options()[active].querySelector("a").href;
      }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearTimeout(sent);                             // search.html counts this search; the list's count would be a second
      pending = null;
      root.location.href = searchUrl(base, input.value.trim());
    });
    form.addEventListener("focusout", function () {
      setTimeout(function () { if (!form.contains(doc.activeElement)) close(); }, 0);
    });
    pop.addEventListener("click", flush);
    doc.addEventListener("click", function (e) { if (!form.contains(e.target)) close(); });
  }

  function wireResults(doc) {
    var out = doc.getElementById("search-results");
    if (!out) return;
    var form = doc.querySelector("form.search-page");
    var base = (doc.querySelector("form.site-search") || form).getAttribute("data-root") || "";
    var fields = { q: form.querySelector("[name=q]"), area: form.querySelector("[name=area]"),
                   door: form.querySelector("[name=door]"), status: form.querySelector("[name=status]") };
    var label = function (sel, v) {
      var o = sel && sel.querySelector('option[value="' + v + '"]');
      return o ? o.textContent : v;
    };
    var params = new URLSearchParams(root.location.search);
    Object.keys(fields).forEach(function (k) { if (fields[k]) fields[k].value = params.get(k) || ""; });

    function para(parts) {                   // a paragraph of text and links: [["text"], ["link text", href], …]
      var p = el(doc, "p");
      parts.forEach(function (x) {
        if (x.length > 1) { var a = el(doc, "a", null, x[0]); a.href = x[1]; p.appendChild(a); }
        else p.appendChild(doc.createTextNode(x[0]));
      });
      return p;
    }
    function item(r) {
      var li = el(doc, "li"), a = el(doc, "a", null, r.t);
      a.href = base + r.u;
      li.appendChild(a);
      if (r.k === "need") {
        li.appendChild(el(doc, "span", "res-asks", "“" + r.a + "”"));
        li.appendChild(el(doc, "span", "res-meta", r.v + " · " + label(fields.door, r.d) + " · " + label(fields.area, r.ar) + " › " + r.tp));
      }
      return li;
    }
    function render(q, f, results) {
      out.textContent = "";
      var g = grouped(results);
      if (!results.length) {
        out.appendChild(para([[q ? "Nothing on this site matches “" + q + "”" + (narrowed(f) ? " with these filters." : ".")
                                 : "Type what the customer asked for, in their words."]]));
        if (q) {
          out.appendChild(para([["If a customer needs it, "], ["tell us the need", base + "feedback/point_request.html"],
                                [": it is how we learn what to build next. Or browse "], ["the needs catalogue", base + "needs/index.html"],
                                [" or "], ["every need on one page", base + "needs/all.html"], ["."]]));
        }
        return;
      }
      out.appendChild(el(doc, "p", "res-count", results.length + (results.length === 1 ? " result" : " results") +
                         (q ? " for “" + q + "”" : "") + (narrowed(f) ? ", needs only (a filter is set)" : "") + "."));
      var cap = { need: 60, recipe: 15, sample: 15, guide: 15 };
      var head = { need: "Needs", recipe: "Recipes", sample: "Samples", guide: "Guide and other pages" };
      KINDS.forEach(function (k) {
        if (!g[k].length) return;
        out.appendChild(el(doc, "h2", null, head[k] + " (" + g[k].length + ")"));
        var ul = el(doc, "ul", "res-list");
        g[k].slice(0, cap[k]).forEach(function (r) { ul.appendChild(item(r)); });
        out.appendChild(ul);
      });
      out.appendChild(para([["Not what the customer needs? "], ["Tell us the need", base + "feedback/point_request.html"],
                            [": a need with no card is how we learn what to build next."]]));
    }
    var counted = null;
    function go(push) {
      var q = fields.q.value.trim();
      var f = { area: fields.area.value, door: fields.door.value, status: fields.status.value };
      if (push) {
        var p = new URLSearchParams();
        if (q) p.set("q", q);
        ["area", "door", "status"].forEach(function (k) { if (f[k]) p.set(k, f[k]); });
        var s = p.toString();
        root.history.replaceState(null, "", root.location.pathname + (s ? "?" + s : ""));
      }
      out.textContent = "Searching…";
      engine(doc, base).then(function (ms) {
        var results = rank(ms, q, f);
        render(q, f, results);
        if (q && q !== counted) { counted = q; track(q, results.length); }   // a filter change is not a new search
      }, function () {
        out.textContent = "";
        out.appendChild(para([["The search could not load. Open "], ["every need on one page", base + "needs/all.html"],
                              [" and use your browser's find."]]));
      });
    }
    form.addEventListener("submit", function (e) { e.preventDefault(); go(true); });
    ["area", "door", "status"].forEach(function (k) { fields[k].addEventListener("change", function () { go(true); }); });
    go(false);
  }

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ivnSearch = api;
    if (root.document) { wireHeader(root.document); wireResults(root.document); }
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
