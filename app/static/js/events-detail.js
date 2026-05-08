/* Events detail — spot qualification check.
 * Each spot edit panel should carry:
 *   data-user-cred-ids="[id1, id2, ...]"  (JSON array of the assigned user's credential IDs)
 * A page-level element #fillers-map-data should carry:
 *   data-fillers-map="{...}"  (JSON object mapping qualification ID → list of filler cred IDs)
 */
(function () {
  var fillersMapEl = document.getElementById('fillers-map-data');
  var fillersMap = {};
  if (fillersMapEl) {
    try { fillersMap = JSON.parse(fillersMapEl.dataset.fillersMap || "{}"); } catch (e) {}
  }

  document.querySelectorAll('.spot-edit-panel[data-user-cred-ids]').forEach(function (panel) {
    var userCredIds;
    try { userCredIds = JSON.parse(panel.dataset.userCredIds || "[]"); } catch (e) { userCredIds = []; }

    var spotId  = panel.dataset.spotId;
    var warning = document.getElementById('unassign-warning-' + spotId);
    if (!warning) return;

    function check() {
      var selected = Array.from(panel.querySelectorAll('input[name="qualification_ids"]:checked'))
                          .map(function (cb) { return String(cb.value); });
      var eligible = selected.length === 0 || selected.every(function (reqId) {
        var fillers = fillersMap[reqId] || [parseInt(reqId)];
        return userCredIds.some(function (uid) { return fillers.indexOf(uid) !== -1; });
      });
      warning.classList.toggle('d-none', eligible);
    }

    panel.querySelectorAll('input[name="qualification_ids"]').forEach(function (cb) {
      cb.addEventListener('change', check);
    });
  });
})();
