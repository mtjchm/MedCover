/* Work report — disable future months in year/month selector.
 * Reads current year and month from data attributes on #work-report-data. */
(function () {
  var dataEl = document.getElementById('work-report-data');
  if (!dataEl) return;
  var currentYear  = parseInt(dataEl.dataset.currentYear, 10);
  var currentMonth = parseInt(dataEl.dataset.currentMonth, 10);

  var yearSel  = document.getElementById('year');
  var monthSel = document.getElementById('month');
  if (!yearSel || !monthSel) return;

  function updateMonths() {
    var selectedYear = parseInt(yearSel.value, 10);
    Array.from(monthSel.options).forEach(function (opt) {
      var m = parseInt(opt.value, 10);
      var isFuture = selectedYear === currentYear && m > currentMonth;
      opt.disabled = isFuture;
      if (isFuture && opt.selected) {
        monthSel.value = currentMonth;
      }
    });
  }

  yearSel.addEventListener('change', updateMonths);
  updateMonths();
})();
