// S24's kiosk page: the scan box keeps the focus (a barcode scanner types and presses Enter), each scan is sent to the
// app's own service with the shop and kiosk named in this page's address (#shop=…&kiosk=…), and the answer is drawn with
// textContent only. The page holds no key and signs nothing.
"use strict";

(function () {
  var CLEAR_AFTER_MS = 20000;
  var params = new URLSearchParams(location.hash.slice(1));
  var shop = params.get("shop") || "", kiosk = params.get("kiosk") || "";
  var el = function (id) { return document.getElementById(id); };
  var box = el("scan"), timer = null;

  function money(value, currency) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: currency }).format(value);
    } catch (e) {
      return value.toFixed(2) + " " + currency;
    }
  }

  function reset() {
    el("result").hidden = true;
    el("message").hidden = true;
    el("prompt").hidden = false;
  }

  function later() {
    clearTimeout(timer);
    timer = setTimeout(reset, CLEAR_AFTER_MS);
  }

  function say(text) {
    el("result").hidden = true;
    el("message").textContent = text;
    el("message").hidden = false;
    later();
  }

  function show(a) {
    el("item").textContent = a.item;
    el("unit").textContent = a.unit ? "Per " + a.unit : "";
    el("price").textContent = money(a.price, a.currency);
    var pic = el("picture");
    if (a.image) { pic.src = a.image; pic.hidden = false; } else { pic.removeAttribute("src"); pic.hidden = true; }
    el("message").hidden = true;
    el("result").hidden = false;
    later();
  }

  function today() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function check(text) {
    el("prompt").hidden = true;
    fetch("prc/price", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shop: shop, kiosk: kiosk, scan: text, date: today() })
    }).then(function (r) {
      return r.json().catch(function () { return {}; });
    }).then(function (a) {
      if (a && a.status === "found") { show(a); } else { say((a && a.message) || "Price checks are not available right now."); }
    }).catch(function () {
      say("Price checks are not available right now.");
    });
  }

  box.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") { return; }
    e.preventDefault();
    var text = box.value.trim();
    box.value = "";
    if (text) { check(text); }
  });
  box.addEventListener("blur", function () { setTimeout(function () { box.focus(); }, 0); });
  if (!kiosk) { say("This kiosk is not set up. Please ask a member of staff."); }
  box.focus();
})();
