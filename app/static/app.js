/**
 * PyCraft Chat & Workspace Application
 * Handles chat messaging, multi-turn history, DOM updates, loading states,
 * error handling, and the interactive workspace file inspector panel.
 */

document.addEventListener("DOMContentLoaded", () => {
  // Chat Elements
  const chatForm = document.getElementById("chat-form");
  const messageInput = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const emptyState = document.getElementById("empty-state");
  const messagesContainer = document.getElementById("messages-container");
  const messagesList = document.getElementById("messages-list");
  const errorBanner = document.getElementById("error-banner");
  const errorBannerText = document.getElementById("error-banner-text");
  const dismissErrorBtn = document.getElementById("dismiss-error-btn");
  const newChatBtn = document.getElementById("new-chat-btn");
  const suggestionCards = document.querySelectorAll(".suggestion-card");

  // Workspace Panel Elements
  const workspaceToggleBtn = document.getElementById("workspace-toggle-btn");
  const workspaceBadge = document.getElementById("workspace-badge");
  const workspacePanel = document.getElementById("workspace-panel");
  const workspaceCloseBtn = document.getElementById("workspace-close-btn");
  const workspaceRefreshBtn = document.getElementById("workspace-refresh-btn");
  const workspaceBackdrop = document.getElementById("workspace-backdrop");
  const workspaceLoading = document.getElementById("workspace-loading");
  const workspaceError = document.getElementById("workspace-error");
  const workspaceErrorText = document.getElementById("workspace-error-text");
  const workspaceRetryBtn = document.getElementById("workspace-retry-btn");
  const workspaceListView = document.getElementById("workspace-list-view");
  const workspaceFileList = document.getElementById("workspace-file-list");
  const workspaceEmpty = document.getElementById("workspace-empty");

  // Workspace Viewer Elements
  const workspaceViewer = document.getElementById("workspace-viewer");
  const viewerBackBtn = document.getElementById("viewer-back-btn");
  const viewerFilePath = document.getElementById("viewer-file-path");
  const viewerFileSize = document.getElementById("viewer-file-size");
  const viewerLoading = document.getElementById("viewer-loading");
  const viewerError = document.getElementById("viewer-error");
  const viewerErrorText = document.getElementById("viewer-error-text");
  const viewerCode = document.getElementById("viewer-code");

  // In-memory conversation history for this browser session
  let conversationHistory = [];
  let currentSelectedFile = null;

  // -------------------------------------------------------------------------
  // Utility Functions
  // -------------------------------------------------------------------------

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function showErrorBanner(message) {
    errorBannerText.textContent = message;
    errorBanner.hidden = false;
  }

  function hideErrorBanner() {
    errorBanner.hidden = true;
    errorBannerText.textContent = "";
  }

  if (dismissErrorBtn) {
    dismissErrorBtn.addEventListener("click", hideErrorBanner);
  }

  function formatBytes(bytes) {
    if (typeof bytes !== "number" || isNaN(bytes)) return "";
    if (bytes < 1024) return `${bytes} B`;
    const kb = (bytes / 1024).toFixed(1);
    return `${kb} KB`;
  }

  // -------------------------------------------------------------------------
  // Chat Conversation Logic
  // -------------------------------------------------------------------------

  function resetConversation() {
    conversationHistory = [];
    messagesList.innerHTML = "";
    emptyState.hidden = false;
    hideErrorBanner();
    messageInput.value = "";
    messageInput.style.height = "auto";
    messageInput.focus();
  }

  if (newChatBtn) {
    newChatBtn.addEventListener("click", resetConversation);
  }

  suggestionCards.forEach((card) => {
    card.addEventListener("click", () => {
      const prompt = card.getAttribute("data-prompt");
      if (prompt) {
        messageInput.value = prompt;
        adjustTextareaHeight();
        chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
      }
    });
  });

  function appendMessage(sender, text, isError = false) {
    if (!emptyState.hidden) {
      emptyState.hidden = true;
    }

    const messageItem = document.createElement("div");
    messageItem.className = `message message-${sender}${isError ? " message-error" : ""}`;

    const bubbleDiv = document.createElement("div");
    bubbleDiv.className = "message-bubble";
    bubbleDiv.textContent = text; // Safe text rendering

    messageItem.appendChild(bubbleDiv);
    messagesList.appendChild(messageItem);
    scrollToBottom();
  }

  function showLoadingIndicator() {
    if (!emptyState.hidden) {
      emptyState.hidden = true;
    }

    removeLoadingIndicator();

    const indicator = document.createElement("div");
    indicator.id = "active-loading-indicator";
    indicator.className = "loading-indicator";
    indicator.setAttribute("aria-live", "polite");
    indicator.setAttribute("aria-label", "Loading response");

    const dot1 = document.createElement("span");
    dot1.className = "loading-dot";
    const dot2 = document.createElement("span");
    dot2.className = "loading-dot";
    const dot3 = document.createElement("span");
    dot3.className = "loading-dot";

    indicator.appendChild(dot1);
    indicator.appendChild(dot2);
    indicator.appendChild(dot3);

    messagesList.appendChild(indicator);
    scrollToBottom();
  }

  function removeLoadingIndicator() {
    const indicator = document.getElementById("active-loading-indicator");
    if (indicator) {
      indicator.remove();
    }
  }

  function setComposerEnabled(enabled) {
    sendButton.disabled = !enabled;
    messageInput.disabled = !enabled;
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

  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const rawMessage = messageInput.value;
    const trimmedMessage = rawMessage.trim();

    if (!trimmedMessage) {
      showErrorBanner("Please enter a message before sending.");
      messageInput.focus();
      return;
    }

    hideErrorBanner();

    appendMessage("user", trimmedMessage);
    conversationHistory.push({ role: "user", content: trimmedMessage });

    messageInput.value = "";
    messageInput.style.height = "auto";

    setComposerEnabled(false);
    showLoadingIndicator();

    try {
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({
          message: trimmedMessage,
          history: conversationHistory.slice(0, -1),
        }),
      });

      removeLoadingIndicator();

      if (!response.ok) {
        let errorMessage = `Server error (${response.status})`;
        try {
          const errorData = await response.json();
          if (errorData && errorData.detail) {
            errorMessage = errorData.detail;
          }
        } catch {
          // Fallback if response isn't JSON
        }

        showErrorBanner(errorMessage);
        appendMessage("assistant", errorMessage, true);
        conversationHistory.pop();
        return;
      }

      const data = await response.json();
      if (data && typeof data.reply === "string") {
        appendMessage("assistant", data.reply);
        conversationHistory.push({ role: "model", content: data.reply });

        // Refresh workspace files after response in case files were touched
        loadWorkspaceFiles();
      } else {
        throw new Error("Received an unexpected response format from the server.");
      }
    } catch (error) {
      console.error("PyCraft request error:", error);
      removeLoadingIndicator();

      const networkMsg =
        "Unable to reach the PyCraft server. Please ensure the backend is running at http://127.0.0.1:8000.";
      showErrorBanner(networkMsg);
      appendMessage("assistant", networkMsg, true);
      conversationHistory.pop();
    } finally {
      setComposerEnabled(true);
    }
  });

  // -------------------------------------------------------------------------
  // Workspace Panel Logic
  // -------------------------------------------------------------------------

  function openWorkspace() {
    workspacePanel.hidden = false;
    // Force DOM reflow before adding transition class
    void workspacePanel.offsetWidth;
    workspacePanel.classList.add("is-open");
    workspaceBackdrop.hidden = false;
    workspaceToggleBtn.classList.add("is-active");
    workspaceToggleBtn.setAttribute("aria-expanded", "true");
    loadWorkspaceFiles();
  }

  function closeWorkspace() {
    workspacePanel.classList.remove("is-open");
    workspaceBackdrop.hidden = true;
    workspaceToggleBtn.classList.remove("is-active");
    workspaceToggleBtn.setAttribute("aria-expanded", "false");
    setTimeout(() => {
      if (!workspacePanel.classList.contains("is-open")) {
        workspacePanel.hidden = true;
      }
    }, 250);
  }

  function toggleWorkspace() {
    const isOpen = workspacePanel.classList.contains("is-open") && !workspacePanel.hidden;
    if (isOpen) {
      closeWorkspace();
    } else {
      openWorkspace();
    }
  }

  if (workspaceToggleBtn) {
    workspaceToggleBtn.addEventListener("click", toggleWorkspace);
  }

  if (workspaceCloseBtn) {
    workspaceCloseBtn.addEventListener("click", closeWorkspace);
  }

  if (workspaceBackdrop) {
    workspaceBackdrop.addEventListener("click", closeWorkspace);
  }

  if (workspaceRefreshBtn) {
    workspaceRefreshBtn.addEventListener("click", () => {
      loadWorkspaceFiles();
    });
  }

  if (workspaceRetryBtn) {
    workspaceRetryBtn.addEventListener("click", () => {
      loadWorkspaceFiles();
    });
  }

  /**
   * Load files from GET /workspace/files and populate the panel list.
   */
  async function loadWorkspaceFiles() {
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
        } catch {}
        throw new Error(errDetail);
      }

      const data = await response.json();
      const files = Array.isArray(data.files) ? data.files : [];
      const count = typeof data.count === "number" ? data.count : files.length;

      // Update badge
      if (workspaceBadge) {
        workspaceBadge.textContent = String(count);
        workspaceBadge.hidden = count === 0;
      }

      // Render file list
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
          iconSpan.className = "workspace-file-item-icon";
          iconSpan.textContent = "📄";

          const nameSpan = document.createElement("span");
          nameSpan.className = "workspace-file-item-name";
          nameSpan.textContent = filePath; // Safe text rendering

          li.appendChild(iconSpan);
          li.appendChild(nameSpan);

          li.addEventListener("click", () => {
            viewWorkspaceFile(filePath);
          });

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

  /**
   * Fetch and display the content of a specific workspace file.
   */
  async function viewWorkspaceFile(filePath) {
    currentSelectedFile = filePath;

    // Highlight selected item in list
    document.querySelectorAll(".workspace-file-item").forEach((item) => {
      const name = item.querySelector(".workspace-file-item-name");
      if (name && name.textContent === filePath) {
        item.classList.add("selected");
      } else {
        item.classList.remove("selected");
      }
    });

    // Switch view to previewer
    workspaceListView.hidden = true;
    workspaceViewer.hidden = false;

    // Reset viewer states
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
        } catch {}
        throw new Error(errDetail);
      }

      const data = await response.json();
      viewerFilePath.textContent = data.path; // Display relative path
      viewerFileSize.textContent = formatBytes(data.size);
      viewerCode.textContent = data.content; // Strictly safe DOM rendering
    } catch (err) {
      console.error("Error reading file:", err);
      viewerErrorText.textContent = err.message || "Error reading file content.";
      viewerError.hidden = false;
    } finally {
      viewerLoading.hidden = true;
    }
  }

  function backToFileList() {
    workspaceViewer.hidden = true;
    workspaceListView.hidden = false;
  }

  if (viewerBackBtn) {
    viewerBackBtn.addEventListener("click", backToFileList);
  }

  // Expose global helper for testing or programmatic refresh
  window.refreshWorkspaceFiles = loadWorkspaceFiles;
  window.viewWorkspaceFile = viewWorkspaceFile;
  window.toggleWorkspace = toggleWorkspace;

  // Initial silent load of workspace files on startup
  loadWorkspaceFiles();

  // Focus message composer on load
  messageInput.focus();
});
