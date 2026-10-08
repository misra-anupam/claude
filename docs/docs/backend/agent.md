# Agent & Model

`backend/app/agent.py`

## Why `create_agent`, not `langgraph.prebuilt.create_react_agent`

`langgraph.prebuilt.create_react_agent` is deprecated as of LangGraph v1.0
(removal targeted for v2.0). The current idiomatic entry point is
`create_agent` from `langchain.agents` -- same underlying
model-&rarr;tools-&rarr;model loop, different import path and one renamed
kwarg (`prompt=` &rarr; `system_prompt=`).

```python
model = ChatOpenRouter(
    model=settings.openrouter_model,
    openrouter_api_key=settings.openrouter_api_key,
    reasoning={"effort": settings.reasoning_effort},
    streaming=True,
    model_kwargs={"parallel_tool_calls": True},
    max_retries=3,
    callbacks=[ReasoningDetailsMergeCallback()],
)

tools = build_tool_list(store, breakers, tool_semaphores, caches, http_client, artifacts, mcp_tools)

return create_agent(
    model=model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
    store=store,
)
```

## `ChatOpenRouter`, not `ChatOpenAI(base_url=...)`

The tempting shortcut -- point a plain `ChatOpenAI` at OpenRouter's
OpenAI-compatible endpoint via `base_url=` -- silently drops OpenRouter's
`reasoning`/`reasoning_details` response fields (confirmed via two closed
upstream LangChain GitHub issues: #32981, #35059). `langchain-openrouter`'s
`ChatOpenRouter` is the first-party fix, wrapping OpenRouter's own SDK and
surfacing reasoning via `additional_kwargs["reasoning_details"]` /
`content_blocks`.

See [Streaming Design](../streaming.md#the-reasoning-parameter-gotcha) for
why `reasoning={"effort": ...}` and not `{"max_tokens": ...}`, and
[Streaming Design](../streaming.md#with_retry-is-incompatible-with-create_agent)
for why `max_retries=3` is a constructor kwarg here rather than
`.with_retry(...)`.

## `create_agent` accepts `store=` directly

Worth noting since it wasn't obvious going in: `create_agent` has a native
`store=` parameter, confirmed by inspecting its real signature
(`inspect.signature(create_agent)`). The memory tools
(`save_memory`/`search_memory`) don't rely on this, though -- they're built
as closures directly over the store object (see
[Long-Term Memory](../tools/memory.md)), which works regardless of exactly
how `create_agent`'s own store-injection plumbing behaves internally. Both
are wired in; the closures are the actual mechanism in use.

## `parallel_tool_calls` passthrough

`model_kwargs={"parallel_tool_calls": True}` is spread directly into the
OpenRouter request payload (confirmed by reading `ChatOpenRouter`'s source:
`**self.model_kwargs` merges into the final request dict). This is what
allows the model to fire multiple tool calls in a single turn -- see
[Streaming Design](../streaming.md#the-sse-event-model) for how that
surfaces as simultaneous `tool_call` events.

## The system prompt

```python title="backend/app/agent.py"
SYSTEM_PROMPT = (
    "You are a helpful assistant with access to web search, a calculator, "
    "stock analysis, text summarization, a sandboxed Python code execution "
    "tool (run_sandboxed_code) for anything too complex for the calculator, "
    "chart/diagram generation tools (generate_chart for bar/line/pie/"
    "scatter charts from data, generate_diagram for Mermaid flowcharts), "
    "an image generation tool (generate_image) for illustrations and other "
    "visuals that aren't data charts, and document generation tools "
    "(generate_html, generate_pdf) for downloadable report-style documents, "
    "persistent memory tools (save_memory, search_memory) scoped to this "
    "one user, and possibly additional tools provided by connected external "
    "MCP servers. "
    "Call save_memory when the user shares a durable personal fact worth "
    "remembering across conversations. Call search_memory when recalling "
    "something the user may have told you before would help answer their "
    "question. Use tools whenever they would make your answer more accurate "
    "than relying on your own knowledge alone."
)
```
