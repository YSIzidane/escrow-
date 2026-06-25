(function () {
  const tabs = document.querySelectorAll("[data-sn-filter]");
  const cards = document.querySelectorAll("[data-sn-card]");
  const markAllForm = document.querySelector("[data-sn-mark-all]");
  const filterEmpty = document.querySelector("[data-sn-filter-empty]");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const filter = tab.dataset.snFilter || "all";
      let visibleCount = 0;

      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      cards.forEach((card) => {
        const visible =
          filter === "all" ||
          (filter === "unread" && card.dataset.state === "unread") ||
          card.dataset.type === filter;
        card.hidden = !visible;
        if (visible) visibleCount += 1;
      });
      if (filterEmpty) filterEmpty.hidden = visibleCount > 0;
    });
  });

  if (markAllForm) {
    markAllForm.addEventListener("submit", (event) => {
      const unreadCards = document.querySelectorAll("[data-sn-card][data-state='unread']");
      if (!unreadCards.length) return;

      event.preventDefault();
      unreadCards.forEach((card) => {
        card.classList.add("sn-read-now", "is-read");
        card.classList.remove("is-unread");
        card.dataset.state = "read";
      });

      const countBadge = document.querySelector("[data-sn-count-badge]");
      const countText = countBadge ? countBadge.querySelector("span") : null;
      if (countText) countText.textContent = countBadge.dataset.zeroText || "0";

      window.setTimeout(() => markAllForm.submit(), 220);
    });
  }

  document.querySelectorAll("[data-sn-delete]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const card = form.closest("[data-sn-card]");
      if (!card) return;

      event.preventDefault();
      card.classList.add("sn-removing");
      window.setTimeout(() => form.submit(), 200);
    });
  });
})();
