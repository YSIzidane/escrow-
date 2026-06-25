/**
 * ============================================================
 *  SafouaneEscrow — enhancements.js v1.0
 *  ميزات JavaScript جديدة لجميع صفحات الموقع
 *  يُضاف بعد main.js
 * ============================================================
 */

(function () {
  'use strict';

  /* ══════════════════════════════════════════════
     A. BACK TO TOP BUTTON
  ══════════════════════════════════════════════ */
  (function initBackTop() {
    // إنشاء الزر إذا لم يكن موجوداً
    let btn = document.getElementById('se-back-top');
    if (!btn) {
      btn = document.createElement('a');
      btn.id = 'se-back-top';
      btn.href = '#';
      btn.innerHTML = '<i class="fas fa-arrow-up"></i>';
      btn.title = 'العودة للأعلى';
      document.body.appendChild(btn);
    }

    window.addEventListener('scroll', () => {
      btn.classList.toggle('visible', window.scrollY > 300);
    }, { passive: true });

    btn.addEventListener('click', (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  })();

  /* ══════════════════════════════════════════════
     B. IMAGE MODAL — عارض الصور المكبّرة
  ══════════════════════════════════════════════ */
  (function initImageModal() {
    // إنشاء المودال
    const modal = document.createElement('div');
    modal.className = 'se-img-modal';
    modal.innerHTML = `
      <button class="se-img-modal-close" id="seModalClose" aria-label="إغلاق">
        <i class="fas fa-times"></i>
      </button>
      <img src="" alt="عرض الصورة" id="seModalImg">
    `;
    document.body.appendChild(modal);

    const img = modal.querySelector('#seModalImg');

    // دالة الفتح
    window.openImageModal = function (src) {
      img.src = src;
      modal.classList.add('open');
      document.body.style.overflow = 'hidden';
    };

    // إغلاق بالنقر على الخلفية أو زر الإغلاق
    modal.addEventListener('click', (e) => {
      if (e.target === modal || e.target.closest('#seModalClose')) {
        modal.classList.remove('open');
        document.body.style.overflow = '';
      }
    });

    // إغلاق بـ ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.classList.contains('open')) {
        modal.classList.remove('open');
        document.body.style.overflow = '';
      }
    });
  })();

  /* ══════════════════════════════════════════════
     C. DEAL ROOM — فلترة الصفقات
  ══════════════════════════════════════════════ */
  (function initDealRoomFilter() {
    if (document.getElementById('deal-room-shell') && typeof window.initDealRoomPage === 'function') {
      return;
    }
    const filterBtns = document.querySelectorAll('.se-dr-filter-btn');
    if (!filterBtns.length) return;

    filterBtns.forEach((btn) => {
      btn.addEventListener('click', function () {
        // تحديث الأزرار
        filterBtns.forEach((b) => b.classList.remove('active'));
        this.classList.add('active');

        const filter = this.dataset.filter;
        const rows = document.querySelectorAll('[data-deal-status]');

        rows.forEach((row) => {
          if (filter === 'all' || row.dataset.dealStatus === filter) {
            row.style.display = '';
            row.style.animation = 'fadeInUp .3s ease both';
          } else {
            row.style.display = 'none';
          }
        });

        // تحديث العدد
        const visible = document.querySelectorAll('[data-deal-status]:not([style*="none"])').length;
        const counter = this.querySelector('.se-filter-count');
        if (counter) counter.textContent = visible;
      });
    });
  })();

  /* ══════════════════════════════════════════════
     D. DEALS PAGE — تأثير الفلتر السلس
  ══════════════════════════════════════════════ */
  (function initDealsFilter() {
    const radios = document.querySelectorAll('.se-radio input[type="radio"]');
    if (!radios.length) return;

    radios.forEach((radio) => {
      radio.addEventListener('change', function () {
        // تأثير بصري للتحميل
        const grid = document.querySelector('.se-deals-grid, .row.g-4');
        if (grid) {
          grid.style.opacity = '0.6';
          grid.style.transition = 'opacity .2s ease';
          setTimeout(() => {
            grid.style.opacity = '1';
          }, 400);
        }

        // تحديث label classes
        document.querySelectorAll('.se-radio').forEach((lbl) => {
          lbl.classList.remove('active');
        });
        this.closest('.se-radio')?.classList.add('active');

        // إرسال الفورم
        this.closest('form')?.submit();
      });
    });
  })();

  /* ══════════════════════════════════════════════
     E. GALLERY — تبديل الصور
  ══════════════════════════════════════════════ */
  window.switchMain = function (thumb) {
    const mainImg = document.getElementById('mainImage');
    if (!mainImg) return;

    // تأثير التبديل
    mainImg.style.opacity = '0';
    mainImg.style.transition = 'opacity .2s ease';

    setTimeout(() => {
      mainImg.src = thumb.src;
      mainImg.style.opacity = '1';
    }, 200);

    // تحديث الـ thumb النشط
    document.querySelectorAll('.se-gallery-thumb').forEach((t) => t.classList.remove('active'));
    thumb.classList.add('active');
  };

  /* ══════════════════════════════════════════════
     F. AUTO-RESIZE TEXTAREA
  ══════════════════════════════════════════════ */
  (function initAutoResize() {
    document.querySelectorAll('.se-chat-input, textarea.se-textarea').forEach((el) => {
      el.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 160) + 'px';
      });
    });
  })();

  /* ══════════════════════════════════════════════
     G. CHARACTER COUNTER
  ══════════════════════════════════════════════ */
  (function initCharCounters() {
    // عنوان الصفقة
    const titleInput = document.getElementById('titleInput');
    const titleCount = document.getElementById('titleCount');
    if (titleInput && titleCount) {
      const update = () => {
        const len = titleInput.value.length;
        titleCount.textContent = len;
        titleCount.style.color = len > 100 ? 'var(--warning)' : '';
      };
      titleInput.addEventListener('input', update);
      update();
    }

    // وصف الصفقة
    const descInput = document.getElementById('descInput');
    const descCount = document.getElementById('descCount');
    if (descInput && descCount) {
      const update = () => {
        descCount.textContent = descInput.value.length;
      };
      descInput.addEventListener('input', update);
      update();
    }
  })();

  /* ══════════════════════════════════════════════
     H. MULTI-STEP FORM — نموذج خطوات
  ══════════════════════════════════════════════ */
  (function initMultiStep() {
    const steps = document.querySelectorAll('.se-form-step');
    const indicators = document.querySelectorAll('.se-step-ind');
    if (!steps.length) return;

    let current = 0;

    window.goToStep = function (n) {
      steps[current].classList.remove('active');
      indicators[current]?.classList.remove('active');
      if (n > current) indicators[current]?.classList.add('done');

      current = n;
      steps[current].classList.add('active');
      indicators[current]?.classList.add('active');

      // تمرير للأعلى
      steps[current].scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    window.nextStep = function () {
      // تحقق من الحقول الإلزامية
      const activeStep = steps[current];
      const required = activeStep.querySelectorAll('[required]');
      let valid = true;

      required.forEach((field) => {
        if (!field.value.trim()) {
          field.style.borderColor = 'var(--danger)';
          field.style.boxShadow = '0 0 0 3px rgba(192,57,43,.15)';
          valid = false;
          setTimeout(() => {
            field.style.borderColor = '';
            field.style.boxShadow = '';
          }, 2000);
        }
      });

      if (!valid) {
        if (window.SE?.toast) SE.toast('يرجى ملء جميع الحقول الإلزامية', 'warning');
        return;
      }

      if (current < steps.length - 1) goToStep(current + 1);
    };

    window.prevStep = function () {
      if (current > 0) goToStep(current - 1);
    };
  })();

  /* ══════════════════════════════════════════════
     I. SEARCH TABS — تبويبات البحث
  ══════════════════════════════════════════════ */
  window.switchSearchTab = function (tab) {
    const panels = { users: 'users-panel', deals: 'deals-panel' };
    const tabs   = { users: 'users-tab',   deals: 'deals-tab'   };

    Object.keys(panels).forEach((key) => {
      const panel = document.getElementById(panels[key]);
      const btn   = document.getElementById(tabs[key]);
      if (!panel || !btn) return;

      if (key === tab) {
        panel.style.display = 'block';
        btn.classList.add('active');
      } else {
        panel.style.display = 'none';
        btn.classList.remove('active');
      }
    });
  };

  /* ══════════════════════════════════════════════
     J. CONFIRM ACTIONS — تأكيد العمليات الخطرة
  ══════════════════════════════════════════════ */
  (function initConfirmActions() {
    document.querySelectorAll('[data-confirm]').forEach((el) => {
      el.addEventListener('click', function (e) {
        const msg = this.dataset.confirm || 'هل أنت متأكد؟';
        if (!confirm(msg)) {
          e.preventDefault();
          e.stopPropagation();
        }
      });
    });
  })();

  /* ══════════════════════════════════════════════
     K. DEAL DETAIL — نظام التعليقات
  ══════════════════════════════════════════════ */
  (function initCommentReply() {
    const replyInput = document.querySelector('[name="parent_id"]');
    const commentTextarea = document.querySelector('[name="comment_text"]');

    window.replyTo = function (id, username) {
      if (replyInput) replyInput.value = id;
      if (commentTextarea) {
        commentTextarea.placeholder = `الرد على ${username}...`;
        commentTextarea.focus();
        // تمرير للنموذج
        commentTextarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    };

    window.cancelReply = function () {
      if (replyInput) replyInput.value = '';
      if (commentTextarea) commentTextarea.placeholder = 'أكتب تعليقك هنا...';
    };
  })();

  /* ══════════════════════════════════════════════
     L. IMAGE UPLOAD PREVIEW
  ══════════════════════════════════════════════ */
  (function initImagePreviews() {
    // معاينة صور إنشاء الصفقة
    const imgInputs = document.querySelectorAll('input[type="file"][accept*="image"]');
    imgInputs.forEach((input) => {
      if (input.id === 'avatarInput') return; // سيُعالَج منفصلاً

      input.addEventListener('change', function () {
        const preview = document.getElementById(this.dataset.preview || 'imgPreview');
        if (!preview) return;
        preview.innerHTML = '';
        [...this.files].forEach((file) => {
          if (!file.type.startsWith('image/')) return;
          const reader = new FileReader();
          reader.onload = (e) => {
            const wrap = document.createElement('div');
            wrap.style.cssText = 'position:relative;display:inline-block;';
            wrap.innerHTML = `
              <img src="${e.target.result}" style="width:90px;height:90px;object-fit:cover;border-radius:10px;border:2px solid var(--gold);">
              <div style="position:absolute;top:4px;left:4px;width:20px;height:20px;background:var(--success);border-radius:50%;display:flex;align-items:center;justify-content:center;">
                <i class="fas fa-check" style="color:white;font-size:9px;"></i>
              </div>
            `;
            preview.appendChild(wrap);
          };
          reader.readAsDataURL(file);
        });
      });
    });

    // معاينة صورة الملف الشخصي
    const avatarInput = document.getElementById('avatarInput');
    if (avatarInput) {
      avatarInput.addEventListener('change', function () {
        const file = this.files[0];
        if (!file?.type.startsWith('image/')) return;
        const reader = new FileReader();
        reader.onload = (e) => {
          const preview = document.getElementById('avatarPreview');
          if (preview) {
            preview.style.opacity = '0';
            setTimeout(() => {
              preview.src = e.target.result;
              preview.style.opacity = '1';
              preview.style.transition = 'opacity .3s ease';
            }, 150);
          }
        };
        reader.readAsDataURL(file);
      });
    }
  })();

  /* ══════════════════════════════════════════════
     M. SMOOTH SCROLL FOR ANCHORS
  ══════════════════════════════════════════════ */
  (function initSmoothAnchors() {
    document.querySelectorAll('a[href^="#"]:not([href="#"])').forEach((link) => {
      link.addEventListener('click', function (e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  })();

  /* ══════════════════════════════════════════════
     N. COPY TO CLIPBOARD HELPER
  ══════════════════════════════════════════════ */
  if (window.SE) {
    SE.copy = async function (text, successMsg = 'تم النسخ!') {
      try {
        await navigator.clipboard.writeText(text);
        if (SE.toast) SE.toast(successMsg, 'success', 2500);
      } catch {
        // Fallback
        const el = document.createElement('textarea');
        el.value = text;
        el.style.cssText = 'position:fixed;opacity:0;';
        document.body.appendChild(el);
        el.select();
        document.execCommand('copy');
        el.remove();
        if (SE.toast) SE.toast(successMsg, 'success', 2500);
      }
    };
  }

  /* ══════════════════════════════════════════════
     O. ANIMATED NUMBERS ON SCROLL
  ══════════════════════════════════════════════ */
  (function initCounters() {
    const counters = document.querySelectorAll(
      '.se-dr-stat-num, .se-hero-stat-num, .se-welcome-stat .num, .stat-box .stat-value'
    );
    if (!counters.length) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const raw = el.textContent.replace(/[^0-9.]/g, '');
        const target = parseFloat(raw);
        if (isNaN(target) || target <= 0) return;

        let start = 0;
        const duration = 800;
        const startTime = performance.now();

        function tick(now) {
          const progress = Math.min((now - startTime) / duration, 1);
          const eased = 1 - Math.pow(1 - progress, 3);
          const current = Math.round(target * eased);
          el.textContent = current.toLocaleString('ar');
          if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
        observer.unobserve(el);
      });
    }, { threshold: 0.6 });

    counters.forEach((el) => observer.observe(el));
  })();

  /* ══════════════════════════════════════════════
     P. ROOM CODE — UPPERCASE INPUT
  ══════════════════════════════════════════════ */
  (function initRoomCode() {
    const codeInput = document.querySelector('[name="code"]');
    if (!codeInput) return;
    codeInput.addEventListener('input', function () {
      const pos = this.selectionStart;
      this.value = this.value.toUpperCase();
      this.setSelectionRange(pos, pos);
    });
  })();

  /* ══════════════════════════════════════════════
     Q. NOTIFICATION AUTO-POLL
  ══════════════════════════════════════════════ */
  (function initNotifPoll() {
    const badge = document.getElementById('notif-badge');
    if (!badge || !window.NOTIF_POLL_URL) return;

    setInterval(async () => {
      try {
        const res = await fetch(window.NOTIF_POLL_URL, {
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!res.ok) return;
        const data = await res.json();
        const unreadCount = Number(data.unread_count ?? data.count ?? 0);
        if (unreadCount > 0) {
          badge.textContent = unreadCount;
          badge.style.display = 'inline-flex';
        } else {
          badge.style.display = 'none';
        }
      } catch { /* تجاهل */ }
    }, 30000);
  })();

  /* ══════════════════════════════════════════════
     R. FORM FLOATING LABELS ENHANCEMENT
  ══════════════════════════════════════════════ */
  (function initFormEnhancements() {
    // إضافة border validation ديناميكي
    document.querySelectorAll('.form-control, .se-input').forEach((input) => {
      input.addEventListener('blur', function () {
        if (this.required && !this.value.trim()) {
          this.style.borderColor = 'var(--danger)';
        } else if (this.value) {
          this.style.borderColor = 'var(--success)';
        }
      });
      input.addEventListener('focus', function () {
        this.style.borderColor = 'var(--gold)';
      });
    });
  })();

  /* ══════════════════════════════════════════════
     S. PAYMENT BUTTON LOADING STATE
  ══════════════════════════════════════════════ */
  (function initPaymentBtn() {
    const payBtn = document.getElementById('payBtn');
    if (!payBtn) return;

    payBtn.closest('form')?.addEventListener('submit', function () {
      payBtn.style.opacity = '0.8';
      payBtn.style.pointerEvents = 'none';
      payBtn.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" style="width:16px;height:16px;"></span>
        جارٍ معالجة الدفع...
      `;
    });
  })();

  /* ══════════════════════════════════════════════
     T. INTERSECTION OBSERVER FOR ANIMATIONS
  ══════════════════════════════════════════════ */
  (function initScrollAnimations() {
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const compactMotion = window.matchMedia?.('(max-width: 768px), (pointer: coarse)').matches;
    if (reduceMotion || compactMotion) return;

    const elements = document.querySelectorAll(
      '.se-dr-stat, .se-deal-card, .se-listing-card, .stat-box, .friend-card, .comment-item'
    );
    if (!elements.length || !('IntersectionObserver' in window)) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.style.animation = 'fadeInUp .45s ease both';
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    elements.forEach((el) => {
      el.style.opacity = '0';
      // تأخير بسيط حتى لا يطمس الـ CSS animations
      setTimeout(() => observer.observe(el), 100);
    });
  })();

})();
