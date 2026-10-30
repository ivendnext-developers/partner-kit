// S59 — the kitchen screen's fitting rules, apart from the page so they are tested without a browser
// (tests/test_page.py runs them under node): the four size steps, which size a screen takes, where a page of whole
// tickets ends, how much of a ticket taller than the board is folded behind "+N more dishes", and which page to show.
// page.js measures the screen and calls these; it never decides any of this itself.
(function (root) {
  "use strict";
  var SIZES = ["compact", "standard", "large", "xlarge"];

  // The size a screen takes: the cook's choice on this device if it is one of the four steps, else the store's
  // default, else Standard. Anything else stored on the device (an old or edited value) is ignored.
  function size(chosen, storeDefault) {
    if (SIZES.indexOf(chosen) >= 0) return chosen;
    return SIZES.indexOf(storeDefault) >= 0 ? storeDefault : "standard";
  }

  // A- and A+: one step, never past Compact or Extra large.
  function step(current, by) {
    var i = SIZES.indexOf(size(current)) + (by < 0 ? -1 : 1);
    return SIZES[Math.max(0, Math.min(SIZES.length - 1, i))];
  }

  // Given each ticket's bottom edge when the page is laid out from its first ticket, the page holds the tickets up to
  // the first one whose bottom passes the board's bottom. A page always holds at least one ticket, so the pager
  // always moves on and a ticket is never skipped.
  function fits(bottoms, limit) {
    for (var i = 1; i < bottoms.length; i++) if (bottoms[i] > limit + 0.5) return i;
    return bottoms.length;
  }

  // The page to show: page `want` if there are that many, else the last one. layout(from) lays the board out from
  // ticket `from` (the ones before it hidden) and returns the bottoms of the tickets from there on. Returns the page
  // shown and the tickets it holds, [from, end).
  function pages(count, want, layout, limit) {
    var starts = [0], end;
    for (;;) {
      var from = starts[starts.length - 1];
      end = from + fits(layout(from), limit);
      if (starts.length - 1 >= want || end >= count) break;
      starts.push(end);
    }
    return { page: starts.length - 1, from: starts[starts.length - 1], end: end };
  }

  // A ticket taller than the board: how many of its dish groups (a dish with its choices), from the last one, are
  // folded away so it fits. The first dish always stays, so a ticket never shows no dish at all.
  function trim(heights, total, cap) {
    var hide = 0, h = total;
    while (h > cap + 0.5 && hide < heights.length - 1) {
      h -= heights[heights.length - 1 - hide];
      hide++;
    }
    return hide;
  }

  var api = { SIZES: SIZES, size: size, step: step, fits: fits, pages: pages, trim: trim };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.kscFit = api;
})(this);
