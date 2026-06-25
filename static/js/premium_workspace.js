(function () {
  function setSearchTab(tab) {
    var safeTab = ["deals", "users"].indexOf(tab) === -1 ? "deals" : tab;
    document.querySelectorAll("[data-search-tab]").forEach(function (button) {
      button.classList.toggle("active", button.dataset.searchTab === safeTab);
    });
    document.querySelectorAll("[data-search-panel]").forEach(function (panel) {
      panel.hidden = panel.dataset.searchPanel !== safeTab;
    });
  }

  window.setSearchTab = setSearchTab;

  document.addEventListener("change", function (event) {
    var input = event.target.closest("[data-pw-file-input]");
    if (!input) return;
    var drop = input.closest(".pw-file-drop");
    var label = drop ? drop.querySelector("[data-pw-file-name]") : null;
    var file = input.files && input.files[0];
    if (drop) drop.classList.toggle("is-filled", Boolean(file));
    if (label) label.textContent = file ? file.name : label.dataset.defaultText;
  });

  document.addEventListener("submit", function (event) {
    var form = event.target.closest("[data-pw-submit-form]");
    if (!form) return;
    var button = form.querySelector("[data-pw-submit-button]");
    if (!button) return;
    button.disabled = true;
    button.classList.add("is-loading");
    var label = button.querySelector("span");
    if (label && button.dataset.loadingText) label.textContent = button.dataset.loadingText;
  });

  document.addEventListener("click", function (event) {
    var filter = event.target.closest("[data-pw-notif-filter]");
    if (!filter) return;
    var value = filter.dataset.pwNotifFilter || "all";
    document.querySelectorAll("[data-pw-notif-filter]").forEach(function (button) {
      button.classList.toggle("is-active", button === filter);
    });
    document.querySelectorAll("[data-pw-notif-item]").forEach(function (item) {
      var state = item.dataset.state;
      var type = item.dataset.type;
      var visible = value === "all" || value === state || value === type;
      item.hidden = !visible;
    });
  });

  document.addEventListener("click", function (event) {
    var suggestion = event.target.closest("[data-pw-search-fill]");
    if (!suggestion) return;
    var input = document.getElementById("searchQuery");
    if (!input) return;
    input.value = suggestion.dataset.pwSearchFill || suggestion.textContent.trim();
    input.focus();
    input.dispatchEvent(new Event("keyup", { bubbles: true }));
  });

  document.addEventListener("input", function (event) {
    var input = event.target.closest("[data-pw-filter-input]");
    if (!input) return;
    var targetSelector = input.dataset.pwFilterTarget;
    var itemSelector = input.dataset.pwFilterItem || "[data-pw-filter-name]";
    var root = targetSelector ? document.querySelector(targetSelector) : document;
    if (!root) return;
    var query = input.value.trim().toLowerCase();
    root.querySelectorAll(itemSelector).forEach(function (item) {
      var name = (item.dataset.pwFilterName || item.dataset.name || "").toLowerCase();
      item.hidden = query && !name.includes(query);
    });
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (!event.detail || !event.detail.target || event.detail.target.id !== "search-results") return;
    var wrapper = event.detail.target.querySelector("[data-active-search-tab]");
    setSearchTab((wrapper && wrapper.dataset.activeSearchTab) || "deals");
  });

  document.addEventListener("DOMContentLoaded", function () {
    var wrapper = document.querySelector("[data-active-search-tab]");
    if (wrapper) setSearchTab(wrapper.dataset.activeSearchTab || "deals");
  });
})();
