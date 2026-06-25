/**
 * SafouaneEscrow — Premium Redesigned Homepage JS
 * Features: Desktop Cursor Glow, Card Tilt Parallax, IntersectionObserver, Eased Stats Counter, Smooth FAQ Accordion.
 */
(function () {
  'use strict';

  const body = document.body;
  const home = document.querySelector('.hp-home');
  if (!home || body?.dataset.page !== 'home') return;

  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const isMobile = window.matchMedia?.('(max-width: 768px), (pointer: coarse)').matches;

  /* ═══════════════════════════════════════
     1. Navbar Scroll Sync
     ═══════════════════════════════════════ */
  function syncNav() {
    body.classList.toggle('hp-nav-solid', window.scrollY > 20);
  }

  let scrollTicking = false;
  window.addEventListener('scroll', () => {
    if (scrollTicking) return;
    scrollTicking = true;
    requestAnimationFrame(() => {
      syncNav();
      scrollTicking = false;
    });
  }, { passive: true });

  /* ═══════════════════════════════════════
     2. IntersectionObserver Scroll Reveals
     ═══════════════════════════════════════ */
  home.classList.add('hp-reveal-ready');
  const revealItems = Array.from(home.querySelectorAll('.hp-reveal, .hp-reveal-zoom'));
  
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, {
      rootMargin: isMobile ? '0px 0px 10% 0px' : '0px 0px -5% 0px',
      threshold: isMobile ? 0.01 : 0.05
    });

    revealItems.forEach((item, index) => {
      if (!reduceMotion) {
        // Stagger entries in rows
        item.style.transitionDelay = `${Math.min(index % 3, 3) * 80}ms`;
      }
      observer.observe(item);
    });
  } else {
    revealItems.forEach((item) => item.classList.add('is-visible'));
  }

  // Instantly reveal top elements
  requestAnimationFrame(() => {
    revealItems.slice(0, 3).forEach((item) => item.classList.add('is-visible'));
    syncNav();
  });

  /* ═══════════════════════════════════════
     3. Desktop Cursor Glow Effect
     ═══════════════════════════════════════ */
  if (!isMobile) {
    const glowCards = home.querySelectorAll('[data-glow-card], .hp-glass-card, .hp-deal-card, .hp-feature-card, .hp-proof-card, .hp-lane-card, .hp-testimonial, .hp-price-card, .hp-visual-pipeline-card, .hp-about-visual .hp-glass-card');
    
    glowCards.forEach((card) => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        card.style.setProperty('--mouse-x', `${x}px`);
        card.style.setProperty('--mouse-y', `${y}px`);
      });
    });
  }

  /* ═══════════════════════════════════════
     4. 3D Card Tilt Parallax Effect
     ═══════════════════════════════════════ */
  if (!isMobile && !reduceMotion) {
    const tiltCards = home.querySelectorAll('.hp-glass-glow-card, .hp-price-card, .hp-deal-card, .hp-visual-pipeline-card');
    
    tiltCards.forEach((card) => {
      card.style.transition = 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease';
      
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        const centerX = rect.width / 2;
        const centerY = rect.height / 2;
        
        const rotateX = ((centerY - y) / centerY) * 5; // Max 5 deg tilt
        const rotateY = ((x - centerX) / centerX) * 5;
        
        card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
      });
      
      card.addEventListener('mouseleave', () => {
        card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)';
      });
    });
  }

  /* ═══════════════════════════════════════
     5. Eased Count-Up Statistics
     ═══════════════════════════════════════ */
  function animateCounter(el) {
    const text = el.textContent.trim();
    const match = text.match(/^([^\d]*)(\d[\d,.]*)([^\d]*)$/);
    if (!match) return;

    const prefix = match[1];
    const numStr = match[2].replace(/,/g, '');
    const suffix = match[3];
    const target = parseFloat(numStr);
    if (isNaN(target)) return;

    const isDecimal = numStr.includes('.');
    const decimals = isDecimal ? (numStr.split('.')[1] || '').length : 0;
    const duration = 1500; // Eased over 1.5s
    const startTime = performance.now();

    function easeOutExpo(t) {
      return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
    }

    function update(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const value = target * easeOutExpo(progress);

      if (isDecimal) {
        el.textContent = prefix + value.toFixed(decimals) + suffix;
      } else {
        el.textContent = prefix + Math.round(value).toLocaleString('en-US') + suffix;
      }

      if (progress < 1) {
        requestAnimationFrame(update);
      }
    }

    el.textContent = prefix + '0' + suffix;
    requestAnimationFrame(update);
  }

  const statElements = home.querySelectorAll('.hp-stat strong');
  if (statElements.length && 'IntersectionObserver' in window) {
    const counterObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          counterObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    statElements.forEach((el) => counterObserver.observe(el));
  }

  /* ═══════════════════════════════════════
     6. Smooth Details/Summary FAQ Accordion
     ═══════════════════════════════════════ */
  const accordion = home.querySelector('[data-home-accordion]');
  if (accordion) {
    const items = accordion.querySelectorAll('.hp-faq-item');
    items.forEach((item) => {
      const summary = item.querySelector('summary');
      const content = item.querySelector('p');

      summary.addEventListener('click', (e) => {
        e.preventDefault();
        
        const isOpen = item.hasAttribute('open');

        // Close other open items
        items.forEach((otherItem) => {
          if (otherItem !== item && otherItem.hasAttribute('open')) {
            const otherContent = otherItem.querySelector('p');
            otherContent.style.height = `${otherContent.offsetHeight}px`;
            requestAnimationFrame(() => {
              otherContent.style.transition = 'height 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease';
              otherContent.style.height = '0px';
              otherContent.style.opacity = '0';
            });
            setTimeout(() => {
              otherItem.removeAttribute('open');
              otherContent.removeAttribute('style');
            }, 300);
          }
        });

        if (isOpen) {
          // Animate closing
          content.style.height = `${content.offsetHeight}px`;
          requestAnimationFrame(() => {
            content.style.transition = 'height 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease';
            content.style.height = '0px';
            content.style.opacity = '0';
          });
          setTimeout(() => {
            item.removeAttribute('open');
            content.removeAttribute('style');
          }, 300);
        } else {
          // Open item and animate height
          item.setAttribute('open', '');
          const targetHeight = content.offsetHeight;
          content.style.height = '0px';
          content.style.opacity = '0';
          
          requestAnimationFrame(() => {
            content.style.transition = 'height 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease';
            content.style.height = `${targetHeight}px`;
            content.style.opacity = '1';
          });

          setTimeout(() => {
            content.removeAttribute('style');
          }, 350);
        }
      });
    });
  }

  /* ═══════════════════════════════════════
     7. Smooth Anchors Navigation
     ═══════════════════════════════════════ */
  home.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', (e) => {
      const targetId = anchor.getAttribute('href');
      if (targetId === '#') return;
      const target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        const navHeight = document.querySelector('.se-navbar')?.offsetHeight || 72;
        const top = target.getBoundingClientRect().top + window.scrollY - navHeight - 15;
        window.scrollTo({ top, behavior: 'smooth' });
      }
    });
  });

  /* ═══════════════════════════════════════
     8. About Escrow Pipeline Real-time Simulator
     ═══════════════════════════════════════ */
  const pipelineSteps = home.querySelectorAll('.hp-pipeline-steps .hp-pipeline-step');
  const connectors = home.querySelectorAll('.hp-pipeline-steps .hp-pipeline-connector');
  if (pipelineSteps.length > 0) {
    let currentActiveIndex = 0;
    
    function cyclePipeline() {
      pipelineSteps.forEach((step, idx) => {
        if (idx === currentActiveIndex) {
          step.classList.add('active');
        } else {
          step.classList.remove('active');
        }
      });

      connectors.forEach((conn, idx) => {
        if (idx < currentActiveIndex) {
          conn.classList.add('active');
        } else {
          conn.classList.remove('active');
        }
      });

      currentActiveIndex = (currentActiveIndex + 1) % pipelineSteps.length;
    }
    
    // Cycle pipeline simulation every 3 seconds
    setInterval(cyclePipeline, 3000);
  }

})();
