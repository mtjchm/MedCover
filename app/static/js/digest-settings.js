/* Admin digest settings — SortableJS block reorder */
(function () {
  var list = document.getElementById('block-list');
  if (!list) return;

  var reorderUrl = list.dataset.reorderUrl;
  var csrfToken = list.dataset.csrf;

  Sortable.create(list, {
    handle: '[data-drag-handle]',
    animation: 150,
    onEnd: function () {
      var order = Array.from(list.querySelectorAll('[data-block-type]'))
                       .map(function (el) { return el.dataset.blockType; });
      fetch(reorderUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(order),
      });
    },
  });
})();
