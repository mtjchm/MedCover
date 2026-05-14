/**
 * Event create — equipment availability check button.
 *
 * Expects a config element:
 *   <div id="eq-create-config" data-check-url="…"></div>
 */
(function () {
  "use strict";
  var cfg = document.getElementById("eq-create-config");
  if (!cfg) return;

  var CHECK_URL = cfg.dataset.checkUrl;
  var csrfMeta  = document.querySelector("meta[name=csrf-token]");
  var CSRF      = csrfMeta ? csrfMeta.content : "";

  function doCheck() {
    var output = document.getElementById("eq-check-results");
    if (!output) return;

    var checked = Array.from(
      document.querySelectorAll("input[name='equipment_item_ids']:checked")
    ).map(function (el) { return parseInt(el.value, 10); });

    if (checked.length === 0) {
      output.innerHTML = '<div class="alert alert-warning py-2 mt-2">Za\u0161krtn\u011bte nejprve alespo\u0148 jednu polo\u017eku vybaven\u00ed.</div>';
      return;
    }

    var startEl = document.getElementById("start_datetime");
    var endEl   = document.getElementById("end_datetime");
    var start = startEl ? startEl.value : "";
    var end   = endEl   ? endEl.value   : "";

    if (!start || !end) {
      output.innerHTML = '<div class="alert alert-warning py-2 mt-2">Vypl\u0148te nejprve datum a \u010das za\u010d\u00e1tku a konce akce.</div>';
      return;
    }

    var btn = document.getElementById("eq-check-btn");
    if (btn) { btn.disabled = true; btn.textContent = "Kontroluji\u2026"; }

    var payload = { item_ids: checked, start_datetime: start, end_datetime: end, exclude_event_id: null };

    fetch(CHECK_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify(payload)
    })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      var results = data.results || [];
      var warnings = results.filter(function (r) { return r.status !== "ok"; });
      var ok       = results.filter(function (r) { return r.status === "ok"; });
      if (results.length === 0) { output.innerHTML = ""; return; }
      var html = "";
      if (warnings.length > 0) {
        html += '<div class="alert alert-warning py-2"><strong>\u26A0 Upozorn\u011bn\u00ed:</strong><ul class="mb-0 mt-1">';
        warnings.forEach(function (r) {
          if (r.status === "unavailable") {
            html += "<li><strong>" + r.item_name + "</strong> \u2014 nedostupn\u00e1: " + (r.reason || "\u2014") + "</li>";
          } else if (r.status === "conflict") {
            var ce = r.conflicting_event;
            var s = ce.start ? new Date(ce.start).toLocaleString("cs-CZ", {dateStyle:"short",timeStyle:"short"}) : "?";
            var edt = ce.end ? new Date(ce.end).toLocaleString("cs-CZ", {dateStyle:"short",timeStyle:"short"}) : "?";
            html += "<li><strong>" + r.item_name + "</strong> \u2014 p\u0159i\u0159azena jin\u00e9 akci: <a href=\"" + ce.url + "\">\u201E" + ce.name + "\u201C</a> (" + s + "\u2013" + edt + ")</li>";
          }
        });
        html += "</ul></div>";
      }
      if (ok.length > 0) {
        html += '<p class="text-success small mb-0 mt-2">\u2705 Dostupn\u00e9: ' + ok.map(function (r) { return r.item_name; }).join(", ") + "</p>";
      }
      output.innerHTML = html;
    })
    .catch(function (err) {
      output.innerHTML = '<div class="alert alert-danger py-2 mt-2">Chyba p\u0159i kontrole: ' + err.message + '</div>';
    })
    .finally(function () {
      if (btn) { btn.disabled = false; btn.textContent = "Zkontrolovat dostupnost vybaven\u00ed"; }
    });
  }

  function bindBtn() {
    var btn = document.getElementById("eq-check-btn");
    if (btn) {
      btn.addEventListener("click", doCheck);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindBtn);
  } else {
    bindBtn();
  }
})();
