/* site/assets-src/plan.js — Plan a project: the visitor ticks the customer's needs and gets the shortlist.
 *
 * It reads catalogue.json (written by site/build.py from the cards) and finds needs with the site's one search
 * (window.ivnSearch, search.js). The shortlist is the address: plan.html?needs=id,id,… (an unknown id is left out, with a
 * message), so it can be sent to a colleague. It shows (a) the needs with verdict and door, (b) the order to build them
 * (each card's build_step, from build.py's BUILD_ORDER: the ladder's order, the manifest straight after configuration),
 * (c) the recipes and samples once each, with the needs each serves, (d) the limits to tell the customer, (e) the requests
 * to file, and (f) the blueprint rows to copy as Markdown, or the page to print. The rows are the cards' own, written at
 * build time from needs.py's blueprint_rows(); this file only numbers and joins them, so the copy equals what
 * `needs.py blueprint` prints for the same ids in the same order (site/test_plan.mjs holds that).
 * Each copy and print calls window.ivnTrack("plan_export", {how}) if the page has one; nothing is sent from here.
 * No account, no server, nothing stored. Without script the page is its seven steps and the link to the blueprint.
 */
(function (root) {
  "use strict";

  function ids(search) {                       // "?needs=a,b,a" → ["a", "b"]
    var raw = new URLSearchParams(search || "").get("needs") || "";
    var seen = {}, out = [];
    raw.split(",").forEach(function (s) {
      s = s.trim();
      if (s && !seen[s]) { seen[s] = true; out.push(s); }
    });
    return out;
  }

  function choose(catalogue, wanted) {         // the cards for the ids, in the order given, and the ids that are no card
    var by = {};
    catalogue.forEach(function (c) { by[c.id] = c; });
    var cards = [], unknown = [];
    wanted.forEach(function (i) { if (by[i]) cards.push(by[i]); else unknown.push(i); });
    return { cards: cards, unknown: unknown };
  }

  function order(cards) {                      // by build step; within a step, in the order the visitor chose them
    return cards.map(function (c, i) { return [c, i]; })
      .sort(function (a, b) { return a[0].build_step - b[0].build_step || a[1] - b[1]; })
      .map(function (x) { return x[0]; });
  }

  function steps(cards) {                      // [{step, why, cards}], in build order
    var out = [];
    order(cards).forEach(function (c) {
      var last = out[out.length - 1];
      if (last && last.step === c.build_step) last.cards.push(c);
      else out.push({ step: c.build_step, why: c.build_why, cards: [c] });
    });
    return out;
  }

  function proofs(cards) {                     // {recipes: [...], samples: [...]}, each path once, with the needs it serves
    var out = { recipes: [], samples: [] };
    ["recipes", "samples"].forEach(function (kind) {
      var at = {};
      order(cards).forEach(function (c) {
        (c[kind] || []).forEach(function (p) {
          var key = p.path.replace(/\/+$/, "");      // samples/x and samples/x/ are one sample
          if (!(key in at)) { at[key] = out[kind].length; out[kind].push({ path: p.path, title: p.title, page: p.page, url: p.url, needs: [] }); }
          var entry = out[kind][at[key]];
          if (entry.needs.indexOf(c) < 0) entry.needs.push(c);
        });
      });
    });
    return out;
  }

  function plain(s) {                           // a card's Markdown line as the words a reader sees
    return String(s).replace(/\*\*/g, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  }

  function limits(cards) {                     // [{card, lines}] for every chosen card with a limit, in build order
    return order(cards).filter(function (c) { return c.limits.length; })
      .map(function (c) { return { card: c, lines: c.limits.map(plain) }; });
  }

  function limitsText(cards) {
    return limits(cards).map(function (x) {
      return "- " + x.card.asks + " (" + x.card.verdict + ")\n" + x.lines.map(function (l) { return "  - " + l; }).join("\n");
    }).join("\n") + "\n";
  }

  function requests(cards) {                    // the forms to file (each handle once), what to ask us, and what to do instead
    var forms = [], at = {}, askUs = [], instead = [];
    order(cards).forEach(function (c) {
      (c.request_forms || []).forEach(function (f) {
        if (!(f.handle in at)) { at[f.handle] = forms.length; forms.push({ handle: f.handle, url: f.url, needs: [] }); }
        forms[at[f.handle]].needs.push(c);
      });
      c.limits.forEach(function (l) {
        if (/^\*\*Ask us:\*\*/.test(l)) askUs.push({ card: c, line: plain(l) });
        if (/^\*\*Instead:\*\*/.test(l)) instead.push({ card: c, line: plain(l) });
      });
    });
    return { forms: forms, askUs: askUs, instead: instead };
  }

  function blueprint(cards, head) {             // section (b) of the project blueprint, numbered in build order
    return head + "\n" + order(cards).map(function (c, i) { return "| " + (i + 1) + " " + c.blueprint_row; }).join("\n") + "\n";
  }

  var api = { ids: ids, choose: choose, order: order, steps: steps, proofs: proofs, limits: limits, limitsText: limitsText,
              requests: requests, blueprint: blueprint, plain: plain };

  // ── the page ──────────────────────────────────────────────────────────────────────────────────────────────────────
  function track(how) {
    try { if (typeof root.ivnTrack === "function") root.ivnTrack("plan_export", { how: how }); } catch (e) { /* never break */ }
  }

  function wire(doc) {
    var tool = doc.getElementById("plan-tool");
    if (!tool) return;
    var base = tool.getAttribute("data-root") || "";
    var head = tool.getAttribute("data-head") || "";
    var input = doc.getElementById("plan-q"), found = doc.getElementById("plan-found"), out = doc.getElementById("plan-out");
    var catalogue = [], chosen = [], unknown = [], timer = null;

    function el(tag, cls, text) {
      var e = doc.createElement(tag);
      if (cls) e.className = cls;
      if (text != null) e.textContent = text;
      return e;
    }
    function link(text, href) { var a = el("a", null, text); a.href = base + href; return a; }
    function needLink(c) { return link(c.asks, c.page); }
    function h2(id, text) { var h = el("h2", null, text); h.id = id; return h; }
    function button(text, fn) {
      var b = el("button", "site-btn site-btn-ghost", text);
      b.type = "button";
      b.addEventListener("click", fn);
      return b;
    }
    function forList(cs) {                       // " — for: need · need"
      var span = el("span", "plan-for", " — for: ");
      cs.forEach(function (c, i) { if (i) span.appendChild(doc.createTextNode(" · ")); span.appendChild(needLink(c)); });
      return span;
    }

    function save() {
      var q = chosen.length ? "?needs=" + chosen.map(function (c) { return encodeURIComponent(c.id); }).join(",") : "";
      try { root.history.replaceState(null, "", root.location.pathname + q); } catch (e) { /* a file:// preview */ }
    }
    function toggle(c, on) {
      var i = chosen.indexOf(c);
      if (on && i < 0) chosen.push(c);
      if (!on && i >= 0) chosen.splice(i, 1);
      unknown = [];                                // the address no longer holds them: the note has done its job
      save();
      render();
    }

    function copy(text, how, status) {
      track(how);
      var done = function () { status.textContent = "Copied."; };
      var fallback = function () {                 // no clipboard: show the text, selected, to copy by hand
        status.textContent = "Select and copy the text below.";
        var t = el("textarea", "plan-copy");
        t.value = text;
        t.rows = Math.min(16, text.split("\n").length + 1);
        t.setAttribute("aria-label", "The text to copy");
        status.appendChild(t);
        t.select();
      };
      if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
        root.navigator.clipboard.writeText(text).then(done, fallback);
      } else fallback();
    }

    function render() {
      out.textContent = "";
      found.querySelectorAll("input[type=checkbox]").forEach(function (box) {
        box.checked = chosen.some(function (c) { return c.id === box.value; });
      });
      if (unknown.length) {
        out.appendChild(el("p", "plan-note", "Not in the catalogue, and left out: " + unknown.join(", ") +
                           ". The address may be older than the catalogue, or mistyped."));
      }
      if (!chosen.length) {
        out.appendChild(el("p", "plan-empty", "No need ticked yet. Find the customer's first need above."));
        return;
      }
      var cards = order(chosen);
      out.appendChild(el("p", "plan-print-only", "Shortlist of " + cards.length + " needs: " + root.location.href));

      // (a) the needs, with verdict and door, and a way to take one out
      out.appendChild(h2("plan-needs", "The needs (" + cards.length + ")"));
      var ul = el("ul", "plan-list");
      chosen.forEach(function (c) {
        var li = el("li");
        li.appendChild(needLink(c));
        li.appendChild(el("span", "plan-meta", " " + c.verdict + " · " + c.door_name));
        var rm = el("button", "plan-rm", "Remove");
        rm.type = "button";
        rm.setAttribute("aria-label", "Remove: " + c.asks);
        rm.addEventListener("click", function () { toggle(c, false); });
        li.appendChild(rm);
        ul.appendChild(li);
      });
      out.appendChild(ul);

      // (b) the order to build them
      out.appendChild(h2("plan-order", "The order to build them"));
      var ol = el("ol", "plan-steps");
      steps(cards).forEach(function (s) {
        var li = el("li");
        li.appendChild(el("p", "plan-why", s.why));
        var inner = el("ul");
        s.cards.forEach(function (c) { var i = el("li"); i.appendChild(needLink(c)); i.appendChild(el("span", "plan-meta", " " + c.door_name)); inner.appendChild(i); });
        li.appendChild(inner);
        ol.appendChild(li);
      });
      out.appendChild(ol);

      // (c) the recipes and samples, once each
      var pr = proofs(cards);
      out.appendChild(h2("plan-proofs", "Recipes and samples, once each"));
      [["recipes", "Recipes"], ["samples", "Samples"]].forEach(function (k) {
        if (!pr[k[0]].length) { out.appendChild(el("p", null, k[1] + ": none for these needs.")); return; }
        out.appendChild(el("h3", null, k[1] + " (" + pr[k[0]].length + ")"));
        var list = el("ul", "plan-list");
        pr[k[0]].forEach(function (p) {
          var li = el("li");
          var a = p.page ? link(p.title, p.page) : el("a", null, p.title);
          if (!p.page) a.href = p.url;                // a contract page or a tool: the file in the kit on GitHub
          li.appendChild(a);
          li.appendChild(forList(p.needs));
          list.appendChild(li);
        });
        out.appendChild(list);
      });

      // (d) the limits to tell the customer
      var lim = limits(cards);
      out.appendChild(h2("plan-limits", "The limits to tell the customer"));
      if (!lim.length) out.appendChild(el("p", null, "None: every need here is Ready with nothing to caveat."));
      else {
        var dl = el("ul", "plan-limits");
        lim.forEach(function (x) {
          var li = el("li");
          li.appendChild(needLink(x.card));
          var inner = el("ul");
          x.lines.forEach(function (l) { inner.appendChild(el("li", null, l)); });
          li.appendChild(inner);
          dl.appendChild(li);
        });
        out.appendChild(dl);
        var st1 = el("p", "plan-status");
        st1.setAttribute("aria-live", "polite");
        var b1 = el("p", "plan-btns");
        b1.appendChild(button("Copy the limits", function () { copy(limitsText(cards), "limits", st1); }));
        out.appendChild(b1);
        out.appendChild(st1);
      }

      // (e) the requests to file
      var rq = requests(cards);
      out.appendChild(h2("plan-requests", "The requests to file"));
      if (!rq.forms.length && !rq.askUs.length && !rq.instead.length) out.appendChild(el("p", null, "None: every need here can be built today."));
      var rl = el("ul", "plan-list");
      rq.forms.forEach(function (f) {
        var li = el("li"), a = el("a", null, "Ask for the extension point " + f.handle);
        a.href = f.url;
        li.appendChild(a);
        li.appendChild(forList(f.needs));
        rl.appendChild(li);
      });
      rq.askUs.forEach(function (x) { var li = el("li", null, x.line); li.appendChild(forList([x.card])); rl.appendChild(li); });
      rq.instead.forEach(function (x) { var li = el("li", null, "Not possible. " + x.line); li.appendChild(forList([x.card])); rl.appendChild(li); });
      if (rl.childNodes.length) {
        out.appendChild(rl);
        if (rq.forms.length) out.appendChild(el("p", "plan-meta", "The request form is for onboarded members; it opens on GitHub with the extension point named in its title."));
      }

      // (f) the blueprint, to copy or print
      out.appendChild(h2("plan-blueprint", "The blueprint"));
      var md = blueprint(cards, head);
      var p = el("p");
      p.appendChild(doc.createTextNode("The rows of section (b) of the "));
      p.appendChild(link("project blueprint", "kit/blueprint.html"));
      p.appendChild(doc.createTextNode(", one per need, in the order to build them. Paste them into "));
      p.appendChild(link("its template", "kit/blueprint_template.html"));
      p.appendChild(doc.createTextNode(", or write them into "));
      p.appendChild(link("the blueprint form (PDF)", "downloads/blueprint_form.pdf"));
      p.appendChild(doc.createTextNode("."));
      out.appendChild(p);
      var st2 = el("p", "plan-status");
      st2.setAttribute("aria-live", "polite");
      var b2 = el("p", "plan-btns");
      b2.appendChild(button("Copy as a blueprint (Markdown)", function () { copy(md, "blueprint", st2); }));
      b2.appendChild(button("Print", function () { track("print"); root.print(); }));
      out.appendChild(b2);
      out.appendChild(st2);
      var det = el("details", "plan-rows");
      det.appendChild(el("summary", null, "See the rows"));
      det.appendChild(el("pre", null, md));
      out.appendChild(det);
      out.appendChild(el("pre", "plan-print-only", md));      // the rows on paper, whether or not they are open on screen
    }

    function showFound(results) {
      found.textContent = "";
      results.slice(0, 8).forEach(function (c, n) {
        var li = el("li"), box = el("input"), label = el("label", null, c.asks);
        box.type = "checkbox";
        box.id = "plan-f-" + n;
        box.value = c.id;
        box.checked = chosen.indexOf(c) >= 0;
        box.addEventListener("change", function () { toggle(c, box.checked); });
        label.htmlFor = box.id;
        label.appendChild(el("span", "plan-meta", " " + c.verdict + " · " + c.door_name));
        li.appendChild(box);
        li.appendChild(label);
        found.appendChild(li);
      });
      if (!results.length) {
        var li = el("li", "plan-empty", "No card matches. ");
        li.appendChild(link("Tell us the need", "feedback/point_request.html"));
        found.appendChild(li);
      }
    }

    function find() {
      var q = input.value.trim();
      if (!q) { found.textContent = ""; return; }
      var by = {};
      catalogue.forEach(function (c) { by[c.page] = c; });
      var simple = function () {                   // the search could not load: words in the customer's line or the title
        var words = q.toLowerCase().split(/\s+/).filter(Boolean);
        showFound(catalogue.filter(function (c) {
          var text = (c.asks + " " + c.title).toLowerCase();
          return words.every(function (w) { return text.indexOf(w) >= 0; });
        }));
      };
      if (!root.ivnSearch || !root.ivnSearch.engine) { simple(); return; }
      root.ivnSearch.engine(doc, base).then(function (ms) {
        if (input.value.trim() !== q) return;
        var needs = root.ivnSearch.grouped(root.ivnSearch.rank(ms, q)).need;
        showFound(needs.map(function (r) { return by[r.u]; }).filter(Boolean));
      }, simple);
    }

    fetch(base + "catalogue.json").then(function (r) { return r.json(); }).then(function (list) {
      catalogue = list;
      var picked = choose(catalogue, ids(root.location.search));
      chosen = picked.cards;
      unknown = picked.unknown;
      if (unknown.length) save();
      tool.hidden = false;
      render();
      input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(find, 120); });
    }, function () { /* the catalogue could not load: the page keeps its seven steps */ });
  }

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ivnPlan = api;
    if (root.document) wire(root.document);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
