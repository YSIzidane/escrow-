/**
 * ============================================================
 *  SafouaneEscrow — main.js  v2.0 (fixed)
 *  تحسينات تجربة المستخدم — نسخة مُصلَحة
 * ============================================================
 */

/* ══════════════════════════════════════════════
   1. NAVBAR — تأثير التمرير + إغلاق القائمة
══════════════════════════════════════════════ */
(function initNavbar() {
  const navbar = document.querySelector('.se-navbar, .navbar');
  if (!navbar) return;

  let lastScroll = 0;
  window.addEventListener('scroll', () => {
    const current = window.scrollY;
    navbar.style.boxShadow = current > 10
      ? '0 4px 24px rgba(0,0,0,0.35)'
      : '0 2px 20px rgba(0,0,0,0.3)';

    if (current > lastScroll && current > 80) {
      navbar.style.transform = 'translateY(-100%)';
      navbar.style.transition = 'transform 0.35s ease, box-shadow 0.3s ease';
    } else {
      navbar.style.transform = 'translateY(0)';
    }
    lastScroll = current;
  }, { passive: true });

  document.addEventListener('click', (e) => {
    const navCollapse = document.querySelector('.navbar-collapse.show');
    if (navCollapse && !navbar.contains(e.target)) {
      navCollapse.classList.remove('show');
    }
  });
})();


/* ══════════════════════════════════════════════
   2. SMOOTH PAGE TRANSITIONS — انتقال سلس
══════════════════════════════════════════════ */
(function initPageTransitions() {
  const shouldSkipTransitions = window.matchMedia('(max-width: 768px), (prefers-reduced-motion: reduce)').matches;
  if (shouldSkipTransitions) return;

  const overlay = document.createElement('div');
  overlay.id = 'se-page-overlay';
  Object.assign(overlay.style, {
    position: 'fixed', inset: '0', background: '#0D1B2A',
    opacity: '0', pointerEvents: 'none',
    transition: 'opacity 0.25s ease', zIndex: '9999'
  });
  document.body.appendChild(overlay);

  window.addEventListener('load', () => {
    overlay.style.opacity = '0';
    overlay.style.pointerEvents = 'none';
  });

  document.querySelectorAll('a[href]').forEach((link) => {
    const href = link.getAttribute('href');
    if (
      !href || href.startsWith('#') || href.startsWith('javascript') ||
      href.startsWith('mailto') || href.startsWith('tel') ||
      link.target === '_blank' || link.closest('form')
    ) return;

    link.addEventListener('click', (e) => {
      e.preventDefault();
      overlay.style.opacity = '0.5';
      overlay.style.pointerEvents = 'all';
      setTimeout(() => { window.location.href = href; }, 180);
    });
  });
})();


/* ══════════════════════════════════════════════
   3. PRICE COUNTER — عداد الأرقام عند الظهور
══════════════════════════════════════════════ */
(function initPriceCounters() {
  function animateNumber(el, target, duration = 900) {
    const startTime = performance.now();
    const isFloat = target % 1 !== 0;
    function update(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = target * eased;
      el.textContent = isFloat ? current.toFixed(2) : Math.floor(current).toLocaleString('ar');
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  const priceObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      const raw = el.textContent.replace(/[^0-9.]/g, '');
      const num = parseFloat(raw);
      if (!isNaN(num) && num > 0) animateNumber(el, num);
      priceObserver.unobserve(el);
    });
  }, { threshold: 0.5 });

  document.querySelectorAll('.price-display, [style*="font-size: 1.8rem"]').forEach((el) => {
    priceObserver.observe(el);
  });
})();


/* ══════════════════════════════════════════════
   4. TOAST NOTIFICATIONS — إشعارات مخصصة
══════════════════════════════════════════════ */
window.SE = window.SE || {};
SE.escapeHtml = function (value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
};

