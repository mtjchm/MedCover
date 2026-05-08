/* Admin digest settings — SortableJS block reorder + enable toggle */
(function () {
  // ── Block reorder ───────────────────────────────────────────────────────────
  var list = document.getElementById('block-list');
  if (list) {
    var reorderUrl = list.dataset.reorderUrl;
    var reorderCsrf = list.dataset.csrf;

    Sortable.create(list, {
      handle: '[data-drag-handle]',
      animation: 150,
      onEnd: function () {
        var order = Array.from(list.querySelectorAll('[data-block-type]'))
                         .map(function (el) { return el.dataset.blockType; });
        fetch(reorderUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': reorderCsrf },
          body: JSON.stringify(order),
        });
      },
    });
  }

  // ── Block enable toggle ─────────────────────────────────────────────────────
  document.querySelectorAll('[data-toggle-url]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.dataset.toggleUrl;
      var csrf = btn.dataset.csrf;
      var blockType = btn.closest('[data-block-type]').dataset.blockType;
      var badge = document.getElementById('badge-' + blockType);

      fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf },
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.enabled) {
            btn.textContent = 'Zapnuto';
            btn.className = btn.className.replace('btn-outline-secondary', 'btn-success');
            if (badge) { badge.className = 'badge bg-success'; badge.textContent = 'Aktivní'; }
          } else {
            btn.textContent = 'Vypnuto';
            btn.className = btn.className.replace('btn-success', 'btn-outline-secondary');
            if (badge) { badge.className = 'badge bg-secondary'; badge.textContent = 'Neaktivní'; }
          }
        });
    });
  });
})();
