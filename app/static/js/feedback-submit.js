/* Feedback form — collect browser/OS info before submit. */
(function () {
  var form = document.querySelector("form");
  if (!form) return;
  form.addEventListener("submit", function () {
    var uaField     = document.getElementById("user_agent_field");
    var screenField = document.getElementById("screen_info_field");
    var puField     = document.getElementById("page_url_field");
    if (uaField)     uaField.value = navigator.userAgent || "";
    if (screenField) {
      var s = window.screen;
      screenField.value = s.width + "×" + s.height + " (" + s.colorDepth + "-bit)";
    }
    if (puField && !puField.value) {
      puField.value = document.referrer || window.location.href;
    }
  });
})();