SE.toast = function (message, type = 'info', duration = 4000) {
  const icons = {
    success: 'fa-check-circle',
    error:   'fa-times-circle',
    warning: 'fa-exclamation-triangle',
    info:    'fa-info-circle',
  };
  const colors = {
    success: '#0E7C5A',
    error:   '#C0392B',
    warning: '#E67E22',
    info:    '#2471A3',
  };

  const container = document.getElementById('toastContainer') ||
    (() => {
      const c = document.createElement('div');
      c.id = 'toastContainer';
      Object.assign(c.style, {
        position: 'fixed', top: '16px', left: '16px',
        zIndex: '1100', display: 'flex', flexDirection: 'column', gap: '10px'
      });
      document.body.appendChild(c);
      return c;
    })();

  const toast = document.createElement('div');
  Object.assign(toast.style, {
    background: colors[type] || colors.info,
    color: 'white', borderRadius: '14px',
    padding: '12px 18px', minWidth: '260px', maxWidth: '360px',
    display: 'flex', alignItems: 'center', gap: '10px',
    boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
    fontFamily: "'Cairo', sans-serif", fontSize: '0.88rem', fontWeight: '600',
    opacity: '0', transform: 'translateX(-24px)',
    transition: 'all 0.35s cubic-bezier(0.34,1.56,0.64,1)',
    cursor: 'pointer', userSelect: 'none', position: 'relative', overflow: 'hidden',
  });

  const progress = document.createElement('div');
  Object.assign(progress.style, {
    position:'absolute', bottom:'0', right:'0', left:'0', height:'3px',
    background:'rgba(255,255,255,0.35)', transformOrigin:'right',
    transform:'scaleX(1)', transition:`transform ${duration}ms linear`,
  });
  const safeMessage = SE.escapeHtml(message);
  toast.innerHTML = `<i class="fas ${icons[type] || icons.info}" style="font-size:1.1rem;flex-shrink:0;"></i><span style="flex:1;">${safeMessage}</span>`;
  toast.appendChild(progress);
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(0)';
    setTimeout(() => { progress.style.transform = 'scaleX(0)'; }, 50);
  });

  const dismiss = () => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-24px)';
    setTimeout(() => toast.remove(), 350);
  };
  toast.addEventListener('click', dismiss);
  setTimeout(dismiss, duration);
};


/* ══════════════════════════════════════════════
   5. FORM ENHANCEMENTS — تحسينات النماذج
══════════════════════════════════════════════ */
(function initForms() {
  // منع الإرسال المزدوج
  document.querySelectorAll('form').forEach((form) => {
    if (form.getAttribute('method') === 'get') return;
    form.addEventListener('submit', function handler() {
      const btn = this.querySelector('button[type="submit"]:not([data-no-disable])');
      if (!btn || btn.disabled) return;
      btn.disabled = true;
      const original = btn.innerHTML;
      btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> جارٍ المعالجة...`;
      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = original;
      }, 8000);
    });
  });

  // تأثير focus على الحقول
  document.querySelectorAll('.form-control, .form-select').forEach((input) => {
    const wrapper = input.parentElement;
    input.addEventListener('focus', () => {
      wrapper.style.transition = 'transform 0.2s ease';
      wrapper.style.transform = 'scale(1.01)';
    });
    input.addEventListener('blur', () => {
      wrapper.style.transform = 'scale(1)';
    });
  });

  // عرض اسم الملف عند الرفع
  document.querySelectorAll('input[type="file"]').forEach((input) => {
    if (input.dataset.noLabel) return;
    input.addEventListener('change', function () {
      const file = this.files[0];
      if (!file) return;
      let label = this.nextElementSibling;
      if (!label || !label.classList.contains('se-file-label')) {
        label = document.createElement('div');
        label.className = 'se-file-label';
        Object.assign(label.style, {
          marginTop: '6px', fontSize: '0.78rem', color: '#9A7228',
          fontWeight: '700', padding: '5px 10px', background: '#FDF8F0',
          borderRadius: '8px', display: 'inline-block',
        });
        this.insertAdjacentElement('afterend', label);
      }
      label.textContent = `📎 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    });
  });
})();


/* ══════════════════════════════════════════════
   6. COPY TO CLIPBOARD — نسخ النصوص
══════════════════════════════════════════════ */
SE.copy = function (text, successMsg = 'تم النسخ!') {
  navigator.clipboard.writeText(text).then(() => {
    SE.toast(successMsg, 'success', 2500);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    SE.toast(successMsg, 'success', 2500);
  });
};

document.querySelectorAll('[data-copy]').forEach((btn) => {
  btn.addEventListener('click', () => SE.copy(btn.dataset.copy));
});

// دالة تنسيق الأسعار
SE.formatPrice = function(amount, currency = 'USD') {
  return new Intl.NumberFormat('ar-DZ', { style: 'currency', currency }).format(amount);
};

// دالة تنسيق الوقت النسبي
SE.timeAgo = function(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'الآن';
  if (mins < 60) return `منذ ${mins} دقيقة`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `منذ ${hrs} ساعة`;
  return `منذ ${Math.floor(hrs / 24)} يوم`;
};


/* ══════════════════════════════════════════════
   7. DEAL CARDS — تأثير hover بحركة الماوس
══════════════════════════════════════════════ */
(function initDealCards() {
  const supportsHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!supportsHover) return;

  document.querySelectorAll('.deal-card').forEach((card) => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      card.style.background = `radial-gradient(circle at ${x}% ${y}%, rgba(201,150,59,0.04) 0%, white 60%)`;
    });
    card.addEventListener('mouseleave', () => {
      card.style.background = 'white';
    });
  });
})();


