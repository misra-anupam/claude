# Frontend

Plain HTML/CSS/JS -- no framework, no build step, no bundler. Three files:
`index.html`, `style.css`, `app.js`, plus three locally-bundled libraries
(`mermaid.min.js`, `marked.min.js`, `purify.min.js` -- no CDN dependency at
runtime, consistent across the whole project).

## The SSE client

Native browser `EventSource` is GET-only with no custom body/headers
(unchanged WHATWG spec) -- unusable for a POST-a-JSON-body chat UI. Instead,
`app.js` manually parses the `text/event-stream` wire format from a
`fetch()` response body:

```javascript
const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
let buffer = "";
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  buffer += value;
  let idx;
  while ((idx = buffer.indexOf("\n\n")) !== -1) {   // events are blank-line delimited
    dispatchSSEEvent(buffer.slice(0, idx), handlers);
    buffer = buffer.slice(idx + 2);
  }
}
```

A chunk boundary can land mid-event, which is why this only splits on
*complete* `\n\n` occurrences and keeps the remainder buffered for the next
read, rather than splitting the whole buffer eagerly.

## Tool cards

Tool calls are tracked in a `Map<toolCallId, cardElement>`, **not** a
single "current tool" variable -- this is what makes simultaneous/parallel
tool calls render correctly as multiple independent cards:

```javascript
function createToolCardTracker(container) {
  const cards = new Map();
  return {
    start(id, name, args) { /* create card, cards.set(id, card) */ },
    finish(id, result, error) { /* look up by id, fill in result */ },
  };
}
```

When the model fires two tool calls in one turn, two `tool_call` SSE events
arrive together and two cards appear in "pending" state simultaneously;
each flips to "done" independently as its own `tool_result` event arrives
-- confirmed visually correct against real parallel tool calls during
development.

## Structured tool results

Most tools return a plain string. Four tools
([charts](tools/charts-diagrams.md), [images](tools/image-generation.md),
[documents](tools/documents.md)) return a JSON-encoded object instead:
`{"text", "artifact_id", "content_type"}` or `{"text", "mermaid"}`. The
`finish()` handler detects this shape and renders accordingly:

```javascript
const structured = parseStructuredResult(result);
if (structured?.artifact_id && structured.content_type?.startsWith("image/")) {
  // inline <img src="/api/artifacts/{id}">
} else if (structured?.artifact_id) {
  // download link
} else if (structured?.mermaid) {
  // render via mermaid.js
} else if (Array.isArray(result) && result.every(b => "text" in b)) {
  // MCP-style content blocks -- join .text fields
} else {
  // plain text fallback
}
```

That last branch exists because [MCP tool results](tools/mcp.md) come back
in a different shape again (a list of `{"type": "text", "text": ...}`
content blocks) -- discovered when the MCP integration was added and the
raw JSON was showing up unparsed in the tool card.

## Mermaid diagrams

Bundled `mermaid.js` locally, initialized once (`startOnLoad: false`), then
rendered on demand per diagram:

```javascript
const { svg } = await window.mermaid.render(`mermaid-${++mermaidCounter}`, code);
container.innerHTML = svg;
```

## Markdown rendering

Assistant message text (both the final answer and the "thinking" content)
is rendered as sanitized HTML via `marked.js` (parsing) +
`DOMPurify` (sanitization) -- headings, code blocks, lists, bold/italic,
links, tables.

```javascript
function renderMarkdown(raw) {
  return window.DOMPurify.sanitize(window.marked.parse(raw));
}
```

**DOMPurify is the actual security boundary**, not any "disable raw HTML"
setting in `marked` -- model output is untrusted regardless of how `marked`
would render it, so the sanitization step is what matters. Verified
directly (via a jsdom-backed test of the exact bundled library files, not
just trusted from documentation): normal markdown renders correctly
(headings, fenced code blocks with language tagging, lists), and three XSS
vectors were confirmed neutralized:

| Input | Result after `DOMPurify.sanitize()` |
|---|---|
| `<script>alert(1)</script>` | Stripped entirely |
| `<img src=x onerror="alert(2)">` | `onerror` attribute stripped, `<img src="x">` remains |
| `[click me](javascript:alert(3))` | The `javascript:` href stripped, plain `<a>` with no href remains |

### Progressive rendering while streaming

Raw markdown text is accumulated in a JS variable separately from the
rendered DOM, and the **entire accumulated string is re-parsed on every
token delta**, rather than appending pre-rendered HTML fragments:

```javascript
appendAnswerDelta(delta) {
  answerRaw += delta;
  answerEl.innerHTML = renderMarkdown(answerRaw);
}
```

This is what lets incomplete markdown "self-heal" mid-stream -- an
unclosed code fence or bold marker renders as plain text until the closing
marker arrives in a later token, then re-renders correctly on the next
delta. The same pattern is applied to both the thinking content and the
final answer, and to history replay (a thread's stored messages are run
through `renderMarkdown()` too, not just live streaming output).

## Conversation sidebar

Date-grouped (Today / Yesterday / Previous 7 days / Previous 30 days /
Older), computed client-side from each conversation's `updated_at`:

```javascript
function dateBucketLabel(isoString) {
  const diffDays = Math.round((startOfDay(now) - startOfDay(new Date(isoString))) / 86400000);
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays <= 7) return "Previous 7 days";
  if (diffDays <= 30) return "Previous 30 days";
  return "Older";
}
```

Clicking a past conversation fetches
`GET /api/conversations/{id}/messages` and replays it as static bubbles
(see [Conversations](backend/conversations.md) for what the backend
returns and why tool-call detail is excluded from replay). The sidebar
collapses to an off-canvas drawer with a backdrop below 768px.

On page load, the frontend auto-resumes whatever `thread_id` is in
`localStorage` by fetching its history -- refreshing the page doesn't lose
your place, mirroring how Claude.ai reopens your last conversation.

## Visual design

Warm, muted palette (cream background, terracotta accent `#c2673f`,
near-black-but-warm text) in both light and dark mode, rather than a
generic blue/gray chat-app look. Assistant messages flow as plain content
(small circular avatar + text, no bubble); user messages get a soft bubble
-- matching Claude.ai's actual asymmetric message treatment rather than
symmetric bubbles on both sides. Composer is a pill-shaped floating input
with a circular send button, centered content column (~46rem max-width).
