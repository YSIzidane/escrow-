(function () {
  function applySearchTab(tab) {
    var safeTab = ["deals", "users"].indexOf(tab) === -1 ? "deals" : tab;

    document.querySelectorAll("[data-search-tab]").forEach(function (button) {
      var isActive = button.dataset.searchTab === safeTab;
      button.classList.toggle("is-active", isActive);
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    document.querySelectorAll("[data-search-panel]").forEach(function (panel) {
      panel.hidden = panel.dataset.searchPanel !== safeTab;
    });
  }

  window.setSearchTab = applySearchTab;

  function setInitialTab() {
    var wrapper = document.querySelector("[data-active-search-tab]");
    applySearchTab((wrapper && wrapper.dataset.activeSearchTab) || "deals");
  }

  document.addEventListener("click", function (event) {
    var suggestion = event.target.closest("[data-sr-search-fill]");
    if (!suggestion) return;

    var input = document.getElementById("searchQuery");
    if (!input) return;

    input.value = suggestion.dataset.srSearchFill || suggestion.textContent.trim();
    input.focus();
    input.form && input.form.requestSubmit();
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (!event.detail || !event.detail.target || event.detail.target.id !== "search-results") return;
    setInitialTab();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setInitialTab, { once: true });
  } else {
    setInitialTab();
  }
})();