/* ══════════════════════════════════════════════
   8. CHAT AUTO-SCROLL + REAL-TIME
══════════════════════════════════════════════ */
(function initChat() {
  document.querySelectorAll('#chatBox, #dealChatBox').forEach((box) => {
    box.scrollTop = box.scrollHeight;
    const observer = new MutationObserver(() => {
      box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
    });
    observer.observe(box, { childList: true });
  });

  document.querySelectorAll('#msgInput, #dealMsgInput').forEach((input) => {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        input.closest('form')?.submit();
      }
    });
  });

  // مؤشر "يكتب..."
  const msgInputs = document.querySelectorAll('#msgInput, #dealMsgInput');
  msgInputs.forEach((input) => {
    const chatBox = input.closest('.card')?.querySelector('#chatBox, #dealChatBox');
    if (!chatBox) return;
    let typingIndicator = null;
    let typingTimeout = null;
    input.addEventListener('input', () => {
      if (!typingIndicator) {
        typingIndicator = document.createElement('div');
        typingIndicator.style.cssText = `
          padding:8px 14px;font-size:.8rem;color:var(--text-light);
          font-style:italic;animation:fadeIn 0.3s ease;
        `;
        typingIndicator.innerHTML = '<i class="fas fa-ellipsis-h"></i> يكتب...';
        chatBox.appendChild(typingIndicator);
        chatBox.scrollTop = chatBox.scrollHeight;
      }
      clearTimeout(typingTimeout);
      typingTimeout = setTimeout(() => {
        typingIndicator?.remove();
        typingIndicator = null;
      }, 2000);
    });
  });
})();


/* ══════════════════════════════════════════════
   9. CONFIRM DIALOGS — مربعات تأكيد أنيقة
══════════════════════════════════════════════ */
SE.confirm = function (message, onConfirm, onCancel) {
  document.getElementById('se-confirm-dialog')?.remove();

  const backdrop = document.createElement('div');
  backdrop.id = 'se-confirm-dialog';
  Object.assign(backdrop.style, {
    position: 'fixed', inset: '0', background: 'rgba(13,27,42,0.65)',
    zIndex: '9998', display: 'flex', alignItems: 'center', justifyContent: 'center',
    backdropFilter: 'blur(4px)', animation: 'fadeIn 0.2s ease',
  });

  const box = document.createElement('div');
  Object.assign(box.style, {
    background: 'white', borderRadius: '20px', padding: '32px 28px',
    maxWidth: '380px', width: '90%', textAlign: 'center',
    boxShadow: '0 20px 60px rgba(13,27,42,0.3)',
    animation: 'scaleIn 0.3s cubic-bezier(0.34,1.56,0.64,1)',
    fontFamily: "'Cairo', sans-serif",
  });

  const safeMessage = SE.escapeHtml(message);
  box.innerHTML = `
    <div style="width:64px;height:64px;background:linear-gradient(135deg,#FEF5E7,#FDECEA);
      border-radius:50%;display:inline-flex;align-items:center;justify-content:center;margin-bottom:16px;">
      <i class="fas fa-question-circle" style="font-size:1.8rem;color:#E67E22;"></i>
    </div>
    <p style="font-size:1rem;font-weight:700;color:#0D1B2A;margin-bottom:24px;line-height:1.6;">${safeMessage}</p>
    <div style="display:flex;gap:12px;justify-content:center;">
      <button id="se-confirm-yes" style="background:linear-gradient(135deg,#C9963B,#E8B96A);color:#0D1B2A;
        border:none;border-radius:10px;padding:10px 28px;font-weight:700;font-size:.9rem;
        cursor:pointer;font-family:'Cairo',sans-serif;transition:all 0.2s ease;">نعم، تأكيد</button>
      <button id="se-confirm-no" style="background:#F0F4F8;color:#5A6A7A;
        border:none;border-radius:10px;padding:10px 28px;font-weight:700;font-size:.9rem;
        cursor:pointer;font-family:'Cairo',sans-serif;transition:all 0.2s ease;">إلغاء</button>
    </div>
  `;

  backdrop.appendChild(box);
  document.body.appendChild(backdrop);

  const close = () => {
    backdrop.style.opacity = '0';
    setTimeout(() => backdrop.remove(), 200);
  };

  document.getElementById('se-confirm-yes').onclick = () => { close(); onConfirm?.(); };
  document.getElementById('se-confirm-no').onclick  = () => { close(); onCancel?.(); };
  backdrop.addEventListener('click', (e) => { if (e.target === backdrop) { close(); onCancel?.(); } });
};

document.querySelectorAll('[data-confirm]').forEach((el) => {
  el.addEventListener('click', (e) => {
    e.preventDefault();
    SE.confirm(el.dataset.confirm, () => {
      if (el.tagName === 'A') window.location.href = el.href;
      else if (el.closest('form')) el.closest('form').submit();
    });
  });
});


