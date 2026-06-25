(function () {
  var root = document.querySelector("[data-private-chat]");
  if (!root) return;

  var friendId = root.dataset.friendId;
  var pollUrl = root.dataset.pollUrl;
  var wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
  var wsUrl = root.dataset.wsUrl || (wsScheme + "://" + window.location.host + "/ws/chat/" + friendId + "/");
  var labels = {
    attachedFile: root.dataset.attachedFile || "Attached file",
    clickDownload: root.dataset.clickDownload || "Click to download",
    sendError: root.dataset.sendError || "Could not send the message. Try again.",
    you: root.dataset.you || "You",
  };

  var chatBox = document.getElementById("chatBox");
  var scrollBtn = document.getElementById("scrollBottomBtn");
  var msgInput = document.getElementById("msgInput");
  var msgForm = document.getElementById("msgForm");
  var fileInput = document.getElementById("fileInput");
  var pollTimeoutId;
  var privateChatWS;
  var reconnectTimer;

  window.filterPrivateChats = function (q) {
    var value = String(q || "").toLowerCase();
    document.querySelectorAll(".se-chat-side-item").forEach(function (item) {
      item.style.display = item.dataset.name.includes(value) ? "grid" : "none";
    });
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char];
    });
  }

  function setLatestScroll() {
    if (chatBox) chatBox.scrollTop = chatBox.scrollHeight;
  }

  function isNearBottom() {
    if (!chatBox) return true;
    return chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 180;
  }

  function smartScroll() {
    if (isNearBottom()) setLatestScroll();
  }

  function checkScrollPosition() {
    if (!chatBox || !scrollBtn) return;
    scrollBtn.classList.toggle("visible", !isNearBottom());
  }

  function nextPollDelay() {
    if (document.hidden) return 30000;
    if (window.matchMedia("(max-width: 768px)").matches) return 18000;
    return 12000;
  }

  function schedulePoll(delay) {
    window.clearTimeout(pollTimeoutId);
    pollTimeoutId = window.setTimeout(pollPrivateMessages, delay || nextPollDelay());
  }

  var lastMessageId = 0;
  var initialMessages = chatBox ? chatBox.querySelectorAll("[data-msg-id]") : [];
  if (initialMessages.length) {
    lastMessageId = Number(initialMessages[initialMessages.length - 1].dataset.msgId || 0);
  }

  function buildMessage(message) {
    var row = document.createElement("div");
    row.className = "se-msg-row " + (message.is_me ? "se-msg-mine" : "se-msg-other");
    row.dataset.msgId = message.id;

    var safeText = escapeHtml(message.text);
    var safeFileUrl = escapeHtml(message.file_url);
    var safeAvatar = escapeHtml(message.avatar);
    var safeUsername = escapeHtml(message.username);
    var safeTime = escapeHtml(message.time);

    var bubble = message.text
      ? '<div class="se-msg-bubble ' + (message.is_me ? "se-bubble-mine" : "se-bubble-other") + '">' + safeText + "</div>"
      : "";
    var file = message.file_url
      ? '<a href="' + safeFileUrl + '" target="_blank" rel="noopener noreferrer" class="se-msg-file ' + (message.is_me ? "se-file-mine" : "") + '">' +
        '<div class="se-msg-file-icon"><i class="fas fa-file-download"></i></div>' +
        "<div><div class=\"se-msg-file-name\">" + escapeHtml(labels.attachedFile) + "</div>" +
        "<div class=\"se-msg-file-sub\">" + escapeHtml(labels.clickDownload) + "</div></div>" +
        '<i class="fas fa-external-link-alt se-msg-file-arrow"></i></a>'
      : "";
    var check = message.is_me ? '<i class="fas fa-check-double se-msg-check"></i>' : "";

    row.innerHTML =
      (message.is_me ? "" : '<img src="' + safeAvatar + '" alt="' + safeUsername + '" class="se-msg-avatar">') +
      '<div class="se-msg-content">' +
      (message.is_me ? "" : '<div class="se-msg-sender-name">' + safeUsername + (message.verification_badge || "") + "</div>") +
      bubble +
      file +
      '<div class="se-msg-time ' + (message.is_me ? "se-time-mine" : "") + '">' + safeTime + check + "</div>" +
      "</div>" +
      (message.is_me ? '<img src="' + safeAvatar + '" alt="' + escapeHtml(labels.you) + '" class="se-msg-avatar">' : "");

    return row;
  }

  function appendMessage(message) {
    if (!chatBox || !message || !message.id) return;
    if (chatBox.querySelector('[data-msg-id="' + message.id + '"]')) return;
    chatBox.querySelector("[data-empty-chat]")?.remove();
    chatBox.appendChild(buildMessage(message));
    lastMessageId = Math.max(lastMessageId, Number(message.id));
    smartScroll();
  }

  function showFilePreview() {
    var preview = document.getElementById("filePreview");
    var nameEl = document.getElementById("fileNameText");
    if (!preview || !nameEl || !fileInput) return;
    var file = fileInput.files && fileInput.files[0];
    preview.hidden = !file;
    if (file) nameEl.textContent = file.name;
  }

  window.clearFile = function () {
    var preview = document.getElementById("filePreview");
    var nameEl = document.getElementById("fileNameText");
    if (fileInput) fileInput.value = "";
    if (preview) preview.hidden = true;
    if (nameEl) nameEl.textContent = "-";
  };

  function sendMessage(event) {
    event.preventDefault();
    if (!msgInput || !msgForm || !fileInput) return;
    var hasFile = fileInput.files.length > 0;
    if (!msgInput.value.trim() && !hasFile) return;

    var button = document.getElementById("sendBtn");
    if (button) {
      button.disabled = true;
      button.classList.add("is-loading");
    }

    fetch(window.location.href, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      body: new FormData(msgForm),
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (data.status !== "ok") return;
        appendMessage(data);
        setLatestScroll();
        msgInput.value = "";
        window.clearFile();
        window.setTimeout(function () { msgInput.focus({ preventScroll: true }); }, 0);
      })
      .catch(function () {
        if (window.SE && window.SE.toast) window.SE.toast(labels.sendError, "error");
      })
      .finally(function () {
        if (button) {
          button.disabled = false;
          button.classList.remove("is-loading");
        }
      });
  }

  function pollPrivateMessages() {
    if (!chatBox || navigator.onLine === false || document.hidden) {
      schedulePoll();
      return;
    }
    if (privateChatWS && privateChatWS.readyState === WebSocket.OPEN) {
      schedulePoll();
      return;
    }
    fetch(pollUrl + "?after=" + lastMessageId, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (response) {
        if (!response.ok) throw new Error("poll_failed");
        return response.json();
      })
      .then(function (data) {
        (data.messages || []).forEach(appendMessage);
      })
      .catch(function () {});
    schedulePoll();
  }

  function connectWebSocket() {
    if (!("WebSocket" in window)) {
      schedulePoll(2500);
      return;
    }
    try {
      privateChatWS = new WebSocket(wsUrl);
    } catch (error) {
      schedulePoll(2500);
      return;
    }
    privateChatWS.onopen = function () { window.clearTimeout(reconnectTimer); };
    privateChatWS.onmessage = function (event) {
      var message = JSON.parse(event.data);
      if (message.type === "chat_message") appendMessage(message);
    };
    privateChatWS.onclose = function () {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connectWebSocket, document.hidden ? 12000 : 5000);
      schedulePoll(2500);
    };
  }

  function currentViewportHeight() {
    if (!window.visualViewport) return window.innerHeight;
    return window.visualViewport.height + window.visualViewport.offsetTop;
  }

  function resizeChatBox() {
    var wrapper = document.querySelector(".se-chat-wrapper");
    var header = document.querySelector(".se-chat-header");
    var footer = document.querySelector(".se-chat-footer");
    if (!wrapper || !chatBox || !header || !footer) return;
    var layout = document.querySelector(".se-chat-layout");
    var layoutHeight = layout && window.innerWidth > 900 ? layout.clientHeight : 0;
    var wrapperTop = Math.max(wrapper.getBoundingClientRect().top, 0);
    var wrapperHeight = layoutHeight || Math.max(currentViewportHeight() - wrapperTop - 18, window.innerWidth <= 768 ? 360 : 560);
    var bodyHeight = Math.max(wrapperHeight - header.offsetHeight - footer.offsetHeight, window.innerWidth <= 768 ? 220 : 300);
    wrapper.style.height = wrapperHeight + "px";
    chatBox.style.height = bodyHeight + "px";
  }

  fileInput?.addEventListener("change", showFilePreview);
  document.querySelector("[data-clear-file]")?.addEventListener("click", window.clearFile);
  msgForm?.addEventListener("submit", sendMessage);
  scrollBtn?.addEventListener("click", setLatestScroll);
  chatBox?.addEventListener("scroll", checkScrollPosition);
  msgInput?.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (msgInput.value.trim() || (fileInput && fileInput.files.length > 0)) msgForm?.requestSubmit();
    }
  });
  msgInput?.addEventListener("focus", function () {
    window.setTimeout(function () {
      resizeChatBox();
      smartScroll();
    }, 160);
  });
  window.addEventListener("resize", resizeChatBox);
  window.visualViewport?.addEventListener("resize", resizeChatBox);
  window.addEventListener("beforeunload", function () {
    window.clearTimeout(pollTimeoutId);
    window.clearTimeout(reconnectTimer);
    if (privateChatWS) privateChatWS.close();
  });

  resizeChatBox();
  setLatestScroll();
  connectWebSocket();
  schedulePoll();
})();
