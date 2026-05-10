/* Reports index — master-event select dropdown handler. */
(function () {
  var sel  = document.getElementById('me-select');
  var btn  = document.getElementById('me-go-btn');
  var form = document.getElementById('me-select-form');
  if (!sel || !btn || !form) return;

  sel.addEventListener('change', function () { btn.disabled = !sel.value; });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var opt = sel.options[sel.selectedIndex];
    if (opt && opt.dataset.url) window.location.href = opt.dataset.url;
  });
})();