/* ══════════════════════════════════════════════
   10. SEARCH ENHANCEMENTS — تحسين البحث
══════════════════════════════════════════════ */
(function initSearch() {
  document.querySelectorAll('input[type="search"], input[name="q"]').forEach((input) => {
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.innerHTML = '<i class="fas fa-times"></i>';
    Object.assign(clearBtn.style, {
      position: 'absolute', left: '10px', top: '50%',
      transform: 'translateY(-50%)', background: 'none', border: 'none',
      color: '#8A9BAB', cursor: 'pointer', display: 'none',
      padding: '4px', fontSize: '12px', transition: 'color 0.2s',
    });

    const parent = input.parentElement;
    if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';
    parent.appendChild(clearBtn);

    input.addEventListener('input', () => {
      clearBtn.style.display = input.value ? 'block' : 'none';
    });
    clearBtn.addEventListener('click', () => {
      input.value = '';
      clearBtn.style.display = 'none';
      input.focus();
      input.dispatchEvent(new Event('keyup'));
    });
  });
})();


/* ══════════════════════════════════════════════
   11. BACK TO TOP — زر العودة للأعلى
══════════════════════════════════════════════ */
(function initBackToTop() {
  const btn = document.createElement('button');
  btn.id = 'se-back-top';
  btn.innerHTML = '<i class="fas fa-chevron-up"></i>';
  Object.assign(btn.style, {
    position: 'fixed', bottom: '104px', left: '28px',
    width: '44px', height: '44px', borderRadius: '12px',
    background: 'rgba(13,27,42,0.8)', color: 'white',
    border: 'none', cursor: 'pointer', fontSize: '14px',
    display: 'none', alignItems: 'center', justifyContent: 'center',
    zIndex: '998', boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
    transition: 'all 0.3s cubic-bezier(0.34,1.56,0.64,1)',
    backdropFilter: 'blur(6px)',
  });
  document.body.appendChild(btn);

  window.addEventListener('scroll', () => {
    if (window.scrollY > 400) {
      btn.style.display = 'flex';
      requestAnimationFrame(() => { btn.style.opacity = '1'; btn.style.transform = 'scale(1)'; });
    } else {
      btn.style.opacity = '0';
      btn.style.transform = 'scale(0.8)';
      setTimeout(() => { if (window.scrollY <= 400) btn.style.display = 'none'; }, 300);
    }
  }, { passive: true });

  btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  btn.addEventListener('mouseenter', () => {
    btn.style.background = 'linear-gradient(135deg,#C9963B,#E8B96A)';
    btn.style.color = '#0D1B2A';
  });
  btn.addEventListener('mouseleave', () => {
    btn.style.background = 'rgba(13,27,42,0.8)';
    btn.style.color = 'white';
  });
})();


/* ══════════════════════════════════════════════
   12. AUCTION COUNTDOWN — عداد تنازلي
══════════════════════════════════════════════ */
(function initAuctionCountdown() {
  document.querySelectorAll('[data-auction-end]').forEach((el) => {
    const endTime = new Date(el.dataset.auctionEnd).getTime();
    function update() {
      const diff = endTime - Date.now();
      if (diff <= 0) {
        el.innerHTML = '<span style="color:var(--danger);font-weight:700;">⏱ انتهت المزايدة</span>';
        return;
      }
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      const isUrgent = diff < 3600000;
      const color = isUrgent ? 'var(--danger)' : diff < 86400000 ? 'var(--warning)' : 'var(--success)';
      el.innerHTML = `
        <div style="display:inline-flex;gap:6px;align-items:center;direction:ltr;">
          ${d > 0 ? `<span style="background:#F0F4F8;border-radius:6px;padding:3px 8px;font-weight:800;font-size:.9rem;color:${color}">${d}ي</span>` : ''}
          <span style="background:#F0F4F8;border-radius:6px;padding:3px 8px;font-weight:800;font-size:.9rem;color:${color}">${String(h).padStart(2,'0')}س</span>
          <span style="color:${color};font-weight:900;">:</span>
          <span style="background:#F0F4F8;border-radius:6px;padding:3px 8px;font-weight:800;font-size:.9rem;color:${color}">${String(m).padStart(2,'0')}د</span>
          <span style="color:${color};font-weight:900;">:</span>
          <span style="background:${isUrgent?color:'#F0F4F8'};border-radius:6px;padding:3px 8px;font-weight:800;font-size:.9rem;color:${isUrgent?'white':color}">${String(s).padStart(2,'0')}ث</span>
        </div>`;
      setTimeout(update, 1000);
    }
    update();
  });
})();


