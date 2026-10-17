# Streaming Design

How tokens, reasoning, and tool calls get from the model to the browser
live -- and the three real bugs that only surfaced by actually running this,
not by reading documentation.

## The SSE event model

The backend emits six named event types over one `POST /api/chat/stream`
connection:

| Event | Payload | Meaning |
|---|---|---|
| `thinking` | `{"delta": "..."}` | A reasoning token delta |
| `token` | `{"delta": "..."}` | A final-answer token delta |
| `tool_call` | `{"id", "name", "args"}` | A tool call has started |
| `tool_result` | `{"id", "result"}` or `{"id", "error"}` | A tool call has finished |
| `done` | `{}` | The turn is complete |
| `error` | `{"message": "..."}` | Something failed; the turn ends |

`tool_call`/`tool_result` are correlated by `id` (the model's tool-call
id), **not** by arrival order -- when the model fires several tool calls in
one turn, multiple `tool_call` events arrive together and `tool_result`
events arrive independently as each tool actually finishes, interleaved
with each other and with ongoing `token`/`thinking` events. The frontend
tracks tool cards in a `Map<id, cardElement>`, not a single "current tool"
slot, specifically so this renders correctly -- see
[Frontend](frontend.md#tool-cards).

## Why POST, not native `EventSource`

The browser's native `EventSource` API is GET-only with no custom body and
no custom headers -- unchanged WHATWG behavior. A chat UI needs to POST a
JSON body (the message, the thread id). The frontend instead uses
`fetch()` + `ReadableStream` + `TextDecoderStream`, manually parsing the
`text/event-stream` wire format (blank-line-delimited events, careful
about a chunk boundary landing mid-event). See
[Frontend](frontend.md#the-sse-client) for the parser itself.

On the server side, this requires SSE that supports POST, which is why the
backend uses FastAPI's native `fastapi.sse.EventSourceResponse` (FastAPI
&ge;0.135) rather than the older `sse-starlette` pattern -- it works with
any HTTP method.

!!! danger "Bug #1 (real): `EventSourceResponse` must be used directly, not constructed"
    The first implementation had the route function build an async
    generator separately and return `EventSourceResponse(gen())`. This
    compiles, imports fine, and crashes on the first real request with
    `AttributeError: 'ServerSentEvent' object has no attribute 'encode'`.

    The actual contract, found by reading FastAPI's `routing.py`: the SSE
    wire encoding only activates when the **route handler itself** is an
    async generator (`async def ... yield ...`) with
    `response_class=EventSourceResponse` on the decorator --
    `_is_async_gen_callable(dependant.call)` is checked directly against the
    route function. Returning a manually-constructed
    `EventSourceResponse(some_other_generator())` falls back to generic
    `StreamingResponse` behavior, which doesn't know how to serialize a
    `ServerSentEvent` object.

    Fixed by making `chat_stream` itself the generator:

    ```python
    @router.post("/chat/stream", response_class=EventSourceResponse)
    @limiter.limit("20/minute")
    async def chat_stream(req: ChatRequest, request: Request) -> AsyncIterator[ServerSentEvent]:
        ...
        while (item := await queue.get()) is not None:
            yield ServerSentEvent(event=item["event"], data=item["data"])
    ```

    Confirmed via a live `curl -N` against a running container, not just by
    re-reading the source.

## End-to-end: how one event travels

Chat is **one request, one response**: the same `POST /api/chat/stream`
carries the user's message in its body and returns the whole reply as a
response body that stays open. There is no separate "poll for the answer"
endpoint and no WebSocket. The only other chat-related calls are the history
reads (`GET /api/conversations`, `GET /api/conversations/{id}/messages`),
which return finished text after the fact.

```
LangGraph (astream_events v3)
   |  messages: reasoning / text chunks, tool_calls
   |  updates:  ToolMessage results
   v
langgraph_v3_adapter._drive_graph --put--> asyncio.Queue --get--> chat_stream (async generator)
   (background task)                          {event, data}         yield ServerSentEvent
                                                                          |
                                         "event: token\ndata: {...}\n\n"  v
                                                  nginx (proxy_buffering off) --> fetch() ReadableStream
                                                                                     |
                                                  app.js: split on \n\n -> dispatchSSEEvent -> handlers
```

### Wire format

Each event is a block of text lines terminated by a blank line (`\n\n`):

```
event: token
data: {"delta": "Hel"}

event: tool_call
data: {"id": "call_1", "name": "...", "args": {...}}

```

`event:` names the type and `data:` carries a JSON payload. A line starting
with `:` is a comment (a keep-alive ping in the SSE spec); the frontend
skips these. The `\n\n` is purely a **delimiter the receiver uses to find
event boundaries** -- nothing is "sent" by it.

### nginx: why `proxy_buffering off`

`proxy_buffering` controls how nginx relays the upstream (backend) response
to the client:

- **On (the default):** nginx reads the backend response into memory (or
  disk) buffers and forwards it only once enough has accumulated or the
  response ends. For a stream, the client sees nothing until the end, then
  gets every token in one burst.
- **Off (this project):** nginx forwards each piece the instant it arrives
  from the backend, which is what makes token-by-token output visible.

The `/api/` location in `frontend/nginx.conf` also sets `proxy_cache off`,
a 300s `proxy_read_timeout`, and `proxy_http_version 1.1` with an empty
`Connection` header (persistent connection). `text/event-stream` is
deliberately left out of `gzip_types` for the same reason as buffering: gzip
holds output until it has a block to compress. The cost of buffering off is
that a slow client keeps a backend connection occupied, which is irrelevant
at this project's scale.

### Browser side: `streamChat` is the receiver

`streamChat` (`frontend/app.js`) runs **in the browser** and receives the
stream; it doesn't send anything onward. It:

1. POSTs `{thread_id, message}` with `fetch`, throwing on a non-2xx status.
2. Reads `resp.body.pipeThrough(new TextDecoderStream()).getReader()`.
   `TextDecoderStream` also handles multi-byte characters split across
   network chunks.
3. Loops on `reader.read()`: append the chunk to a `buffer` string, then
   while the buffer contains `"\n\n"`, slice off one complete event, pass it
   to `dispatchSSEEvent`, and keep the remainder.
4. Exits when the server closes the response (`done: true` from
   `reader.read()`), dispatching any leftover buffer once.

The buffer is required because network chunks don't align with event
boundaries: one read may contain half an event, exactly one, or three and a
half. The remainder waits for the next chunk.

```
read chunk -> buffer += chunk -> extract every complete "\n\n"-terminated event
     ^                                 | each -> dispatchSSEEvent -> handler
     |                                 |          (token -> append text to the page)
     +------------ wait for next chunk <+
```

`dispatchSSEEvent` defaults the event name to `message`, skips `:` comment
lines, joins multiple `data:` lines with `\n` (per the SSE spec), and
`JSON.parse`s the result -- malformed data is silently dropped. It then
calls `handlers[eventName] ?? handlers.default`. The handlers in
`sendMessage` update the DOM: `thinking` fills the collapsible reasoning
block, `token` appends to the answer and re-renders the markdown,
`tool_call`/`tool_result` create and resolve cards by `id`, `done`
collapses the thinking block, and `error` adds an error note to the message.

### Failure paths

- A server-side failure *during* the run arrives as an `error` **event**
  (see the circuit breaker section below).
- A dropped connection or non-2xx response is a different path: `fetch` /
  `reader.read()` throws, and `sendMessage` shows a standalone error bubble.
- There is **no reconnect or resume**. Native `EventSource` auto-reconnects;
  this manual `fetch` client does not, so a connection lost mid-answer leaves
  a partial answer.
- Closing the connection cancels the work: the `chat_stream` generator is
  closed, its `finally: task.cancel()` runs, and the LangGraph run stops.

## The producer/consumer queue

`chat_stream` doesn't drive the graph itself. It creates an `asyncio.Queue`,
hands it to a background task running the adapter, and just pumps whatever
arrives back out as SSE:

```python
queue: asyncio.Queue = asyncio.Queue()
task = asyncio.create_task(
    adapter.run_and_translate(runtime.graph, payload, config, queue, runtime.breakers["openrouter"])
)
try:
    while (item := await queue.get()) is not None:
        yield ServerSentEvent(event=item["event"], data=item["data"])
finally:
    task.cancel()
```

This loop is intentionally generic -- it has no branching on `item["event"]`
at all. It doesn't know or care whether the item it just pulled is a
`thinking` delta or a `tool_result`; it forwards every item through the same
two lines. All the variety in event types comes entirely from the producer
side deciding what to `put()` and when (`langgraph_v3_adapter.py`'s
`consume_messages()`/`consume_updates()`, run concurrently via
`asyncio.gather`). The queue is the reason that works: it's an async-safe
FIFO mailbox that lets a coroutine awaiting `get()` suspend (no busy-polling)
until any producer calls `put()`, and it preserves real arrival order across
multiple concurrent producers -- exactly what's needed when a `tool_result`
for a fast tool can legitimately arrive before the `tool_call` event for a
slower one has even finished being described.

The shutdown signal is just one more item flowing through the same channel:
the adapter's own `finally: await queue.put(None)` is what ends the `while`
loop here -- not an exception, not task completion, a plain sentinel value.

!!! note "No backpressure today -- and what would change if there were"
    `asyncio.Queue()` is created with no `maxsize`, so `put()` never blocks
    the producer, no matter how far ahead of the consumer it gets. In
    practice this is safe here because the queue is scoped to a single
    request: growth is capped by one conversational turn's worth of events
    (at most a few hundred token/thinking chunks), not an open-ended stream,
    and the queue is discarded when the request ends.

    If a `maxsize` were set, `await queue.put(...)` would suspend the
    producer once the queue is full, until `get()` frees a slot -- real
    backpressure. Tracing where that would actually bite: `put()` is called
    mid-iteration of `async for chunk in message.text`/`.reasoning`, so a
    blocked `put()` stalls further consumption of the live
    `astream_events` stream. That stall can propagate further upstream than
    it looks: if the backend stops reading bytes off the HTTP connection to
    OpenRouter because the consuming coroutine is parked on a full queue,
    the TCP receive buffer fills and real TCP flow control kicks in --
    OpenRouter's sending side would genuinely slow down too. The one risk a
    bounded queue would introduce is a producer permanently stuck on `put()`
    if the consumer disappears entirely (not just slow, but gone) --
    `task.cancel()` in the `finally` guards against that by raising
    `CancelledError` at whichever `await` the task is parked on, including
    an in-progress `put()`.

## The LangGraph v3 event-streaming API

The adapter (`backend/app/streaming/langgraph_v3_adapter.py`) drives
`graph.astream_events(payload, config=config, version="v3", transformers=[UpdatesTransformer])`
and translates two concurrent projections into the SSE queue:

```python
async def consume_messages():
    async for message in stream.messages:          # one per LLM call
        # .text and .reasoning are separate async iterables on each message
        await asyncio.gather(pump_reasoning(), pump_text())
        for call in await message.tool_calls:        # finalized list
            await queue.put(make_event("tool_call", {...}))

async def consume_updates():
    async for update in stream.updates:               # opt-in via UpdatesTransformer
        for node_output in update.values():
            for msg in node_output.get("messages", []):
                if isinstance(msg, ToolMessage):
                    await queue.put(make_event("tool_result", {...}))

await asyncio.gather(consume_messages(), consume_updates())
```

These two functions read different native projections and cover opposite
halves of a tool call -- the *request* vs. the *result*:

| | `consume_messages()` | `consume_updates()` |
|---|---|---|
| Reads from | `stream.messages` -- native | `stream.updates` -- opt-in, only exists because `transformers=[UpdatesTransformer]` was passed to `astream_events` |
| One item per | LLM call | graph node state change |
| Produces | `thinking`, `token`, `tool_call` | `tool_result` |
| Represents | what the model said and *decided to call* (`message.tool_calls` is explicitly documented as the request, not the execution result) | proof a tool *actually ran*, via `ToolMessage` instances scanned out of the node's state update, matched by `.tool_call_id` |

Neither one alone is enough: `consume_messages` alone would never show that
a tool finished (it only sees the model's side), and `consume_updates` alone
would never show what was asked for, or produce any token/thinking text at
all. They're run concurrently via `asyncio.gather`, not sequentially,
because a `tool_call` event and its matching `tool_result` arrive on
genuinely independent timelines -- when the model fires two tool calls in
one turn, both `tool_call` events land together as soon as the model
finalizes, while the two `tool_result` events trickle in separately and out
of order as each tool actually completes (e.g. `calculator` instantly,
`web_search` after real network latency). They're stitched back together
downstream purely by `id`/`tool_call_id`, never by which function emitted
them or in what order.

!!! danger "Bug #2 (real): the researched `.tools` channel doesn't exist"
    Initial research (an LLM-generated summary of the LangGraph v1.2
    changelog and a blog post) claimed `stream_events(version="v3")` exposes
    a native `.tools` channel with `tool-started`/`tool-finished` events.

    Installing the real package (`langgraph==1.2.14`) and reading
    `langgraph/stream/*.py` directly showed this is wrong: the only
    **native** projections are `values`, `messages`, `lifecycle`,
    `subgraphs`. There is no `.tools` channel at all.

    The actual mechanism, found by reading source:

    - `message.tool_calls` on each `ChatModelStream` (from `stream.messages`)
      is "async iterable, awaitable for finalized list" per its own
      docstring -- the model's tool-call *request*, not the execution
      result. `await message.tool_calls` after draining `.text`/`.reasoning`
      gives the finalized `[{"id", "name", "args"}, ...]` -- this is the
      real source for `tool_call` events.
    - The execution **result** only shows up via the opt-in `updates`
      projection: pass `transformers=[UpdatesTransformer]`
      (`from langgraph.stream import UpdatesTransformer`), then
      `stream.updates` yields dicts keyed by node name whose value is the
      node's state update (e.g. `{"tools": {"messages": [ToolMessage(...)]}}`)
      -- scan for `ToolMessage` instances, match `.tool_call_id`. This is the
      real source for `tool_result` events.

    Verified **with zero network calls**, before trusting any of this in the
    real app: a toy graph (`create_agent` + a real tool + a fake chat model
    emitting correct `tool_call_chunks`) driven through the actual adapter
    function, for both a single tool call and two simultaneous tool calls --
    confirmed correct id-matched `tool_call`/`tool_result` ordering in both
    cases before ever touching a real OpenRouter call.

## The OpenRouter circuit breaker needs the exception to escape

The adapter wraps the whole turn in a circuit breaker
(`runtime.breakers["openrouter"]`) so repeated OpenRouter failures fail
fast instead of retrying into a hung connection on every subsequent
request:

```python
async def run_and_translate(graph, payload, config, queue, openrouter_breaker=None):
    try:
        if openrouter_breaker is not None:
            await openrouter_breaker.call_async(_drive_graph, graph, payload, config, queue)
        else:
            await _drive_graph(graph, payload, config, queue)
        await queue.put(make_event("done", {}))
    except CircuitBreakerError:
        await queue.put(make_event("error", {"message": "OpenRouter is temporarily unavailable..."}))
    except Exception as exc:
        await queue.put(make_event("error", {"message": str(exc)}))
    finally:
        await queue.put(None)
```

!!! danger "Bug #3 (real): catching the error inside the driven function hides it from the breaker"
    The first version had `_drive_graph` catch its own exceptions and
    translate them into an `error` SSE event internally, for convenience.
    This looked correct and even "worked" -- errors reached the client.

    What it broke: `aiobreaker.CircuitBreaker.call_async(fn, ...)` only
    registers a failure if `fn` raises **out** to the breaker. If
    `_drive_graph` swallows its own exception and returns normally, the
    breaker sees a successful call every time, and never trips -- defeating
    the entire point of having it.

    Fixed by moving all error-to-SSE-event translation to the one caller
    that wraps the breaker call, and letting `_drive_graph` propagate
    exceptions uncaught. Verified live with a real breaker (`fail_max=2`)
    wrapping a function engineered to always fail: confirmed the real
    underlying error reaches the client on the first failure, and the
    breaker's own "temporarily unavailable" message reaches it from the
    second failure onward -- matching `aiobreaker`'s actual semantics
    (the call that crosses the threshold reports the breaker error, not the
    underlying one).

## The `reasoning` parameter gotcha

`ChatOpenRouter(reasoning={...})` controls whether/how much the model
exposes its reasoning. Research (and OpenRouter's own docs, read in
isolation) suggested Anthropic models use a token-budget style:
`{"max_tokens": N}`.

!!! danger "Bug #4 (real): `anthropic/claude-sonnet-4.5` needs `effort`, not `max_tokens`"
    Tested live, side by side, with a real API key:

    ```python
    # Returns empty reasoning_details -- no thinking tokens at all
    ChatOpenRouter(model="anthropic/claude-sonnet-4.5", reasoning={"max_tokens": 2000})

    # Returns populated reasoning_details
    ChatOpenRouter(model="anthropic/claude-sonnet-4.5", reasoning={"effort": "high"})
    ```

    Cross-checked against `deepseek/deepseek-r1`, which **does** work with
    `max_tokens` -- confirming this is model/provider-specific, not a
    universal Anthropic rule contradicting the docs. The config field is
    named `REASONING_EFFORT` (not `REASONING_MAX_TOKENS`) for this reason.

## `.with_retry()` is incompatible with `create_agent`

`ChatOpenRouter(...).with_retry(...)` is a standard LangChain `Runnable`
method and looks like the obvious way to get retry behavior on the model
call.

!!! danger "Bug #5 (real): `RunnableRetry` has no `.bind_tools()`"
    `.with_retry()` wraps the model in a generic `RunnableRetry`, which
    doesn't expose `.bind_tools()` -- and `create_agent` calls
    `model.bind_tools(tools)` internally. The combination fails immediately:
    `'RunnableRetry' object has no attribute 'bind_tools'`.

    Fixed by using `ChatOpenRouter`'s own native `max_retries` constructor
    field instead, which achieves the same retry goal without wrapping the
    model object at all.

## The v2 fallback

`backend/app/streaming/langgraph_v2_fallback.py` implements the same
`run_and_translate(graph, payload, config, queue, breaker)` signature using
the "classic" `stream_mode=["messages", "updates"], version="v2"` API,
selected via `STREAMING_API_VERSION=v2`. It exists because the v3 API is
young (shipped ~5 months before this project was built) and the exact
attribute shapes could drift in a future `langgraph` release -- if that
happens, only `langgraph_v3_adapter.py` needs to change; `routers/chat.py`
is agnostic to which adapter produced the queue items.
