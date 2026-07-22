(function () {
  "use strict";

  var storageKey = "poetry-theme";
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");

  function storedTheme() {
    try {
      var value = window.localStorage.getItem(storageKey);
      return value === "light" || value === "dark" ? value : null;
    } catch (_error) {
      return null;
    }
  }

  function applyTheme(theme) {
    root.dataset.theme = theme;
    root.removeAttribute("data-theme-pending");
    var toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) return;
    var dark = theme === "dark";
    toggle.setAttribute("aria-pressed", String(dark));
    toggle.querySelector("[data-theme-label]").textContent = dark
      ? "Use light theme"
      : "Use dark theme";
  }

  applyTheme(storedTheme() || (media.matches ? "dark" : "light"));

  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(root.dataset.theme);
    var toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) return;
    toggle.addEventListener("click", function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(storageKey, next);
      } catch (_error) {
        // Theme switching still works when storage is blocked.
      }
      applyTheme(next);
    });
  });

  function followSystem(event) {
    if (!storedTheme()) applyTheme(event.matches ? "dark" : "light");
  }
  if (media.addEventListener) media.addEventListener("change", followSystem);
  else media.addListener(followSystem);
})();
