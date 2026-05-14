/**
 * Event detail — equipment availability check button.
 *
 * Expects a config element:
 *   <div id="eq-check-config"
 *        data-check-url="…"
 *        data-event-id="…"
 *        data-start="…"
 *        data-end="…">
 *   </div>
 */
(function () {
  "use strict";
  var cfg = document.getElementById("eq-check-config");
  if (!cfg) return;

  try {
    var CHECK_URL = cfg.dataset.checkUrl;
    var EVENT_ID  = parseInt(cfg.dataset.eventId, 10);
    var START     = cfg.dataset.start;
    var END       = cfg.dataset.end;
    var csrfMeta  = document.querySelector("meta[name=csrf-token]");
    var CSRF      = csrfMeta ? csrfMeta.content : "";

    var btn    = document.getElementById("eq-check-btn");
    var dropOut = document.getElementById("eq-check-results");
    if (!btn || !dropOut) return;

    btn.addEventListener("click", function () {
      var select = document.getElementById("eq-item-select");
      var itemId = select ? parseInt(select.value, 10) : NaN;
      if (!itemId) {
        dropOut.innerHTML = '<p class="text-warning small mb-1">Vyberte nejprve polo\u017eku vybaven\u00ed.</p>';
        return;
      }
      btn.disabled = true;
      btn.textContent = "Kontroluji\u2026";
      fetch(CHECK_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify({ item_ids: [itemId], start_datetime: START, end_datetime: END, exclude_event_id: EVENT_ID })
      })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) {
        var results = data.results || [];
        if (!results.length) { dropOut.innerHTML = ""; return; }
        var warnings = results.filter(function (r) { return r.status !== "ok"; });
        var ok = results.filter(function (r) { return r.status === "ok"; });
        var html = "";
        if (warnings.length > 0) {
          warnings.forEach(function (r) {
            if (r.status === "unavailable") {
              html += '<p class="text-warning small mb-1">\u26A0 <strong>' + r.item_name + '</strong> \u2014 nedostupn\u00e1: ' + (r.reason || "\u2014") + '</p>';
            } else if (r.status === "conflict") {
              var ce = r.conflicting_event;
              var s = ce.start ? new Date(ce.start).toLocaleString("cs-CZ", {dateStyle:"short",timeStyle:"short"}) : "?";
              var edt = ce.end ? new Date(ce.end).toLocaleString("cs-CZ", {dateStyle:"short",timeStyle:"short"}) : "?";
              html += '<p class="text-warning small mb-1">\u26A0 <strong>' + r.item_name + '</strong> \u2014 p\u0159i\u0159azena jin\u00e9 akci: <a href="' + ce.url + '">\u201E' + ce.name + '\u201C</a> (' + s + '\u2013' + edt + ')</p>';
            }
          });
        }
        if (ok.length > 0) {
          html += '<p class="text-success small mb-1">\u2705 ' + ok[0].item_name + ' \u2014 dostupn\u00e1 pro tuto akci.</p>';
        }
        dropOut.innerHTML = html;
      })
      .catch(function (err) {
        dropOut.innerHTML = '<p class="text-danger small mb-1">Chyba p\u0159i kontrole: ' + err.message + '</p>';
      })
      .finally(function () { btn.disabled = false; btn.textContent = "Zkontrolovat dostupnost"; });
    });
  } catch (err) {
    var out = document.getElementById("eq-check-results");
    if (out) out.innerHTML = '<p class="text-danger small mb-1">Chyba skriptu: ' + err.message + '</p>';
  }
})();
