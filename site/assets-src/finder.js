/* site/assets-src/finder.js — the Needs page's finder: a customer's list goes in, and each line comes back with the nearest need.
 *
 * Each line is matched to a need by the site's own search (window.ivnSearch, search.js: the same ranking, synonyms and spelling
 * slips as the header box). A line that fits closely shows the need, its verdict and door, what to tell the customer, and the card's
 * own recipes and samples (a page of this site, or the kit file on GitHub); "Not this one?" offers the next two matches, or none of
 * them. A line that fits nothing closely shows no verdict: only the nearest needs to choose from, and "Tell us the need". "Plan these
 * needs" opens Plan a project with the chosen needs (plan.html?needs=id,id). A list can arrive in the address: ?list=… (from the home
 * page's box) or ?q=…. Nothing is sent or stored. Without script the section stays hidden and the page is the catalogue below it.
 * site/test_finder.mjs loads this file in node and finds the distributor's three lines in the built index.
 */
(function (root) {
  "use strict";
  var PILL = { "ready": "st-ready", "ready-with-limits": "st-limits", "not-yet": "st-notyet", "not-possible": "st-never" };
  var ALTERNATIVES = 3;
  var CLOSE = 400;                            // every card's own words score over this; a line that merely shares a word scores under it
  var NONE = -1;

  function lines(text) {                      // one need a line; no empties
    return (text || "").split("\n").map(function (s) { return s.trim(); }).filter(function (s) { return s.length > 1; });
  }

  function given(search) {                    // what the address carries: ?list=… first, then ?q=…
    var p = new URLSearchParams(search || "");
    return (p.get("list") || p.get("q") || "").trim();
  }

  function fits(search, ms, line, cards) {    // the needs that match a line, best first
    return search.rank(ms, line).filter(function (r) { return r.k === "need" && cards[r.id]; }).slice(0, ALTERNATIVES);
  }

  function picked(hits, choice) {             // which hit a line shows: the reader's choice, else the first if it fits closely, else none
    if (choice != null) return choice < hits.length ? choice : NONE;
    return hits.length && hits[0].score >= CLOSE ? 0 : NONE;
  }

  function planHref(base, ids) { return base + "plan.html?needs=" + ids.join(","); }

  function uses(card) {                       // the card's own recipes and samples: those with a page here or a file in the kit
    return (card.recipes || []).concat(card.samples || []).filter(function (u) { return u.page || u.url; });
  }

  function wire(doc) {
    var box = doc.getElementById("finder");
    if (!box || !root.ivnSearch) return;
    var base = box.getAttribute("data-root") || "";
    var list = doc.getElementById("finder-list"), out = doc.getElementById("finder-out");
    var plan = doc.getElementById("finder-plan"), planLink = doc.getElementById("finder-plan-link");
    var count = doc.getElementById("finder-count");
    box.hidden = false;
    var start = given(root.location.search);
    if (start) list.value = start;

    var cards = {}, chosen = {}, ready = null;
    function load() {                         // the catalogue and the index arrive when the box is first used
      ready = ready || Promise.all([
        fetch(base + "catalogue.json").then(function (r) { return r.json(); }),
        root.ivnSearch.engine(doc, base)
      ]).then(function (all) {
        all[0].forEach(function (c) { cards[c.page] = c; });
        return all[1];
      });
      return ready;
    }

    function el(tag, cls, text) {
      var n = doc.createElement(tag);
      if (cls) n.className = cls;
      if (text != null) n.textContent = text;
      return n;
    }
    function link(href, text) { var a = el("a", null, text); a.href = href; return a; }
    function choice(label, text, j, ms) {
      var b = el("button", null, label);
      b.type = "button";
      b.addEventListener("click", function () { chosen[text] = j; render(ms); });
      return b;
    }

    function row(text, hits, ms) {
      var li = el("li", "fit");
      li.appendChild(el("p", "fit-q", "“" + text + "”"));
      var a = el("div", "fit-a");
      li.appendChild(a);
      var pick = picked(hits, chosen[text]);
      if (pick === NONE) {
        a.appendChild(el("p", null, hits.length ? "No need in the catalogue fits this closely." : "No need in the catalogue matches these words."));
        if (hits.length) {
          var near = el("p", "fit-alt", "The nearest: ");
          hits.forEach(function (hit, j) { near.appendChild(choice(cards[hit.id].title, text, j, ms)); });
          a.appendChild(near);
        }
        var p0 = el("p");
        p0.appendChild(link(base + "feedback/point_request.html", "Tell us the need"));
        a.appendChild(p0);
        return { li: li, id: null };
      }
      var c = cards[hits[pick].id];
      var h = el("h3");
      h.appendChild(link(base + c.page, c.title));
      h.appendChild(doc.createTextNode(" "));
      h.appendChild(el("span", "pill " + (PILL[c.status] || ""), c.verdict));
      a.appendChild(h);
      a.appendChild(el("p", "fit-meta", "Door: " + c.door_name + " · " + c.area_name));
      if (c.tell) {
        var t = el("p");
        t.appendChild(el("strong", null, "Tell the customer: "));
        t.appendChild(doc.createTextNode(c.tell));
        a.appendChild(t);
      }
      var build = el("p"), used = uses(c);
      if (used.length) {
        build.appendChild(el("strong", null, "Build it with: "));
        used.forEach(function (u, i) {
          if (i) build.appendChild(doc.createTextNode(" · "));
          var a2 = link(u.page ? base + u.page : u.url, u.title);
          if (!u.page) { a2.target = "_blank"; a2.rel = "noopener"; }
          build.appendChild(a2);
        });
      } else {
        build.appendChild(link(base + c.page + "#what-next", "What next, for this need"));
      }
      a.appendChild(build);
      var alt = el("p", "fit-alt", "Not this one? ");
      hits.forEach(function (hit, j) { if (j !== pick) alt.appendChild(choice(cards[hit.id].title, text, j, ms)); });
      alt.appendChild(choice("None of these", text, NONE, ms));
      a.appendChild(alt);
      return { li: li, id: c.id };
    }

    function render(ms) {
      var all = lines(list.value), ids = [];
      out.textContent = "";
      all.forEach(function (text) {
        var r = row(text, fits(root.ivnSearch, ms, text, cards), ms);
        out.appendChild(r.li);
        if (r.id && ids.indexOf(r.id) < 0) ids.push(r.id);
      });
      plan.hidden = !ids.length;
      planLink.href = planHref(base, ids);
      count.textContent = ids.length + (ids.length === 1 ? " need" : " needs") + " from " + all.length +
        (all.length === 1 ? " line" : " lines");
    }

    var timer = null;
    function go() {
      clearTimeout(timer);
      timer = setTimeout(function () {
        load().then(render, function () { out.textContent = "The finder could not load the catalogue. Use the search above."; });
      }, 150);
    }
    list.addEventListener("focus", load);
    list.addEventListener("input", go);
    root.addEventListener("pageshow", function () { if (list.value.trim()) go(); });   // a list the browser put back on Back
    if (start) go();
  }

  if (typeof module === "object" && module.exports) {
    module.exports = { lines: lines, given: given, fits: fits, picked: picked, planHref: planHref, uses: uses, CLOSE: CLOSE, NONE: NONE };
  } else if (root.document) {
    wire(root.document);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
