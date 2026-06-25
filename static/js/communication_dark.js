(function () {
  const ready = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  };

  const getFilterName = (item) => {
    return String(item.dataset.cmFilterName || item.dataset.name || "").toLowerCase();
  };

  ready(() => {
    document.addEventListener("input", (event) => {
      const input = event.target.closest("[data-cm-filter-input]");
      if (!input) return;

      const root = document.querySelector(input.dataset.cmFilterTarget || "body");
      if (!root) return;

      const itemSelector = input.dataset.cmFilterItem || "[data-cm-filter-name]";
      const query = input.value.trim().toLowerCase();
      root.querySelectorAll(itemSelector).forEach((item) => {
        item.hidden = Boolean(query) && !getFilterName(item).includes(query);
      });
    });
  });
})();
