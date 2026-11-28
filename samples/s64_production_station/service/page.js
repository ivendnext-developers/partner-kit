// S64 — the production station's page. Its address carries #s=<the retailer's site>&t=<station>.<number>.<signature>; the
// part after # is never sent to a server in the address, only in the body of the calls below. A worker taps their name
// once (kept on this device), then a category and a price: one tag printed and counted. The category stays chosen, so
// the next piece of the same kind is one tap. Undo last tag takes the last tag of this cart back; Cart full asks where
// the cart goes and sends it. Every word the retailer wrote (a name, a category, a place) is put on the page as text,
// never as markup, with dir="auto". The page holds no secret and decides no price: the service answers the tag's price,
// colour and barcode, and the page prints exactly that.
// PRINTING: the page fills the print-only tag (its size from the settings, @page at the same millimetres and no margin)
// and calls the browser's own print. A station's browser opened with its print-without-asking switch (Chrome and Edge:
// --kiosk-printing) prints with no window; a tablet opens its print sheet on each tag.
(function () {
  "use strict";
  var READ_MS = 60000, RETRY_MS = 5000, NOTE_MS = 6000;
  var WORDS = {
    en: { pickWorker: "Tap your name", changeWorker: "Change worker", thisWeek: "This week: {colour}", today: "Today: {colour}",
          inCart: "In this cart: {n}", undo: "Undo last tag", cartFull: "Cart full", whereTo: "Where does this cart go?",
          cancel: "Cancel", printed: "Printed: {price} {category}", undone: "Taken back: {price} {category}",
          sent: "Cart {cart}: {n} pieces sent to {place}.", kept: "Cart {cart}: {n} pieces received in the processing room.",
          busy: "This cart is being sent. Wait a minute, then tap Cart full again.",
          empty: "No tags since the last cart.", no_undo: "No tag to take back since the last cart.",
          no_worker: "Tap your name again.", no_price: "That price is no longer one of this category's. The screen is read again.",
          no_colour: "This week's colour is not set. Tell your lead.",
          no_item: "No {category} item has this week's colour ({colour}). Tell your lead.",
          no_mask: "This item has no price label set up. Tell your lead to set its barcode mask.",
          no_label: "This item's price label cannot be made. Tell your lead to check its barcode mask and its barcode.",
          too_old: "This price cannot be printed on a tag yet. Tell your lead: iVendNext needs an update.",
          no_place: "That place is no longer on the list. The screen is read again.",
          no_room: "The processing room is not set. Tell your lead.",
          unknown: "This station's link does not work, or it was replaced. Ask your lead for the station's new link.",
          not_set_up: "This station cannot reach iVendNext. Ask your lead to check the app's user and its key.",
          unavailable: "That did not go through. Tap again.", loading: "Reading the station...",
          lostTag: "That tag did not come back. Tap the same price again: it prints and counts once.",
          cannotReach: "Cannot reach iVendNext. Trying again.",
          no_move: "This cart could not go to {place}. Pick another place, or tell your lead.",
          noWorkers: "No workers are set up for this station. Tell your lead.",
          noPrices: "No price points are set up. Tell your lead.", noColour: "No colour this week. Tell your lead." },
    es: { pickWorker: "Toque su nombre", changeWorker: "Cambiar de persona", thisWeek: "Esta semana: {colour}", today: "Hoy: {colour}",
          inCart: "En este carro: {n}", undo: "Deshacer la última etiqueta", cartFull: "Carro lleno",
          whereTo: "¿Adónde va este carro?", cancel: "Cancelar", printed: "Impresa: {price} {category}",
          undone: "Retirada: {price} {category}", sent: "Carro {cart}: {n} piezas enviadas a {place}.",
          kept: "Carro {cart}: {n} piezas recibidas en la sala de proceso.",
          busy: "Este carro se está enviando. Espere un minuto y toque Carro lleno otra vez.",
          empty: "No hay etiquetas desde el último carro.", no_undo: "No hay etiqueta que retirar desde el último carro.",
          no_worker: "Toque su nombre otra vez.", no_price: "Ese precio ya no es de esta categoría. La pantalla se lee de nuevo.",
          no_colour: "El color de esta semana no está configurado. Avise a su responsable.",
          no_item: "Ningún artículo de {category} tiene el color de esta semana ({colour}). Avise a su responsable.",
          no_mask: "Este artículo no tiene etiqueta de precio configurada. Pida a su responsable que configure su máscara de código.",
          no_label: "No se puede hacer la etiqueta de este artículo. Pida a su responsable que revise su máscara y su código.",
          too_old: "Este precio todavía no se puede imprimir en una etiqueta. Avise a su responsable: iVendNext necesita una actualización.",
          no_place: "Ese destino ya no está en la lista. La pantalla se lee de nuevo.",
          no_room: "La sala de proceso no está configurada. Avise a su responsable.",
          unknown: "El enlace de esta estación no funciona o fue sustituido. Pida el nuevo enlace a su responsable.",
          not_set_up: "Esta estación no llega a iVendNext. Pida a su responsable que revise el usuario de la app y su clave.",
          unavailable: "No se aplicó. Toque otra vez.", loading: "Leyendo la estación...",
          lostTag: "Esa etiqueta no volvió. Toque el mismo precio otra vez: se imprime y se cuenta una sola vez.",
          cannotReach: "No se llega a iVendNext. Se intenta otra vez.",
          no_move: "Este carro no pudo ir a {place}. Elija otro destino o avise a su responsable.",
          noWorkers: "No hay personas configuradas para esta estación. Avise a su responsable.",
          noPrices: "No hay precios configurados. Avise a su responsable.", noColour: "Sin color esta semana. Avise a su responsable." }
  };
  var lang = (function () {
    var want = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"]);
    for (var i = 0; i < want.length; i++) { var l = String(want[i] || "").slice(0, 2).toLowerCase(); if (WORDS[l]) return l; }
    return "en";
  })();
  function w(key, args) {
    var s = (WORDS[lang] && WORDS[lang][key]) || WORDS.en[key] || "";
    Object.keys(args || {}).forEach(function (k) { s = s.split("{" + k + "}").join(String(args[k])); });
    return s;
  }

  var hash = new URLSearchParams(location.hash.slice(1));
  var LINK = { s: hash.get("s") || "", t: hash.get("t") || "" };
  var KEY = "pst.worker." + LINK.s + "." + LINK.t.split(".")[0];
  var $ = function (id) { return document.getElementById(id); };
  var last = null, worker = "", category = "", busy = false, printed = 0, count = 0, timer = null, noteUntil = 0, sized = "";
  var noteKey = "", pending = null, lastTag = "";   // pending: a tap whose answer was lost ({key, req}); lastTag: the tag Undo takes back

  function kept() { try { return window.localStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  function keep(v) {
    try { if (v) window.localStorage.setItem(KEY, v); else window.localStorage.removeItem(KEY); }
    catch (e) { /* not kept on this device: the worker taps their name again after a reload */ }
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function money(p) {
    var n = Number(p);
    // one fixed locale on every tile and tag, never the worker's browser language (a Spanish tablet wrote 19,99 US$)
    try { if (last && last.currency) return new Intl.NumberFormat("en", { style: "currency", currency: last.currency, currencyDisplay: "narrowSymbol" }).format(n); }
    catch (e) { /* an unknown currency code: the figure alone */ }
    return n.toFixed(2);
  }
  function call(path, extra) {
    var body = Object.assign({ s: LINK.s, t: LINK.t }, extra || {});
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
                         cache: "no-store", credentials: "omit" })
      .then(function (r) { return r.json().catch(function () { return { state: "unavailable" }; }); })
      .catch(function () { return { state: "unavailable" }; });
  }
  function note(key, args, good, lasting) {
    var n = $("note");
    if (!key) { if (performance.now() >= noteUntil) { n.hidden = true; n.textContent = ""; } noteKey = ""; return; }
    n.textContent = w(key, args); n.hidden = false; noteKey = key;
    n.classList.toggle("is-good", !!good);
    noteUntil = good || lasting ? 0 : performance.now() + NOTE_MS;
  }
  function reqId() {               // a tap's own id: the same tap sent again after a lost answer is found, never made twice
    var b = new Uint8Array(12), s = "";
    try { window.crypto.getRandomValues(b); } catch (e) { for (var i = 0; i < 12; i++) b[i] = Math.floor(Math.random() * 256); }
    for (var j = 0; j < b.length; j++) s += ("0" + b[j].toString(16)).slice(-2);
    return s;
  }
  function tile(label, on, fn) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "ivn-btn pst-tile" + (on ? " is-on" : "");
    b.setAttribute("dir", "auto"); b.textContent = String(label);
    if (on) b.setAttribute("aria-pressed", "true");
    b.addEventListener("click", fn);
    return b;
  }
  function setBusy(on) {
    busy = on;
    Array.prototype.forEach.call(document.querySelectorAll(".pst-tile, .pst-act"), function (b) { b.disabled = on; });
  }

  // the tag's size: the settings' millimetres, on the printed page and the tag
  function size() {
    var t = (last && last.tag) || { width_mm: 50, height_mm: 30 }, want = t.width_mm + "mm " + t.height_mm + "mm";
    $("tag").style.width = t.width_mm + "mm"; $("tag").style.height = t.height_mm + "mm";
    if (sized === want) return;
    Array.prototype.forEach.call(document.styleSheets, function (sh) {
      if (!sh.href || !/page\.css$/.test(sh.href)) return;
      try { sh.insertRule("@page { size: " + want + "; margin: 0; }", sh.cssRules.length); sized = want; }
      catch (e) { /* the browser keeps its own page size: the tag still prints at its millimetres */ }
    });
  }

  function draw() {
    var a = last;
    $("title").textContent = a.title || "";
    $("colour").textContent = a.colour ? w(a.one_day ? "today" : "thisWeek", { colour: a.colour }) : w("noColour");
    if (worker && a.workers.indexOf(worker) < 0) { worker = ""; keep(""); }
    var cats = a.categories.map(function (c) { return c.name; });
    if (category && cats.indexOf(category) < 0) category = "";
    if (!category && cats.length === 1) category = cats[0];
    $("who").hidden = $("change").hidden = !worker;
    $("who").textContent = worker;
    $("workers-title").hidden = $("workers").hidden = !!worker;
    $("work").hidden = $("foot").hidden = !worker;
    clear($("workers")); clear($("cats")); clear($("prices"));
    if (!worker) {
      $("workers-title").textContent = a.workers.length ? w("pickWorker") : w("noWorkers");
      a.workers.forEach(function (n) {
        $("workers").appendChild(tile(n, false, function () { worker = n; keep(n); note(""); draw(); }));
      });
      return;
    }
    if (!a.categories.length) note("noPrices");
    a.categories.forEach(function (c) {
      $("cats").appendChild(tile(c.name, c.name === category, function () { category = c.name; draw(); }));
      if (c.name !== category) return;
      c.prices.forEach(function (p) { $("prices").appendChild(tile(money(p), false, function () { tap(c.name, p); })); });
    });
    $("count").textContent = w("inCart", { n: count });
    setBusy(busy);
  }

  function read() {
    clearTimeout(timer);
    return call("/pst/board").then(function (a) {
      if (a.state === "open") {
        last = a; count = a.cart || 0; size();
        if (noteKey === "cannotReach") note("");
        draw();
        timer = setTimeout(function () { if (!busy) read(); else timer = setTimeout(read, RETRY_MS); }, READ_MS);
      } else {
        note(a.state === "unavailable" ? "cannotReach" : (WORDS.en[a.state] ? a.state : "cannotReach"), null, false, true);
        if (a.state !== "unknown") timer = setTimeout(read, RETRY_MS);
      }
    });
  }

  function printTag(t) {
    var title = document.title;
    $("tag-price").textContent = money(t.price);
    $("tag-what").textContent = t.category + " · " + t.colour;
    clear($("tag-bars"));
    $("tag-bars").appendChild(window.pstCode128.svg(document, t.barcode, Math.round(((last.tag || {}).height_mm || 30) * 0.36)));
    $("tag-digits").textContent = t.barcode;
    document.title = "tag " + (t.name || t.barcode);    // a kept print job is named by its tag
    try { window.print(); } finally { document.title = title; }
    printed += 1;
    document.body.setAttribute("data-printed", String(printed));
  }

  function refused(a) {
    if (a.state === "refused" && WORDS.en[a.why]) {
      note(a.why, { colour: a.colour || "", category: a.category || "", place: a.place || "" });
      if (a.why === "no_price" || a.why === "no_place" || a.why === "no_worker") read();
    } else note(WORDS.en[a.state] ? a.state : "unavailable");
  }

  function tap(cat, price) {
    if (busy) return;
    setBusy(true);
    var key = worker + "|" + cat + "|" + price, req = pending && pending.key === key ? pending.req : reqId();
    call("/pst/tag", { worker: worker, category: cat, price: price, req: req }).then(function (a) {
      setBusy(false);
      if (a.state === "tagged") {
        pending = null; lastTag = a.tag.name || "";
        printTag(a.tag); count += 1;
        note("printed", { price: money(a.tag.price), category: a.tag.category }, true);
        draw();
      } else if (a.state === "unavailable") {
        pending = { key: key, req: req };          // the next tap of the same price is this tap again
        note("lostTag");
      } else { pending = null; refused(a); }
    });
  }

  $("undo").addEventListener("click", function () {
    if (busy) return;
    setBusy(true);
    call("/pst/undo", lastTag ? { tag: lastTag } : {}).then(function (a) {
      setBusy(false);
      if (a.state === "undone") {
        lastTag = "";
        count = Math.max(0, count - 1);
        note("undone", { price: money(a.tag.price), category: a.tag.category || "" }, true);
        draw();
      } else refused(a);
    });
  });
  $("full").addEventListener("click", function () {
    if (busy || !last) return;
    clear($("places"));
    last.places.forEach(function (p) {
      $("places").appendChild(tile(p.label, false, function () { window.ivnKit.closeDialog($("places-dialog")); send(p.warehouse); }));
    });
    window.ivnKit.openDialog($("places-dialog"));
  });
  function send(where) {
    if (busy) return;
    setBusy(true);
    call("/pst/cart", { warehouse: where }).then(function (a) {
      setBusy(false);
      if (a.state === "sent") {
        count = 0; lastTag = ""; pending = null;
        note(a.kept ? "kept" : "sent", { cart: a.cart, n: a.pieces, place: a.place }, true);
        draw();
      } else refused(a);
    });
  }
  $("change").addEventListener("click", function () { worker = ""; keep(""); note(""); draw(); });

  $("change").textContent = w("changeWorker");
  $("undo").textContent = w("undo");
  $("full").textContent = w("cartFull");
  $("places-title").textContent = w("whereTo");
  $("places-close").textContent = w("cancel");
  document.documentElement.setAttribute("lang", lang);
  window.addEventListener("hashchange", function () { location.reload(); });
  window.addEventListener("online", function () { read(); });
  worker = kept();
  if (!LINK.s || !LINK.t) { note("unknown"); return; }
  note("loading", null, true);
  read().then(function () { if (last) note(""); });
})();
