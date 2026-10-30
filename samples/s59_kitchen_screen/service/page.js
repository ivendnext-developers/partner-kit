// S59 — the kitchen screen's page: a station screen, the expo, or the Now serving board, by the screen record its link
// names. Its address carries #s=<the retailer's site>&t=<screen>.<number>.<signature>; the part after # is never sent to
// a server in the address, only in the body of the calls below. It reads the board every READ_MS (the station-ticket
// door's own fallback: no cursor, every read is the whole board), so a screen that lost its connection has caught up on
// its next read. Every word the retailer wrote (a dish, a note, a station, a table) is put on the page as text, never as
// markup, inside a <bdi> in a block of the page's own direction, so a ticket has one reading edge whatever the words'
// script. A state is shown by an icon, a word and a colour together. The page never scrolls: fit() (with fit.js's
// rules) folds a ticket taller than the board behind "+N more dishes" and shows only whole tickets, paged.
(function () {
  "use strict";
  var READ_MS = 3000, RETRY_MS = 3000, LATE_READ_S = 15, NOTE_MS = 6000, PAGE_BACK_MS = 60000, SHIFT_MS = 1000;
  var STRIP_SHARE = 0.25;            // "Still to make" takes at most a quarter of the screen's height
  // The till's own words where it has them (guest and sold out, from its ar, es and fr tables at T21; send is never
  // used for a bump, which is the kitchen's own step); German and Portuguese are this app's own until the till signs them.
  var WORDS = {
    en: { moreChoice: "+1 more choice", moreChoices: "+{n} more choices",
          moreDish: "+1 more dish", moreDishes: "+{n} more dishes", moreTicket: "+1 more ticket",
          moreTickets: "+{n} more tickets", earlier: "Earlier tickets", later: "Later tickets", smaller: "Smaller tickets",
          bigger: "Larger tickets", compact: "Compact", standard: "Standard", large: "Large", xlarge: "Extra large",
          start: "Start", ready: "Ready", bump: "Bump", bumpOrder: "Bump order", recall: "Recall", soldOut: "Sold out",
          soldTitle: "Sold out at this store", markSold: "Mark sold out", markBack: "Available again", isSold: "Sold out",
          close: "Close", waiting: "Still to make", preparing: "Preparing", readyCol: "Ready", void: "Void: stop making",
          recallNote: "Bumped in the last 30 minutes, to read again. A bumped ticket cannot be moved back.",
          lastRead: "Last read {t}", empty: "No tickets", nothing: "Nothing waiting", onTime: "On time",
          warn: "Late soon", late: "Late", min: "{n} min", guest: "Guest {n}", stNew: "New", stStarted: "Started",
          stReady: "Ready", stBumped: "Bumped", loading: "Reading the kitchen's tickets...",
          unknown: "This screen's link does not work, or it was replaced. Ask your manager for the screen's new link.",
          closed: "This store is not set up for kitchen screens. Ask your manager.",
          not_set_up: "This screen cannot read the kitchen's tickets. Ask your manager to check the app's user and its key.",
          unavailable: "The kitchen's tickets cannot be read right now. This screen tries again by itself.",
          step: "This ticket moved on another screen. The board is read again.", gone: "This ticket is no longer on the board.",
          not_yours: "This ticket is another station's.", wait: "One moment, then tap again.",
          not_listed: "That dish is not on this screen's list.", off: "Sold out is switched off for this store." },
    ar: { moreChoice: "+خيار واحد آخر", moreChoices: "+{n} خيارات أخرى", moreDish2: "+طبقان آخران",
          moreDishes11: "+{n} طبقًا آخر", moreTicket2: "+تذكرتان أخريان", moreTickets11: "+{n} تذكرةً أخرى",
          moreChoice2: "+خياران آخران", moreChoices11: "+{n} خيارًا آخر",
          moreDish: "+طبق واحد آخر", moreDishes: "+{n} أطباق أخرى", moreTicket: "+تذكرة واحدة أخرى",
          moreTickets: "+{n} تذاكر أخرى", earlier: "التذاكر السابقة", later: "التذاكر التالية", smaller: "تذاكر أصغر",
          bigger: "تذاكر أكبر", compact: "مضغوط", standard: "عادي", large: "كبير", xlarge: "كبير جدًا",
          start: "ابدأ", ready: "جاهز", bump: "أنهِ", bumpOrder: "أنهِ الطلب", recall: "استرجاع", soldOut: "نفدت الكمية",
          soldTitle: "نفدت الكمية في هذا المتجر", markSold: "علّمه نافدًا", markBack: "متوفر مرة أخرى", isSold: "نفدت الكمية",
          close: "إغلاق", waiting: "ما زال للتحضير", preparing: "قيد التحضير", readyCol: "جاهز", void: "ملغى: أوقف التحضير",
          recallNote: "أُنهيت في آخر 30 دقيقة، لقراءتها مرة أخرى. لا يمكن إعادة تذكرة منتهية.",
          lastRead: "آخر قراءة {t}", empty: "لا تذاكر", nothing: "لا شيء بانتظار التحضير", onTime: "في الوقت",
          warn: "سيتأخر قريبًا", late: "متأخر", min: "{n} د", guest: "الضيف {n}", stNew: "جديد", stStarted: "بدأ",
          stReady: "جاهز", stBumped: "منتهٍ", loading: "جارٍ قراءة تذاكر المطبخ...",
          unknown: "رابط هذه الشاشة لا يعمل أو استُبدل. اطلب من المدير الرابط الجديد.",
          closed: "هذا المتجر غير مُعدّ لشاشات المطبخ. اسأل المدير.",
          not_set_up: "لا تستطيع هذه الشاشة قراءة تذاكر المطبخ. اطلب من المدير التحقق من مستخدم التطبيق ومفتاحه.",
          unavailable: "لا يمكن قراءة تذاكر المطبخ الآن. ستحاول الشاشة مرة أخرى بنفسها.",
          step: "تغيّرت هذه التذكرة على شاشة أخرى. تُقرأ اللوحة مرة أخرى.", gone: "لم تعد هذه التذكرة على اللوحة.",
          not_yours: "هذه التذكرة لمحطة أخرى.", wait: "لحظة، ثم اضغط مرة أخرى.",
          not_listed: "هذا الطبق ليس في قائمة هذه الشاشة.", off: "خاصية النفاد متوقفة في هذا المتجر." },
    es: { moreChoice: "+1 opción más", moreChoices: "+{n} opciones más",
          moreDish: "+1 plato más", moreDishes: "+{n} platos más", moreTicket: "+1 ticket más",
          moreTickets: "+{n} tickets más", earlier: "Tickets anteriores", later: "Tickets siguientes",
          smaller: "Tickets más pequeños", bigger: "Tickets más grandes", compact: "Compacto", standard: "Estándar",
          large: "Grande", xlarge: "Muy grande",
          start: "Empezar", ready: "Listo", bump: "Retirar", bumpOrder: "Retirar pedido", recall: "Recuperar", soldOut: "Agotado",
          soldTitle: "Agotado en esta tienda", markSold: "Marcar agotado", markBack: "Disponible otra vez", isSold: "Agotado",
          close: "Cerrar", waiting: "Por preparar", preparing: "Preparando", readyCol: "Listo", void: "Anulado: no preparar",
          recallNote: "Retirados en los últimos 30 minutos, para leer otra vez. Un ticket retirado no puede volver atrás.",
          lastRead: "Última lectura {t}", empty: "Sin tickets", nothing: "Nada pendiente", onTime: "A tiempo",
          warn: "Casi tarde", late: "Tarde", min: "{n} min", guest: "Comensal {n}", stNew: "Nuevo", stStarted: "Empezado",
          stReady: "Listo", stBumped: "Retirado", loading: "Leyendo los tickets de la cocina...",
          unknown: "El enlace de esta pantalla no funciona o fue sustituido. Pida el nuevo enlace a su encargado.",
          closed: "Esta tienda no tiene pantallas de cocina configuradas. Pregunte a su encargado.",
          not_set_up: "Esta pantalla no puede leer los tickets. Pida a su encargado que revise el usuario de la app y su clave.",
          unavailable: "Ahora no se pueden leer los tickets. La pantalla lo intentará de nuevo sola.",
          step: "Este ticket cambió en otra pantalla. Se lee el tablero otra vez.", gone: "Este ticket ya no está en el tablero.",
          not_yours: "Este ticket es de otra estación.", wait: "Un momento y pulse otra vez.",
          not_listed: "Ese plato no está en la lista de esta pantalla.", off: "Agotado está desactivado en esta tienda." },
    fr: { moreChoice: "+1 option de plus", moreChoices: "+{n} options de plus",
          moreDish: "+1 plat de plus", moreDishes: "+{n} plats de plus", moreTicket: "+1 ticket de plus",
          moreTickets: "+{n} tickets de plus", earlier: "Tickets précédents", later: "Tickets suivants",
          smaller: "Tickets plus petits", bigger: "Tickets plus grands", compact: "Compact", standard: "Standard",
          large: "Grand", xlarge: "Très grand",
          start: "Commencer", ready: "Prêt", bump: "Retirer", bumpOrder: "Retirer la commande", recall: "Rappel",
          soldOut: "Épuisé", soldTitle: "Épuisé dans ce magasin", markSold: "Marquer épuisé", markBack: "De nouveau disponible",
          isSold: "Épuisé", close: "Fermer", waiting: "Reste à préparer", preparing: "En préparation", readyCol: "Prêt",
          void: "Annulé : ne pas préparer",
          recallNote: "Retirés dans les 30 dernières minutes, à relire. Un ticket retiré ne peut pas revenir en arrière.",
          lastRead: "Dernière lecture {t}", empty: "Aucun ticket", nothing: "Rien en attente", onTime: "À l'heure",
          warn: "Bientôt en retard", late: "En retard", min: "{n} min", guest: "Couvert {n}", stNew: "Nouveau",
          stStarted: "Commencé", stReady: "Prêt", stBumped: "Retiré", loading: "Lecture des tickets de la cuisine...",
          unknown: "Le lien de cet écran ne fonctionne pas ou a été remplacé. Demandez le nouveau lien à votre responsable.",
          closed: "Ce magasin n'a pas d'écrans de cuisine configurés. Demandez à votre responsable.",
          not_set_up: "Cet écran ne peut pas lire les tickets. Demandez à votre responsable de vérifier l'utilisateur de l'app et sa clé.",
          unavailable: "Les tickets ne peuvent pas être lus pour le moment. L'écran réessaie tout seul.",
          step: "Ce ticket a changé sur un autre écran. Le tableau est relu.", gone: "Ce ticket n'est plus au tableau.",
          not_yours: "Ce ticket est celui d'un autre poste.", wait: "Un instant, puis appuyez de nouveau.",
          not_listed: "Ce plat n'est pas dans la liste de cet écran.", off: "Épuisé est désactivé dans ce magasin." },
    de: { moreChoice: "+1 weitere Option", moreChoices: "+{n} weitere Optionen",
          moreDish: "+1 weiteres Gericht", moreDishes: "+{n} weitere Gerichte", moreTicket: "+1 weiterer Bon",
          moreTickets: "+{n} weitere Bons", earlier: "Frühere Bons", later: "Spätere Bons", smaller: "Kleinere Bons",
          bigger: "Größere Bons", compact: "Kompakt", standard: "Standard", large: "Groß", xlarge: "Sehr groß",
          start: "Starten", ready: "Fertig", bump: "Abräumen", bumpOrder: "Bestellung abräumen", recall: "Zurückholen",
          soldOut: "Ausverkauft", soldTitle: "Ausverkauft in dieser Filiale", markSold: "Als ausverkauft markieren",
          markBack: "Wieder verfügbar", isSold: "Ausverkauft", close: "Schließen", waiting: "Noch zuzubereiten",
          preparing: "In Zubereitung", readyCol: "Fertig", void: "Storniert: nicht zubereiten",
          recallNote: "In den letzten 30 Minuten abgeräumt, zum erneuten Lesen. Ein abgeräumter Bon kann nicht zurück.",
          lastRead: "Zuletzt gelesen {t}", empty: "Keine Bons", nothing: "Nichts offen", onTime: "Pünktlich",
          warn: "Bald spät", late: "Spät", min: "{n} Min.", guest: "Gast {n}", stNew: "Neu", stStarted: "Begonnen",
          stReady: "Fertig", stBumped: "Abgeräumt", loading: "Die Bons der Küche werden gelesen...",
          unknown: "Der Link dieses Bildschirms funktioniert nicht oder wurde ersetzt. Fragen Sie Ihre Leitung nach dem neuen Link.",
          closed: "Diese Filiale ist nicht für Küchenbildschirme eingerichtet. Fragen Sie Ihre Leitung.",
          not_set_up: "Dieser Bildschirm kann die Bons nicht lesen. Ihre Leitung soll den Benutzer der App und seinen Schlüssel prüfen.",
          unavailable: "Die Bons können gerade nicht gelesen werden. Der Bildschirm versucht es selbst erneut.",
          step: "Dieser Bon wurde an einem anderen Bildschirm geändert. Die Tafel wird neu gelesen.",
          gone: "Dieser Bon ist nicht mehr auf der Tafel.", not_yours: "Dieser Bon gehört zu einer anderen Station.",
          wait: "Einen Moment, dann noch einmal tippen.", not_listed: "Dieses Gericht steht nicht auf der Liste dieses Bildschirms.",
          off: "Ausverkauft ist für diese Filiale ausgeschaltet." },
    pt: { moreChoice: "+1 opção a mais", moreChoices: "+{n} opções a mais",
          moreDish: "+1 prato a mais", moreDishes: "+{n} pratos a mais", moreTicket: "+1 pedido a mais",
          moreTickets: "+{n} pedidos a mais", earlier: "Pedidos anteriores", later: "Próximos pedidos",
          smaller: "Pedidos menores", bigger: "Pedidos maiores", compact: "Compacto", standard: "Padrão",
          large: "Grande", xlarge: "Muito grande",
          start: "Começar", ready: "Pronto", bump: "Retirar", bumpOrder: "Retirar pedido", recall: "Recuperar",
          soldOut: "Esgotado", soldTitle: "Esgotado nesta loja", markSold: "Marcar esgotado", markBack: "Disponível de novo",
          isSold: "Esgotado", close: "Fechar", waiting: "Ainda por fazer", preparing: "Em preparo", readyCol: "Pronto",
          void: "Cancelado: não preparar",
          recallNote: "Retirados nos últimos 30 minutos, para ler de novo. Um pedido retirado não pode voltar atrás.",
          lastRead: "Última leitura {t}", empty: "Sem pedidos", nothing: "Nada pendente", onTime: "No prazo",
          warn: "Quase atrasado", late: "Atrasado", min: "{n} min", guest: "Cliente {n}", stNew: "Novo", stStarted: "Começado",
          stReady: "Pronto", stBumped: "Retirado", loading: "Lendo os pedidos da cozinha...",
          unknown: "O link desta tela não funciona ou foi substituído. Peça o novo link ao seu gerente.",
          closed: "Esta loja não tem telas de cozinha configuradas. Pergunte ao seu gerente.",
          not_set_up: "Esta tela não consegue ler os pedidos. Peça ao seu gerente para verificar o usuário do app e a chave.",
          unavailable: "Os pedidos não podem ser lidos agora. A tela tenta de novo sozinha.",
          step: "Este pedido mudou em outra tela. O quadro é lido de novo.", gone: "Este pedido não está mais no quadro.",
          not_yours: "Este pedido é de outra estação.", wait: "Um momento e toque de novo.",
          not_listed: "Esse prato não está na lista desta tela.", off: "Esgotado está desligado nesta loja." }
  };
  var lang = "en";
  function count(one, many, n) {     // "+1 more dish", "+N more dishes"; Arabic's dual and 11-and-over forms
    if (n === 1) return w(one);
    if (lang === "ar" && n === 2) return w(one + "2");
    if (lang === "ar" && n >= 11) return w(many + "11", { n: n });
    return w(many, { n: n });
  }
  function w(key, args) {
    var s = (WORDS[lang] && WORDS[lang][key]) || WORDS.en[key] || "";
    Object.keys(args || {}).forEach(function (k) { s = s.split("{" + k + "}").join(String(args[k])); });
    return s;
  }

  var hash = new URLSearchParams(location.hash.slice(1));
  var LINK = { s: hash.get("s") || "", t: hash.get("t") || "" };
  var $ = function (id) { return document.getElementById(id); };
  var last = null, readAt = 0, goodAt = 0, timer = null, busy = {}, showRecall = false, page = 0, touchedAt = 0;
  var shiftedAt = -1e9, openKey = "";

  // ── drawing helpers: text only, never markup ──
  function bdi(text) { var b = document.createElement("bdi"); b.textContent = String(text); return b; }
  function el(tag, cls, text, own) {   // own: the retailer's words, isolated so the block keeps the page's edge
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) {
      if (own) e.appendChild(bdi(text));
      else e.textContent = String(text);
    }
    return e;
  }
  var ICONS = {   // 24×24 strokes, drawn in currentColor
    clock: ["M12 7v5l3 2", "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18"],
    warn: ["M12 3l9 16H3z", "M12 10v4", "M12 17v.5"],
    check: ["M5 12l5 5L19 7"],
    cross: ["M6 6l12 12", "M18 6L6 18"],
    play: ["M8 5l11 7-11 7z"],
    flame: ["M12 3c3 4 5 6 5 10a5 5 0 0 1-10 0c0-2 1-4 3-5c0 2 1 3 2 3c0-3-1-5 0-8"],
    back: ["M15 5l-7 7 7 7"],
    forth: ["M9 5l7 7-7 7"]
  };
  function icon(name) {
    var NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("class", "ksc-icon"); svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("fill", "none"); svg.setAttribute("stroke", "currentColor"); svg.setAttribute("stroke-width", "2.2");
    svg.setAttribute("stroke-linecap", "round"); svg.setAttribute("stroke-linejoin", "round");
    ICONS[name].forEach(function (d) { var p = document.createElementNS(NS, "path"); p.setAttribute("d", d); svg.appendChild(p); });
    return svg;
  }
  function withIcon(tag, cls, name, text, own) {
    var e = el(tag, cls); e.appendChild(icon(name)); e.appendChild(el("span", "", text, own)); return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  // ── the site's own clock: a ticket's age is the door's as_of minus its sent_at, plus the time since the read ──
  function stamp(s) {
    var m = /^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)/.exec(s || "");
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) : NaN;
  }
  function ageMin(from) {
    var a = stamp(last && last.as_of), b = stamp(from);
    if (isNaN(a) || isNaN(b)) return 0;
    return Math.max(0, Math.floor(((a - b) + (Date.now() - readAt)) / 60000));
  }
  function timerOf(from, look) {
    var m = ageMin(from), cls = m >= look.late ? "is-late" : m >= look.warn ? "is-warn" : "";
    var t = withIcon("span", "ksc-timer " + cls, cls === "is-late" ? "flame" : cls ? "warn" : "clock",
      w("min", { n: m }) + " · " + (cls === "is-late" ? w("late") : cls ? w("warn") : w("onTime")));
    t.setAttribute("data-from", from || "");
    return { node: t, cls: cls };
  }

  // ── the calls ──
  function call(path, extra) {
    var body = Object.assign({ s: LINK.s, t: LINK.t }, extra || {});
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
                         cache: "no-store", credentials: "omit" })
      .then(function (r) { return r.json().catch(function () { return { state: "unavailable" }; }); })
      .catch(function () { return { state: "unavailable" }; });
  }
  var noteUntil = 0, noteFor = "";
  function answered(a, what) {       // a refusal is held; only a later success on the SAME ticket or dish takes it down
    if (a.state === "refused" && WORDS.en[a.why]) { note(a.why, true); noteFor = what; }
    else if (what === noteFor && (a.state === "moved" || a.state === "set")) { noteUntil = 0; note(""); }
  }
  function note(key, hold) {         // a tap's refusal is held NOTE_MS, so the read that follows does not wipe it
    var n = $("note");
    if (!key) {
      if (performance.now() < noteUntil || n.hidden) return;
      n.hidden = true; n.textContent = ""; fit(); return;
    }
    n.textContent = w(key); n.hidden = false;
    noteUntil = hold ? performance.now() + NOTE_MS : 0;
    fit();                           // the note sits above the board: the board is fitted again below it
  }
  function schedule(ms) { clearTimeout(timer); timer = setTimeout(read, ms); }
  function read() {
    return call("/ksc/board").then(function (a) {
      if (a.state === "open") {
        last = a; readAt = Date.now(); goodAt = readAt;
        if (a.look) {
          lang = WORDS[a.look.lang] ? a.look.lang : "en";
          var vars = a.look.accent ? { "--ivn-primary": a.look.accent, "--ivn-primary-strong": a.look.accent, "--ivn-focus": a.look.accent } : {};
          window.ivnKit.applyTheme({ mode: a.look.mode, vars: vars });
          window.ivnKit.applyDir(lang);
        }
        applySize();
        note("");
        draw();
        schedule(READ_MS);
      } else if (a.state === "unknown" || a.state === "closed" || a.state === "not_set_up") {
        last = null; clear($("board")); $("waiting").hidden = true; pager(0, 0, false, false); note(a.state);
        schedule(a.state === "unknown" ? 60000 : 15000);   // a replaced link stays refused: read again rarely
      } else {
        note(goodAt ? "" : "unavailable"); stale(); schedule(RETRY_MS);
      }
    });
  }
  function stale() {
    var r = $("read"), late = goodAt && (Date.now() - goodAt) / 1000 > LATE_READ_S;
    r.className = "ksc-read" + (late ? " is-late" : "");
    r.textContent = goodAt ? w("lastRead", { t: new Date(goodAt).toLocaleTimeString(lang) }) : w("loading");
  }

  // ── moves ──
  function move(btn, extra) {
    var key = extra.kitchen_order + "." + (extra.ticket || "order");
    if (busy[key] || performance.now() - shiftedAt < SHIFT_MS) return;   // the page just changed under the finger
    busy[key] = true; btn.disabled = true;
    call("/ksc/move", extra).then(function (a) {
      busy[key] = false;
      answered(a, key);
      read();
    });
  }
  var NEXT = { "new": ["started", "start"], started: ["ready", "ready"], ready: ["bumped", "bump"] };
  var STATE_WORD = { "new": "stNew", started: "stStarted", ready: "stReady", bumped: "stBumped" };
  var STATE_ICON = { "new": "clock", started: "play", ready: "check", bumped: "check" };

  function lines(t, cls) {
    var ul = el("ul", "ksc-lines " + (cls || ""));
    t.lines.forEach(function (ln) {
      var li = el("li", "ksc-line" + (ln.under !== null ? " is-choice" : ""));
      li.appendChild(el("span", "", (ln.qty || "") + "× "));
      li.appendChild(bdi(ln.item_name || ln.item_code));
      if (ln.note) li.appendChild(el("span", "ksc-line-note", ln.note, true));
      var who = [ln.guest ? w("guest", { n: ln.guest }) : "", ln.course || ""].filter(Boolean).join(" · ");
      if (who && ln.under === null) li.appendChild(el("span", "ksc-line-who", who, true));
      if (ln.allergens) li.appendChild(withIcon("span", "ksc-allergens", "warn", ln.allergens, true));
      ul.appendChild(li);
    });
    return ul;
  }

  function ticketCard(t, look, readOnly) {
    var tm = timerOf(t.sent_at, look);
    var card = el("article", "ksc-ticket ksc-slip " + (t.kind === "void" ? "is-void " : "") + (t.state === "bumped" ? "" : tm.cls));
    card.setAttribute("data-key", t.kitchen_order + "." + t.ticket);
    var head = el("div", "ksc-ticket-head");
    head.appendChild(el("p", "ksc-call", t.call_number || "#" + t.ticket, true));
    head.appendChild(tm.node);
    card.appendChild(head);
    card.appendChild(withIcon("p", "ksc-meta ksc-state ksc-st-" + t.state, STATE_ICON[t.state], w(STATE_WORD[t.state])));
    var meta = [t.till, last.stations.length > 1 ? t.station : ""].filter(Boolean).join(" · ");
    if (meta) card.appendChild(el("p", "ksc-meta", meta, true));
    if (t.kind === "void") card.appendChild(withIcon("p", "ksc-void", "cross", w("void")));
    card.appendChild(lines(t));
    card.appendChild(more(t.call_number || "#" + t.ticket, t.kitchen_order + "." + t.ticket, function () {
      var box = el("div", t.kind === "void" ? "is-void" : "");     // a void reads as one in the dialog too
      if (t.kind === "void") box.appendChild(withIcon("p", "ksc-void", "cross", w("void")));
      box.appendChild(lines(t));
      return [box];
    }));
    var next = NEXT[t.state];
    if (!readOnly && next) {
      var b = el("button", "ivn-btn " + (next[0] === "bumped" ? "ivn-btn-primary " : "") + "ivn-btn-block ksc-act", w(next[1]));
      b.type = "button";
      b.addEventListener("click", function () { move(b, { kitchen_order: t.kitchen_order, ticket: t.ticket, state: next[0] }); });
      card.appendChild(b);
    }
    return card;
  }

  function drawStation(main, v, look) {
    var list = showRecall ? v.recall : v.tickets;
    if (showRecall) main.appendChild(el("p", "ksc-empty", w("recallNote")));
    if (!list.length && !showRecall) main.appendChild(el("p", "ksc-empty", w("empty")));
    list.forEach(function (t) { main.appendChild(ticketCard(t, look, showRecall)); });
  }

  function part(t) {                 // one station's share of an order, on the expo
    var sec = el("section", "ksc-part" + (t.kind === "void" ? " ksc-ticket is-void" : ""));
    var ph = el("div", "ksc-part-head");
    ph.appendChild(el("span", "", t.station, true));
    ph.appendChild(withIcon("span", "ksc-state", t.kind === "void" ? "cross" : STATE_ICON[t.state],
      t.kind === "void" ? w("void") : w(STATE_WORD[t.state])));
    sec.appendChild(ph);
    sec.appendChild(lines(t));
    return sec;
  }

  function drawExpo(main, v, look) {
    var strip = $("waiting"); clear(strip);
    strip.hidden = false;
    strip.appendChild(el("span", "", w("waiting") + ":"));
    if (!v.waiting.length) strip.appendChild(el("span", "", w("nothing")));
    v.waiting.forEach(function (d) {
      var sp = el("span", "ksc-wait", d.qty + "× "); sp.appendChild(bdi(d.item_name)); strip.appendChild(sp);
    });
    var rest = el("span", "ksc-wait-more"); rest.hidden = true; strip.appendChild(rest);
    if (!v.orders.length) main.appendChild(el("p", "ksc-empty", w("empty")));
    v.orders.forEach(function (o) {
      var card = el("article", "ksc-order ksc-slip" + (o.bump ? " is-ready" : ""));
      card.setAttribute("data-key", o.kitchen_order);
      var head = el("div", "ksc-ticket-head"), tm = timerOf(o.sent_at, look);
      head.appendChild(el("p", "ksc-call", o.call_number || o.kitchen_order, true));
      head.appendChild(tm.node);
      card.appendChild(head);
      o.tickets.forEach(function (t) { card.appendChild(part(t)); });
      card.appendChild(more(o.call_number || o.kitchen_order, o.kitchen_order, function () { return o.tickets.map(part); }));
      if (o.bump) {
        var b = el("button", "ivn-btn ivn-btn-primary ivn-btn-block ksc-act", w("bumpOrder"));
        b.type = "button";
        b.addEventListener("click", function () { move(b, { kitchen_order: o.kitchen_order, order: true }); });
        card.appendChild(b);
      }
      main.appendChild(card);
    });
  }

  function drawBoard(main, v) {
    main.className = "ksc-serving";
    [["preparing", "clock", v.preparing, ""], ["readyCol", "check", v.ready, " is-ready"]].forEach(function (c) {
      var col = el("section", "ksc-col" + c[3]);
      col.appendChild(withIcon("h2", "", c[1], w(c[0])));
      var ul = el("ul", "ksc-nums");
      c[2].forEach(function (n) { ul.appendChild(el("li", "ksc-num", n, true)); });
      col.appendChild(ul);
      main.appendChild(col);
    });
  }

  function drawSold() {
    var so = last && last.sold_out, list = $("sold-list");
    clear(list);
    if (!so) return;
    var out = {}; so.out.forEach(function (d) { out[d.item_code] = true; });
    var rows = so.dishes.slice();
    so.out.forEach(function (d) { if (!rows.some(function (r) { return r.item_code === d.item_code; })) rows.push({ item_code: d.item_code, item_name: d.item_code }); });
    rows.forEach(function (d) {
      var li = el("li", "ivn-list-row"), isOut = !!out[d.item_code];
      li.appendChild(el("span", "ivn-list-title", d.item_name, true));
      if (isOut) li.appendChild(el("span", "ivn-pill ivn-pill-red", w("isSold")));
      var b = el("button", "ivn-btn" + (isOut ? "" : " ivn-btn-danger"), isOut ? w("markBack") : w("markSold"));
      b.type = "button";
      b.addEventListener("click", function () {
        b.disabled = true;
        call("/ksc/soldout", { item_code: d.item_code, sold_out: !isOut }).then(function (a) {
          answered(a, "sold." + d.item_code);
          return read();
        }).then(drawSold);
      });
      li.appendChild(b);
      list.appendChild(li);
    });
  }

  function draw() {
    var a = last, main = $("board");
    main.className = "ksc-board";
    clear(main);
    clear($("title")); $("title").appendChild(bdi(a.title));
    clear($("stations"));
    a.stations.forEach(function (st, i) { if (i) $("stations").appendChild(document.createTextNode(" · ")); $("stations").appendChild(bdi(st)); });
    $("recall").hidden = a.kind !== "Station";
    $("recall").textContent = w("recall");
    $("recall").setAttribute("aria-pressed", showRecall ? "true" : "false");
    $("sold").hidden = !a.sold_out;
    $("sold").textContent = w("soldOut");
    $("sold-title").textContent = w("soldTitle");
    $("sold-close").textContent = w("close");
    $("ticket-close").textContent = w("close");
    $("waiting").hidden = true;
    if (a.kind === "Station") drawStation(main, a.view, a.look);
    else if (a.kind === "Expo") drawExpo(main, a.view, a.look);
    else drawBoard(main, a.view);
    stale();
    fit();
    if (openKey && $("ticket-dialog").open &&               // the ticket in the dialog left the board: close it
        !Array.prototype.some.call(main.children, function (c) { return c.getAttribute && c.getAttribute("data-key") === openKey; })) {
      window.ivnKit.closeDialog($("ticket-dialog"));
    }
  }

  // ── fitting the screen: whole tickets only, paged; a ticket taller than the board folded behind "+N more" ──
  function more(title, key, make) {  // the fold's button: opens the whole ticket in a dialog
    var b = el("button", "ivn-btn ksc-more");
    b.type = "button"; b.hidden = true;
    b.addEventListener("click", function () {
      clear($("ticket-title")); $("ticket-title").appendChild(bdi(title));
      var body = $("ticket-body"); clear(body);
      make().forEach(function (n) { body.appendChild(n); });
      openKey = key;
      window.ivnKit.openDialog($("ticket-dialog"));
    });
    return b;
  }
  function tall(e) { return e.getBoundingClientRect().height; }
  function capSlip(slip, cap) {
    var parts = slip.querySelectorAll(".ksc-part"), btn = slip.querySelector(".ksc-more"), groups = [];
    slip.querySelectorAll(".ksc-line").forEach(function (li) { li.hidden = false; });
    parts.forEach(function (p) { p.hidden = false; });
    slip.classList.remove("is-tall"); slip.style.maxBlockSize = "";
    if (btn) btn.hidden = true;
    if (!btn || tall(slip) <= cap + 0.5) return;
    btn.hidden = false;                // counted in the slip's height before anything is folded
    slip.querySelectorAll(".ksc-lines").forEach(function (ul) {
      if (ul.parentNode && ul.parentNode.classList.contains("ksc-part") && ul.parentNode.classList.contains("is-void")) return;
      Array.prototype.forEach.call(ul.children, function (li, i) {   // a dish and its choices fold together; a void
        if (!i || !li.classList.contains("is-choice")) groups.push([]);   // station's dishes on the expo never fold
        groups[groups.length - 1].push(li);
      });
    });
    var fold = function (n) {
      groups.forEach(function (g, i) { g.forEach(function (li) { li.hidden = i >= groups.length - n; }); });
      parts.forEach(function (p) {     // the expo: a station whose every dish is folded folds with them, heading and all
        var ls = p.querySelectorAll(".ksc-line");
        p.hidden = ls.length > 0 && Array.prototype.every.call(ls, function (li) { return li.hidden; });
      });
    };
    var heights = groups.map(function (g) { return g.reduce(function (h, li) { return h + tall(li); }, 0); });
    var hide = window.kscFit.trim(heights, tall(slip), cap);
    fold(hide);
    while (hide < groups.length - 1 && tall(slip) > cap + 0.5) fold(++hide);   // margins and headings measured
    while (hide > 0) {                 // and what fits again is shown again (a folded heading freed more than its lines)
      fold(hide - 1);
      if (tall(slip) > cap + 0.5) { fold(hide); break; }
      hide--;
    }
    var first = groups[0] || [], choices = 0;   // the first dish alone too tall: its last choices fold, the dish stays
    while (tall(slip) > cap + 0.5 && choices < first.length - 1) first[first.length - ++choices].hidden = true;
    var said = [];
    if (hide) said.push(count("moreDish", "moreDishes", hide));
    if (choices) said.push(count("moreChoice", "moreChoices", choices));
    if (!said.length) { btn.hidden = true; return; }
    btn.textContent = said.join(" · ");
    if (tall(slip) > cap + 0.5) {      // one dish taller than the board: this ticket scrolls, so Bump stays in reach
      slip.classList.add("is-tall"); slip.style.maxBlockSize = cap + "px";
    }
  }
  function fitStrip() {              // the expo's "Still to make": whole dishes only, the rest counted
    var strip = $("waiting"), rest = strip.querySelector(".ksc-wait-more");
    if (strip.hidden || !rest) return;
    var dishes = strip.querySelectorAll(".ksc-wait"), cap = window.innerHeight * STRIP_SHARE, hide = 0;
    dishes.forEach(function (d) { d.hidden = false; });
    rest.hidden = true;
    if (tall(strip) <= cap + 0.5) return;
    rest.hidden = false;
    while (hide < dishes.length - 1 && tall(strip) > cap + 0.5) {
      dishes[dishes.length - 1 - hide++].hidden = true;
      rest.textContent = count("moreDish", "moreDishes", hide);
    }
  }
  function fitNumbers(main) {        // the board: the numbers shrink a step at a time; at the last, the rest are counted
    main.querySelectorAll(".ksc-num").forEach(function (n) { n.hidden = false; });
    main.querySelectorAll(".ksc-num-more").forEach(function (n) { n.parentNode.removeChild(n); });
    for (var n = 0; n <= 4; n++) {
      main.setAttribute("data-shrink", String(n));
      if (main.scrollHeight <= main.clientHeight + 1) return;
    }
    var limit = main.getBoundingClientRect().bottom;
    main.querySelectorAll(".ksc-nums").forEach(function (ul) {
      var nums = ul.querySelectorAll(".ksc-num"), hide = 0, tag = el("li", "ksc-num ksc-num-more");
      while (hide < nums.length && nums[nums.length - 1 - hide].getBoundingClientRect().bottom > limit) nums[nums.length - 1 - hide++].hidden = true;
      if (!hide) return;
      tag.textContent = "+" + hide; ul.appendChild(tag);
      while (tag.getBoundingClientRect().bottom > limit && hide < nums.length) {
        nums[nums.length - 1 - hide++].hidden = true;
        tag.textContent = "+" + hide;
      }
    });
  }
  function lateIn(slips) {           // a ticket's own late colour; on the expo, an order's oldest open ticket's timer
    return slips.some(function (s) {
      return s.classList.contains("is-late") || (s.classList.contains("ksc-order") && !!s.querySelector(".ksc-timer.is-late"));
    });
  }
  function pager(before, after, lateBefore, lateAfter) {
    var paged = before > 0 || after > 0;
    $("prev").hidden = $("next").hidden = !paged;
    $("prev").disabled = !before; $("next").disabled = !after;
    $("prev").classList.toggle("is-late", lateBefore); $("next").classList.toggle("is-late", lateAfter);
    $("more").hidden = !after;
    $("more").classList.toggle("is-late", lateAfter);
    $("more").textContent = count("moreTicket", "moreTickets", after);
    $("prev").setAttribute("aria-label", w("earlier")); $("prev").title = w("earlier");
    $("next").setAttribute("aria-label", w("later")); $("next").title = w("later");
  }
  function fit() {
    var main = $("board");
    if (!last) return;
    fitStrip();
    if (main.classList.contains("ksc-serving")) { fitNumbers(main); pager(0, 0, false, false); return; }
    var slips = Array.prototype.filter.call(main.children, function (c) { return c.classList.contains("ksc-slip"); });
    slips.forEach(function (sl) { sl.hidden = false; });
    if (!slips.length) { pager(0, 0, false, false); return; }
    var box = main.getBoundingClientRect(), limit = box.bottom - parseFloat(getComputedStyle(main).paddingBottom);
    var cap = limit - slips[0].getBoundingClientRect().top;
    slips.forEach(function (sl) { capSlip(sl, cap); });
    var want = page;
    if (want && performance.now() - touchedAt > PAGE_BACK_MS) want = 0;   // left on a later page: back to the oldest
    var shown = window.kscFit.pages(slips.length, want, function (from) {
      slips.forEach(function (sl, i) { sl.hidden = i < from; });
      return slips.slice(from).map(function (sl) { return sl.getBoundingClientRect().bottom; });
    }, limit);
    if (shown.page !== page) shiftedAt = performance.now();   // the page changed without the cook: hold taps a moment
    page = shown.page;
    slips.forEach(function (sl, i) { sl.hidden = i < shown.from || i >= shown.end; });
    pager(shown.from, slips.length - shown.end, lateIn(slips.slice(0, shown.from)), lateIn(slips.slice(shown.end)));
  }
  var fitting = 0;
  function refit() { cancelAnimationFrame(fitting); fitting = requestAnimationFrame(fit); }

  // ── the size: the store's default, or the cook's A- / A+ on this screen, remembered on this device ──
  var SIZE_KEY = "ksc.size." + LINK.s + "." + LINK.t.split(".")[0], chosen = "";
  try { chosen = window.localStorage.getItem(SIZE_KEY) || ""; } catch (e) { chosen = ""; }
  function applySize() {
    var v = window.kscFit.size(chosen, last && last.look && last.look.size), S = window.kscFit.SIZES;
    document.body.setAttribute("data-size", v);
    $("smaller").disabled = !last || v === S[0]; $("bigger").disabled = !last || v === S[S.length - 1];   // the store's size first
    $("smaller").textContent = "A\u2212"; $("bigger").textContent = "A+";
    $("smaller").setAttribute("aria-label", w("smaller") + " (" + w(v) + ")"); $("smaller").title = w("smaller");
    $("bigger").setAttribute("aria-label", w("bigger") + " (" + w(v) + ")"); $("bigger").title = w("bigger");
  }
  function resize(by) {
    chosen = window.kscFit.step(window.kscFit.size(chosen, last && last.look && last.look.size), by);
    try { window.localStorage.setItem(SIZE_KEY, chosen); } catch (e) { /* not kept on this device: this visit only */ }
    applySize(); fit();
  }

  // the timers move every second between reads, with no call
  setInterval(function () {
    if (!last) return;
    stale();
    var moved = false;
    document.querySelectorAll(".ksc-timer").forEach(function (t) {
      var fresh = timerOf(t.getAttribute("data-from"), last.look).node;
      moved = moved || t.className !== fresh.className;
      t.className = fresh.className; t.replaceChildren.apply(t, Array.prototype.slice.call(fresh.childNodes));
    });
    if (moved) refit();                // Late soon / Late can change a ticket's height and the pager's colour
  }, 1000);

  $("recall").addEventListener("click", function () { showRecall = !showRecall; page = 0; if (last) draw(); });
  $("prev").appendChild(icon("back")); $("next").appendChild(icon("forth"));
  $("prev").addEventListener("click", function () { touchedAt = performance.now(); page = Math.max(0, page - 1); fit(); });
  $("next").addEventListener("click", function () { touchedAt = performance.now(); page += 1; fit(); });
  $("smaller").addEventListener("click", function () { resize(-1); });
  $("bigger").addEventListener("click", function () { resize(1); });
  $("ticket-close").textContent = w("close");
  document.addEventListener("pointerdown", function () { touchedAt = performance.now(); }, true);
  document.addEventListener("keydown", function () { touchedAt = performance.now(); }, true);
  window.addEventListener("resize", refit);
  if (window.ResizeObserver) new window.ResizeObserver(refit).observe($("board"));   // the top bar or the strip wrapped
  $("sold").addEventListener("click", function () { drawSold(); window.ivnKit.openDialog($("sold-dialog")); });
  window.addEventListener("online", function () { read(); });   // back on the network: read at once, not in 3 s
  window.addEventListener("hashchange", function () { location.reload(); });

  applySize();
  if (!LINK.s || !LINK.t) { note("unknown"); return; }
  stale();
  read();
})();