/* ══════════════════════════════════════════════
   13. TOOLTIPS — تلميحات
══════════════════════════════════════════════ */
(function initTooltips() {
  const tip = document.createElement('div');
  tip.id = 'se-tooltip';
  Object.assign(tip.style, {
    position: 'fixed', background: '#0D1B2A', color: 'white',
    padding: '6px 12px', borderRadius: '8px', fontSize: '0.78rem',
    fontFamily: "'Cairo', sans-serif", fontWeight: '600',
    pointerEvents: 'none', opacity: '0', zIndex: '9997',
    transition: 'opacity 0.2s ease', whiteSpace: 'normal',
    boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
    maxWidth: '200px', textAlign: 'center',
  });
  document.body.appendChild(tip);

  document.querySelectorAll('[title]').forEach((el) => {
    const titleText = el.getAttribute('title');
    if (!titleText) return;
    el.removeAttribute('title');
    el.dataset.tip = titleText;
    el.addEventListener('mouseenter', (e) => { tip.textContent = titleText; tip.style.opacity = '1'; positionTip(e); });
    el.addEventListener('mousemove', positionTip);
    el.addEventListener('mouseleave', () => { tip.style.opacity = '0'; });
  });

  function positionTip(e) {
    const x = e.clientX + 12;
    const y = e.clientY - 36;
    tip.style.left = Math.min(x, window.innerWidth - 220) + 'px';
    tip.style.top = Math.max(y, 8) + 'px';
  }
})();


/* ══════════════════════════════════════════════
   14. RIPPLE EFFECT — تأثير موجة على الأزرار
══════════════════════════════════════════════ */
(function initRipple() {
  if (!document.getElementById('se-ripple-style')) {
    const s = document.createElement('style');
    s.id = 'se-ripple-style';
    s.textContent = '@keyframes se-ripple{to{transform:scale(2.5);opacity:0}}';
    document.head.appendChild(s);
  }

  document.querySelectorAll('.btn').forEach((btn) => {
    btn.addEventListener('click', function (e) {
      const rect = this.getBoundingClientRect();
      const ripple = document.createElement('span');
      const size = Math.max(rect.width, rect.height);
      Object.assign(ripple.style, {
        position: 'absolute',
        width: size + 'px', height: size + 'px',
        left: (e.clientX - rect.left - size / 2) + 'px',
        top:  (e.clientY - rect.top  - size / 2) + 'px',
        background: 'rgba(255,255,255,0.25)',
        borderRadius: '50%',
        transform: 'scale(0)',
        animation: 'se-ripple 0.55s ease-out forwards',
        pointerEvents: 'none',
      });
      if (getComputedStyle(this).position === 'static') this.style.position = 'relative';
      this.style.overflow = 'hidden';
      this.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove());
    });
  });
})();


/* ══════════════════════════════════════════════
   15. READING PROGRESS BAR — شريط القراءة
══════════════════════════════════════════════ */
(function initReadingProgress() {
  if (!document.querySelector('.deal-card, #dealChatBox, .comment-item')) return;

  const bar = document.createElement('div');
  Object.assign(bar.style, {
    position: 'fixed', top: '0', right: '0', left: '0',
    height: '3px', background: 'transparent',
    zIndex: '1001', pointerEvents: 'none',
  });
  const fill = document.createElement('div');
  Object.assign(fill.style, {
    height: '100%', width: '0%',
    background: 'linear-gradient(90deg, var(--gold), var(--gold-light))',
    transition: 'width 0.1s ease',
  });
  bar.appendChild(fill);
  document.body.appendChild(bar);

  window.addEventListener('scroll', () => {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const pct = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
    fill.style.width = pct + '%';
  }, { passive: true });
})();


/* ══════════════════════════════════════════════
   16. ACTIVE NAV LINK — تمييز الرابط الحالي
══════════════════════════════════════════════ */
(function highlightActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll('.nav-link').forEach((link) => {
    const href = link.getAttribute('href');
    if (href && href !== '/' && path.startsWith(href)) {
      link.classList.add('active');
    }
  });
})();


/* ══════════════════════════════════════════════
   17. MOBILE MENU — se-navbar toggle
══════════════════════════════════════════════ */
(function initMobileMenu() {
  const toggle = document.querySelector('.se-mobile-toggle');
  const menu   = document.getElementById('mobileMenu');
  if (!toggle || !menu) return;

  toggle.addEventListener('click', () => {
    const isOpen = menu.classList.contains('open');
    menu.classList.toggle('open');
    toggle.innerHTML = isOpen ? '<i class="fas fa-bars"></i>' : '<i class="fas fa-times"></i>';
  });

  document.addEventListener('click', (e) => {
    if (menu.classList.contains('open') && !menu.contains(e.target) && !toggle.contains(e.target)) {
      menu.classList.remove('open');
      toggle.innerHTML = '<i class="fas fa-bars"></i>';
    }
  });
})();


/* ══════════════════════════════════════════════
   18. KEYBOARD SHORTCUTS
══════════════════════════════════════════════ */
(function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const modal = document.querySelector('.modal.show');
      if (modal && window.bootstrap) bootstrap.Modal.getInstance(modal)?.hide();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      const search = document.querySelector('.se-search input, input[name="q"]');
      if (search) { search.focus(); search.select(); }
    }
  });
})();


/* ══════════════════════════════════════════════
   19. DEAL ROOM SEARCH — بحث في جدول الصفقات
══════════════════════════════════════════════ */
function searchDeals(q) {
  const lower = q.toLowerCase().trim();
  const rows = document.querySelectorAll('.se-deal-row');
  let visible = 0;
  rows.forEach(row => {
    const match = !lower || row.textContent.toLowerCase().includes(lower);
    row.style.display = match ? '' : 'none';
    if (match) visible++;
  });
  const counter = document.getElementById('visibleCount');
  if (counter) counter.textContent = visible + ' صفقة';
}


