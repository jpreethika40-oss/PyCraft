/**
 * PyCraft Chat Interface - Phase 1
 * Handles chat messaging, DOM updates, loading states, and error handling.
 */

document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  const messageInput = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const messagesContainer = document.getElementById("messages-container");
  const messagesList = document.getElementById("messages-list");
  const loadingIndicator = document.getElementById("loading-indicator");
  const errorBanner = document.getElementById("error-banner");
  const errorBannerText = document.getElementById("error-banner-text");
  const dismissErrorBtn = document.getElementById("dismiss-error-btn");

  /**
   * Scroll chat container smoothly to bottom.
   */
  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  /**
   * Show an error banner at top of chat.
   * @param {string} message - Error description
   */
  function showErrorBanner(message) {
    errorBannerText.textContent = message;
    errorBanner.hidden = false;
  }

  /**
   * Hide the error banner.
   */
  function hideErrorBanner() {
    errorBanner.hidden = true;
    errorBannerText.textContent = "";
  }

  dismissErrorBtn.addEventListener("click", hideErrorBanner);

  /**
   * Safely append a message bubble to the messages list using textContent.
   * NEVER inserts user input or agent responses as raw HTML to prevent XSS.
   *
   * @param {"user" | "agent"} sender - Who sent the message
   * @param {string} text - Message text
   * @param {boolean} [isError=false] - Whether this is an error bubble
   */
  function appendMessage(sender, text, isError = false) {
    const messageItem = document.createElement("div");
    messageItem.className = `message message-${sender}${isError ? " message-error" : ""}`;

    // Metadata header
    const metaDiv = document.createElement("div");
    metaDiv.className = "message-meta";

    const senderSpan = document.createElement("span");
    senderSpan.className = "sender-name";
    senderSpan.textContent = sender === "user" ? "You" : "PyCraft";

    const tagSpan = document.createElement("span");
    tagSpan.className = "message-tag";
    tagSpan.textContent = isError ? "Error" : (sender === "user" ? "User" : "Assistant");

    metaDiv.appendChild(senderSpan);
    metaDiv.appendChild(tagSpan);

    // Message body (textContent guarantees raw text safety)
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    contentDiv.textContent = text;

    messageItem.appendChild(metaDiv);
    messageItem.appendChild(contentDiv);

    messagesList.appendChild(messageItem);
    scrollToBottom();
  }

  /**
   * Set loading UI state while awaiting backend response.
   * @param {boolean} isLoading
   */
  function setLoadingState(isLoading) {
    if (isLoading) {
      loadingIndicator.hidden = false;
      loadingIndicator.removeAttribute("aria-hidden");
      sendButton.disabled = true;
      messageInput.disabled = true;
      scrollToBottom();
    } else {
      loadingIndicator.hidden = true;
      loadingIndicator.setAttribute("aria-hidden", "true");
      sendButton.disabled = false;
      messageInput.disabled = false;
      messageInput.focus();
    }
  }

  /**
   * Auto-adjust textarea height based on content.
   */
  function adjustTextareaHeight() {
    messageInput.style.height = "auto";
    const newHeight = Math.min(messageInput.scrollHeight, 140);
    messageInput.style.height = `${newHeight}px`;
  }

  messageInput.addEventListener("input", adjustTextareaHeight);

  // Send message on Enter key (without Shift key)
  messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });

  /**
   * Form submission handler.
   */
  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const rawMessage = messageInput.value;
    const trimmedMessage = rawMessage.trim();

    // Client-side validation: reject empty or whitespace-only messages
    if (!trimmedMessage) {
      showErrorBanner("Cannot send an empty message. Please enter some text.");
      messageInput.focus();
      return;
    }

    hideErrorBanner();

    // 1. Render user message safely
    appendMessage("user", trimmedMessage);

    // 2. Clear input field and reset height
    messageInput.value = "";
    messageInput.style.height = "auto";

    // 3. Set loading state
    setLoadingState(true);

    try {
      // 4. Send request to FastAPI backend
      const response = await fetch("/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ message: trimmedMessage }),
      });

      // 5. Handle HTTP errors
      if (!response.ok) {
        let errorMessage = `Server returned status ${response.status} (${response.statusText})`;
        try {
          const errorData = await response.json();
          if (errorData && errorData.detail) {
            errorMessage = errorData.detail;
          }
        } catch {
          // If response body is not JSON, use default status text
        }

        showErrorBanner(`Backend Error (${response.status}): ${errorMessage}`);
        appendMessage("agent", `⚠️ Error (${response.status}): ${errorMessage}`, true);
        return;
      }

      // 6. Handle successful response
      const data = await response.json();
      if (data && typeof data.reply === "string") {
        appendMessage("agent", data.reply);
      } else {
        throw new Error("Received an unexpected response format from backend.");
      }
    } catch (error) {
      // 7. Handle network failure or offline backend
      console.error("PyCraft chat network error:", error);
      const networkMessage =
        "Unable to reach the PyCraft backend. Please verify that the server is running on http://127.0.0.1:8000.";
      showErrorBanner(networkMessage);
      appendMessage("agent", `⚠️ Connection Failure: ${networkMessage}`, true);
    } finally {
      // 8. Reset loading state
      setLoadingState(false);
    }
  });

  // Focus message input on page load
  messageInput.focus();
});
