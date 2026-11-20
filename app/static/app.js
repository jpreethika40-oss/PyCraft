/**
 * PyCraft: Personal AI Coding Agent
 * Frontend Application Logic
 *
 * Features:
 * - Persistent saved chats in localStorage (survive refresh, switch, rename, delete with confirmation)
 * - Dark and Light themes persisted in localStorage
 * - Functional Application Menubar (File, Edit, View, Help)
 * - Collapsible sidebar (closed by default)
 * - Safe Workspace browser & file previewer with clean loading/error state isolation
 * - Multi-turn conversation awareness with Gemini agent loop & tool calling
 */

document.addEventListener("DOMContentLoaded", () => {
  // -------------------------------------------------------------------------
  // DOM Elements
  // -------------------------------------------------------------------------

  // Layout & Navigation
  const sidebarToggleBtn = document.getElementById("sidebar-toggle-btn");
  const appSidebar = document.getElementById("app-sidebar");
  const sidebarCloseBtn = document.getElementById("sidebar-close-btn");
  const sidebarBackdrop = document.getElementById("sidebar-backdrop");
  const activeChatTitleBadge = document.getElementById("active-chat-title-badge");
  const themeToggleBtn = document.getElementById("theme-toggle-btn");
  const themeIcon = document.getElementById("theme-icon");
  const headerNewChatBtn = document.getElementById("header-new-chat-btn");
  const sidebarNewChatBtn = document.getElementById("sidebar-new-chat-btn");
  const savedChatsList = document.getElementById("saved-chats-list");
  const chatsEmptyState = document.getElementById("chats-empty-state");
  const sidebarWorkspaceBtn = document.getElementById("sidebar-workspace-btn");
  const sidebarWorkspaceBadge = document.getElementById("sidebar-workspace-badge");

  // Views
  const chatView = document.getElementById("chat-view");
  const workspaceView = document.getElementById("workspace-view");

  // Chat View Elements
  const chatMain = document.getElementById("chat-main");
  const emptyState = document.getElementById("empty-state");
  const messagesList = document.getElementById("messages-list");
  const chatForm = document.getElementById("chat-form");
  const messageInput = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const errorBanner = document.getElementById("error-banner");
  const errorBannerText = document.getElementById("error-banner-text");
  const dismissErrorBtn = document.getElementById("dismiss-error-btn");

  // Workspace Elements
  const workspaceCloseBtn = document.getElementById("workspace-close-btn");
  const workspaceRefreshBtn = document.getElementById("workspace-refresh-btn");
  const workspaceCountBadge = document.getElementById("workspace-count-badge");
  const workspaceLoading = document.getElementById("workspace-loading");
  const workspaceError = document.getElementById("workspace-error");
  const workspaceErrorText = document.getElementById("workspace-error-text");
  const workspaceRetryBtn = document.getElementById("workspace-retry-btn");
  const workspaceListView = document.getElementById("workspace-list-view");
  const workspaceFileList = document.getElementById("workspace-file-list");
  const workspaceEmpty = document.getElementById("workspace-empty");
  const workspaceViewer = document.getElementById("workspace-viewer");
  const viewerBackBtn = document.getElementById("viewer-back-btn");
  const viewerCloseBtn = document.getElementById("viewer-close-btn");
  const viewerFilePath = document.getElementById("viewer-file-path");
  const viewerFileSize = document.getElementById("viewer-file-size");
  const viewerLoading = document.getElementById("viewer-loading");
  const viewerError = document.getElementById("viewer-error");
  const viewerErrorText = document.getElementById("viewer-error-text");
  const viewerCode = document.getElementById("viewer-code");

  // Modal Elements
  const appModal = document.getElementById("app-modal");
  const modalTitle = document.getElementById("modal-title");
  const modalBody = document.getElementById("modal-body");
  const modalFooter = document.getElementById("modal-footer");
  const modalCloseBtn = document.getElementById("modal-close-btn");
  const modalCancelBtn = document.getElementById("modal-cancel-btn");
  const modalConfirmBtn = document.getElementById("modal-confirm-btn");

  // Menu Dropdown Triggers
  const menuTriggers = [
    { trigger: document.getElementById("menu-file-trigger"), dropdown: document.getElementById("menu-file-dropdown") },
    { trigger: document.getElementById("menu-edit-trigger"), dropdown: document.getElementById("menu-edit-dropdown") },
    { trigger: document.getElementById("menu-view-trigger"), dropdown: document.getElementById("menu-view-dropdown") },
    { trigger: document.getElementById("menu-help-trigger"), dropdown: document.getElementById("menu-help-dropdown") },
  ];

  // Menu Action Buttons
  const actionFileNewChat = document.getElementById("action-file-new-chat");
  const actionFileOpenWorkspace = document.getElementById("action-file-open-workspace");
  const actionEditCopyResponse = document.getElementById("action-edit-copy-response");
  const actionEditClearChat = document.getElementById("action-edit-clear-chat");
  const actionViewToggleSidebar = document.getElementById("action-view-toggle-sidebar");
  const actionViewShowWorkspace = document.getElementById("action-view-show-workspace");
  const actionViewDarkTheme = document.getElementById("action-view-dark-theme");
  const actionViewLightTheme = document.getElementById("action-view-light-theme");
  const actionHelpHowTo = document.getElementById("action-help-how-to");
  const actionHelpAbout = document.getElementById("action-help-about");

  // -------------------------------------------------------------------------
  // Application State
  // -------------------------------------------------------------------------
  let activeChatId = null;
  let savedChats = [];
  let currentTheme = "dark";
  let currentSelectedFile = null;
  let isSendingMessage = false;

  const STORAGE_KEYS = {
    THEME: "pycraft_theme",
    CHATS: "pycraft_saved_chats",
    ACTIVE_CHAT: "pycraft_active_chat_id",
  };

  // -------------------------------------------------------------------------
  // Theme Management
  // -------------------------------------------------------------------------

  function initTheme() {
    try {
      const storedTheme = localStorage.getItem(STORAGE_KEYS.THEME);
      if (storedTheme === "light" || storedTheme === "dark") {
        currentTheme = storedTheme;
      } else {
        currentTheme = "dark";
      }
    } catch {
      currentTheme = "dark";
    }
    applyTheme(currentTheme);
  }

  function applyTheme(theme) {
    currentTheme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    if (themeIcon) {
      themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
    }
    try {
      localStorage.setItem(STORAGE_KEYS.THEME, theme);
    } catch (e) {
      console.warn("Could not save theme to localStorage:", e);
    }
  }

  function toggleTheme() {
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", toggleTheme);
  }

  // -------------------------------------------------------------------------
  // Saved Chats Management (localStorage)
  // -------------------------------------------------------------------------

  function loadSavedChatsFromStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEYS.CHATS);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          savedChats = parsed.filter(
            (c) => c && typeof c.id === "string" && Array.isArray(c.messages)
          );
        }
      }
    } catch (err) {
      console.error("Failed to parse saved chats from storage:", err);
      savedChats = [];
    }

    // Try restoring active chat ID or create a fresh one if empty
    try {
      const storedActiveId = localStorage.getItem(STORAGE_KEYS.ACTIVE_CHAT);
      if (storedActiveId && savedChats.some((c) => c.id === storedActiveId)) {
        activeChatId = storedActiveId;
      }
    } catch { }

    if (!activeChatId || !savedChats.some((c) => c.id === activeChatId)) {
      if (savedChats.length > 0) {
        activeChatId = savedChats[0].id;
      } else {
        createNewChat();
        return; // createNewChat handles render
      }
    }

    renderSavedChatsList();
    renderActiveChatMessages();
  }

  function saveChatsToStorage() {
    try {
      localStorage.setItem(STORAGE_KEYS.CHATS, JSON.stringify(savedChats));
      if (activeChatId) {
        localStorage.setItem(STORAGE_KEYS.ACTIVE_CHAT, activeChatId);
      }
    } catch (err) {
      console.warn("Failed to persist chats to localStorage:", err);
    }
  }

  function getActiveChat() {
    return savedChats.find((c) => c.id === activeChatId) || null;
  }

  function createNewChat() {
    const newId = "chat_" + Date.now() + "_" + Math.random().toString(36).substring(2, 7);
    const newChat = {
      id: newId,
      title: "New Chat",
      createdAt: Date.now(),
      messages: [],
    };
    savedChats.unshift(newChat);
    activeChatId = newId;
    saveChatsToStorage();

    // Show Chat view in case workspace was open
    showChatView();

    renderSavedChatsList();
    renderActiveChatMessages();

    // On mobile, close sidebar after starting a chat
    if (window.innerWidth <= 768) {
      closeSidebar();
    }

    messageInput.focus();
  }

  function switchChat(chatId) {
    if (chatId === activeChatId) {
      showChatView();
      if (window.innerWidth <= 768) closeSidebar();
      return;
    }

    activeChatId = chatId;
    saveChatsToStorage();

    showChatView();
    renderSavedChatsList();
    renderActiveChatMessages();

    if (window.innerWidth <= 768) {
      closeSidebar();
    }
  }

  function renameChatPrompt(chatId) {
    const chat = savedChats.find((c) => c.id === chatId);
    if (!chat) return;

    showModal({
      title: "Rename Chat",
      bodyHtml: `
        <div style="display: flex; flex-direction: column; gap: 8px;">
          <label for="rename-input" style="font-size: 0.85rem; color: var(--text-muted);">Enter new title for this conversation:</label>
          <input type="text" id="rename-input" value="${escapeHtml(chat.title)}" style="padding: 8px; border-radius: 6px; border: 1px solid var(--border-subtle); background: var(--bg-surface-elevated); color: var(--text-main); font-size: 0.9rem;" maxlength="50" />
        </div>
      `,
      confirmText: "Rename",
      confirmVariant: "primary",
      onConfirm: () => {
        const input = document.getElementById("rename-input");
        if (input) {
          const newTitle = input.value.trim();
          if (newTitle) {
            chat.title = newTitle;
            saveChatsToStorage();
            renderSavedChatsList();
            updateActiveChatTitleBadge();
          }
        }
      },
    });

    // Auto focus the input after modal renders
    setTimeout(() => {
      const input = document.getElementById("rename-input");
      if (input) {
        input.focus();
        input.select();
      }
    }, 50);
  }

  function deleteChatPrompt(chatId) {
    const chat = savedChats.find((c) => c.id === chatId);
    if (!chat) return;

    showModal({
      title: "Delete Conversation?",
      bodyHtml: `<p>Are you sure you want to delete <strong>${escapeHtml(chat.title)}</strong>? This action cannot be undone.</p>`,
      confirmText: "Delete",
      confirmVariant: "danger",
      onConfirm: () => {
        savedChats = savedChats.filter((c) => c.id !== chatId);
        if (activeChatId === chatId) {
          if (savedChats.length > 0) {
            activeChatId = savedChats[0].id;
          } else {
            createNewChat();
            return;
          }
        }
        saveChatsToStorage();
        renderSavedChatsList();
        renderActiveChatMessages();
      },
    });
  }

  function clearCurrentChatPrompt() {
    const activeChat = getActiveChat();
    if (!activeChat || activeChat.messages.length === 0) return;

    showModal({
      title: "Clear Current Chat?",
      bodyHtml: `<p>Clear all messages in <strong>${escapeHtml(activeChat.title)}</strong>? Conversation history for this chat will be reset.</p>`,
      confirmText: "Clear Messages",
      confirmVariant: "danger",
      onConfirm: () => {
        activeChat.messages = [];
        saveChatsToStorage();
        renderActiveChatMessages();
      },
    });
  }

  function updateActiveChatTitleBadge() {
    const activeChat = getActiveChat();
    const title = activeChat ? activeChat.title : "PyCraft";
    if (activeChatTitleBadge) {
      activeChatTitleBadge.textContent = title;
    }
  }

  function renderSavedChatsList() {
    if (!savedChatsList) return;
    savedChatsList.innerHTML = "";

    if (savedChats.length === 0) {
      if (chatsEmptyState) chatsEmptyState.hidden = false;
      return;
    }

    if (chatsEmptyState) chatsEmptyState.hidden = true;

    savedChats.forEach((chat) => {
      const li = document.createElement("li");
      li.className = `chat-list-item${chat.id === activeChatId ? " active" : ""}`;
      li.setAttribute("role", "button");
      li.setAttribute("tabindex", "0");
      li.setAttribute("title", chat.title);

      const titleSpan = document.createElement("span");
      titleSpan.className = "chat-item-title";
      titleSpan.textContent = chat.title;

      const actionsDiv = document.createElement("div");
      actionsDiv.className = "chat-item-actions";

      // Rename button
      const renameBtn = document.createElement("button");
      renameBtn.type = "button";
      renameBtn.className = "chat-item-btn";
      renameBtn.title = "Rename chat";
      renameBtn.setAttribute("aria-label", "Rename chat");
      renameBtn.textContent = "✏️";
      renameBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        renameChatPrompt(chat.id);
      });

      // Delete button
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "chat-item-btn";
      deleteBtn.title = "Delete chat";
      deleteBtn.setAttribute("aria-label", "Delete chat");
      deleteBtn.textContent = "🗑️";
      deleteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteChatPrompt(chat.id);
      });

      actionsDiv.appendChild(renameBtn);
      actionsDiv.appendChild(deleteBtn);

      li.appendChild(titleSpan);
      li.appendChild(actionsDiv);

      li.addEventListener("click", () => switchChat(chat.id));
      li.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          switchChat(chat.id);
        }
      });

      savedChatsList.appendChild(li);
    });

    updateActiveChatTitleBadge();
  }

  function renderActiveChatMessages() {
    const activeChat = getActiveChat();
    messagesList.innerHTML = "";

    if (!activeChat || activeChat.messages.length === 0) {
      emptyState.hidden = false;
      return;
    }

    emptyState.hidden = true;

    activeChat.messages.forEach((msg) => {
      appendMessageToDOM(msg.role, msg.content, msg.isError || false);
    });

    scrollToBottom();
  }

  function appendMessageToDOM(role, text, isError = false) {
    const messageRow = document.createElement("div");
    messageRow.className = `message-row ${role}${isError ? " error" : ""}`;

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = text; // Safe text rendering

    messageRow.appendChild(bubble);
    messagesList.appendChild(messageRow);
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      chatMain.scrollTop = chatMain.scrollHeight;
    });
  }

  // -------------------------------------------------------------------------
  // Sidebar Controls (Closed by Default)
  // -------------------------------------------------------------------------

  function openSidebar() {
    appSidebar.hidden = false;
    sidebarBackdrop.hidden = false;
    sidebarToggleBtn.setAttribute("aria-expanded", "true");
  }

  function closeSidebar() {
    appSidebar.hidden = true;
    sidebarBackdrop.hidden = true;
    sidebarToggleBtn.setAttribute("aria-expanded", "false");
  }

  function toggleSidebar() {
    if (appSidebar.hidden) {
      openSidebar();
    } else {
      closeSidebar();
    }
  }

  if (sidebarToggleBtn) sidebarToggleBtn.addEventListener("click", toggleSidebar);
  if (sidebarCloseBtn) sidebarCloseBtn.addEventListener("click", closeSidebar);
  if (sidebarBackdrop) sidebarBackdrop.addEventListener("click", closeSidebar);

  if (headerNewChatBtn) headerNewChatBtn.addEventListener("click", createNewChat);
  if (sidebarNewChatBtn) sidebarNewChatBtn.addEventListener("click", createNewChat);

  // -------------------------------------------------------------------------
  // Main View Switching: Chat vs. Workspace
  // -------------------------------------------------------------------------

  function showChatView() {
    chatView.hidden = false;
    workspaceView.hidden = true;
  }

  function showWorkspaceView() {
    chatView.hidden = true;
    workspaceView.hidden = false;
    // Load or refresh workspace files
    loadWorkspaceFiles();
    // Close sidebar on small screens
    if (window.innerWidth <= 768) {
      closeSidebar();
    }
  }

  if (sidebarWorkspaceBtn) {
    sidebarWorkspaceBtn.addEventListener("click", showWorkspaceView);
  }

  if (workspaceCloseBtn) {
    workspaceCloseBtn.addEventListener("click", showChatView);
  }

  // -------------------------------------------------------------------------
  // Menubar Actions (File, Edit, View, Help)
  // -------------------------------------------------------------------------

  let activeMenuIndex = -1;

  function closeAllDropdowns() {
    menuTriggers.forEach(({ trigger, dropdown }) => {
      if (dropdown) dropdown.hidden = true;
      if (trigger) {
        trigger.setAttribute("aria-expanded", "false");
        trigger.classList.remove("is-open");
      }
    });
    activeMenuIndex = -1;
  }

  function openMenu(index, focusFirst = false) {
    if (index < 0 || index >= menuTriggers.length) return;

    // Ensure all other menus are closed first
    closeAllDropdowns();

    const { trigger, dropdown } = menuTriggers[index];
    if (trigger && dropdown) {
      dropdown.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      trigger.classList.add("is-open");
      activeMenuIndex = index;

      if (focusFirst) {
        const firstBtn = dropdown.querySelector(".dropdown-action-btn:not([disabled])");
        if (firstBtn) firstBtn.focus();
      }
    }
  }

  function toggleMenu(index) {
    if (activeMenuIndex === index) {
      closeAllDropdowns();
    } else {
      openMenu(index);
    }
  }

  menuTriggers.forEach(({ trigger, dropdown }, index) => {
    if (!trigger || !dropdown) return;

    // Click trigger: opens or toggles menu
    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleMenu(index);
    });

    // Hover trigger: if a menu is already open, hovering switches to this menu seamlessly
    trigger.addEventListener("mouseenter", () => {
      if (activeMenuIndex !== -1 && activeMenuIndex !== index) {
        openMenu(index);
      }
    });

    // Keyboard navigation on trigger button
    trigger.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openMenu(index, true);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        const nextIndex = (index + 1) % menuTriggers.length;
        if (activeMenuIndex !== -1) {
          openMenu(nextIndex);
        }
        menuTriggers[nextIndex].trigger.focus();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        const prevIndex = (index - 1 + menuTriggers.length) % menuTriggers.length;
        if (activeMenuIndex !== -1) {
          openMenu(prevIndex);
        }
        menuTriggers[prevIndex].trigger.focus();
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeAllDropdowns();
      }
    });

    // Keyboard navigation inside dropdown menu items
    dropdown.addEventListener("keydown", (e) => {
      const items = Array.from(dropdown.querySelectorAll(".dropdown-action-btn:not([disabled])"));
      const currentIdx = items.indexOf(document.activeElement);

      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = (currentIdx + 1) % items.length;
        items[next]?.focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prev = (currentIdx - 1 + items.length) % items.length;
        items[prev]?.focus();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        const nextIndex = (index + 1) % menuTriggers.length;
        openMenu(nextIndex, true);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        const prevIndex = (index - 1 + menuTriggers.length) % menuTriggers.length;
        openMenu(prevIndex, true);
      } else if (e.key === "Escape") {
        e.preventDefault();
        closeAllDropdowns();
        trigger.focus();
      } else if (e.key === "Tab") {
        closeAllDropdowns();
      }
    });
  });

  // Clicking outside any dropdown menu closes it
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".app-menu-nav")) {
      closeAllDropdowns();
    }
  });

  // Global Escape key handling
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (activeMenuIndex !== -1) {
        const trigger = menuTriggers[activeMenuIndex]?.trigger;
        closeAllDropdowns();
        if (trigger) trigger.focus();
      } else {
        closeModal();
      }
    }
  });

  // Action: File -> New Chat
  if (actionFileNewChat) {
    actionFileNewChat.addEventListener("click", () => {
      closeAllDropdowns();
      createNewChat();
    });
  }

  // Action: File -> Open Workspace
  if (actionFileOpenWorkspace) {
    actionFileOpenWorkspace.addEventListener("click", () => {
      closeAllDropdowns();
      showWorkspaceView();
    });
  }

  // Action: Edit -> Copy Last Response
  if (actionEditCopyResponse) {
    actionEditCopyResponse.addEventListener("click", () => {
      closeAllDropdowns();
      const activeChat = getActiveChat();
      if (!activeChat) return;

      const assistantMsgs = activeChat.messages.filter((m) => m.role === "assistant");
      if (assistantMsgs.length > 0) {
        const lastResp = assistantMsgs[assistantMsgs.length - 1].content;
        navigator.clipboard.writeText(lastResp).then(() => {
          showNotification("Last response copied to clipboard!");
        }).catch(() => {
          showNotification("Could not access clipboard.");
        });
      } else {
        showNotification("No assistant response to copy.");
      }
    });
  }

  // Action: Edit -> Clear Current Chat
  if (actionEditClearChat) {
    actionEditClearChat.addEventListener("click", () => {
      closeAllDropdowns();
      clearCurrentChatPrompt();
    });
  }

  // Action: View -> Toggle Sidebar
  if (actionViewToggleSidebar) {
    actionViewToggleSidebar.addEventListener("click", () => {
      closeAllDropdowns();
      toggleSidebar();
    });
  }

  // Action: View -> Show Workspace
  if (actionViewShowWorkspace) {
    actionViewShowWorkspace.addEventListener("click", () => {
      closeAllDropdowns();
      showWorkspaceView();
    });
  }

  // Action: View -> Dark Theme
  if (actionViewDarkTheme) {
    actionViewDarkTheme.addEventListener("click", () => {
      closeAllDropdowns();
      applyTheme("dark");
    });
  }

  // Action: View -> Light Theme
  if (actionViewLightTheme) {
    actionViewLightTheme.addEventListener("click", () => {
      closeAllDropdowns();
      applyTheme("light");
    });
  }

  // Action: Help -> How to Use
  if (actionHelpHowTo) {
    actionHelpHowTo.addEventListener("click", () => {
      closeAllDropdowns();
      showModal({
        title: "How to use PyCraft",
        bodyHtml: `
          <div style="display: flex; flex-direction: column; gap: 10px;">
            <p><strong>PyCraft</strong> is your personal AI coding assistant equipped with safe workspace file tools.</p>
            <ul style="padding-left: 20px; display: flex; flex-direction: column; gap: 6px;">
              <li><strong>Chat:</strong> Ask questions, write code, or get explanations across all programming languages.</li>
              <li><strong>Workspace Tools:</strong> Ask PyCraft to inspect or create files (e.g. <em>"List my workspace files"</em> or <em>"Create palindrome.py"</em>).</li>
              <li><strong>Safety:</strong> Existing files are protected from accidental overwrite; PyCraft will ask for your confirmation before replacing any file.</li>
              <li><strong>Saved Chats:</strong> Conversations are automatically saved locally and can be reopened, renamed, or deleted from the sidebar (☰).</li>
            </ul>
          </div>
        `,
        confirmText: "Got it",
        singleButton: true,
      });
    });
  }

  // Action: Help -> About
  if (actionHelpAbout) {
    actionHelpAbout.addEventListener("click", () => {
      closeAllDropdowns();
      showModal({
        title: "About PyCraft",
        bodyHtml: `
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <p><strong>PyCraft: Your Personal AI Coding Agent</strong></p>
            <p style="color: var(--text-muted); font-size: 0.85rem;">Autonomous tool-calling, sandboxed workspace operations, and local conversation history.</p>
            <p style="font-size: 0.82rem; margin-top: 6px;">Version 0.5.0 &bull; Running on FastAPI &amp; Google Gemini</p>
          </div>
        `,
        confirmText: "Close",
        singleButton: true,
      });
    });
  }

  // -------------------------------------------------------------------------
  // Modal Dialog System
  // -------------------------------------------------------------------------

  let activeModalConfirmCallback = null;

  function showModal({
    title,
    bodyHtml,
    confirmText = "Confirm",
    cancelText = "Cancel",
    confirmVariant = "primary",
    singleButton = false,
    onConfirm = null,
  }) {
    if (!appModal) return;

    modalTitle.textContent = title;
    modalBody.innerHTML = bodyHtml;
    activeModalConfirmCallback = onConfirm;

    modalConfirmBtn.textContent = confirmText;
    modalConfirmBtn.className = `modal-btn ${confirmVariant === "danger" ? "danger-action" : "primary-btn"}`;

    if (singleButton) {
      modalCancelBtn.hidden = true;
    } else {
      modalCancelBtn.hidden = false;
      modalCancelBtn.textContent = cancelText;
    }

    appModal.hidden = false;
  }

  function closeModal() {
    if (appModal) appModal.hidden = true;
    activeModalConfirmCallback = null;
  }

  if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeModal);
  if (modalCancelBtn) modalCancelBtn.addEventListener("click", closeModal);
  if (modalConfirmBtn) {
    modalConfirmBtn.addEventListener("click", () => {
      const cb = activeModalConfirmCallback;
      closeModal();
      if (cb) cb();
    });
  }

  // -------------------------------------------------------------------------
  // Workspace File Listing & Preview (Bug Fix & State Isolation)
  // -------------------------------------------------------------------------

  async function loadWorkspaceFiles() {
    // Isolated state management: clear previous errors and show list loading
    workspaceLoading.hidden = false;
    workspaceError.hidden = true;
    workspaceEmpty.hidden = true;

    try {
      const response = await fetch("/workspace/files", {
        headers: { "Accept": "application/json" },
      });

      if (!response.ok) {
        let errDetail = `Failed to list files (${response.status})`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) errDetail = errData.detail;
        } catch { }
        throw new Error(errDetail);
      }

      const data = await response.json();
      const files = Array.isArray(data.files) ? data.files : [];
      const count = typeof data.count === "number" ? data.count : files.length;

      // Update file count badges in header and sidebar
      if (workspaceCountBadge) {
        workspaceCountBadge.textContent = `${count} ${count === 1 ? "file" : "files"}`;
      }
      if (sidebarWorkspaceBadge) {
        sidebarWorkspaceBadge.textContent = String(count);
        sidebarWorkspaceBadge.hidden = count === 0;
      }

      workspaceFileList.innerHTML = "";

      if (files.length === 0) {
        workspaceEmpty.hidden = false;
      } else {
        files.forEach((filePath) => {
          const li = document.createElement("li");
          li.className = `workspace-file-item${filePath === currentSelectedFile ? " selected" : ""}`;
          li.setAttribute("role", "button");
          li.setAttribute("tabindex", "0");
          li.setAttribute("title", `View ${filePath}`);

          const iconSpan = document.createElement("span");
          iconSpan.textContent = "📄";

          const nameSpan = document.createElement("span");
          nameSpan.className = "file-item-name";
          nameSpan.textContent = filePath; // Safe relative path rendering

          const actionSpan = document.createElement("span");
          actionSpan.className = "file-item-action";
          actionSpan.textContent = "Click to view &rarr;";

          li.appendChild(iconSpan);
          li.appendChild(nameSpan);
          li.appendChild(actionSpan);

          li.addEventListener("click", () => viewWorkspaceFile(filePath));
          li.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              viewWorkspaceFile(filePath);
            }
          });

          workspaceFileList.appendChild(li);
        });
      }
    } catch (err) {
      console.error("Workspace file list error:", err);
      workspaceErrorText.textContent = err.message || "Failed to load workspace files.";
      workspaceError.hidden = false;
    } finally {
      workspaceLoading.hidden = true;
    }
  }

  async function viewWorkspaceFile(filePath) {
    currentSelectedFile = filePath;

    // Highlight selected item in list
    document.querySelectorAll(".workspace-file-item").forEach((item) => {
      const name = item.querySelector(".file-item-name");
      if (name && name.textContent === filePath) {
        item.classList.add("selected");
      } else {
        item.classList.remove("selected");
      }
    });

    // Switch view to previewer and cleanly hide list state
    workspaceListView.hidden = true;
    workspaceViewer.hidden = false;

    // CRITICAL BUG FIX: Ensure list-level loading and error boxes are hidden while in previewer!
    workspaceLoading.hidden = true;
    workspaceError.hidden = true;

    // Reset viewer-specific states
    viewerFilePath.textContent = filePath;
    viewerFileSize.textContent = "";
    viewerCode.textContent = "";
    viewerError.hidden = true;
    viewerLoading.hidden = false;

    try {
      const response = await fetch(`/workspace/file?path=${encodeURIComponent(filePath)}`, {
        headers: { "Accept": "application/json" },
      });

      if (!response.ok) {
        let errDetail = `Could not read file (${response.status})`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) errDetail = errData.detail;
        } catch { }
        throw new Error(errDetail);
      }

      const data = await response.json();
      viewerFilePath.textContent = data.path; // Clean workspace-relative path
      viewerFileSize.textContent = formatBytes(data.size);
      viewerCode.textContent = data.content; // Safe textContent rendering
    } catch (err) {
      console.error("Error reading workspace file:", err);
      viewerErrorText.textContent = err.message || "Error reading file content.";
      viewerError.hidden = false;
    } finally {
      viewerLoading.hidden = true;
    }
  }

  function backToFileListView() {
    workspaceViewer.hidden = true;
    workspaceListView.hidden = false;

    // Clear viewer states
    viewerLoading.hidden = true;
    viewerError.hidden = true;
    viewerCode.textContent = "";
    viewerFilePath.textContent = "";
    viewerFileSize.textContent = "";
  }

  if (viewerBackBtn) viewerBackBtn.addEventListener("click", backToFileListView);
  if (viewerCloseBtn) viewerCloseBtn.addEventListener("click", showChatView);
  if (workspaceRefreshBtn) workspaceRefreshBtn.addEventListener("click", loadWorkspaceFiles);
  if (workspaceRetryBtn) workspaceRetryBtn.addEventListener("click", loadWorkspaceFiles);

  // -------------------------------------------------------------------------
  // Chat Messaging & Agent Tool Calling
  // -------------------------------------------------------------------------

  function showLoadingIndicator(activityText = "") {
    removeLoadingIndicator();

    const indicator = document.createElement("div");
    indicator.id = "active-loading-indicator";
    indicator.className = "loading-indicator";

    const dotsGroup = document.createElement("div");
    dotsGroup.className = "loading-dots-group";
    const dot1 = document.createElement("span");
    dot1.className = "typing-dot";
    const dot2 = document.createElement("span");
    dot2.className = "typing-dot";
    const dot3 = document.createElement("span");
    dot3.className = "typing-dot";
    dotsGroup.appendChild(dot1);
    dotsGroup.appendChild(dot2);
    dotsGroup.appendChild(dot3);
    indicator.appendChild(dotsGroup);

    const textSpan = document.createElement("span");
    textSpan.id = "active-activity-text";
    textSpan.className = "loading-activity-text";
    textSpan.textContent = activityText ? ` ${activityText}` : "";
    indicator.appendChild(textSpan);

    messagesList.appendChild(indicator);
    scrollToBottom();
  }

  function updateLoadingActivity(text) {
    const textSpan = document.getElementById("active-activity-text");
    if (textSpan) {
      textSpan.textContent = text ? ` ${text}` : "";
      scrollToBottom();
    }
  }

  function removeLoadingIndicator() {
    const indicator = document.getElementById("active-loading-indicator");
    if (indicator) indicator.remove();
  }

  function setComposerEnabled(enabled) {
    sendButton.disabled = !enabled;
    messageInput.disabled = !enabled;
    isSendingMessage = !enabled;
    if (enabled) {
      messageInput.focus();
    }
  }

  function adjustTextareaHeight() {
    messageInput.style.height = "auto";
    const newHeight = Math.min(messageInput.scrollHeight, 160);
    messageInput.style.height = `${newHeight}px`;
  }

  messageInput.addEventListener("input", adjustTextareaHeight);

  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });

  // Suggestion buttons click handler
  document.querySelectorAll(".suggestion-card").forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.getAttribute("data-prompt");
      if (prompt) {
        messageInput.value = prompt;
        adjustTextareaHeight();
        chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
      }
    });
  });

  // Submit Handler
  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isSendingMessage) return;

    const rawMessage = messageInput.value;
    const trimmedMessage = rawMessage.trim();

    if (!trimmedMessage) {
      showNotification("Please enter a message before sending.");
      messageInput.focus();
      return;
    }

    hideErrorBanner();

    const activeChat = getActiveChat();
    if (!activeChat) {
      createNewChat();
    }

    // Auto-generate title from first user message
    if (activeChat.messages.length === 0 && activeChat.title === "New Chat") {
      activeChat.title = trimmedMessage.slice(0, 32) + (trimmedMessage.length > 32 ? "..." : "");
      renderSavedChatsList();
    }

    // Append user message
    activeChat.messages.push({ role: "user", content: trimmedMessage });
    appendMessageToDOM("user", trimmedMessage);
    emptyState.hidden = true;
    saveChatsToStorage();

    messageInput.value = "";
    messageInput.style.height = "auto";

    setComposerEnabled(false);
    showLoadingIndicator();

    // Prepare multi-turn history strictly for current chat
    const historyPayload = activeChat.messages.slice(0, -1).map((m) => ({
      role: m.role === "user" ? "user" : "model",
      content: m.content,
    }));

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream, application/json",
        },
        body: JSON.stringify({
          message: trimmedMessage,
          history: historyPayload,
        }),
      });

      const contentType = response.headers.get("content-type") || "";

      if (contentType.includes("text/event-stream") && response.body) {
        // SSE streaming mode
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";
        let finalReply = "";
        let filesModified = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const lines = buffer.split("\n\n");
          buffer = lines.pop();

          for (const block of lines) {
            const dataMatch = block.match(/data:\s*(.+)/s);
            if (!dataMatch) continue;
            try {
              const eventData = JSON.parse(dataMatch[1].trim());
              if (eventData.type === "activity") {
                updateLoadingActivity(eventData.activity);
              } else if (eventData.type === "done") {
                finalReply = eventData.reply;
                if (eventData.files_modified) filesModified = true;
              } else if (eventData.type === "error") {
                removeLoadingIndicator();
                showNotification(eventData.detail);
                activeChat.messages.push({ role: "assistant", content: eventData.detail, isError: true });
                appendMessageToDOM("assistant", eventData.detail, true);
                saveChatsToStorage();
                return;
              }
            } catch (err) {
              console.warn("Failed to parse SSE payload:", err);
            }
          }
        }

        removeLoadingIndicator();

        if (finalReply) {
          activeChat.messages.push({ role: "assistant", content: finalReply });
          appendMessageToDOM("assistant", finalReply);
          saveChatsToStorage();

          // Refresh workspace list only if files were modified
          if (filesModified) {
            loadWorkspaceFiles();
          }
        } else {
          appendMessageToDOM("assistant", "The model completed the request without a response.");
        }
      } else {
        // Standard JSON fallback mode
        removeLoadingIndicator();

        if (!response.ok) {
          let errorMessage = `Server error (${response.status})`;
          try {
            const errorData = await response.json();
            if (errorData && errorData.detail) errorMessage = errorData.detail;
          } catch { }

          showNotification(errorMessage);
          activeChat.messages.push({ role: "assistant", content: errorMessage, isError: true });
          appendMessageToDOM("assistant", errorMessage, true);
          saveChatsToStorage();
          return;
        }

        const data = await response.json();
        if (data && typeof data.reply === "string") {
          activeChat.messages.push({ role: "assistant", content: data.reply });
          appendMessageToDOM("assistant", data.reply);
          saveChatsToStorage();

          if (data.files_modified) {
            loadWorkspaceFiles();
          }
        } else {
          throw new Error("Received an unexpected response format from the server.");
        }
      }
    } catch (error) {
      console.error("PyCraft chat request error:", error);
      removeLoadingIndicator();

      const networkMsg = "Unable to reach the PyCraft server. Please ensure the backend is running at http://127.0.0.1:8000.";
      showNotification(networkMsg);
      activeChat.messages.push({ role: "assistant", content: networkMsg, isError: true });
      appendMessageToDOM("assistant", networkMsg, true);
      saveChatsToStorage();
    } finally {
      setComposerEnabled(true);
      scrollToBottom();
    }
  });

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function showNotification(msg) {
    if (!msg || typeof msg !== "string" || !msg.trim()) {
      hideErrorBanner();
      return;
    }
    if (errorBannerText) errorBannerText.textContent = msg.trim();
    if (errorBanner) errorBanner.hidden = false;
  }

  function hideErrorBanner() {
    if (errorBanner) errorBanner.hidden = true;
    if (errorBannerText) errorBannerText.textContent = "";
  }

  if (dismissErrorBtn) {
    dismissErrorBtn.addEventListener("click", hideErrorBanner);
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // -------------------------------------------------------------------------
  // Global Test Hooks
  // -------------------------------------------------------------------------
  window.pycraft = {
    loadSavedChatsFromStorage,
    createNewChat,
    switchChat,
    renameChatPrompt,
    deleteChatPrompt,
    applyTheme,
    toggleTheme,
    openSidebar,
    closeSidebar,
    showWorkspaceView,
    showChatView,
    loadWorkspaceFiles,
    viewWorkspaceFile,
    openMenu,
    closeAllDropdowns,
    toggleMenu,
    getActiveMenuIndex: () => activeMenuIndex,
    showNotification,
    hideErrorBanner,
    getSavedChats: () => savedChats,
    getActiveChatId: () => activeChatId,
  };

  // -------------------------------------------------------------------------
  // Application Startup
  // -------------------------------------------------------------------------
  hideErrorBanner();
  initTheme();
  loadSavedChatsFromStorage();
  loadWorkspaceFiles(); // Initial silent load to populate badge
  messageInput.focus();
});