/* ══════════════════════════════════════════════
   20. CHAT HUB SEARCH
══════════════════════════════════════════════ */
function filterChats(q) {
  const lower = q.toLowerCase().trim();
  let found = 0;
  document.querySelectorAll('.se-chat-item').forEach(item => {
    const match = item.dataset.name.includes(lower);
    item.style.display = match ? '' : 'none';
    if (match) found++;
  });
  let noRes = document.getElementById('chatSearchEmpty');
  if (!noRes) {
    noRes = document.createElement('div');
    noRes.id = 'chatSearchEmpty';
    noRes.style.cssText = 'text-align:center;padding:20px;color:var(--text-light);font-size:.82rem;display:none;';
    noRes.innerHTML = '<i class="fas fa-search" style="display:block;font-size:1.5rem;margin-bottom:8px;"></i>لا توجد نتائج';
    const list = document.getElementById('chatList');
    if (list) list.appendChild(noRes);
  }
  noRes.style.display = (found === 0 && q.length > 0) ? 'block' : 'none';
}


/* ══════════════════════════════════════════════
   21. INIT LOG
══════════════════════════════════════════════ */
console.log(
  '%c SafouaneEscrow JS %c v2.0 ',
  'background:#0D1B2A;color:#C9963B;padding:4px 8px;border-radius:4px 0 0 4px;font-weight:bold;',
  'background:#C9963B;color:#0D1B2A;padding:4px 8px;border-radius:0 4px 4px 0;font-weight:bold;'
);

