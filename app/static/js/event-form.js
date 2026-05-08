/* Paid checkbox label toggle — event create/edit forms. */
(function () {
  var cb  = document.getElementById('paid');
  var lbl = cb ? cb.closest('.form-check').querySelector('.paid-label') : null;
  function update() { if (lbl) lbl.classList.toggle('is-paid', cb.checked); }
  if (cb) { cb.addEventListener('change', update); update(); }
})();

/* Dynamic spot rows — event create form only. */
(function () {
  var addBtn    = document.getElementById('addSpotBtn');
  var container = document.getElementById('spotRows');
  var totalInp  = document.getElementById('spotTotal');
  var tpl       = document.getElementById('spotRowTpl');
  if (!addBtn || !tpl) return;

  var idx = 0;

  function addRow() {
    var frag = tpl.content.cloneNode(true);
    var row  = frag.querySelector('.spot-row-item');
    row.innerHTML = row.innerHTML
      .replaceAll('__SPOT_DESC__',        'spot_desc_'     + idx)
      .replaceAll('__SPOT_OPTIONAL__',    'spot_optional_' + idx)
      .replaceAll('__SPOT_OPTIONAL_ID__', 'spot_optional_id_' + idx)
      .replaceAll('__SPOT_CRED__',        'spot_cred_'     + idx)
      .replaceAll('__SPOT_CRED_ID_',      'spot_cred_id_'  + idx + '_')
      .replaceAll('__', '');
    row.querySelector('.remove-spot-btn').addEventListener('click', function () {
      row.remove();
      reindex();
    });
    container.appendChild(frag);
    idx++;
    totalInp.value = container.querySelectorAll('.spot-row-item').length;
  }

  function reindex() {
    container.querySelectorAll('.spot-row-item').forEach(function (row, i) {
      row.querySelectorAll('[name^="spot_desc_"]').forEach(function (el) { el.name = 'spot_desc_' + i; });
      row.querySelectorAll('[name^="spot_cred_"]').forEach(function (el) { el.name = 'spot_cred_' + i; });
    });
    idx = container.querySelectorAll('.spot-row-item').length;
    totalInp.value = idx;
  }

  addBtn.addEventListener('click', addRow);
})();
