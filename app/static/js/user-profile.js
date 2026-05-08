/* Dark mode toggle label update — profile page. */
(function () {
  var cb  = document.getElementById('dark_mode');
  var lbl = cb ? cb.closest('.form-check').querySelector('.dark-label') : null;
  function update() { if (lbl) lbl.classList.toggle('is-dark', cb.checked); }
  if (cb) { cb.addEventListener('change', update); update(); }
})();
