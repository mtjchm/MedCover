/* Global Bootstrap and Flatpickr initialisation — loaded by base.html */
document.addEventListener("DOMContentLoaded", function () {
  // Bootstrap popovers (used by help_icon macro)
  document.querySelectorAll('[data-bs-toggle="popover"]').forEach(function (el) {
    new bootstrap.Popover(el, { html: false });
  });
  // Bootstrap tooltips
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
    new bootstrap.Tooltip(el);
  });
  // Flatpickr datetime inputs
  flatpickr(".flatpickr-dt", {
    enableTime: true,
    time_24hr: true,
    dateFormat: "Y-m-dTH:i",
    altInput: true,
    altFormat: "d.m.Y H:i",
    locale: "cs",
    allowInput: true,
  });
});

/* Set a flatpickr field to the current date/time.
 * Called by the "Teď" button placed inside the same .input-group wrapper. */
function fpNow(btn) {
  var input = btn.closest(".input-group").querySelector(".flatpickr-dt");
  if (input && input._flatpickr) {
    input._flatpickr.setDate(new Date(), true);
  }
}
