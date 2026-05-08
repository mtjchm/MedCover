/* Generic client-side sortable table.
 * Requires table rows to carry data-sv='{"col": value, ...}' attributes.
 * Sortable headers must have class "sortable" and data-col="<key>".
 * The table must have an id attribute passed via data-table-id on the thead. */
(function () {
  document.querySelectorAll('table[id] thead').forEach(function (thead) {
    var table  = thead.closest('table');
    var tbody  = table.querySelector('tbody');
    if (!tbody) return;

    var sortCol = null;
    var sortDir = 1;

    function getRows() { return Array.from(tbody.querySelectorAll('tr')); }

    function val(row, col) {
      try {
        var sv = row.dataset.sv ? JSON.parse(row.dataset.sv) : {};
        return (sv[col] !== undefined && sv[col] !== null) ? String(sv[col]) : '';
      } catch (e) { return ''; }
    }

    function sort() {
      if (!sortCol) return;
      var rows = getRows();
      rows.sort(function (a, b) {
        var av = val(a, sortCol), bv = val(b, sortCol);
        var an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return (an - bn) * sortDir;
        return av.localeCompare(bv) * sortDir;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
      thead.querySelectorAll('th.sortable').forEach(function (th) {
        var icon = th.querySelector('.sort-icon');
        if (icon) icon.textContent = th.dataset.col === sortCol ? (sortDir === 1 ? '↑' : '↓') : '↕';
      });
    }

    thead.querySelectorAll('th.sortable').forEach(function (th) {
      th.addEventListener('click', function () {
        if (sortCol === th.dataset.col) {
          sortDir *= -1;
        } else {
          sortCol = th.dataset.col;
          sortDir = 1;
        }
        sort();
      });
    });

    // Auto-sort by first sortable column on load
    var firstSortable = thead.querySelector('th.sortable');
    if (firstSortable) {
      sortCol = firstSortable.dataset.col;
      sort();
    }
  });
})();
