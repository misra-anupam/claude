(() => {
  "use strict";

  const scrollArea = document.getElementById("scroll-area");
  const transcript = document.getElementById("transcript");
  const emptyState = document.getElementById("empty-state");
  const composer = document.getElementById("composer");
  const input = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const assistantTemplate = document.getElementById("assistant-message-template");
  const toolCardTemplate = document.getElementById("tool-card-template");

  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebarBackdrop = document.getElementById("sidebar-backdrop");
  const newChatButton = document.getElementById("new-chat-button");
  const conversationList = document.getElementById("conversation-list");
  const conversationListEmpty = document.getElementById("conversation-list-empty");
  const conversationSectionTemplate = document.getElementById("conversation-section-template");
  const conversationItemTemplate = document.getElementById("conversation-item-template");

  if (window.mermaid) {
    window.mermaid.initialize({ startOnLoad: false });
  }
  let mermaidCounter = 0;

  function newThreadId() {
    return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  }

  let currentThreadId = localStorage.getItem("threadId") || newThreadId();
  localStorage.setItem("threadId", currentThreadId);

  function scrollToBottom() {
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }

  function hideEmptyState() {
    emptyState.hidden = true;
  }

  function clearTranscript() {
    transcript.innerHTML = "";
    transcript.appendChild(emptyState);
    emptyState.hidden = false;
  }

  function appendUserMessage(text) {
    hideEmptyState();
    const el = document.createElement("div");
    el.className = "message user";
    el.textContent = text;
    transcript.appendChild(el);
    scrollToBottom();
  }

  function appendAssistantMessageShell() {
    hideEmptyState();
    const fragment = assistantTemplate.content.cloneNode(true);
    const el = fragment.querySelector(".message");
    transcript.appendChild(el);
    scrollToBottom();
    return {
      root: el,
      thinking: el.querySelector(".thinking"),
      thinkingBody: el.querySelector(".thinking-body"),
      toolCards: el.querySelector(".tool-cards"),
      answer: el.querySelector(".answer"),
    };
  }

  function appendErrorMessage(text) {
    hideEmptyState();
    const el = document.createElement("div");
    el.className = "message error";
    el.textContent = text;
    transcript.appendChild(el);
    scrollToBottom();
  }

  /**
   * Tool results are normally plain strings, but the chart/diagram tools
   * return a JSON-encoded object instead ({"text":..., "artifact_id":...,
   * "content_type":...} for images, {"text":..., "mermaid":...} for
   * diagrams) -- detect that shape and render specially, falling back to
   * plain text for every other tool.
   */
  function parseStructuredResult(result) {
    if (typeof result !== "string") return null;
    try {
      const parsed = JSON.parse(result);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
      return null;
    }
  }

  async function renderMermaid(code, container) {
    if (!window.mermaid) {
      container.textContent = code;
      return;
    }
    const id = `mermaid-${++mermaidCounter}`;
    try {
      const { svg } = await window.mermaid.render(id, code);
      container.innerHTML = svg;
    } catch (err) {
      container.textContent = `[diagram render failed: ${err.message}]\n${code}`;
    }
  }

  /**
   * Keyed by tool_call id, NOT a single "current tool" slot -- when the
   * model fires multiple tool calls in one turn, several cards can sit in
   * "pending" state simultaneously, each resolving independently as its own
   * tool_result event arrives.
   */
  function createToolCardTracker(container) {
    const cards = new Map();
    return {
      start(id, name, args) {
        const fragment = toolCardTemplate.content.cloneNode(true);
        const card = fragment.querySelector(".tool-card");
        card.querySelector(".tool-card-name").textContent = name;
        card.querySelector(".tool-card-args").textContent = JSON.stringify(args ?? {});
        container.appendChild(card);
        cards.set(id, card);
        scrollToBottom();
      },
      finish(id, result, error) {
        const card = cards.get(id);
        if (!card) return;
        const resultEl = card.querySelector(".tool-card-result");
        const renderEl = card.querySelector(".tool-card-render");
        const statusEl = card.querySelector(".tool-card-status");

        if (error) {
          card.classList.remove("pending");
          card.classList.add("error");
          statusEl.textContent = "Error";
          resultEl.hidden = false;
          resultEl.textContent = error;
          scrollToBottom();
          return;
        }

        card.classList.remove("pending");
        card.classList.add("done");
        statusEl.textContent = "Done";

        const structured = parseStructuredResult(result);
        if (structured && structured.artifact_id && String(structured.content_type || "").startsWith("image/")) {
          renderEl.hidden = false;
          const img = document.createElement("img");
          img.src = `/api/artifacts/${structured.artifact_id}`;
          img.alt = structured.text || "generated chart";
          img.className = "tool-artifact-image";
          renderEl.appendChild(img);
          resultEl.hidden = false;
          resultEl.textContent = structured.text || "";
        } else if (structured && structured.artifact_id) {
          // Non-image artifact (PDF, HTML, ...) -- offer a download link
          // rather than trying to render it inline in the chat transcript.
          renderEl.hidden = false;
          const link = document.createElement("a");
          link.href = `/api/artifacts/${structured.artifact_id}`;
          link.download = structured.filename || "download";
          link.className = "tool-artifact-download";
          link.textContent = `⬇ Download ${structured.filename || "file"}`;
          renderEl.appendChild(link);
          resultEl.hidden = false;
          resultEl.textContent = structured.text || "";
        } else if (structured && structured.mermaid) {
          renderEl.hidden = false;
          resultEl.hidden = false;
          resultEl.textContent = structured.text || "";
          renderMermaid(structured.mermaid, renderEl).then(scrollToBottom);
        } else {
          // MCP tool results come back as an array of content blocks
          // ([{"type":"text","text":"..."}]) rather than a plain string --
          // join the text blocks for display instead of dumping raw JSON.
          let displayText;
          if (Array.isArray(result) && result.every((b) => b && typeof b === "object" && "text" in b)) {
            displayText = result.map((b) => b.text).join("\n");
          } else if (typeof result === "string") {
            displayText = result;
          } else {
            displayText = JSON.stringify(result);
          }
          resultEl.hidden = false;
          resultEl.textContent = displayText;
        }
        scrollToBottom();
      },
    };
  }

  /**
   * Native EventSource can't POST a JSON body (GET-only, no custom body) --
   * this manually parses the text/event-stream response from fetch()'s
   * ReadableStream. SSE events are blank-line-delimited; a chunk boundary
   * can land mid-event, so only split on complete "\n\n" occurrences and
   * keep the remainder buffered for the next read.
   */
  async function streamChat(userText, handlers) {
    const resp = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: currentThreadId, message: userText }),
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`Request failed (${resp.status}): ${text || resp.statusText}`);
    }

    const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        dispatchSSEEvent(buffer.slice(0, idx), handlers);
        buffer = buffer.slice(idx + 2);
      }
    }
    if (buffer.trim()) dispatchSSEEvent(buffer, handlers);
  }

  function dispatchSSEEvent(rawEvent, handlers) {
    let eventName = "message";
    const dataLines = [];
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith(":")) continue; // keep-alive comment
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (dataLines.length === 0) return;
    let data;
    try {
      data = JSON.parse(dataLines.join("\n"));
    } catch {
      return;
    }
    const handler = handlers[eventName] ?? handlers.default;
    if (handler) handler(data);
  }

  async function sendMessage(text) {
    appendUserMessage(text);
    const shell = appendAssistantMessageShell();
    const toolCards = createToolCardTracker(shell.toolCards);
    let thinkingOpened = false;

    try {
      await streamChat(text, {
        thinking: (d) => {
          if (!thinkingOpened) {
            shell.thinking.hidden = false;
            shell.thinking.open = true;
            thinkingOpened = true;
          }
          const delta = typeof d.delta === "string" ? d.delta : JSON.stringify(d.delta);
          shell.thinkingBody.textContent += delta;
          scrollToBottom();
        },
        token: (d) => {
          shell.answer.textContent += d.delta ?? "";
          scrollToBottom();
        },
        tool_call: (d) => toolCards.start(d.id, d.name, d.args),
        tool_result: (d) => toolCards.finish(d.id, d.result, d.error),
        done: () => {
          if (thinkingOpened) shell.thinking.open = false;
        },
        error: (d) => {
          shell.answer.textContent += `\n[error: ${d.message}]`;
        },
      });
      // A title may have just been created (first message in this thread) or
      // updated_at bumped -- refresh the sidebar so it shows up/reorders.
      loadConversations();
    } catch (err) {
      appendErrorMessage(String(err.message || err));
    }
  }

  // ---------- Sidebar: conversation list, date grouping, history replay ----------

  function dateBucketLabel(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / 86400000);

    if (diffDays <= 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays <= 7) return "Previous 7 days";
    if (diffDays <= 30) return "Previous 30 days";
    return "Older";
  }

  const BUCKET_ORDER = ["Today", "Yesterday", "Previous 7 days", "Previous 30 days", "Older"];

  function renderConversationList(conversations) {
    conversationList.querySelectorAll(".conversation-section").forEach((el) => el.remove());
    conversationListEmpty.hidden = conversations.length > 0;
    if (conversations.length === 0) return;

    const buckets = new Map();
    for (const conv of conversations) {
      const label = dateBucketLabel(conv.updated_at);
      if (!buckets.has(label)) buckets.set(label, []);
      buckets.get(label).push(conv);
    }

    for (const label of BUCKET_ORDER) {
      const items = buckets.get(label);
      if (!items || items.length === 0) continue;

      const sectionFragment = conversationSectionTemplate.content.cloneNode(true);
      const section = sectionFragment.querySelector(".conversation-section");
      section.querySelector(".conversation-section-title").textContent = label;
      const itemsContainer = section.querySelector(".conversation-section-items");

      for (const conv of items) {
        const itemFragment = conversationItemTemplate.content.cloneNode(true);
        const button = itemFragment.querySelector(".conversation-item");
        button.querySelector(".conversation-item-title").textContent = conv.title;
        button.dataset.threadId = conv.thread_id;
        if (conv.thread_id === currentThreadId) button.classList.add("active");
        button.addEventListener("click", () => selectConversation(conv.thread_id));
        itemsContainer.appendChild(itemFragment);
      }

      conversationList.appendChild(sectionFragment);
    }
  }

  async function loadConversations() {
    try {
      const resp = await fetch("/api/conversations");
      if (!resp.ok) return;
      const conversations = await resp.json();
      renderConversationList(conversations);
    } catch {
      // Sidebar is a convenience, not critical path -- fail silently and
      // leave whatever was last rendered (or the empty state).
    }
  }

  async function selectConversation(threadId) {
    if (threadId === currentThreadId && transcript.children.length > 1) {
      closeSidebarOnMobile();
      return;
    }
    currentThreadId = threadId;
    localStorage.setItem("threadId", threadId);
    clearTranscript();

    try {
      const resp = await fetch(`/api/conversations/${encodeURIComponent(threadId)}/messages`);
      if (resp.ok) {
        const messages = await resp.json();
        for (const msg of messages) {
          if (msg.role === "user") {
            appendUserMessage(msg.content);
          } else {
            const shell = appendAssistantMessageShell();
            shell.answer.textContent = msg.content;
          }
        }
      }
    } catch {
      appendErrorMessage("Could not load this conversation's history.");
    }

    conversationList.querySelectorAll(".conversation-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.threadId === threadId);
    });
    closeSidebarOnMobile();
  }

  function startNewChat() {
    currentThreadId = newThreadId();
    localStorage.setItem("threadId", currentThreadId);
    clearTranscript();
    conversationList.querySelectorAll(".conversation-item.active").forEach((btn) => {
      btn.classList.remove("active");
    });
    closeSidebarOnMobile();
    input.focus();
  }

  function closeSidebarOnMobile() {
    document.body.classList.remove("sidebar-open");
    sidebarBackdrop.hidden = true;
    sidebarToggle.setAttribute("aria-expanded", "false");
  }

  function toggleSidebar() {
    const open = !document.body.classList.contains("sidebar-open");
    document.body.classList.toggle("sidebar-open", open);
    sidebarBackdrop.hidden = !open;
    sidebarToggle.setAttribute("aria-expanded", String(open));
  }

  newChatButton.addEventListener("click", startNewChat);
  sidebarToggle.addEventListener("click", toggleSidebar);
  sidebarBackdrop.addEventListener("click", closeSidebarOnMobile);

  composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendButton.disabled = true;
    try {
      await sendMessage(text);
    } finally {
      sendButton.disabled = false;
      input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      composer.requestSubmit();
    }
  });

  // On load: populate the sidebar, and if the thread id we have (from
  // localStorage, or freshly generated) already has history, replay it so
  // refreshing the page doesn't lose your place -- mirrors how Claude.ai
  // reopens your last conversation.
  loadConversations();
  fetch(`/api/conversations/${encodeURIComponent(currentThreadId)}/messages`)
    .then((r) => (r.ok ? r.json() : []))
    .then((messages) => {
      if (!messages || messages.length === 0) return;
      clearTranscript();
      for (const msg of messages) {
        if (msg.role === "user") {
          appendUserMessage(msg.content);
        } else {
          const shell = appendAssistantMessageShell();
          shell.answer.textContent = msg.content;
        }
      }
    })
    .catch(() => {});
})();
