// S49 — the customer's answer page. Its address carries #s=<the retailer's site>&t=<the sale>.<signature>; the part
// after # is never sent to a server in the address, only in the body of the two calls below.
(function () {
  "use strict";
  var WORDS = {
    en: { comment: "Anything to add? (optional)", stop: "Stop these messages", send: "Send", thanks: "Thank you. We have your answer.",
          closed: "This link has closed. Thank you.", unknown: "This link does not work.", busy: "Please try again in a few minutes.",
          stopped: "We will not send you these messages again.", sending: "Sending…" },
    ar: { comment: "هل تود إضافة شيء؟ (اختياري)", stop: "أوقف هذه الرسائل", send: "إرسال", thanks: "شكرًا لك. وصلنا ردك.",
          closed: "انتهت صلاحية هذا الرابط. شكرًا لك.", unknown: "هذا الرابط لا يعمل.", busy: "يرجى المحاولة مرة أخرى بعد دقائق.",
          stopped: "لن نرسل إليك هذه الرسائل مرة أخرى.", sending: "جارٍ الإرسال…" },
    es: { comment: "¿Algo que añadir? (opcional)", stop: "No enviarme más estos mensajes", send: "Enviar",
          thanks: "Gracias. Tenemos su respuesta.", closed: "Este enlace ya no está activo. Gracias.",
          unknown: "Este enlace no funciona.", busy: "Inténtelo de nuevo en unos minutos.",
          stopped: "No le enviaremos más estos mensajes.", sending: "Enviando…" }
  };
  var lang = (navigator.language || "en").slice(0, 2).toLowerCase();
  var W = WORDS[lang] || WORDS.en;
  if (lang === "ar") { document.documentElement.dir = "rtl"; document.documentElement.lang = "ar"; }
  else if (WORDS[lang]) { document.documentElement.lang = lang; }

  var hash = new URLSearchParams(location.hash.slice(1));
  var who = { s: hash.get("s") || "", t: hash.get("t") || "" };
  var $ = function (id) { return document.getElementById(id); };
  var chosen = null;

  $("comment-label").textContent = W.comment;
  $("stop-label").textContent = W.stop;
  $("send").textContent = W.send;

  function call(path, extra) {
    var body = Object.assign({ s: who.s, t: who.t }, extra || {});
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
                         credentials: "omit", cache: "no-store" })
      .then(function (r) { return r.json().catch(function () { return { state: "unavailable" }; }); })
      .catch(function () { return { state: "unavailable" }; });
  }

  function ready() { $("send").disabled = chosen === null && !$("stop").checked; }

  function show(v) {
    var card = $("card");
    card.classList.remove("done", "stopped");
    $("name").textContent = v.name || "";
    $("date").textContent = v.date || "";
    $("question").textContent = v.question || "";
    var box = $("answers");
    box.textContent = "";
    (v.answers || []).forEach(function (text, i) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = text;
      b.dir = "auto";                                  // the retailer's words keep their own direction on an Arabic page
      b.setAttribute("aria-pressed", chosen === i ? "true" : "false");
      b.addEventListener("click", function () { chosen = i; show(v); });
      box.appendChild(b);
    });
    var note = { answered: W.thanks, closed: W.closed, unknown: W.unknown, unavailable: W.busy }[v.state] || "";
    card.classList.toggle("stopped", !!v.stopped || v.state === "unknown" || v.state === "unavailable");
    if (v.state !== "open") {
      chosen = null;                                   // only Stop these messages is left to send
      card.classList.add("done");
      if (v.state === "unknown" || v.state === "unavailable") { $("question").textContent = ""; }
    }
    if (v.stopped) { note = (note ? note + " " : "") + W.stopped; }
    $("note").textContent = note;
    ready();
  }

  $("stop").addEventListener("change", ready);
  $("send").addEventListener("click", function () {
    $("send").disabled = true;
    $("note").textContent = W.sending;
    call("/psf/answer", { answer: chosen, comment: $("comment").value, stop: $("stop").checked })
      .then(function (v) {
        // still open after the call: the customer only asked to stop (the answer stays theirs to give)
        if (v.state === "open") { v.state = chosen === null ? "stopped" : "answered"; }
        show(v);
      });
  });

  if (!who.s || !who.t) { show({ state: "unknown" }); return; }
  call("/psf/open").then(show);
})();
