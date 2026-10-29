// S56 — the guest's ordering page. Its address carries #s=<the retailer's site>&t=<code>.<number>.<signature>; the part
// after # is never sent to a server in the address, only in the body of the two calls below. Every word the retailer
// wrote (a table, a dish, a choice) is put on the page as text, never as markup, with dir="auto".
(function () {
  "use strict";
  var WORDS = {
    en: { hint: "Prices before any offer: your bill is priced when you pay.", add: "Add", choose: "Choose",
          addOrder: "Add to order", pick: "choose {n}", upTo: "up to {n}", optional: "optional", basket: "Your order",
          send: "Send order", sending: "Sending...", note: "Note for the kitchen (optional)", loading: "Loading the menu...",
          kiosk: "Order here", lost: "We could not tell if your order was sent. Press Send order again: it will not be sent twice.",
          unknown: "This code does not work. Please ask a member of staff.",
          unavailable: "Ordering is not available right now. Please ask a member of staff.",
          tooMany: "An order holds at most {n} lines.", remove: "Remove", less: "One less", more: "One more",
          ask_staff: "This table cannot take orders from your phone right now. Please ask a member of staff.",
          ask_staff_kiosk: "This kiosk cannot take orders right now. Please order at the counter.",
          many_bills: "This table has more than one bill open. Please ask your server to take your order.",
          sent_twice: "This order was already sent once. Please ask your server to check your table's bill.",
          item_refused: "Something in your order cannot be ordered now. Please ask your server.",
          changed: "This table's bill changed a moment ago. Please send your order again.",
          wait: "An order for this table was sent a moment ago. Please send yours again in a few seconds.",
          sent_table: "Your order is on your table's bill. Your server will confirm it with you.",
          sent_kiosk: "Your order is {code}. Please pay at the counter.",
          order: "Something in your order has changed on the menu. Please open the menu again and check your order.",
          paying: "This table's bill is being paid. Please ask your server." },
    ar: { hint: "الأسعار قبل أي عرض: تُحسب فاتورتك عند الدفع.", add: "أضف", choose: "اختر", addOrder: "أضف إلى الطلب",
          pick: "اختر {n}", upTo: "حتى {n}", optional: "اختياري", basket: "طلبك", send: "أرسل الطلب", sending: "جارٍ الإرسال...",
          note: "ملاحظة للمطبخ (اختياري)", loading: "جارٍ تحميل القائمة...", kiosk: "اطلب هنا",
          lost: "لم نتمكن من التأكد من إرسال طلبك. اضغط أرسل الطلب مرة أخرى: لن يُرسل مرتين.",
          unknown: "هذا الرمز لا يعمل. يرجى سؤال أحد الموظفين.",
          unavailable: "الطلب غير متاح الآن. يرجى سؤال أحد الموظفين.",
          tooMany: "يحمل الطلب {n} أسطر على الأكثر.", remove: "احذف", less: "واحد أقل", more: "واحد أكثر",
          ask_staff: "لا تستقبل هذه الطاولة الطلبات من هاتفك الآن. يرجى سؤال أحد الموظفين.",
          ask_staff_kiosk: "لا يستقبل هذا الجهاز الطلبات الآن. يرجى الطلب عند الصندوق.",
          many_bills: "لهذه الطاولة أكثر من فاتورة مفتوحة. يرجى أن يأخذ النادل طلبك.",
          sent_twice: "أُرسل هذا الطلب من قبل. يرجى أن يتحقق النادل من فاتورة طاولتك.",
          item_refused: "شيء في طلبك غير متاح الآن. يرجى سؤال النادل.",
          changed: "تغيّرت فاتورة هذه الطاولة قبل لحظة. يرجى إرسال طلبك مرة أخرى.",
          wait: "أُرسل طلب لهذه الطاولة قبل لحظة. يرجى إرسال طلبك مرة أخرى بعد ثوانٍ.",
          sent_table: "طلبك على فاتورة طاولتك. سيؤكده النادل معك.",
          sent_kiosk: "رقم طلبك {code}. يرجى الدفع عند الصندوق.",
          order: "تغيّر شيء في طلبك على القائمة. يرجى فتح القائمة مرة أخرى ومراجعة طلبك.",
          paying: "تُدفع فاتورة هذه الطاولة الآن. يرجى سؤال النادل." },
    es: { hint: "Precios antes de ofertas: su cuenta se calcula al pagar.", add: "Añadir", choose: "Elegir",
          addOrder: "Añadir al pedido", pick: "elija {n}", upTo: "hasta {n}", optional: "opcional", basket: "Su pedido",
          send: "Enviar pedido", sending: "Enviando...", note: "Nota para la cocina (opcional)", loading: "Cargando la carta...",
          kiosk: "Pida aquí", lost: "No sabemos si su pedido se envió. Pulse Enviar pedido otra vez: no se enviará dos veces.",
          unknown: "Este código no funciona. Pregunte a un miembro del personal.",
          unavailable: "Ahora no se puede pedir. Pregunte a un miembro del personal.",
          tooMany: "Un pedido tiene como máximo {n} líneas.", remove: "Quitar", less: "Uno menos", more: "Uno más",
          ask_staff: "Esta mesa no acepta pedidos desde el teléfono ahora. Pregunte a un miembro del personal.",
          ask_staff_kiosk: "Este quiosco no acepta pedidos ahora. Pida en el mostrador.",
          many_bills: "Esta mesa tiene más de una cuenta abierta. Pida a su camarero que tome su pedido.",
          sent_twice: "Este pedido ya se envió una vez. Pida a su camarero que revise la cuenta de su mesa.",
          item_refused: "Algo de su pedido no se puede pedir ahora. Pregunte a su camarero.",
          changed: "La cuenta de esta mesa cambió hace un momento. Envíe su pedido otra vez.",
          wait: "Se acaba de enviar un pedido para esta mesa. Envíe el suyo de nuevo en unos segundos.",
          sent_table: "Su pedido está en la cuenta de su mesa. Su camarero lo confirmará con usted.",
          sent_kiosk: "Su pedido es el {code}. Pague en el mostrador.",
          order: "Algo de su pedido ha cambiado en la carta. Abra la carta de nuevo y revise su pedido.",
          paying: "Se está pagando la cuenta de esta mesa. Pregunte a su camarero." },
    fr: { hint: "Prix avant toute offre : votre addition est calculée au paiement.", add: "Ajouter", choose: "Choisir",
          addOrder: "Ajouter à la commande", pick: "choisissez {n}", upTo: "jusqu'à {n}", optional: "facultatif",
          basket: "Votre commande", send: "Envoyer la commande", sending: "Envoi...", note: "Note pour la cuisine (facultatif)",
          loading: "Chargement de la carte...", kiosk: "Commandez ici",
          lost: "Nous ne savons pas si votre commande est partie. Appuyez à nouveau sur Envoyer la commande : elle ne partira pas deux fois.",
          unknown: "Ce code ne fonctionne pas. Demandez à un membre du personnel.",
          unavailable: "La commande n'est pas disponible pour le moment. Demandez à un membre du personnel.",
          tooMany: "Une commande compte au plus {n} lignes.", remove: "Retirer", less: "Un de moins", more: "Un de plus",
          ask_staff: "Cette table ne prend pas de commandes par téléphone pour le moment. Demandez à un membre du personnel.",
          ask_staff_kiosk: "Cette borne ne prend pas de commandes pour le moment. Commandez au comptoir.",
          many_bills: "Cette table a plus d'une addition ouverte. Demandez à votre serveur de prendre votre commande.",
          sent_twice: "Cette commande a déjà été envoyée. Demandez à votre serveur de vérifier l'addition de votre table.",
          item_refused: "Un article de votre commande n'est pas disponible. Demandez à votre serveur.",
          changed: "L'addition de cette table vient de changer. Envoyez votre commande à nouveau.",
          wait: "Une commande vient d'être envoyée pour cette table. Renvoyez la vôtre dans quelques secondes.",
          sent_table: "Votre commande est sur l'addition de votre table. Votre serveur la confirmera avec vous.",
          sent_kiosk: "Votre commande est la {code}. Payez au comptoir.",
          order: "Un élément de votre commande a changé sur la carte. Rouvrez la carte et vérifiez votre commande.",
          paying: "L'addition de cette table est en cours de paiement. Demandez à votre serveur." },
    de: { hint: "Preise vor Angeboten: Ihre Rechnung wird beim Bezahlen berechnet.", add: "Hinzufügen", choose: "Auswählen",
          addOrder: "Zur Bestellung", pick: "{n} wählen", upTo: "bis zu {n}", optional: "optional", basket: "Ihre Bestellung",
          send: "Bestellung senden", sending: "Wird gesendet...", note: "Hinweis für die Küche (optional)",
          loading: "Die Karte wird geladen...", kiosk: "Hier bestellen",
          lost: "Wir wissen nicht, ob Ihre Bestellung gesendet wurde. Tippen Sie erneut auf Bestellung senden: Sie wird nicht doppelt gesendet.",
          unknown: "Dieser Code funktioniert nicht. Bitte fragen Sie das Personal.",
          unavailable: "Bestellen ist gerade nicht möglich. Bitte fragen Sie das Personal.",
          tooMany: "Eine Bestellung hat höchstens {n} Zeilen.", remove: "Entfernen", less: "Eins weniger", more: "Eins mehr",
          ask_staff: "An diesem Tisch kann gerade nicht per Telefon bestellt werden. Bitte fragen Sie das Personal.",
          ask_staff_kiosk: "An diesem Terminal kann gerade nicht bestellt werden. Bitte bestellen Sie an der Theke.",
          many_bills: "An diesem Tisch ist mehr als eine Rechnung offen. Bitte lassen Sie Ihre Bestellung vom Service aufnehmen.",
          sent_twice: "Diese Bestellung wurde bereits gesendet. Bitte lassen Sie die Rechnung Ihres Tisches vom Service prüfen.",
          item_refused: "Etwas in Ihrer Bestellung ist gerade nicht bestellbar. Bitte fragen Sie den Service.",
          changed: "Die Rechnung dieses Tisches hat sich gerade geändert. Bitte senden Sie Ihre Bestellung erneut.",
          wait: "Für diesen Tisch wurde gerade bestellt. Bitte senden Sie Ihre Bestellung in ein paar Sekunden erneut.",
          sent_table: "Ihre Bestellung steht auf der Rechnung Ihres Tisches. Der Service bestätigt sie mit Ihnen.",
          sent_kiosk: "Ihre Bestellung ist {code}. Bitte bezahlen Sie an der Theke.",
          order: "Etwas in Ihrer Bestellung hat sich auf der Karte geändert. Bitte öffnen Sie die Karte erneut und prüfen Sie Ihre Bestellung.",
          paying: "Die Rechnung dieses Tisches wird gerade bezahlt. Bitte fragen Sie den Service." },
    pt: { hint: "Preços antes de promoções: a conta é calculada no pagamento.", add: "Adicionar", choose: "Escolher",
          addOrder: "Adicionar ao pedido", pick: "escolha {n}", upTo: "até {n}", optional: "opcional", basket: "O seu pedido",
          send: "Enviar pedido", sending: "A enviar...", note: "Nota para a cozinha (opcional)", loading: "A carregar o menu...",
          kiosk: "Peça aqui", lost: "Não sabemos se o seu pedido foi enviado. Toque em Enviar pedido outra vez: não será enviado duas vezes.",
          unknown: "Este código não funciona. Pergunte a um membro da equipa.",
          unavailable: "Não é possível pedir agora. Pergunte a um membro da equipa.",
          tooMany: "Um pedido tem no máximo {n} linhas.", remove: "Remover", less: "Menos um", more: "Mais um",
          ask_staff: "Esta mesa não aceita pedidos pelo telemóvel agora. Pergunte a um membro da equipa.",
          ask_staff_kiosk: "Este quiosque não aceita pedidos agora. Peça ao balcão.",
          many_bills: "Esta mesa tem mais de uma conta aberta. Peça ao seu empregado que registe o pedido.",
          sent_twice: "Este pedido já foi enviado. Peça ao seu empregado que verifique a conta da mesa.",
          item_refused: "Algo no seu pedido não pode ser pedido agora. Pergunte ao seu empregado.",
          changed: "A conta desta mesa mudou há um momento. Envie o pedido outra vez.",
          wait: "Acabou de ser enviado um pedido para esta mesa. Envie o seu outra vez daqui a uns segundos.",
          sent_table: "O seu pedido está na conta da sua mesa. O seu empregado vai confirmá-lo consigo.",
          sent_kiosk: "O seu pedido é o {code}. Pague ao balcão.",
          order: "Algo no seu pedido mudou no menu. Abra o menu outra vez e verifique o seu pedido.",
          paying: "A conta desta mesa está a ser paga. Pergunte ao seu empregado." }
  };
  var lang = (navigator.language || "en").slice(0, 2).toLowerCase();
  var W = WORDS[lang] || WORDS.en;
  if (WORDS[lang]) { document.documentElement.lang = lang; }
  if (lang === "ar") { document.documentElement.dir = "rtl"; }

  var hash = new URLSearchParams(location.hash.slice(1));
  var who = { s: hash.get("s") || "", t: hash.get("t") || "" };
  var $ = function (id) { return document.getElementById(id); };
  var menu = null, basket = [], key = null, busy = false, money = null;
  var KEPT_MS = 10 * 60 * 1000;      // an order's key kept this long in the browser, for a reload or a second scan

  function fmt(text, vals) { return text.replace(/\{(\w+)\}/g, function (_, k) { return vals[k]; }); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text !== undefined && text !== null) { e.textContent = text; }
    return e;
  }
  function own(tag, cls, text) { var e = el(tag, cls, text); e.dir = "auto"; return e; }   // the retailer's words
  function newKey() {
    if (window.crypto && crypto.randomUUID) { return crypto.randomUUID(); }
    var b = new Uint8Array(16); crypto.getRandomValues(b);
    return Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }
  function price(v) {
    if (v === null || v === undefined) { return ""; }
    try { return money ? money.format(v) : String(v); } catch (e) { return String(v); }
  }
  function say(answer) {
    var w = answer.say && W[answer.say];
    return w ? fmt(w, { code: answer.code || "" }) : (answer.words || W.unavailable);
  }
  function note(text, done) { var n = $("note"); n.textContent = text || ""; n.className = done ? "note done" : "note"; }

  function call(path, extra) {
    var body = Object.assign({ s: who.s, t: who.t }, extra || {});
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
                         credentials: "omit", cache: "no-store" })
      .then(function (r) { return r.json().catch(function () { return { state: "unavailable" }; }); });
  }

  function rule(g) {
    if (g.min && g.max === g.min) { return fmt(W.pick, { n: g.min }); }
    if (g.max && !g.min) { return W.optional + ", " + fmt(W.upTo, { n: g.max }); }
    if (g.max) { return fmt(W.pick, { n: g.min }) + ", " + fmt(W.upTo, { n: g.max }); }
    return g.min ? fmt(W.pick, { n: g.min }) : W.optional;
  }

  function chooser(dish, box) {
    var panel = el("div", "choose"), inputs = [];
    dish.groups.forEach(function (g, gi) {
      var fs = el("fieldset", "group"), lg = el("legend");
      lg.appendChild(own("span", null, g.label));
      lg.appendChild(el("span", "group-rule", " (" + rule(g) + ")"));
      fs.appendChild(lg);
      g.choices.forEach(function (c) {
        var lab = el("label", "choice"), inp = el("input");
        inp.type = g.min >= 1 && g.max === 1 ? "radio" : "checkbox";   // an optional choice can be unticked
        inp.name = dish.code + "-" + gi;
        inp.value = c.code;
        inputs.push({ input: inp, group: g, choice: c });
        lab.appendChild(inp);
        lab.appendChild(own("span", null, c.name));
        if (c.price) { lab.appendChild(el("span", "price", "+" + price(c.price))); }
        fs.appendChild(lab);
      });
      panel.appendChild(fs);
    });
    var go = el("button", "add", W.addOrder);
    go.type = "button";
    go.addEventListener("click", function () {
      var picked = inputs.filter(function (x) { return x.input.checked; });
      for (var i = 0; i < dish.groups.length; i++) {
        var g = dish.groups[i], n = picked.filter(function (x) { return x.group === g; }).length;
        if (n < g.min || (g.max && n > g.max)) { note(g.label + ": " + rule(g)); return; }
      }
      addLine(dish, picked.map(function (x) { return x.choice; }));
      panel.remove();
    });
    panel.appendChild(go);
    box.appendChild(panel);
  }

  function addLine(dish, choices) {
    if (basket.length >= menu.most_lines) { note(fmt(W.tooMany, { n: menu.most_lines })); return; }
    basket.push({ dish: dish, choices: choices, qty: 1, note: "" });
    key = null;
    note("");
    drawBasket();
  }

  function drawMenu() {
    var root = $("menu");
    root.textContent = "";
    menu.menu.forEach(function (sec) {
      if (sec.group) { root.appendChild(own("h2", null, sec.group)); }
      sec.dishes.forEach(function (d) {
        var box = el("div", "dish"), head = el("div", "dish-head");
        head.appendChild(own("span", "dish-name", d.name));
        head.appendChild(el("span", "price", price(d.price)));
        box.appendChild(head);
        var b = el("button", "add", d.groups.length ? W.choose : W.add);
        b.type = "button";
        b.addEventListener("click", function () {
          if (!d.groups.length) { addLine(d, []); return; }
          var open = box.querySelector(".choose");
          if (open) { open.remove(); } else { chooser(d, box); }
        });
        box.appendChild(b);
        root.appendChild(box);
      });
    });
  }

  function drawBasket() {
    var list = $("lines");
    list.textContent = "";
    $("basket").hidden = basket.length === 0;
    basket.forEach(function (ln, i) {
      var li = el("li", "line"), head = el("div", "line-head");
      head.appendChild(own("span", "line-name", ln.dish.name));
      var q = el("span", "qty"), minus = el("button", null, "-"), plus = el("button", null, "+");
      minus.type = plus.type = "button";
      minus.setAttribute("aria-label", ln.qty > 1 ? W.less : W.remove);
      plus.setAttribute("aria-label", W.more);
      minus.addEventListener("click", function () { if (ln.qty > 1) { ln.qty--; } else { basket.splice(i, 1); } key = null; drawBasket(); });
      plus.addEventListener("click", function () { if (ln.qty < menu.most_qty) { ln.qty++; key = null; drawBasket(); } });
      q.appendChild(minus); q.appendChild(el("span", null, String(ln.qty))); q.appendChild(plus);
      head.appendChild(q);
      li.appendChild(head);
      if (ln.choices.length) {
        li.appendChild(own("div", "line-choices", ln.choices.map(function (c) { return c.name; }).join(", ")));
      }
      var inp = el("input");
      inp.maxLength = 80; inp.placeholder = W.note; inp.value = ln.note; inp.dir = "auto";
      inp.addEventListener("input", function () { ln.note = inp.value; key = null; });
      li.appendChild(inp);
      list.appendChild(li);
    });
  }

  // The order's key, kept in the browser beside the order it was made for: the page reloaded or the card scanned again
  // after a lost answer, the same order sends the same key, and the till's door writes it once.
  function keptKey(sig) {
    try {
      var k = JSON.parse(localStorage.getItem("gor:" + who.t) || "null");
      return k && k.sig === sig && Date.now() - k.at < KEPT_MS ? k.key : null;
    } catch (e) { return null; }
  }
  function keepKey(sig, k) {
    try { if (k) { localStorage.setItem("gor:" + who.t, JSON.stringify({ sig: sig, key: k, at: Date.now() })); }
          else { localStorage.removeItem("gor:" + who.t); } } catch (e) { /* private window: the page's own key */ }
  }

  function send() {
    if (busy || !basket.length) { return; }
    busy = true;
    var lines = basket.map(function (ln) {
      return { item_code: ln.dish.code, qty: ln.qty, note: ln.note,
               options: ln.choices.map(function (c) { return c.code; }) };
    });
    var sig = JSON.stringify(lines);
    key = key || keptKey(sig) || newKey();   // the same key until the order changes: a retry is never sent twice
    keepKey(sig, key);
    $("send").disabled = true;
    $("send").textContent = W.sending;
    call("/gor/order", { key: key, lines: lines }).then(function (a) {
      if (a.state === "sent") { basket = []; key = null; keepKey(sig, null); drawBasket(); note(say(a), true); }
      else if (a.state === "unknown") { note(W.unknown); }
      else if (a.state === "unavailable") { note(W.lost); }     // it may have landed: the same key is sent again
      else { note(say(a)); }
    }).catch(function () { note(W.lost); }).then(function () {
      busy = false;
      $("send").disabled = false;
      $("send").textContent = W.send;
    });
  }

  $("basket-title").textContent = W.basket;
  $("send").textContent = W.send;
  $("send").addEventListener("click", send);
  if (!who.s || !who.t) { note(W.unknown); return; }
  note(W.loading);
  call("/gor/menu").then(function (a) {
    if (a.state !== "open") { note(a.state === "unknown" ? W.unknown : say(a)); return; }
    menu = a;
    try { money = a.currency ? new Intl.NumberFormat(navigator.language || "en", { style: "currency", currency: a.currency }) : null; }
    catch (e) { money = null; }
    $("where").textContent = a.where || (a.kind === "Kiosk" ? W.kiosk : "");
    $("hint").textContent = W.hint;
    note("");
    drawMenu();
  }).catch(function () { note(W.unavailable); });
})();
