/* site/assets-src/analytics.js — the developer site's visit counter. The one place the site reports anything.
 *
 * It defines window.ivnTrack(name, props); search.js and plan.js only call it, guarded. It sets no cookie, keeps nothing
 * in the browser that names a visitor, sends no address of its own and no Referer header (the page view carries only the
 * referring site's host name), and sends nothing at all when:
 *   - the browser says Do Not Track or Global Privacy Control, or the address carries ?notrack (kept for the tab only);
 *   - the page is on localhost or opened from a file;
 *   - the page does not name a counter, or names one the page's content policy does not list. The counter's address is the
 *     <meta name="ivn-analytics"> that site/build.py writes from check_links.ANALYTICS_HOST; the policy (connect-src)
 *     is built from the same list, so the browser enforces it as well.
 * Nothing waits for the counter: a report is sent after the page is ready, its answer is never read, and a counter that is
 * down changes nothing the visitor sees. A report is a plain text body in a cors request without credentials, so the
 * browser asks no permission first and names the page's own origin, which the counter checks (a no-cors request with
 * no referrer would name "null" and be refused). A call made before this file loads can be queued in window.ivnTrack.q.
 *
 * Events (the counter takes exactly these): pageview · search {q, n} (and no_result {q} when n is 0) · sandbox_request ·
 * request_form {h} · outbound {to} · plan_export {how}. Clicks are found by the link's address, never by its words.
 * site/test_analytics.mjs loads this file in node and checks every sentence above, each guard shown able to fail.
 */
