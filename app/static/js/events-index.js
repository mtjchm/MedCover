/* Events list + calendar page.
 * Page config is read from <script id="events-page-cfg" type="application/json"> */
(function () {
  var cfg = {};
  try {
    var cfgEl = document.getElementById("events-page-cfg");
    if (cfgEl) cfg = JSON.parse(cfgEl.textContent);
  } catch (e) {}

  var FEED_URL_BASE  = cfg.feedUrl  || "";
  var HAS_DRAFT_PERM = cfg.hasDraftPerm || false;
  var CLAIM_BASE     = cfg.claimBase || "";

  var STORAGE_VIEW  = "medcover_events_view";
  var STORAGE_FILT  = "medcover_events_filters";
  var STORAGE_SORT  = "medcover_events_sort";
  var STORAGE_ELIG  = "medcover_events_elig";
  var STORAGE_ME    = "medcover_events_me";

  var DEFAULT_FILTERS = ["PUBLISHED", "ASSIGNMENTS_OPEN", "ASSIGNMENTS_CLOSED"];

  var calendarInitialized = false;
  var calendar = null;
  var allCalendarEvents = null;
  var sortState = { col: "start", dir: "asc" };
  var eligFilter = false;
  var meFilter = "";

  // ── Filter state ──────────────────────────────────────────────────────────

  function loadFilters() {
    try { var s = localStorage.getItem(STORAGE_FILT); if (s) return JSON.parse(s); } catch(e) {}
    return DEFAULT_FILTERS.slice();
  }
  function saveFilters(f) { localStorage.setItem(STORAGE_FILT, JSON.stringify(f)); }
  function loadEligFilter() {
    try { return localStorage.getItem(STORAGE_ELIG) === "1"; } catch(e) { return false; }
  }
  function saveEligFilter(v) { localStorage.setItem(STORAGE_ELIG, v ? "1" : "0"); }
  function loadMeFilter() {
    try { return localStorage.getItem(STORAGE_ME) || ""; } catch(e) { return ""; }
  }
  function saveMeFilter(v) { localStorage.setItem(STORAGE_ME, v || ""); }
  function loadSort() {
    try { var s = localStorage.getItem(STORAGE_SORT); if (s) return JSON.parse(s); } catch(e) {}
    return { col: "start", dir: "asc" };
  }
  function saveSort(s) { localStorage.setItem(STORAGE_SORT, JSON.stringify(s)); }

  // ── Filter buttons ────────────────────────────────────────────────────────

  function renderFilterButtons(activeFilters) {
    document.querySelectorAll(".filter-btn[data-status]").forEach(function (btn) {
      btn.classList.toggle("active", activeFilters.includes(btn.dataset.status));
    });
  }

  function toggleFilter(key) {
    var f = loadFilters();
    var idx = f.indexOf(key);
    if (idx >= 0) f.splice(idx, 1); else f.push(key);
    saveFilters(f);
    renderFilterButtons(f);
    applyFilters(f);
  }

  function toggleEligFilter() {
    eligFilter = !eligFilter;
    saveEligFilter(eligFilter);
    var btn = document.getElementById("btn-elig-filter");
    if (btn) btn.classList.toggle("active", eligFilter);
    applyFilters(loadFilters());
  }

  function setMeFilter(value) {
    meFilter = value || "";
    saveMeFilter(meFilter);
    var sel = document.getElementById("me-filter-select");
    if (sel) sel.value = meFilter;
    applyFilters(loadFilters());
    if (calendarInitialized && calendar) calendar.refetchEvents();
  }

  function populateMeSelect() {
    var sel = document.getElementById("me-filter-select");
    if (!sel) return;
    var names = new Set();
    document.querySelectorAll("#events-table tbody tr[data-me]").forEach(function (row) {
      if (row.dataset.me && row.dataset.meArchived !== "1") names.add(row.dataset.me);
    });
    if (names.size < 1) return; // hide only when no non-archived MEs present
    names.forEach(function (name) {
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    });
    sel.value = meFilter;
    sel.classList.remove("d-none");
  }

  function resetFilters() {
    eligFilter = false;
    saveEligFilter(false);
    var btn = document.getElementById("btn-elig-filter");
    if (btn) btn.classList.remove("active");
    meFilter = "";
    saveMeFilter("");
    var sel = document.getElementById("me-filter-select");
    if (sel) sel.value = "";
    saveFilters(DEFAULT_FILTERS.slice());
    renderFilterButtons(DEFAULT_FILTERS.slice());
    applyFilters(DEFAULT_FILTERS.slice());
    if (calendarInitialized && calendar) calendar.refetchEvents();
  }

  // ── Table filter + sort ───────────────────────────────────────────────────

  function applyFilters(activeFilters) {
    var tbody = document.querySelector("#events-table tbody");
    if (!tbody) return;
    var visibleCount = 0;
    tbody.querySelectorAll("tr").forEach(function (row) {
      var statusOk = activeFilters.includes(row.dataset.status);
      var eligOk = !eligFilter || row.dataset.eligible === "1";
      var meOk = !meFilter || row.dataset.me === meFilter;
      var visible = statusOk && eligOk && meOk;
      row.style.display = visible ? "" : "none";
      if (visible) visibleCount++;
    });
    var emptyMsg = document.getElementById("table-empty-msg");
    if (emptyMsg) emptyMsg.classList.toggle('d-none', visibleCount > 0);
    if (calendarInitialized && calendar) calendar.refetchEvents();
  }

  function sortTable(col) {
    if (sortState.col === col) {
      sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
    } else {
      sortState.col = col;
      sortState.dir = "asc";
    }
    saveSort(sortState);
    renderSortIcons();
    doSort();
  }

  function renderSortIcons() {
    document.querySelectorAll(".sortable").forEach(function (th) {
      var icon = th.querySelector(".sort-icon");
      if (!icon) return;
      if (th.dataset.col === sortState.col) {
        icon.textContent = sortState.dir === "asc" ? "↑" : "↓";
        icon.classList.remove("text-muted");
      } else {
        icon.textContent = "↕";
        icon.classList.add("text-muted");
      }
    });
  }

  function doSort() {
    var tbody = document.querySelector("#events-table tbody");
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll("tr"));
    var col = sortState.col;
    var dir = sortState.dir === "asc" ? 1 : -1;
    rows.sort(function (a, b) {
      var aVals = JSON.parse(a.dataset.sv || "{}");
      var bVals = JSON.parse(b.dataset.sv || "{}");
      var av = aVals[col] != null ? String(aVals[col]) : "";
      var bv = bVals[col] != null ? String(bVals[col]) : "";
      if (col === "start") return dir * av.localeCompare(bv);
      if (col === "staffing" || col === "total") return dir * (parseFloat(av) - parseFloat(bv));
      return dir * av.localeCompare(bv, "cs");
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
  }

  // ── View toggle ───────────────────────────────────────────────────────────

  function setView(view) {
    localStorage.setItem(STORAGE_VIEW, view);
    document.getElementById("view-table").classList.toggle('d-none', view !== "table");
    document.getElementById("view-calendar").classList.toggle('d-none', view !== "calendar");
    document.getElementById("btn-table-view").classList.toggle("active", view === "table");
    document.getElementById("btn-calendar-view").classList.toggle("active", view === "calendar");
    if (view === "calendar" && !calendarInitialized) initCalendar();
  }

  // ── Calendar ──────────────────────────────────────────────────────────────

  function initCalendar() {
    calendarInitialized = true;
    var el = document.getElementById("fullcalendar");
    calendar = new FullCalendar.Calendar(el, {
      initialView: "dayGridMonth",
      locale: "cs",
      firstDay: 1,
      headerToolbar: { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,listMonth" },
      buttonText: { today: "Dnes", month: "Měsíc", week: "Týden", list: "Seznam" },
      events: async function (fetchInfo, successCallback, failureCallback) {
        try {
          if (!allCalendarEvents) {
            var r = await fetch(FEED_URL_BASE);
            allCalendarEvents = await r.json();
          }
          var active = loadFilters();
          successCallback(allCalendarEvents.filter(function (e) {
            var statusOk = active.includes(e.extendedProps.status_key);
            var eligOk = !eligFilter || e.extendedProps.eligible;
            var meOk = !meFilter || (e.extendedProps.me_name || "") === meFilter;
            return statusOk && eligOk && meOk;
          }));
        } catch (err) { failureCallback(err); }
      },
      eventClick: function (info) {
        info.jsEvent.preventDefault();
        window.location.href = info.event.url;
      },
      eventDidMount: function (info) {
        var p = info.event.extendedProps;
        var cancelled = p.status === "Zrušena";
        var spotsLine = cancelled ? "" : "\nObsazení: " + p.filled + "/" + p.total;
        var title = p.me_name ? info.event.title + " (" + p.me_name + ")" : info.event.title;
        var rpLine = p.rp ? "\nZodpovědný zdravotník: " + p.rp : "";
        info.el.setAttribute("title",
          title + "\n" + p.start_local + " – " + p.end_local + spotsLine + rpLine + "\nStav: " + p.status);
        if (cancelled) {
          info.el.style.opacity = "0.55";
          var titleEl = info.el.querySelector(".fc-list-event-title a") || info.el.querySelector(".fc-event-title");
          if (titleEl) { titleEl.style.textDecoration = "line-through"; titleEl.style.color = "#6c757d"; }
        }
      },
      height: "auto"
    });
    calendar.render();
  }

  // ── Spot pick modal ───────────────────────────────────────────────────────

  function initSpotPickModal() {
    var modal = document.getElementById('spotPickModal');
    if (!modal || !CLAIM_BASE) return;
    modal.addEventListener('show.bs.modal', function (e) {
      var btn = e.relatedTarget;
      var eventName = btn.dataset.eventName;
      var spots = JSON.parse(btn.dataset.spots);
      var csrf = btn.dataset.csrf;
      document.getElementById('spotPickModalLabel').textContent = eventName;
      var body = document.getElementById('spotPickBody');
      body.innerHTML = '';
      spots.forEach(function (s) {
        var spotId = s[0], desc = s[1] || 'Pozice #' + spotId;
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = CLAIM_BASE + spotId;
        form.className = 'mb-1';
        form.innerHTML = '<input type="hidden" name="csrf_token" value="' + csrf + '">' +
          '<button class="btn btn-success btn-sm w-100 text-start">' + desc + '</button>';
        body.appendChild(form);
      });
    });
  }

  // ── Bulk selection ────────────────────────────────────────────────────────

  function clearSelection() {
    document.querySelectorAll(".row-event-check").forEach(function (cb) { cb.checked = false; });
    var ca = document.getElementById("check-all-events");
    if (ca) { ca.checked = false; ca.indeterminate = false; }
    var tb = document.getElementById("bulk-toolbar");
    if (tb) tb.classList.add("d-none");
  }

  function submitBulk(action) {
    var ids = Array.from(document.querySelectorAll(".row-event-check:checked")).map(function (cb) { return cb.value; });
    if (ids.length === 0) return;
    var actionLabels = { publish: "Zveřejnit", open_assignments: "Otevřít přihlášky", cancel: "Zrušit" };
    var label = actionLabels[action] || action;
    if (!confirm("Akce: " + label + "\nPočet vybraných akcí: " + ids.length + "\n\nPokračovat?")) return;
    var form = document.getElementById("bulk-form");
    document.getElementById("bulk-action-input").value = action;
    var container = document.getElementById("bulk-ids-container");
    container.innerHTML = "";
    ids.forEach(function (id) {
      var inp = document.createElement("input");
      inp.type = "hidden"; inp.name = "event_ids"; inp.value = id;
      container.appendChild(inp);
    });
    form.submit();
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", function () {
    sortState = loadSort();
    renderSortIcons();
    doSort();

    document.querySelectorAll(".sortable").forEach(function (th) {
      th.addEventListener("click", function () { sortTable(th.dataset.col); });
    });
    document.querySelectorAll(".filter-btn[data-status]").forEach(function (btn) {
      var touchStartY = 0;
      var touchFired = false;
      btn.addEventListener("touchstart", function (e) {
        touchStartY = e.touches[0].clientY;
      }, { passive: true });
      btn.addEventListener("touchend", function (e) {
        var dy = Math.abs(e.changedTouches[0].clientY - touchStartY);
        if (dy > 10) return; // scroll — ignore
        touchFired = true;
        e.preventDefault(); // prevents simulated hover state + synthetic click
        toggleFilter(btn.dataset.status);
        setTimeout(function () { touchFired = false; }, 500);
      }, { passive: false });
      btn.addEventListener("click", function () {
        if (touchFired) return; // already handled by touchend
        toggleFilter(btn.dataset.status);
      });
    });

    eligFilter = loadEligFilter();
    meFilter = loadMeFilter();
    var eligBtn = document.getElementById("btn-elig-filter");
    if (eligBtn) {
      eligBtn.classList.toggle("active", eligFilter);
      var eligTouchStartY = 0;
      var eligTouchFired = false;
      eligBtn.addEventListener("touchstart", function (e) {
        eligTouchStartY = e.touches[0].clientY;
      }, { passive: true });
      eligBtn.addEventListener("touchend", function (e) {
        var dy = Math.abs(e.changedTouches[0].clientY - eligTouchStartY);
        if (dy > 10) return;
        eligTouchFired = true;
        e.preventDefault();
        toggleEligFilter();
        setTimeout(function () { eligTouchFired = false; }, 500);
      }, { passive: false });
      eligBtn.addEventListener("click", function () {
        if (eligTouchFired) return;
        toggleEligFilter();
      });
    }

    var activeFilters = loadFilters();
    renderFilterButtons(activeFilters);
    populateMeSelect();
    applyFilters(activeFilters);

    var saved = localStorage.getItem(STORAGE_VIEW) || "table";
    setView(saved);

    // Bulk selection
    var checkAll   = document.getElementById("check-all-events");
    var toolbar    = document.getElementById("bulk-toolbar");
    var countLabel = document.getElementById("bulk-count-label");

    function visibleChecks() {
      return Array.from(document.querySelectorAll(".row-event-check")).filter(function (cb) {
        var tr = cb.closest("tr");
        return tr && tr.style.display !== "none";
      });
    }

    function updateBulkToolbar() {
      if (!toolbar) return;
      var checked = visibleChecks().filter(function (cb) { return cb.checked; });
      var total   = visibleChecks().length;
      toolbar.classList.toggle("d-none", checked.length === 0);
      if (countLabel) countLabel.textContent = checked.length + " vybráno";
      if (checkAll) {
        checkAll.indeterminate = checked.length > 0 && checked.length < total;
        checkAll.checked = total > 0 && checked.length === total;
      }
    }

    if (checkAll) {
      checkAll.addEventListener("change", function () {
        visibleChecks().forEach(function (cb) { cb.checked = checkAll.checked; });
        updateBulkToolbar();
      });
    }
    document.querySelectorAll(".row-event-check").forEach(function (cb) {
      cb.addEventListener("change", updateBulkToolbar);
    });

    initSpotPickModal();
  });

  // Expose globals used by inline HTML onclick attributes in the template
  window.setView = setView;
  window.setMeFilter = setMeFilter;
  window.clearSelection = clearSelection;
  window.submitBulk = submitBulk;
  window.resetFilters = resetFilters;
  window.toggleEligFilter = toggleEligFilter;
})();
