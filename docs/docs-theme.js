(function () {
  const STORAGE_KEY = "vicwanderDocsTheme";

  function getTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);

    if (saved === "light" || saved === "dark") {
      return saved;
    }

    const prefersLight = window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: light)").matches;

    return prefersLight ? "light" : "dark";
  }

  function applyTheme(theme) {
    document.body.dataset.docTheme = theme;
    localStorage.setItem(STORAGE_KEY, theme);

    const text = document.querySelector(".doc-theme-text");
    if (text) {
      text.textContent = theme === "dark" ? "Тёмная тема" : "Светлая тема";
    }

    const button = document.querySelector(".doc-theme-toggle");
    if (button) {
      button.title = theme === "dark"
        ? "Переключить на светлую тему"
        : "Переключить на тёмную тему";

      button.setAttribute(
        "aria-label",
        theme === "dark" ? "Переключить на светлую тему" : "Переключить на тёмную тему"
      );
    }
  }

  function createButton() {
    if (document.querySelector(".doc-theme-toggle")) return;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "doc-theme-toggle";
    button.innerHTML = `
      <span class="doc-theme-dot" aria-hidden="true"></span>
      <span class="doc-theme-text">Тема</span>
    `;

    button.addEventListener("click", () => {
      const current = document.body.dataset.docTheme || "dark";
      applyTheme(current === "dark" ? "light" : "dark");
    });

    const sidebar = document.querySelector(".sidebar");
    const nav = document.querySelector(".nav");
    const subtitle = document.querySelector(".subtitle");

    if (sidebar && nav) {
      sidebar.insertBefore(button, nav);
    } else if (sidebar && subtitle) {
      subtitle.insertAdjacentElement("afterend", button);
    } else {
      button.style.width = "auto";
      button.style.position = "fixed";
      button.style.right = "18px";
      button.style.bottom = "18px";
      button.style.zIndex = "9999";
      document.body.appendChild(button);
    }
  }

  function init() {
    applyTheme(getTheme());
    createButton();
    applyTheme(document.body.dataset.docTheme || getTheme());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
