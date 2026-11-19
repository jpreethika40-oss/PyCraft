/**
 * PyCraft Chat Application
 * Handles chat messaging, multi-turn history, DOM updates, loading states, and error handling.
 */

document.addEventListener("DOMContentLoaded", () => {
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

  // In-memory conversation history for this browser session
  let conversationHistory = [];

  /**
   * Scroll messages container smoothly to bottom.
   */
  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  /**
   * Show error notification banner.
   */
  function showErrorBanner(message) {
    errorBannerText.textContent = message;
    errorBanner.hidden = false;
  }

  /**
   * Hide error notification banner.
   */
  function hideErrorBanner() {
    errorBanner.hidden = true;
    errorBannerText.textContent = "";
  }

  dismissErrorBtn.addEventListener("click", hideErrorBanner);

  /**
   * Reset conversation (New Chat).
   */
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

  /**
   * Wire suggestion cards in empty state.
   */
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

  /**
   * Safely append a message bubble using textContent to prevent XSS.
   * Speakers are differentiated purely through visual layout and styling.
   *
   * @param {"user" | "assistant"} sender - Who sent the message
   * @param {string} text - Message text
   * @param {boolean} [isError=false] - Whether this is an error bubble
   */
  function appendMessage(sender, text, isError = false) {
    // Hide empty state once conversation starts
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

  /**
   * Show temporary typing indicator.
   */
  function showLoadingIndicator() {
    // Hide empty state if first message
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

  /**
   * Remove loading indicator from DOM.
   */
  function removeLoadingIndicator() {
    const indicator = document.getElementById("active-loading-indicator");
    if (indicator) {
      indicator.remove();
    }
  }

  /**
   * Toggle composer controls (disable during pending requests).
   */
  function setComposerEnabled(enabled) {
    sendButton.disabled = !enabled;
    messageInput.disabled = !enabled;
    if (enabled) {
      messageInput.focus();
    }
  }

  /**
   * Auto-adjust textarea height up to 160px.
   */
  function adjustTextareaHeight() {
    messageInput.style.height = "auto";
    const newHeight = Math.min(messageInput.scrollHeight, 160);
    messageInput.style.height = `${newHeight}px`;
  }

  messageInput.addEventListener("input", adjustTextareaHeight);

  // Send message on Enter key (Shift+Enter inserts newline)
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });

  /**
   * Main Form Submit Handler.
   */
  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const rawMessage = messageInput.value;
    const trimmedMessage = rawMessage.trim();

    // 1. Client-side input validation
    if (!trimmedMessage) {
      showErrorBanner("Please enter a message before sending.");
      messageInput.focus();
      return;
    }

    hideErrorBanner();

    // 2. Append user message to conversation list
    appendMessage("user", trimmedMessage);

    // 3. Add to local conversation history
    conversationHistory.push({ role: "user", content: trimmedMessage });

    // 4. Reset input box
    messageInput.value = "";
    messageInput.style.height = "auto";

    // 5. Show typing indicator and lock composer
    setComposerEnabled(false);
    showLoadingIndicator();

    try {
      // 6. Send request with conversation history to backend
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({
          message: trimmedMessage,
          history: conversationHistory.slice(0, -1), // Prior history excluding current message
        }),
      });

      // 7. ALWAYS remove loading indicator BEFORE displaying response or error
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
        // Remove the failed turn from history so it doesn't corrupt subsequent turns
        conversationHistory.pop();
        return;
      }

      // 8. Handle successful AI response
      const data = await response.json();
      if (data && typeof data.reply === "string") {
        appendMessage("assistant", data.reply);
        // Add assistant response to history for multi-turn follow-ups
        conversationHistory.push({ role: "model", content: data.reply });
      } else {
        throw new Error("Received an unexpected response format from the server.");
      }
    } catch (error) {
      // 9. Handle network failure or unreachable server
      console.error("PyCraft request error:", error);
      removeLoadingIndicator();

      const networkMsg =
        "Unable to reach the PyCraft server. Please ensure the backend is running at http://127.0.0.1:8000.";
      showErrorBanner(networkMsg);
      appendMessage("assistant", networkMsg, true);
      conversationHistory.pop();
    } finally {
      // 10. Re-enable composer controls and focus
      setComposerEnabled(true);
    }
  });

  // Focus message composer on load
  messageInput.focus();
});
