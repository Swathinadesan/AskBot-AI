/*
  Shared login / register form behaviour:
  - Submits via fetch as JSON (server also supports classic form posts
    as a fallback, see app.py).
  - Shows a loading state on the submit button.
  - Shows a friendly inline error on failure.
  - Redirects on success.
  - Wires up any password show/hide toggles on the page.
*/
(function () {
  "use strict";

  function showError(form, message) {
    var alertBox = form.querySelector("[data-form-alert]");
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.classList.remove("alert-hidden");
  }

  function hideError(form) {
    var alertBox = form.querySelector("[data-form-alert]");
    if (!alertBox) return;
    alertBox.classList.add("alert-hidden");
  }

  function setLoading(button, loading) {
    if (!button) return;
    button.disabled = loading;
    button.classList.toggle("is-loading", loading);
  }

  function initAuthForm(form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      hideError(form);

      var submitBtn = form.querySelector('[type="submit"]');
      var formData = new FormData(form);
      var payload = {};
      formData.forEach(function (value, key) { payload[key] = value; });

      setLoading(submitBtn, true);

      fetch(form.action, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (data) { return { ok: res.ok, data: data }; });
        })
        .then(function (result) {
          if (result.ok && result.data.success) {
            window.location.href = result.data.redirect || "/";
            return;
          }
          setLoading(submitBtn, false);
          showError(form, result.data.message || "Something went wrong. Please try again.");
        })
        .catch(function () {
          setLoading(submitBtn, false);
          showError(form, "Couldn't reach the server. Check your connection and try again.");
        });
    });
  }

  function initPasswordToggles() {
    document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
      var targetId = btn.getAttribute("data-toggle-password");
      var input = document.getElementById(targetId);
      if (!input) return;
      btn.addEventListener("click", function () {
        var isHidden = input.type === "password";
        input.type = isHidden ? "text" : "password";
        btn.classList.toggle("is-visible", isHidden);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-auth-form]").forEach(initAuthForm);
    initPasswordToggles();
  });
})();
