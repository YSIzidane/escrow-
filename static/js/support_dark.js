(function () {
  const ready = (callback) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  };

  ready(() => {
    document.querySelectorAll("[data-sd-file-input]").forEach((input) => {
      input.addEventListener("change", () => {
        const wrap = input.closest("[data-sd-file-wrap]");
        const label = wrap ? wrap.querySelector("[data-sd-file-name]") : null;
        if (!label) return;

        const fileName = input.files && input.files.length ? input.files[0].name : "";
        label.textContent = fileName || label.dataset.defaultText || "Choose file";
      });
    });

    document.querySelectorAll("[data-sd-submit-form]").forEach((form) => {
      form.addEventListener("submit", () => {
        const button = form.querySelector("[data-sd-submit-button]");
        if (!button) return;

        const text = button.querySelector("span");
        if (text && button.dataset.loadingText) {
          text.textContent = button.dataset.loadingText;
        }
        button.disabled = true;
      });
    });

    const searchInput = document.querySelector("[data-sd-ticket-search]");
    const ticketRows = Array.from(document.querySelectorAll("[data-sd-ticket-row]"));
    const emptyState = document.querySelector("[data-sd-search-empty]");

    if (searchInput && ticketRows.length) {
      const normalize = (value) => String(value || "").toLocaleLowerCase();

      const applySearch = () => {
        const query = normalize(searchInput.value).trim();
        let visibleCount = 0;

        ticketRows.forEach((row) => {
          const haystack = normalize(row.dataset.ticketSearch || row.textContent);
          const isVisible = !query || haystack.includes(query);
          row.hidden = !isVisible;
          if (isVisible) visibleCount += 1;
        });

        if (emptyState) {
          emptyState.hidden = visibleCount !== 0;
        }
      };

      searchInput.addEventListener("input", applySearch);
      applySearch();
    }
  });
})();
