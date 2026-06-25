(function () {
  const perf = window.SE_PERF || {};
  const vendor = window.SE_VENDOR || {};
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const canSpendBandwidth = !connection?.saveData && !/(slow-2g|2g)/i.test(connection?.effectiveType || "");

  function onIdle(callback, timeout = 2400) {
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(callback, { timeout });
      return;
    }
    window.setTimeout(callback, Math.min(timeout, 1200));
  }

  function loadScriptOnce(src, id) {
    if (!src) return Promise.resolve();
    if (id && document.getElementById(id)) return Promise.resolve();

    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      if (id) script.id = id;
      script.src = src;
      script.async = true;
      script.crossOrigin = "anonymous";
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function tuneMedia() {
    const fold = window.innerHeight * 1.25;
    document.querySelectorAll("img").forEach((image) => {
      if (!image.hasAttribute("decoding")) image.decoding = "async";
      if (!image.hasAttribute("loading") && image.getAttribute("fetchpriority") !== "high") {
        const rect = image.getBoundingClientRect();
        image.loading = rect.top > fold ? "lazy" : "eager";
      }
      if (!image.hasAttribute("fetchpriority") && image.loading === "lazy") {
        image.setAttribute("fetchpriority", "low");
      }
    });

    document.querySelectorAll("video").forEach((video) => {
      if (!video.hasAttribute("preload")) video.preload = "metadata";
      video.playsInline = true;
    });
  }

  function setupLazyVendors() {
    const needsBootstrap = document.querySelector(".modal, [data-bs-toggle], [data-bs-dismiss]");
    if (!needsBootstrap || window.bootstrap) return;

    const loadBootstrap = () => loadScriptOnce(vendor.bootstrap, "se-bootstrap-js").catch(() => {});
    document.addEventListener("click", (event) => {
      if (window.bootstrap) return;
      const dealGallery = event.target.closest?.(".se-gallery-main");
      const auctionGallery = event.target.closest?.(".se-auction-main-image");
      if (!dealGallery && !auctionGallery) return;

      event.preventDefault();
      event.stopPropagation();
      loadBootstrap().then(() => {
        if (dealGallery) {
          const image = dealGallery.querySelector("img");
          if (image && typeof window.openImageModal === "function") window.openImageModal(image.src);
        }
        if (auctionGallery && typeof window.showImageModal === "function") {
          const image = document.getElementById("auctionMainImage");
          if (image) window.showImageModal(image.src);
        }
      });
    }, true);
    ["pointerenter", "focusin", "touchstart"].forEach((eventName) => {
      document.addEventListener(eventName, (event) => {
        if (event.target.closest?.(".modal, [data-bs-toggle], [data-bs-dismiss], .se-gallery-main, .se-auction-main-image")) {
          loadBootstrap();
        }
      }, { once: true, passive: true, capture: true });
    });
    onIdle(loadBootstrap, 3200);
  }

  function setupVitals() {
    const vitalsUrl = perf.vitalsUrl;
    const sampleRate = Number(perf.sampleRate ?? 0.25);
    if (!vitalsUrl || Math.random() > sampleRate || !("PerformanceObserver" in window)) return;

    const metrics = {
      path: window.location.pathname,
      page: document.body?.dataset?.page || "default",
      nav: performance.getEntriesByType("navigation")[0]?.type || "navigate",
      fcp: 0,
      lcp: 0,
      cls: 0,
      inp: 0,
      tbt: 0,
      dcl: 0,
      load: 0,
    };

    function observe(type, callback, buffered = true) {
      try {
        const observer = new PerformanceObserver((list) => callback(list.getEntries()));
        observer.observe({ type, buffered });
      } catch {
        /* Unsupported entry type in this browser. */
      }
    }

    observe("paint", (entries) => {
      entries.forEach((entry) => {
        if (entry.name === "first-contentful-paint") metrics.fcp = Math.round(entry.startTime);
      });
    });

    observe("largest-contentful-paint", (entries) => {
      const last = entries[entries.length - 1];
      if (last) metrics.lcp = Math.round(last.startTime);
    });

    observe("layout-shift", (entries) => {
      entries.forEach((entry) => {
        if (!entry.hadRecentInput) metrics.cls += entry.value;
      });
      metrics.cls = Math.round(metrics.cls * 10000) / 10000;
    });

    observe("event", (entries) => {
      entries.forEach((entry) => {
        const latency = entry.processingStart - entry.startTime;
        if (latency > metrics.inp) metrics.inp = Math.round(latency);
      });
    });

    observe("longtask", (entries) => {
      entries.forEach((entry) => {
        metrics.tbt += Math.max(0, entry.duration - 50);
      });
      metrics.tbt = Math.round(metrics.tbt);
    });

    window.addEventListener("load", () => {
      const nav = performance.getEntriesByType("navigation")[0];
      if (!nav) return;
      metrics.dcl = Math.round(nav.domContentLoadedEventEnd);
      metrics.load = Math.round(nav.loadEventEnd);
    }, { once: true });

    function sendMetrics() {
      if (sendMetrics.sent) return;
      sendMetrics.sent = true;

      const body = JSON.stringify({
        ...metrics,
        cls: Math.round(metrics.cls * 10000) / 10000,
        effectiveType: connection?.effectiveType || "",
        saveData: Boolean(connection?.saveData),
        viewport: `${window.innerWidth}x${window.innerHeight}`,
      });

      if (navigator.sendBeacon) {
        navigator.sendBeacon(vitalsUrl, new Blob([body], { type: "application/json" }));
        return;
      }

      fetch(vitalsUrl, {
        method: "POST",
        body,
        headers: { "Content-Type": "application/json" },
        keepalive: true,
        credentials: "same-origin",
      }).catch(() => {});
    }

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") sendMetrics();
    });
    window.addEventListener("pagehide", sendMetrics);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      tuneMedia();
      setupLazyVendors();
      setupVitals();
    }, { once: true });
  } else {
    tuneMedia();
    setupLazyVendors();
    setupVitals();
  }

  if (canSpendBandwidth) {
    onIdle(() => {
      document.querySelectorAll('link[rel="preload"][as="image"]').forEach((link) => {
        link.setAttribute("importance", link.getAttribute("fetchpriority") || "auto");
      });
    }, 1800);
  }
})();
