(function () {
  const mobileQuery = window.matchMedia("(max-width: 768px), (pointer: coarse)");
  if (!mobileQuery.matches) return;

  const doc = document.documentElement;
  const body = document.body;
  const isArabic = (doc.dir || "").toLowerCase() === "rtl" || (doc.lang || "").startsWith("ar");

  body.classList.add("se-mobile-app");

  function setKeyboardState() {
    if (!window.visualViewport) return;
    const delta = window.innerHeight - window.visualViewport.height - window.visualViewport.offsetTop;
    body.classList.toggle("se-mobile-keyboard", delta > 120);
  }

  function setupTapFeedback() {
    const selector = "a, button, summary, [role='button'], input[type='submit'], input[type='button']";
    document.addEventListener("pointerdown", (event) => {
      const target = event.target.closest(selector);
      if (!target || target.disabled || target.closest(".se-bottom-nav")?.classList.contains("is-disabled")) return;
      target.classList.add("is-tapping");
    }, { passive: true });

    ["pointerup", "pointercancel", "pointerleave", "blur"].forEach((eventName) => {
      document.addEventListener(eventName, (event) => {
        const target = event.target.closest?.(".is-tapping");
        if (!target) return;
        window.setTimeout(() => target.classList.remove("is-tapping"), 90);
      }, { passive: true });
    });
  }

  function setupBottomNavActiveState() {
    const current = new URL(window.location.href);
    document.querySelectorAll(".se-bottom-nav a[href]").forEach((link) => {
      const url = new URL(link.href, window.location.origin);
      const isExact = url.pathname === current.pathname;
      const isDeals = current.pathname.startsWith("/deals/") && url.pathname.startsWith("/deals/");
      const isProfile = current.pathname.startsWith("/profile/") && url.pathname.startsWith("/profile/");
      const isChat = current.pathname.startsWith("/chat/") && url.pathname.startsWith("/chat/");
      link.classList.toggle("active", isExact || isDeals || isProfile || isChat);
    });
  }

  function setupMobileMenuGestures() {
    const menu = document.getElementById("mobileMenu");
    if (!menu) return;

    let startY = 0;
    let currentY = 0;

    menu.addEventListener("touchstart", (event) => {
      startY = event.touches[0].clientY;
      currentY = startY;
    }, { passive: true });

    menu.addEventListener("touchmove", (event) => {
      currentY = event.touches[0].clientY;
      const delta = Math.max(0, currentY - startY);
      if (delta > 14 && menu.scrollTop <= 0) {
        menu.style.transform = `translate3d(0, ${Math.min(delta, 120)}px, 0)`;
      }
    }, { passive: true });

    menu.addEventListener("touchend", () => {
      const delta = currentY - startY;
      menu.style.transform = "";
      if (delta > 78 && menu.classList.contains("open") && typeof window.closeMobileMenu === "function") {
        window.closeMobileMenu();
      }
    }, { passive: true });
  }

  function setupFormHints() {
    document.querySelectorAll("input").forEach((input) => {
      const name = `${input.name || ""} ${input.id || ""}`.toLowerCase();
      if (!input.autocomplete) {
        if (input.type === "email" || name.includes("email")) input.autocomplete = "email";
        if (name.includes("username")) input.autocomplete = "username";
        if (name.includes("password")) input.autocomplete = input.name === "password1" ? "new-password" : "current-password";
        if (name.includes("search") || input.type === "search") input.autocomplete = "off";
      }
      if ((input.type === "text" || input.type === "search") && name.includes("search")) {
        input.setAttribute("enterkeyhint", "search");
      }
      if (input.type === "email") input.setAttribute("inputmode", "email");
      if (input.type === "number") input.setAttribute("inputmode", "decimal");
    });
  }

  function createSectionNav() {
    if (body.dataset.page !== "deal_detail" || document.querySelector(".dx-mobile-section-nav")) return;

    const sections = [
      { id: "mobile-deal-summary", icon: "fa-file-lines", labelAr: "الملخص", labelEn: "Summary", selector: ".se-product-card" },
      { id: "mobile-deal-chat", icon: "fa-comments", labelAr: "المحادثة", labelEn: "Chat", selector: ".se-deal-chat-card" },
      { id: "mobile-deal-actions", icon: "fa-bolt", labelAr: "الإجراءات", labelEn: "Actions", selector: "#dealActions" },
      { id: "mobile-deal-seller", icon: "fa-user-shield", labelAr: "البائع", labelEn: "Seller", selector: ".se-seller-card" },
      { id: "mobile-deal-activity", icon: "fa-clock-rotate-left", labelAr: "النشاط", labelEn: "Activity", selector: ".dx-intel-grid" }
    ];

    const available = sections
      .map((item) => ({ ...item, element: document.querySelector(item.selector) }))
      .filter((item) => item.element);

    if (available.length < 2) return;

    available.forEach((item) => {
      item.element.id = item.element.id || item.id;
    });

    const nav = document.createElement("nav");
    nav.className = "dx-mobile-section-nav";
    nav.setAttribute("aria-label", isArabic ? "أقسام الصفقة" : "Deal sections");
    nav.innerHTML = available.map((item, index) => {
      const label = isArabic ? item.labelAr : item.labelEn;
      return `<a href="#${item.element.id}" class="${index === 0 ? "is-active" : ""}"><i class="fas ${item.icon}" aria-hidden="true"></i><span>${label}</span></a>`;
    }).join("");

    const anchor = document.querySelector(".dx-progress-panel") || document.querySelector(".dx-hero");
    anchor?.insertAdjacentElement("afterend", nav);

    const links = Array.from(nav.querySelectorAll("a"));
    links.forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const target = document.querySelector(link.getAttribute("href"));
        if (!target) return;
        links.forEach((item) => item.classList.remove("is-active"));
        link.classList.add("is-active");
        target.scrollIntoView({ block: "start", behavior: "smooth" });
      });
    });

    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          links.forEach((link) => link.classList.toggle("is-active", link.getAttribute("href") === `#${entry.target.id}`));
        });
      }, { rootMargin: "-35% 0px -50% 0px", threshold: 0.01 });
      available.forEach((item) => observer.observe(item.element));
    }
  }

  function isVisible(element) {
    if (!element) return false;
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.offsetParent !== null;
  }

  function createActionClone(original) {
    const clone = original.tagName === "A" ? document.createElement("a") : document.createElement("button");
    clone.className = original.className;
    clone.innerHTML = original.innerHTML;
    clone.setAttribute("aria-label", original.getAttribute("aria-label") || original.textContent.trim());

    if (original.tagName === "A") {
      clone.href = original.href;
    } else {
      clone.type = "button";
      clone.addEventListener("click", () => original.click());
    }

    return clone;
  }

  function setupDealActionBar() {
    if (body.dataset.page !== "deal_detail" || document.querySelector(".se-mobile-action-bar")) return;
    const actionsBox = document.getElementById("dealActions");
    if (!actionsBox) return;

    const candidates = Array.from(actionsBox.querySelectorAll(".se-buy-box-container > a.btn, .se-buy-box-container > button.btn, .se-buy-box-container form button.btn"))
      .filter((item) => isVisible(item) && item.textContent.trim().length > 0)
      .slice(0, 2);

    if (!candidates.length) return;

    const bar = document.createElement("div");
    bar.className = "se-mobile-action-bar";
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", isArabic ? "إجراءات الصفقة السريعة" : "Quick deal actions");
    candidates.forEach((button) => bar.appendChild(createActionClone(button)));
    document.body.appendChild(bar);
    body.classList.add("se-has-action-bar");

    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          bar.classList.toggle("is-hidden", entry.isIntersecting);
        });
      }, { threshold: 0.25 });
      observer.observe(actionsBox);
    }
  }

  function setupSwipeBackCue() {
    let startX = 0;
    let startY = 0;
    document.addEventListener("touchstart", (event) => {
      if (event.touches.length !== 1) return;
      startX = event.touches[0].clientX;
      startY = event.touches[0].clientY;
    }, { passive: true });

    document.addEventListener("touchend", (event) => {
      const touch = event.changedTouches[0];
      if (!touch || startX > 28 || Math.abs(touch.clientY - startY) > 48) return;
      if (touch.clientX - startX > 84 && history.length > 1) {
        body.classList.add("se-swipe-back-ready");
        window.setTimeout(() => body.classList.remove("se-swipe-back-ready"), 260);
      }
    }, { passive: true });
  }

  function boot() {
    setupTapFeedback();
    setupBottomNavActiveState();
    setupMobileMenuGestures();
    setupFormHints();
    createSectionNav();
    setupDealActionBar();
    setupSwipeBackCue();

    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", setKeyboardState, { passive: true });
      window.visualViewport.addEventListener("scroll", setKeyboardState, { passive: true });
      setKeyboardState();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
