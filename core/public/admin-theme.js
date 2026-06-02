/*
  Admin Theme Patch
  Подключать ПОСЛЕ admin.js:
  <script src="admin-theme.js"></script>
*/

(function () {
  const STORAGE_KEY = "donationGoalAdminTheme";

  function getSavedTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") {
      return saved;
    }

    const prefersLight = window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: light)").matches;

    return prefersLight ? "light" : "dark";
  }

  function applyTheme(theme) {
    document.body.dataset.theme = theme;
    localStorage.setItem(STORAGE_KEY, theme);

    const text = document.querySelector(".theme-toggle-text");
    if (text) {
      text.textContent = theme === "dark" ? "Тёмная тема" : "Светлая тема";
    }

    const button = document.querySelector(".theme-toggle");
    if (button) {
      button.setAttribute(
        "aria-label",
        theme === "dark" ? "Переключить на светлую тему" : "Переключить на тёмную тему"
      );
      button.title = theme === "dark" ? "Переключить на светлую тему" : "Переключить на тёмную тему";
    }
  }

  function ensureDocsButton() {
    const headerActions = document.querySelector(".header-actions");
    if (!headerActions) return;

    const existing = headerActions.querySelector('a[href="/docs/index.html"], a[href="docs/index.html"], a[data-docs-link="true"]');
    if (existing) return;

    const link = document.createElement("a");
    link.className = "link-button secondary";
    link.href = "/docs/index.html";
    link.target = "_blank";
    link.rel = "noopener";
    link.dataset.docsLink = "true";
    link.textContent = "Документация";

    headerActions.appendChild(link);
  }

  function createToggle() {
    if (document.querySelector(".theme-toggle")) return;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "theme-toggle";
    button.innerHTML = `
      <span class="theme-toggle-mark" aria-hidden="true"></span>
      <span class="theme-toggle-text">Тема</span>
    `;

    button.addEventListener("click", () => {
      const current = document.body.dataset.theme || "dark";
      applyTheme(current === "dark" ? "light" : "dark");
    });

    const headerActions = document.querySelector(".header-actions");

    if (headerActions) {
      headerActions.prepend(button);
    } else {
      button.classList.add("theme-toggle-floating");
      document.body.appendChild(button);
    }
  }

  function init() {
    applyTheme(getSavedTheme());
    ensureDocsButton();
    createToggle();
    applyTheme(document.body.dataset.theme || getSavedTheme());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
