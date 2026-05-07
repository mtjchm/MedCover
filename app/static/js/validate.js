/**
 * MedCover — client-side form validation
 *
 * UX enhancement only — all rules are also enforced server-side.
 * Hooks into Bootstrap 5 validation classes (was-validated / is-invalid).
 */
(function () {
  "use strict";

  // ── Helpers ──────────────────────────────────────────────────────────────

  function setInvalid(el, message) {
    el.classList.add("is-invalid");
    el.classList.remove("is-valid");
    var fb = el.nextElementSibling;
    if (fb && fb.classList.contains("invalid-feedback")) {
      fb.textContent = message;
    } else {
      fb = document.createElement("div");
      fb.className = "invalid-feedback";
      fb.textContent = message;
      el.parentNode.insertBefore(fb, el.nextSibling);
    }
  }

  function setValid(el) {
    el.classList.remove("is-invalid");
    el.classList.add("is-valid");
  }

  function clearValidity(el) {
    el.classList.remove("is-invalid", "is-valid");
  }

  // ── Rules ─────────────────────────────────────────────────────────────────

  function validateRequired(el) {
    if (el.hasAttribute("required") && !el.value.trim()) {
      setInvalid(el, "Toto pole je povinné.");
      return false;
    }
    return true;
  }

  function validateMinLength(el) {
    var min = parseInt(el.getAttribute("minlength"), 10);
    if (!isNaN(min) && el.value.length > 0 && el.value.length < min) {
      setInvalid(el, "Minimální délka je " + min + " znaků.");
      return false;
    }
    return true;
  }

  function validateMaxLength(el) {
    var max = parseInt(el.getAttribute("maxlength"), 10);
    if (!isNaN(max) && el.value.length > max) {
      setInvalid(el, "Maximální délka je " + max + " znaků.");
      return false;
    }
    return true;
  }

  function validateNumericRange(el) {
    if (el.type !== "number") return true;
    var val = parseFloat(el.value);
    if (isNaN(val)) return true;
    var min = el.getAttribute("min");
    var max = el.getAttribute("max");
    if (min !== null && val < parseFloat(min)) {
      setInvalid(el, "Minimální hodnota je " + min + ".");
      return false;
    }
    if (max !== null && val > parseFloat(max)) {
      setInvalid(el, "Maximální hodnota je " + max + ".");
      return false;
    }
    return true;
  }

  // ── Date range: end must be ≥ start ──────────────────────────────────────

  function validateDateRange(form) {
    var startEl = form.querySelector("[name='start_datetime']");
    var endEl = form.querySelector("[name='end_datetime']");
    if (!startEl || !endEl) return true;
    // Read from flatpickr hidden input or raw value
    var startVal = startEl._flatpickr ? startEl._flatpickr.selectedDates[0] : new Date(startEl.value);
    var endVal = endEl._flatpickr ? endEl._flatpickr.selectedDates[0] : new Date(endEl.value);
    if (!startVal || !endVal) return true;
    if (endVal < startVal) {
      setInvalid(endEl, "Konec akce musí být po jejím začátku.");
      return false;
    }
    setValid(endEl);
    return true;
  }

  // ── Password confirmation ─────────────────────────────────────────────────

  function validatePasswordConfirm(form) {
    var pw = form.querySelector("[name='new_password']");
    var conf = form.querySelector("[name='confirm_password']");
    if (!pw || !conf) return true;
    if (pw.value && conf.value && pw.value !== conf.value) {
      setInvalid(conf, "Hesla se neshodují.");
      return false;
    }
    if (conf.value) setValid(conf);
    return true;
  }

  // ── Validate a single form ────────────────────────────────────────────────

  function validateForm(form) {
    var ok = true;
    form.querySelectorAll("input, textarea, select").forEach(function (el) {
      if (el.disabled || el.type === "hidden") return;
      clearValidity(el);
      var fieldOk = true;
      fieldOk = validateRequired(el) && fieldOk;
      fieldOk = validateMinLength(el) && fieldOk;
      fieldOk = validateMaxLength(el) && fieldOk;
      fieldOk = validateNumericRange(el) && fieldOk;
      if (fieldOk && el.value.trim()) setValid(el);
      ok = fieldOk && ok;
    });
    ok = validateDateRange(form) && ok;
    ok = validatePasswordConfirm(form) && ok;
    return ok;
  }

  // ── Wire up all forms ─────────────────────────────────────────────────────

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form[novalidate]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        if (!validateForm(form)) {
          e.preventDefault();
          e.stopPropagation();
        }
        form.classList.add("was-validated");
      });
    });
  });
})();
