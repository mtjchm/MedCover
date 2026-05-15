/* Admin digest settings — SortableJS block reorder + enable toggle */
(function () {
  // ── Block reorder ───────────────────────────────────────────────────────────
  var list = document.getElementById('block-list');
  if (list) {
    var reorderUrl = list.dataset.reorderUrl;

    Sortable.create(list, {
      handle: '[data-drag-handle]',
      animation: 150,
      onEnd: function () {
        var ids = Array.from(list.querySelectorAll('[data-block-id]'))
                       .map(function (el) { return parseInt(el.dataset.blockId, 10); });
        csrfFetch(reorderUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(ids),
        });
      },
    });
  }

  // ── Block enable toggle ─────────────────────────────────────────────────────
  document.querySelectorAll('[data-toggle-url]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.dataset.toggleUrl;
      var blockId = btn.dataset.toggleBlockId;
      var badge = document.getElementById('badge-' + blockId);

      csrfFetch(url, {
        method: 'POST',
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.enabled) {
            btn.textContent = 'Zapnuto';
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-success');
            if (badge) { badge.className = 'badge bg-success'; badge.textContent = 'Aktivní'; }
          } else {
            btn.textContent = 'Vypnuto';
            btn.classList.remove('btn-success');
            btn.classList.add('btn-outline-secondary');
            if (badge) { badge.className = 'badge bg-secondary'; badge.textContent = 'Neaktivní'; }
          }
        });
    });
  });
})();
