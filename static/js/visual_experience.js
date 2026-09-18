(function () {
  const doc = document.documentElement;
  const body = document.body;
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const liteEffects = document.documentElement.classList.contains('se-lite-effects');
  const compactMotion = liteEffects || window.matchMedia?.('(max-width: 768px), (pointer: coarse)').matches;
  let maxScroll = 1;

  function refreshScrollBounds() {
    maxScroll = Math.max(1, doc.scrollHeight - window.innerHeight);
  }

  function updateScrollExperience() {
    const progress = Math.min(1, Math.max(0, window.scrollY / maxScroll));

    if (!compactMotion) {
      doc.style.setProperty('--se-scroll-progress', progress.toFixed(4));
    }

    if (!reduceMotion && !compactMotion) {
      doc.style.setProperty('--vx-scroll', progress.toFixed(4));
    } else {
      doc.style.setProperty('--vx-scroll', '0');
    }

    body.classList.toggle('se-scrolled', window.scrollY > 8);
  }

  function setupPressFeedback() {
    const selector = [
      '.se-main .btn',
      '.se-main button',
      '.se-main .safo-btn',
      '.se-nav-auth a',
      '.se-bnav-item',
      '.se-chat-fab'
    ].join(',');

    document.addEventListener('pointerdown', (event) => {
      const target = event.target.closest(selector);
      if (!target || target.disabled) return;

      target.classList.add('is-pressing');
    }, { passive: true });

    ['pointerup', 'pointercancel', 'pointerleave'].forEach((eventName) => {
      document.addEventListener(eventName, (event) => {
        const target = event.target.closest?.('.is-pressing');
        if (!target) return;

        window.setTimeout(() => target.classList.remove('is-pressing'), 90);
      }, { passive: true });
    });
  }

  let ticking = false;
  window.addEventListener('scroll', () => {
    if (ticking) return;

    ticking = true;
    window.requestAnimationFrame(() => {
      updateScrollExperience();
      ticking = false;
    });
  }, { passive: true });

  window.addEventListener('resize', () => {
    refreshScrollBounds();
    updateScrollExperience();
  }, { passive: true });
  window.addEventListener('load', () => {
    refreshScrollBounds();
    updateScrollExperience();
  }, { once: true });

  if ('ResizeObserver' in window) {
    new ResizeObserver(refreshScrollBounds).observe(document.body);
  }

  refreshScrollBounds();
  updateScrollExperience();
  setupPressFeedback();
})();
