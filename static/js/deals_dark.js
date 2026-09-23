(function () {
  const countdowns = new Set();
  let countdownTimer = null;

  function refreshCounters() {
    document.querySelectorAll("[data-dl-count-source]").forEach((field) => {
      const key = field.dataset.dlCountSource;
      const target = document.querySelector(`[data-dl-count="${key}"]`);
      if (!target) return;
      const update = () => {
        target.textContent = String(field.value.length);
      };
      field.addEventListener("input", update);
      update();
    });
  }

  function initDealTypeToggle() {
    const form = document.querySelector("[data-dl-create-form]");
    if (!form) return;

    const radios = Array.from(form.querySelectorAll('input[name="deal_type"]'));
    const fixedWrap = form.querySelector('[data-dl-price-mode="fixed"]');
    const auctionWrap = form.querySelector('[data-dl-price-mode="auction"]');
    const price = form.querySelector('input[name="price"]');
    const startingPrice = form.querySelector('input[name="starting_price"]');
    const auctionEndsAt = form.querySelector('input[name="auction_ends_at"]');
    const increment = form.querySelector('input[name="min_bid_increment"]');

    function apply() {
      const type = radios.find((radio) => radio.checked)?.value || "fixed";
      const isAuction = type === "auction";

      if (fixedWrap) fixedWrap.hidden = isAuction;
      if (auctionWrap) auctionWrap.hidden = !isAuction;

      if (price) {
        price.required = !isAuction;
        price.disabled = isAuction;
      }
      if (startingPrice) {
        startingPrice.required = isAuction;
        startingPrice.disabled = !isAuction;
      }
      if (auctionEndsAt) {
        auctionEndsAt.required = isAuction;
        auctionEndsAt.disabled = !isAuction;
      }
      if (increment) {
        increment.disabled = !isAuction;
      }
    }

    radios.forEach((radio) => radio.addEventListener("change", apply));
    apply();
  }

  function initCategoryExtras() {
    const deliveryMap = {
      games: "digital",
      accounts: "digital",
      services: "service",
      electronics: "shipping",
      digital: "digital",
      physical: "shipping",
    };

    const radios = Array.from(document.querySelectorAll('input[name="category"]'));
    const deliveryType = document.getElementById("deliveryTypeInput");
    const platform = document.querySelector('[data-dl-category-extra="platform"]');
    const deliveryTime = document.querySelector('[data-dl-category-extra="delivery_time"]');

    if (!radios.length) return;

    function apply() {
      const category = radios.find((radio) => radio.checked)?.value || "games";
      if (deliveryType) deliveryType.value = deliveryMap[category] || "shipping";
      if (platform) platform.hidden = !(category === "games" || category === "accounts");
      if (deliveryTime) deliveryTime.hidden = category !== "services";
    }

    radios.forEach((radio) => radio.addEventListener("change", apply));
    apply();
  }

  function initImageUpload() {
    const input = document.querySelector("[data-dl-images]");
    const zone = document.querySelector("[data-dl-upload-zone]");
    const preview = document.querySelector("[data-dl-preview]");
    if (!input || !zone || !preview) return;

    function render(files) {
      preview.innerHTML = "";
      Array.from(files).slice(0, 10).forEach((file) => {
        if (!file.type.startsWith("image/")) return;
        const reader = new FileReader();
        reader.onload = () => {
          const item = document.createElement("span");
          item.className = "dl-preview";
          item.innerHTML = `<img src="${reader.result}" alt="">`;
          preview.appendChild(item);
        };
        reader.readAsDataURL(file);
      });
    }

    input.addEventListener("change", () => render(input.files));

    ["dragenter", "dragover"].forEach((eventName) => {
      zone.addEventListener(eventName, (event) => {
        event.preventDefault();
        zone.classList.add("is-dragging");
      });
    });

    ["dragleave", "drop"].forEach((eventName) => {
      zone.addEventListener(eventName, () => {
        zone.classList.remove("is-dragging");
      });
    });

    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!event.dataTransfer?.files?.length) return;
      input.files = event.dataTransfer.files;
      render(input.files);
    });
  }

  function initSubmitState() {
    const form = document.getElementById("createDealForm");
    const button = document.getElementById("submitBtn");
    if (!form || !button) return;

    form.addEventListener("submit", () => {
      if (!form.checkValidity()) return;
      button.disabled = true;
      button.style.opacity = "0.78";
      const loadingText = button.dataset.loadingText || "Publishing deal...";
      button.innerHTML = `<i class="fas fa-circle-notch fa-spin" aria-hidden="true"></i><span>${loadingText}</span>`;
    });
  }

  function formatCountdown(diff, item) {
    const totalSeconds = Math.max(0, Math.floor(diff / 1000));
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const dayLabel = item?.dataset.dayLabel || "day";
    const hourLabel = item?.dataset.hourLabel || "h";

    if (days > 0) {
      return `${days} ${dayLabel} ${String(hours).padStart(2, "0")}${hourLabel}`;
    }
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function tickCountdowns() {
    const now = Date.now();
    countdowns.forEach((item) => {
      if (!item.isConnected) {
        countdowns.delete(item);
        return;
      }

      const end = new Date(item.dataset.auctionEnd).getTime();
      if (Number.isNaN(end) || end <= now) {
        item.textContent = item.dataset.endedText || "Ended";
        item.removeAttribute("data-auction-end");
        countdowns.delete(item);
        return;
      }

      item.innerHTML = `<i class="fas fa-clock" aria-hidden="true"></i>${formatCountdown(end - now, item)}`;
    });

    if (!countdowns.size && countdownTimer) {
      window.clearInterval(countdownTimer);
      countdownTimer = null;
    }
  }

  function refreshCountdowns() {
    document.querySelectorAll(".dl-countdown[data-auction-end]").forEach((item) => countdowns.add(item));
    tickCountdowns();
    if (countdowns.size && !countdownTimer) {
      countdownTimer = window.setInterval(tickCountdowns, 1000);
    }
  }

  function initDealsPage() {
    refreshCountdowns();

    // Catch image load failures and remove them to reveal the fallback shield cleanly
    window.addEventListener(
      "error",
      (event) => {
        if (event.target && event.target.tagName === "IMG" && event.target.closest(".dl-deal-media")) {
          event.target.remove();
        }
      },
      true
    );

    document.body.addEventListener("htmx:afterSwap", (event) => {
      if (event.detail?.target?.id === "deals-container") {
        refreshCountdowns();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    refreshCounters();
    initDealTypeToggle();
    initCategoryExtras();
    initImageUpload();
    initSubmitState();
    initDealsPage();
  });
})();
