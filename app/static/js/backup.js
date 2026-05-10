/* Backup page — restore and delete confirmation modals. */
(function () {
  var restoreModal = document.getElementById('restoreModal');
  if (restoreModal) {
    restoreModal.addEventListener('show.bs.modal', function (event) {
      var btn = event.relatedTarget;
      var filename = btn.getAttribute('data-filename');
      document.getElementById('restoreFilename').textContent = filename;
      document.getElementById('restoreForm').action = '/admin/backup/restore/' + encodeURIComponent(filename);
      document.getElementById('restore_confirmation').value = '';
    });
  }

  var deleteModal = document.getElementById('deleteModal');
  if (deleteModal) {
    deleteModal.addEventListener('show.bs.modal', function (event) {
      var btn = event.relatedTarget;
      var filename = btn.getAttribute('data-filename');
      document.getElementById('deleteFilename').textContent = filename;
      document.getElementById('deleteForm').action = '/admin/backup/delete/' + encodeURIComponent(filename);
      document.getElementById('delete_confirmation').value = '';
    });
  }
})();
