/* Import preview — check-all and row selection. */
document.addEventListener("DOMContentLoaded", function () {
  var checkAll  = document.getElementById("checkAll");
  var rowChecks = document.querySelectorAll(".row-include");
  var btnImport = document.getElementById("btnImport");
  var countSpan = document.getElementById("selectedCount");

  function updateCount() {
    var selected = Array.from(rowChecks).filter(function (c) { return c.checked; }).length;
    if (countSpan) countSpan.textContent = "Vybráno: " + selected + " z " + rowChecks.length;
    if (btnImport) btnImport.disabled = selected === 0;
    rowChecks.forEach(function (c) {
      c.closest("tr").classList.toggle("row-excluded", !c.checked);
    });
  }

  if (checkAll) {
    checkAll.addEventListener("change", function () {
      rowChecks.forEach(function (c) { c.checked = checkAll.checked; });
      updateCount();
    });
  }

  rowChecks.forEach(function (c) {
    c.addEventListener("change", function () {
      if (checkAll) checkAll.checked = Array.from(rowChecks).every(function (c) { return c.checked; });
      updateCount();
    });
  });

  var confirmForm = document.getElementById("confirmForm");
  if (confirmForm) {
    confirmForm.addEventListener("submit", function (e) {
      var selected = Array.from(rowChecks).filter(function (c) { return c.checked; }).length;
      if (!confirm("Opravdu chcete importovat " + selected + " akcí? Tato operace vytvoří nové záznamy v databázi.")) {
        e.preventDefault();
      }
    });
  }

  updateCount();
});
