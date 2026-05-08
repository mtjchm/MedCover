/* Users list — select-all checkbox and batch role toolbar. */
(function () {
  var selectAll = document.getElementById('selectAll');
  var toolbar   = document.getElementById('batchToolbar');
  var selCount  = document.getElementById('selCount');
  var clearBtn  = document.getElementById('clearSel');

  if (!selectAll) return;

  function allRows()     { return Array.from(document.querySelectorAll('.row-check')); }
  function checkedRows() { return allRows().filter(function (cb) { return cb.checked; }); }

  function updateToolbar() {
    var total = allRows().length;
    var n     = checkedRows().length;
    toolbar.style.display       = n > 0 ? 'flex' : 'none';
    selCount.textContent        = n + ' vybráno';
    selectAll.indeterminate     = n > 0 && n < total;
    selectAll.checked           = total > 0 && n === total;
  }

  selectAll.addEventListener('change', function () {
    var checked = selectAll.checked;
    allRows().forEach(function (cb) { cb.checked = checked; });
    updateToolbar();
  });

  document.querySelectorAll('.row-check').forEach(function (cb) {
    cb.addEventListener('change', updateToolbar);
  });

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      allRows().forEach(function (cb) { cb.checked = false; });
      selectAll.checked = false;
      updateToolbar();
    });
  }
})();
