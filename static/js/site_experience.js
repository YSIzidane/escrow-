(function () {
  const doc = document.documentElement;
  const body = document.body;
  const topLoader = document.getElementById('se-top-loader');
  const networkOverlay = document.getElementById('se-network-overlay');
  const networkLabel = networkOverlay?.querySelector('[data-network-label]');
  const networkTitle = networkOverlay?.querySelector('[data-network-title]');
  const networkBody = networkOverlay?.querySelector('[data-network-body]');
  const networkRetry = networkOverlay?.querySelector('[data-network-retry]');
  const prefetched = new Set();
  const chatInputSelector = '.se-msg-input, .er-chat-input, #msgInput, input[name="message"], input[name="text"]';
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const ui = window.SE_UI || {};
  let slowTimer = 0;

  function getNetworkCopy(state) {
    return ui.network?.[state] || {};
  }

  function showNetworkState(state) {
    if (!networkOverlay) return;

    const copy = getNetworkCopy(state);
    networkOverlay.dataset.state = state;
    if (networkLabel) networkLabel.textContent = copy.label || '';
    if (networkTitle) networkTitle.textContent = copy.title || '';
    if (networkBody) networkBody.textContent = copy.body || '';
    networkOverlay.hidden = false;
    window.requestAnimationFrame(() => networkOverlay.classList.add('is-visible'));
  }

  function hideNetworkState(force = false) {
    if (!networkOverlay) return;
    if (!force && networkOverlay.dataset.state === 'offline' && !navigator.onLine) return;

    networkOverlay.classList.remove('is-visible');
    window.setTimeout(() => {
      if (!networkOverlay.classList.contains('is-visible')) {
        networkOverlay.hidden = true;
      }
    }, 220);
  }

  function clearNetworkTimers() {
    window.clearTimeout(slowTimer);
  }

  function canPrefetch() {
    if (connection?.saveData) return false;
    if (/(slow-2g|2g|3g)/i.test(connection?.effectiveType || '')) return false;
    if (navigator.deviceMemory && navigator.deviceMemory <= 2) return false;
    if (window.matchMedia?.('(pointer: coarse)').matches) return false;
    return true;
  }

  function finishLoader() {
    clearNetworkTimers();
    if (!topLoader) return;
    topLoader.classList.remove('loading');
    topLoader.classList.add('done');
    body.classList.remove('is-navigating');
    if (navigator.onLine) {
      hideNetworkState(true);
    } else {
      showNetworkState('offline');
    }
    window.setTimeout(() => {
      topLoader.classList.remove('done');
      topLoader.style.width = '0';
    }, 550);
  }

  function startLoader() {
    if (!topLoader) return;
    clearNetworkTimers();
    topLoader.classList.remove('done');
    topLoader.classList.add('loading');
    body.classList.add('is-navigating');

    if (!navigator.onLine) {
      showNetworkState('offline');
      return;
    }

    // Keep fast navigation lightweight. The full-screen overlay is reserved
    // for genuinely slow transitions instead of appearing on every click.
    slowTimer = window.setTimeout(() => {
      if (body.classList.contains('is-navigating') && navigator.onLine) {
        showNetworkState('slow');
      }
    }, 4500);
  }

  function isPrefetchable(link) {
    if (!link || !link.href) return false;
    if (link.target === '_blank' || link.hasAttribute('download')) return false;
    if (link.origin !== window.location.origin) return false;
    if (link.hash && link.pathname === window.location.pathname) return false;
    return /^https?:$/.test(link.protocol);
  }

  function prefetchLink(link) {
    if (!canPrefetch() || !isPrefetchable(link) || prefetched.has(link.href)) return;
    prefetched.add(link.href);

    const hint = document.createElement('link');
    hint.rel = 'prefetch';
    hint.href = link.href;
    hint.as = 'document';
    document.head.appendChild(hint);
  }

  function handleLinkIntent(event) {
    const link = event.target.closest('a');
    if (!link) return;

    if (event.type !== 'click') {
      prefetchLink(link);
      return;
    }

    if (
      event.defaultPrevented ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.button !== 0
    ) {
      return;
    }

    if (isPrefetchable(link)) {
      startLoader();
    }
  }

  function updateKeyboardState() {
    updateViewportMetrics();
    if (!window.visualViewport) return;
    const isMobile = window.innerWidth <= 991;
    const heightDelta = window.innerHeight - window.visualViewport.height;
    body.classList.toggle('keyboard-open', isMobile && heightDelta > 140);
  }

  function updateViewportMetrics() {
    const viewport = window.visualViewport;
    const viewportHeight = viewport ? viewport.height : window.innerHeight;
    const viewportTop = viewport ? viewport.offsetTop : 0;
    const keyboardOffset = Math.max(0, window.innerHeight - viewportHeight - viewportTop);

    doc.style.setProperty('--se-app-vh', `${Math.round(viewportHeight)}px`);
    doc.style.setProperty('--se-keyboard-offset', `${Math.round(keyboardOffset)}px`);
  }

  function keepInputVisible(input) {
    if (!input || window.innerWidth > 991) return;

    const reveal = () => {
      input.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    };

    window.setTimeout(reveal, 0);
    window.setTimeout(reveal, 220);
  }

  function handleChatInputIntent(event) {
    const input = event.target.closest?.(chatInputSelector);
    if (!input) return;

    if (document.activeElement !== input) {
      input.focus({ preventScroll: false });
    }

    keepInputVisible(input);
  }

  function setupRevealObserver() {
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const isCompactScreen = window.matchMedia?.('(max-width: 768px)').matches;
    const isTouchDevice = window.matchMedia?.('(pointer: coarse)').matches;
    const mobileRevealOnce = isCompactScreen || isTouchDevice;
    const page = body.dataset.page || '';
    const skipAutoPages = new Set(['home', 'private_chat', 'room', 'escrow_room']);

    if (!reduceMotion && !mobileRevealOnce && !skipAutoPages.has(page)) {
      const autoTargets = document.querySelectorAll([
        '.se-main > section',
        '.se-main > div',
        '.se-main article',
        '.se-main .card',
        '.se-main .pf-card',
        '.se-main .adm-surface',
        '.se-main .adm-card',
        '.se-main .auth-card',
        '.se-main .auth-status-card',
        '.se-main .email-card',
        '.se-main .account-card',
        '.se-main .logout-card'
      ].join(','));

      let revealIndex = 0;
      autoTargets.forEach((element) => {
        if (
          element.matches('[data-reveal], .safo-reveal, .si-reveal, script, style') ||
          element.closest('#chatBox, .se-chat-body, .er-chat-body, .se-room-chat-box, .se-deal-chat-box, table, thead, tbody') ||
          element.closest('.se-navbar, .se-footer, .se-bottom-nav, .se-mobile-menu') ||
          element.offsetParent === null
        ) {
          return;
        }

        const tag = element.tagName.toLowerCase();
        const isCard = element.matches('article, .card, .pf-card, .adm-card, .adm-surface, .auth-card, .email-card, .account-card, .logout-card');
        element.dataset.reveal = isCard ? 'zoom' : 'lift';
        element.style.setProperty('--se-reveal-delay', `${Math.min((revealIndex % 6) * 45, 225)}ms`);
        if (!isCompactScreen && (tag === 'section' || element.classList.contains('adm-surface'))) {
          element.dataset.reveal = revealIndex % 2 === 0 ? 'left' : 'right';
        }
        revealIndex += 1;
      });
    }

    const elements = document.querySelectorAll('[data-reveal]');
    if (!elements.length) return;

    if (reduceMotion || !('IntersectionObserver' in window)) {
      elements.forEach((element) => element.classList.add('revealed'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          if (mobileRevealOnce || entry.target.dataset.revealRepeat !== 'true') {
            observer.unobserve(entry.target);
          }
          return;
        }

        if (entry.target.dataset.revealRepeat !== 'true') return;
        entry.target.classList.remove('revealed');
      });
    }, {
      threshold: mobileRevealOnce ? 0.01 : 0.12,
      rootMargin: mobileRevealOnce ? '0px 0px 18% 0px' : '0px 0px -8% 0px'
    });

    elements.forEach((element) => observer.observe(element));
  }

  function setupNativeShareButtons() {
    const buttons = document.querySelectorAll('[data-share-native]');
    if (!buttons.length) return;

    const supported = typeof navigator.share === 'function';
    buttons.forEach((button) => {
      button.classList.toggle('is-supported', supported);
      if (!supported || button.dataset.shareBound === '1') return;

      button.dataset.shareBound = '1';
      button.addEventListener('click', async () => {
        try {
          await navigator.share({
            title: button.dataset.shareTitle || document.title,
            text: button.dataset.shareText || '',
            url: button.dataset.shareUrl || window.location.href,
          });
        } catch (error) {
          if (error?.name === 'AbortError') return;
          window.SE?.toast?.(
            ui.shareUnsupported || 'Native sharing is not available on this device.',
            'warning',
            2800,
          );
        }
      });
    });
  }

  document.addEventListener('mouseover', handleLinkIntent, { passive: true });
  if (canPrefetch()) {
    document.addEventListener('touchstart', handleLinkIntent, { passive: true });
  }
  document.addEventListener('click', handleLinkIntent);
  document.addEventListener('pointerup', handleChatInputIntent);
  document.addEventListener('focusin', (event) => {
    const input = event.target.closest?.(chatInputSelector);
    if (!input) return;
    updateKeyboardState();
    keepInputVisible(input);
  });
  document.addEventListener('focusout', () => {
    window.setTimeout(updateKeyboardState, 120);
  });
  window.addEventListener('pageshow', finishLoader);
  window.addEventListener('load', finishLoader);
  window.addEventListener('offline', () => showNetworkState('offline'));
  window.addEventListener('online', () => {
    window.SE?.toast?.(ui.onlineRestored || 'Connection restored.', 'success', 2400);
    if (body.classList.contains('is-navigating')) {
      hideNetworkState(true);
      clearNetworkTimers();
      slowTimer = window.setTimeout(() => {
        if (body.classList.contains('is-navigating') && navigator.onLine) {
          showNetworkState('slow');
        }
      }, 4500);
      return;
    }
    hideNetworkState(true);
  });

  networkRetry?.addEventListener('click', () => {
    if (!navigator.onLine) {
      window.location.reload();
      return;
    }
    hideNetworkState(true);
    if (body.classList.contains('is-navigating')) {
      clearNetworkTimers();
      slowTimer = window.setTimeout(() => {
        if (body.classList.contains('is-navigating') && navigator.onLine) {
          showNetworkState('slow');
        }
      }, 6000);
    }
  });

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', updateKeyboardState);
    window.visualViewport.addEventListener('scroll', updateKeyboardState);
    window.addEventListener('resize', updateKeyboardState);
    updateKeyboardState();
  } else {
    window.addEventListener('resize', updateViewportMetrics);
    updateViewportMetrics();
  }

  doc.classList.add('js-ready');
  setupRevealObserver();
  setupNativeShareButtons();
  if (!navigator.onLine) {
    showNetworkState('offline');
  }
})();