(function (root) {
  "use strict";
  var OUT_HOSTS = ["library.ivendnext.app", "www.ivendnext.com", "ivendnext.com", "docs.ivendnext.com"];
  var SANDBOX_FORM = "https://www.ivendnext.com/partner/#be-a-partner";
  var REQUEST_FORM = "https://github.com/ivendnext-developers/partner-feedback/issues/new";
  var NOTRACK_FLAG = "ivnNoTrack";

  function hostOf(url) { var m = /^https:\/\/([^\/:?#]+)(?::443)?(?:[\/?#]|$)/i.exec(url || ""); return m ? m[1].toLowerCase() : ""; }

  function off(win) {                      // true when this visit must not be counted at all
    var nav = win.navigator || {}, loc = win.location || {};
    if (nav.doNotTrack === "1" || nav.doNotTrack === "yes" || win.doNotTrack === "1" || nav.msDoNotTrack === "1") return true;
    if (nav.globalPrivacyControl === true) return true;
    var h = (loc.hostname || "").toLowerCase();
    if (!h || h === "localhost" || h === "127.0.0.1" || h === "[::1]" || /\.localhost$/.test(h)) return true;
    try {
      if (/(^|[?&])notrack(=|&|$)/.test(loc.search || "")) { win.sessionStorage.setItem(NOTRACK_FLAG, "1"); return true; }
      if (win.sessionStorage.getItem(NOTRACK_FLAG) === "1") return true;
    } catch (e) { /* no storage: only this page's ?notrack counts */ if (/(^|[?&])notrack(=|&|$)/.test(loc.search || "")) return true; }
    return false;
  }

  function counter(doc) {                  // the counter's address, or "" when the page does not name an allowed one
    var meta = doc && doc.querySelector && doc.querySelector('meta[name="ivn-analytics"]');
    var csp = doc && doc.querySelector && doc.querySelector('meta[http-equiv="Content-Security-Policy"]');
    var url = meta && meta.getAttribute("content") || "";
    var host = hostOf(url);
    if (!host || url.replace(/\/+$/, "") !== "https://" + host || !csp) return "";
    var m = /(?:^|;)\s*connect-src ([^;]*)/.exec(csp.getAttribute("content") || "");
    var listed = m ? m[1].split(/\s+/) : [];
    return listed.indexOf("https://" + host) >= 0 ? "https://" + host : "";
  }

  function pathOf(p) { p = String(p || "/").replace(/index\.html$/, ""); return p.charAt(0) === "/" ? p : "/" + p; }
  function text(s, n) { return String(s == null ? "" : s).replace(/\s+/g, " ").trim().slice(0, n); }

  function bodies(name, props, here) {    // the reports one call makes; [] for a name the counter does not take
    props = props || {};
    if (name === "search") {
      var q = text(props.q, 80), n = typeof props.n === "number" ? Math.max(0, Math.floor(props.n)) : 0;
      if (!q) return [];
      var out = [{ e: "search", q: q, n: n }];
      if (n === 0) out.push({ e: "no_result", q: q, n: 0 });
      return out;
    }
    if (name === "pageview") return [{ e: "pageview", p: pathOf(props.p || here), r: text(props.r, 100) }];
    if (name === "sandbox_request") return [{ e: "sandbox_request", p: pathOf(here) }];
    if (name === "request_form") return [{ e: "request_form", h: text(props.h, 40) }];
    if (name === "outbound") return props.to ? [{ e: "outbound", to: text(props.to, 100) }] : [];
    if (name === "plan_export") return props.how ? [{ e: "plan_export", how: props.how === "print" ? "print" : "copy" }] : [];   // plan.js says "limits" or "blueprint" for a copy
    return [];
  }

  function classify(href, here) {         // the event a click on this address is, or null: [name, props]
    var u;
    try { u = new URL(href, here); } catch (e) { return null; }
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    var full = u.href;
    if (full.indexOf(SANDBOX_FORM) === 0 || (u.origin === new URL(here).origin && /(^|\/)sandbox\.html$/.test(u.pathname))) return ["sandbox_request", {}];
    if (full.indexOf(REQUEST_FORM) === 0) {
      var m = /P-[A-Z0-9][A-Z0-9-]{1,30}/.exec(decodeURIComponent((u.searchParams.get("title") || "").replace(/\+/g, " ")));
      return ["request_form", { h: m ? m[0] : "" }];
    }
    if (u.protocol === "https:" && OUT_HOSTS.indexOf(u.hostname.toLowerCase()) >= 0) return ["outbound", { to: u.hostname.toLowerCase() }];
    return null;
  }

  function init(win) {
    var loc = win.location || {};
    var base = off(win) ? "" : counter(win.document);
    var sent = [];

    function post(obj) {
      try {
        var p = win.fetch(base + "/e", { method: "POST", body: JSON.stringify(obj), mode: "cors", credentials: "omit",
                                         keepalive: true, cache: "no-store", referrerPolicy: "no-referrer" });
        if (p && typeof p.catch === "function") p.catch(function () { /* a counter that is down changes nothing */ });
      } catch (e) { /* nor does a browser without fetch */ }
    }

    function track(name, props) {
      if (!base) return;
      try { bodies(name, props, loc.pathname).forEach(function (b) { post(b); sent.push(b.e); }); } catch (e) { /* never break a page */ }
    }

    function onClick(ev) {
      if (!base) return;
      try {
        var el = ev && ev.target;
        while (el && !(el.tagName === "A" && el.getAttribute && el.getAttribute("href"))) el = el.parentNode;
        if (!el) return;
        var hit = classify(el.getAttribute("href"), loc.href);
        if (hit) track(hit[0], hit[1]);
      } catch (e) { /* never break a click */ }
    }

    var queued = win.ivnTrack && win.ivnTrack.q;
    win.ivnTrack = track;
    if (base) {
      var doc = win.document;
      doc.addEventListener("click", onClick);
      doc.addEventListener("auxclick", function (ev) { if (ev && ev.button === 1) onClick(ev); });
      if (Array.isArray(queued)) queued.forEach(function (c) { track(c[0], c[1]); });
      var ref = hostOf(doc.referrer || "");
      track("pageview", { p: loc.pathname, r: ref });
    }
    return { enabled: !!base, base: base, track: track, sent: sent, onClick: onClick };
  }

  var api = { init: init, off: off, counter: counter, bodies: bodies, classify: classify, pathOf: pathOf };
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else if (root.document) {
    api.state = init(root);
    root.ivnAnalytics = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
