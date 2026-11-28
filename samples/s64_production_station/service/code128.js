// S64 — a small Code 128 encoder for the station's tag: the page draws the tag's barcode itself, as inline SVG, so nothing
// is loaded from another site and no font is needed. Code set B carries any printable ASCII character; a barcode of digits
// only is written in code set C (two digits a symbol, so a 13-digit tag fits a 50 mm label), with a last odd digit in B.
// The symbols, the checksum (start value plus each symbol's value times its place, modulo 103) and the stop are the
// standard's; each pattern is six bar and space widths of 11 modules, the stop seven of 13. Works in a browser
// (window.pstCode128) and in node (require), for the tests.
(function (root) {
  "use strict";
  var P = ["212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112"];
  var START_B = 104, START_C = 105, CODE_B = 100, STOP = 106, QUIET = 10;

  // the symbol values of ``text``: [start, data..., checksum, stop]
  function values(text) {
    var s = String(text), out = [], i;
    if (!s.length) throw new Error("nothing to encode");
    for (i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c < 32 || c > 126) throw new Error("Code 128 B carries printable ASCII only");
    }
    if (/^[0-9]+$/.test(s) && s.length >= 4) {          // digits: code set C, two a symbol
      var even = s.length - (s.length % 2);
      out.push(START_C);
      for (i = 0; i < even; i += 2) out.push(+s.substr(i, 2));
      if (even < s.length) { out.push(CODE_B); out.push(s.charCodeAt(even) - 32); }
    } else {
      out.push(START_B);
      for (i = 0; i < s.length; i++) out.push(s.charCodeAt(i) - 32);
    }
    var sum = out[0];
    for (i = 1; i < out.length; i++) sum += out[i] * i;
    out.push(sum % 103);
    out.push(STOP);
    return out;
  }

  // the bar and space widths, in modules, from the first bar to the last (quiet zones not included)
  function widths(text) {
    return values(text).map(function (v) { return P[v]; }).join("").split("").map(Number);
  }

  // the tag's barcode as an SVG element of ``doc``: bars in currentColor, a quiet zone of 10 modules on each side
  function svg(doc, text, heightMm) {
    var NS = "http://www.w3.org/2000/svg", w = widths(text), total = QUIET * 2, x = QUIET, i;
    for (i = 0; i < w.length; i++) total += w[i];
    var el = doc.createElementNS(NS, "svg");
    el.setAttribute("viewBox", "0 0 " + total + " 10");
    el.setAttribute("preserveAspectRatio", "none");
    el.setAttribute("shape-rendering", "crispEdges");
    el.setAttribute("class", "pst-bars");
    el.setAttribute("aria-hidden", "true");
    if (heightMm) el.setAttribute("height", heightMm + "mm");
    for (i = 0; i < w.length; i++) {
      if (i % 2 === 0) {                                  // even places are bars, odd places spaces
        var r = doc.createElementNS(NS, "rect");
        r.setAttribute("x", String(x)); r.setAttribute("y", "0");
        r.setAttribute("width", String(w[i])); r.setAttribute("height", "10");
        r.setAttribute("fill", "currentColor");
        el.appendChild(r);
      }
      x += w[i];
    }
    return el;
  }

  var api = { PATTERNS: P, QUIET: QUIET, values: values, widths: widths, svg: svg };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.pstCode128 = api;
})(this);
