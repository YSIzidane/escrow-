(function () {
  const page = document.body?.dataset?.page;
  if (!['deal_detail', 'escrow_room'].includes(page)) return;

  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  document.querySelectorAll('[title]').forEach((el) => {
    const title = el.getAttribute('title');
    if (!title || el.dataset.dxTooltip) return;
    el.dataset.dxTooltip = title;
    el.removeAttribute('title');
  });

  document.querySelectorAll('.dx-reveal').forEach((el, index) => {
    if (reduceMotion) return;
    el.style.animationDelay = `${Math.min(index, 6) * 55}ms`;
  });

  function closeConfirm(modal, onCancel) {
    modal?.remove();
    if (typeof onCancel === 'function') onCancel();
  }

  function premiumConfirm(message, onConfirm, onCancel) {
    const isArabic = document.documentElement.lang === 'ar' || document.documentElement.dir === 'rtl';
    const backdrop = document.createElement('div');
    backdrop.className = 'dx-confirm-backdrop';
    backdrop.setAttribute('role', 'dialog');
    backdrop.setAttribute('aria-modal', 'true');
    backdrop.innerHTML = `
      <div class="dx-confirm-modal">
        <h2>${page === 'escrow_room' ? 'Escrow confirmation' : 'Deal confirmation'}</h2>
        <p></p>
        <div class="dx-confirm-actions">
          <button class="dx-confirm-cancel" type="button">${isArabic ? 'إلغاء' : 'Cancel'}</button>
          <button class="dx-confirm-ok" type="button">${isArabic ? 'تأكيد' : 'Confirm'}</button>
        </div>
      </div>
    `;

    backdrop.querySelector('h2').textContent = isArabic ? 'تأكيد الإجراء' : (page === 'escrow_room' ? 'Escrow confirmation' : 'Deal confirmation');
    backdrop.querySelector('p').textContent = message || 'Are you sure?';
    document.body.appendChild(backdrop);

    const cancel = backdrop.querySelector('.dx-confirm-cancel');
    const ok = backdrop.querySelector('.dx-confirm-ok');
    cancel?.focus();

    cancel?.addEventListener('click', () => closeConfirm(backdrop, onCancel));
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) closeConfirm(backdrop, onCancel);
    });
    ok?.addEventListener('click', () => {
      backdrop.remove();
      if (typeof onConfirm === 'function') onConfirm();
    });
    backdrop.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeConfirm(backdrop, onCancel);
    });
  }

  window.SE = window.SE || {};
  window.SE.confirm = premiumConfirm;

  const fileInputs = [
    ['dealFileInput', '.se-deal-attach-btn'],
  ];

  fileInputs.forEach(([inputId, labelSelector]) => {
    const input = document.getElementById(inputId);
    const label = document.querySelector(labelSelector);
    if (!input || !label) return;
    input.addEventListener('change', () => {
      const fileName = input.files?.[0]?.name;
      label.classList.toggle('has-file', Boolean(fileName));
      if (fileName) label.dataset.dxTooltip = fileName;
    });
  });

  const chatBoxes = [
    document.getElementById('dealChatBox'),
    document.getElementById('chatBox'),
  ].filter(Boolean);

  chatBoxes.forEach((box) => {
    requestAnimationFrame(() => {
      box.scrollTop = box.scrollHeight;
    });
  });
})();
