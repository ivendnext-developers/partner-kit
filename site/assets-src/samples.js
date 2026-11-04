/* site/assets-src/samples.js — the Samples page's filters: words, industry and way in.
 *
 * A card shows when it matches all three; a sample for every industry shows under each industry. A group with no card left
 * hides, and a group's count follows the filter. The cards carry what is matched in data- attributes (site/gallery.py). Nothing
 * is sent or stored. Without script the form stays hidden and every sample shows. site/test_finder.mjs runs matches() in node.
 */
(function (root) {
  "use strict";
  var EVERY = "every industry";

  function matches(card, f) {                 // card {text, door, industries}, filter {words, industry, door}
    var words = (f.words || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    return (!f.industry || card.industries.indexOf(f.industry) >= 0 || card.industries.indexOf(EVERY) >= 0) &&
      (!f.door || card.door === f.door) &&
      words.every(function (w) { return card.text.indexOf(w) >= 0; });
  }

  function wire(doc) {
    var form = doc.getElementById("sample-filters");
    if (!form) return;
    form.hidden = false;
    var q = doc.getElementById("sf-q"), ind = doc.getElementById("sf-ind"), door = doc.getElementById("sf-door");
    var out = doc.getElementById("sf-count"), none = doc.getElementById("sf-none");
    var cards = [].slice.call(doc.querySelectorAll(".card.sample"));
    var groups = [].slice.call(doc.querySelectorAll(".sgroup"));
    function run() {
      var f = { words: q.value, industry: ind.value, door: door.value }, n = 0;
      cards.forEach(function (c) {
        var ok = matches({ text: c.getAttribute("data-text"), door: c.getAttribute("data-door"),
                           industries: c.getAttribute("data-ind").split("|") }, f);
        c.hidden = !ok;
        if (ok) n++;
      });
      groups.forEach(function (g) {
        var shown = g.querySelectorAll(".card.sample:not([hidden])").length, c = g.querySelector(".gcount");
        g.hidden = !shown;
        if (c) c.textContent = shown;
      });
      out.textContent = n + (n === 1 ? " sample" : " samples");
      none.hidden = n > 0;
    }
    form.addEventListener("input", run);
    form.addEventListener("change", run);
    form.addEventListener("submit", function (e) { e.preventDefault(); });
  }

  if (typeof module === "object" && module.exports) {
    module.exports = { matches: matches };
  } else if (root.document) {
    wire(root.document);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