/* ══════════════════════════════════════════════
   22. AJAX ENGINE — بدون إعادة تحميل
   يغطي: الدردشة الخاصة، غرف الدردشة، رسائل الصفقة،
         التعليقات، إرسال عروض المزايدة، أزرار الصفقة
══════════════════════════════════════════════ */
(function initAjax() {
  function shouldSkipGlobalAjax(form) {
    return form?.dataset?.skipGlobalAjax === 'true';
  }

  /* ── مساعد: قراءة CSRF token ── */
  function getCsrf() {
    return document.cookie.split(';')
      .map(c => c.trim())
      .find(c => c.startsWith('csrftoken='))
      ?.split('=')[1] || '';
  }

  /* ── مساعد: إرسال POST بدون إعادة تحميل ── */
  async function ajaxPost(url, formData) {
    formData.append('csrfmiddlewaretoken', getCsrf());
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: formData,
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[char]));
  }

  /* ── مساعد: بناء فقاعة رسالة ── */
  function buildMsgBubble({ text, time, avatar, isMe, username }) {
    const div = document.createElement('div');
    div.style.cssText = `display:flex;${isMe ? 'justify-content:flex-end' : 'justify-content:flex-start'};margin-bottom:16px;animation:fadeInUp .3s ease both;`;

    const safeText = escapeHtml(text);
    const safeTime = escapeHtml(time);
    const safeAvatar = escapeHtml(avatar);
    const safeUsername = escapeHtml(username);
    const avatarImg = `<img src="${safeAvatar}" style="width:34px;height:34px;border-radius:50%;object-fit:cover;${isMe ? 'margin-right:10px' : 'margin-left:10px'};align-self:flex-end;flex-shrink:0;">`;
    const nameLine  = !isMe && safeUsername ? `<div style="font-size:.72rem;color:var(--text-light);font-weight:600;margin-bottom:3px;padding-right:4px;">${safeUsername}</div>` : '';
    const bubble    = `
      <div style="max-width:68%;">
        ${nameLine}
        <div style="padding:11px 16px;font-size:.9rem;line-height:1.6;
          ${isMe
            ? 'background:linear-gradient(135deg,var(--navy),var(--navy-mid));color:white;border-radius:18px 18px 18px 4px;'
            : 'background:white;color:var(--text-primary);border:1px solid var(--border-light);border-radius:18px 18px 4px 18px;'}
          box-shadow:var(--shadow-sm);">${safeText}</div>
        <div style="font-size:.7rem;color:var(--text-light);margin-top:4px;${isMe ? 'text-align:right' : 'text-align:left'}">${safeTime}</div>
      </div>`;

    div.innerHTML = isMe ? bubble + avatarImg : avatarImg + bubble;
    return div;
  }

  /* ══ A. دردشة خاصة (private_chat.html) ══ */
  const privateChatForm = document.getElementById('privateChatForm');
  if (privateChatForm) {
    const chatBox  = document.getElementById('chatBox');
    const msgInput = document.getElementById('msgInput');
    const sendBtn  = document.getElementById('sendBtn');

    privateChatForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = msgInput.value.trim();
      if (!text) return;

      const fd = new FormData();
      fd.append('message', text);

      const fileInput = privateChatForm.querySelector('input[type="file"]');
      if (fileInput?.files[0]) fd.append('file', fileInput.files[0]);

      sendBtn.disabled = true;
      sendBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

      try {
        const data = await ajaxPost(window.location.href, fd);
        if (data.status === 'ok') {
          const bubble = buildMsgBubble({
            text: data.text,
            time: data.time,
            avatar: data.avatar,
            isMe: true,
          });
          chatBox.appendChild(bubble);
          chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
          msgInput.value = '';
          if (fileInput) fileInput.value = '';
        }
      } catch {
        SE.toast('فشل إرسال الرسالة، حاول مجدداً', 'error');
      } finally {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane" style="font-size:16px;"></i>';
      }
    });

    /* Enter → إرسال */
    msgInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); privateChatForm.requestSubmit(); }
    });
  }

  /* ══ B. غرف الدردشة (room.html) ══ */
  const roomMsgForm = document.getElementById('msgForm');
  if (roomMsgForm && !privateChatForm && !shouldSkipGlobalAjax(roomMsgForm)) {
    const chatBox  = document.getElementById('chatBox');
    const msgInput = document.getElementById('msgInput');
    const sendBtn  = document.getElementById('sendBtn');

    roomMsgForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = msgInput.value.trim();
      if (!text) return;

      const fd = new FormData();
      fd.append('message', text);

      sendBtn.disabled = true;
      sendBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

      try {
        const data = await ajaxPost(window.location.href, fd);
        if (data.status === 'ok') {
          const bubble = buildMsgBubble({
            text: data.text || text,
            time: data.time || new Date().toLocaleTimeString('ar', { hour: '2-digit', minute: '2-digit' }),
            avatar: data.avatar,
            isMe: true,
          });
          chatBox.appendChild(bubble);
          chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
          msgInput.value = '';
        }
      } catch {
        SE.toast('فشل إرسال الرسالة', 'error');
      } finally {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane" style="font-size:16px;"></i>';
      }
    });

    msgInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); roomMsgForm.requestSubmit(); }
    });
  }

  /* ══ C. رسائل الصفقة (deal_detail.html) ══ */
  const dealMsgForm = document.getElementById('dealMsgForm');
  if (dealMsgForm && !shouldSkipGlobalAjax(dealMsgForm)) {
    const chatBox  = document.getElementById('dealChatBox');
    const msgInput = document.getElementById('dealMsgInput');
    const sendBtn  = document.getElementById('dealSendBtn') || dealMsgForm.querySelector('button[type="submit"]');

    dealMsgForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = msgInput.value.trim();
      const file = dealMsgForm.querySelector('input[type="file"]')?.files[0];
      if (!text && !file) return;

      const fd = new FormData();
      fd.append('message', text);
      if (file) fd.append('file', file);

      sendBtn.disabled = true;
      sendBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

      try {
        const data = await ajaxPost(window.location.href, fd);
        if (data.status === 'ok') {
          const bubble = buildMsgBubble({ text, time: 'الآن', avatar: data.avatar, isMe: true });
          chatBox?.appendChild(bubble);
          chatBox?.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
          msgInput.value = '';
        }
      } catch {
        SE.toast('فشل إرسال الرسالة', 'error');
      } finally {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
      }
    });

    msgInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); dealMsgForm.requestSubmit(); }
    });
  }

  /* ══ D. إضافة تعليق (deal_detail.html) ══ */
  const commentForm = document.getElementById('commentForm');
  if (commentForm && !shouldSkipGlobalAjax(commentForm)) {
    commentForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text     = commentForm.querySelector('[name="comment_text"]').value.trim();
      const parentId = commentForm.querySelector('[name="parent_id"]')?.value || '';
      if (!text) return;

      const fd = new FormData();
      fd.append('add_comment', '1');
      fd.append('comment_text', text);
      if (parentId) fd.append('parent_id', parentId);

      const btn = commentForm.querySelector('button[type="submit"]');
      btn.disabled = true;

      try {
        const data = await ajaxPost(window.location.href, fd);
        if (data.status === 'ok') {
          const commentsList = document.getElementById('commentsList');
          const safeAvatar = escapeHtml(data.avatar);
          const safeAuthor = escapeHtml(data.author);
          const safeText = escapeHtml(data.text);
          const newComment = document.createElement('div');
          newComment.className = 'comment-item';
          newComment.style.cssText = 'animation:fadeInUp .4s ease both;';
          newComment.innerHTML = `
            <div style="display:flex;gap:12px;padding:16px;background:white;border-radius:14px;border:1px solid var(--border-light);margin-bottom:12px;">
              <img src="${safeAvatar}" style="width:38px;height:38px;border-radius:50%;object-fit:cover;border:2px solid var(--gold);flex-shrink:0;">
              <div style="flex:1;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                  <span style="font-weight:700;color:var(--navy);font-size:.88rem;">${safeAuthor}</span>
                  <span style="font-size:.72rem;color:var(--text-light);">الآن</span>
                </div>
                <p style="font-size:.88rem;color:var(--text-primary);line-height:1.7;margin:0;">${safeText}</p>
              </div>
            </div>`;
          commentsList?.appendChild(newComment);
          commentForm.querySelector('[name="comment_text"]').value = '';
          SE.toast('تم إضافة التعليق!', 'success');
        }
      } catch {
        SE.toast('فشل إرسال التعليق', 'error');
      } finally {
        btn.disabled = false;
      }
    });
  }

  /* ══ E. أزرار الصفقة (approve, ship, confirm, dispute) ══ */
  document.querySelectorAll('[data-deal-action]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const action = btn.dataset.dealAction;
      const form   = btn.closest('form') || document.createElement('form');
      const fd     = new FormData(form);
      fd.append(action, '1');

      const originalHTML = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

      try {
        const res = await fetch(window.location.href, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCsrf() },
          body: fd,
        });
        if (res.ok) {
          SE.toast('تم بنجاح! ✅', 'success');
          setTimeout(() => window.location.reload(), 800);
        }
      } catch {
        SE.toast('حدث خطأ، حاول مجدداً', 'error');
        btn.disabled = false;
        btn.innerHTML = originalHTML;
      }
    });
  });

  /* ══ F. تذكرة الدعم — ردود ── */
  const ticketReplyForm = document.getElementById('ticketReplyForm');
  if (ticketReplyForm) {
    ticketReplyForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd  = new FormData(ticketReplyForm);
      const btn = ticketReplyForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>إرسال...';

      try {
        const data = await ajaxPost(window.location.href, fd);
        if (data.status === 'ok') {
          const replies = document.getElementById('ticketReplies');
          const safeSender = escapeHtml(data.sender);
          const safeMessage = escapeHtml(data.message);
          const el = document.createElement('div');
          el.style.cssText = 'display:flex;justify-content:flex-end;margin-bottom:12px;animation:fadeInUp .3s ease both;';
          el.innerHTML = `
            <div style="max-width:75%;">
              <div style="text-align:right;margin-bottom:4px;">
                <span style="font-size:.72rem;font-weight:700;color:var(--text-secondary);">${safeSender}</span>
                <span style="font-size:.68rem;color:var(--text-light);margin-right:6px;">الآن</span>
              </div>
              <div style="padding:12px 16px;border-radius:16px 16px 4px 16px;background:linear-gradient(135deg,var(--navy),var(--navy-mid));color:white;font-size:.88rem;line-height:1.7;box-shadow:var(--shadow-sm);">
                ${safeMessage}
              </div>
            </div>`;
          replies?.appendChild(el);
          ticketReplyForm.querySelector('textarea').value = '';
          SE.toast('تم إرسال الرد!', 'success');
        }
      } catch {
        SE.toast('فشل إرسال الرد', 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane" style="margin-left:6px;"></i>إرسال';
      }
    });
  }

  /* ══ G. استطلاع تلقائي للرسائل الجديدة (polling) ══ */
  function startPolling(chatBoxId, pollUrl, renderFn) {
    const chatBox = document.getElementById(chatBoxId);
    if (!chatBox) return;

    let lastId = chatBox.querySelectorAll('[data-msg-id]');
    lastId = lastId.length ? lastId[lastId.length - 1].dataset.msgId : '0';
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    let pollTimer = null;

    function nextDelay() {
      if (document.hidden) return 30000;
      if (connection?.saveData) return 25000;
      if (window.matchMedia('(max-width: 768px)').matches) return 12000;
      return 5000;
    }

    async function runPoll() {
      if (navigator.onLine === false) {
        pollTimer = setTimeout(runPoll, nextDelay());
        return;
      }
      try {
        const res  = await fetch(`${pollUrl}?after=${lastId}`, {
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!res.ok) {
          pollTimer = setTimeout(runPoll, nextDelay());
          return;
        }
        const data = await res.json();
        if (data.messages?.length) {
          data.messages.forEach((msg) => {
            const el = renderFn(msg);
            el.dataset.msgId = msg.id;
            chatBox.appendChild(el);
            lastId = msg.id;
          });
          chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
        }
      } catch { /* تجاهل أخطاء الشبكة */ }
      pollTimer = setTimeout(runPoll, nextDelay());
    }
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && !pollTimer) {
        runPoll();
      }
    });
    window.addEventListener('beforeunload', () => clearTimeout(pollTimer), { once: true });
    runPoll();
  }

  /* تشغيل polling للدردشة الخاصة */
  if (document.getElementById('chatBox') && window.POLL_URL) {
    startPolling('chatBox', window.POLL_URL, (msg) => buildMsgBubble({
      text: msg.text,
      time: msg.time,
      avatar: msg.avatar,
      isMe: msg.is_me,
      username: msg.username,
    }));
  }

})();
