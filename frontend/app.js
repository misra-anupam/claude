(() => {
  "use strict";

  const transcript = document.getElementById("transcript");
  const composer = document.getElementById("composer");
  const input = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const assistantTemplate = document.getElementById("assistant-message-template");
  const toolCardTemplate = document.getElementById("tool-card-template");

  if (window.mermaid) {
    window.mermaid.initialize({ startOnLoad: false });
  }
  let mermaidCounter = 0;

  const threadId = (() => {
    let id = localStorage.getItem("threadId");
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
      localStorage.setItem("threadId", id);
    }
    return id;
  })();

  function appendUserMessage(text) {
    const el = document.createElement("div");
    el.className = "message user";
    el.textContent = text;
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function appendAssistantMessageShell() {
    const fragment = assistantTemplate.content.cloneNode(true);
    const el = fragment.querySelector(".message");
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
    return {
      root: el,
      thinking: el.querySelector(".thinking"),
      thinkingBody: el.querySelector(".thinking-body"),
      toolCards: el.querySelector(".tool-cards"),
      answer: el.querySelector(".answer"),
    };
  }

  function appendErrorMessage(text) {
    const el = document.createElement("div");
    el.className = "message error";
    el.textContent = text;
    transcript.appendChild(el);
    transcript.scrollTop = transcript.scrollHeight;
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
        transcript.scrollTop = transcript.scrollHeight;
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
          statusEl.textContent = "error";
          resultEl.hidden = false;
          resultEl.textContent = error;
          transcript.scrollTop = transcript.scrollHeight;
          return;
        }

        card.classList.remove("pending");
        card.classList.add("done");
        statusEl.textContent = "done";

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
          renderMermaid(structured.mermaid, renderEl).then(() => {
            transcript.scrollTop = transcript.scrollHeight;
          });
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
        transcript.scrollTop = transcript.scrollHeight;
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
      body: JSON.stringify({ thread_id: threadId, message: userText }),
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
          transcript.scrollTop = transcript.scrollHeight;
        },
        token: (d) => {
          shell.answer.textContent += d.delta ?? "";
          transcript.scrollTop = transcript.scrollHeight;
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
    } catch (err) {
      appendErrorMessage(String(err.message || err));
    }
  }

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
})();
