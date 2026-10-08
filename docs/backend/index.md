# Backend Overview

FastAPI + LangGraph, Python. Module layout:

```text
backend/app/
├── main.py              # FastAPI app, lifespan, router registration
├── config.py             # pydantic-settings, all env vars
├── runtime.py             # AgentRuntime -- built once at startup
├── agent.py                # create_agent + ChatOpenRouter wiring
├── artifacts.py             # chart/image/doc binary storage
├── conversations.py          # sidebar metadata table + history replay
├── mcp_tools.py                # external MCP server connection
├── db.py                        # Postgres readiness retry helper
├── checkpointer.py                # AsyncPostgresSaver lifecycle
├── store.py                        # AsyncPostgresStore lifecycle
├── schemas.py                       # ChatRequest
├── tools/                            # all 13 tools, see Tools section
├── streaming/                         # SSE adapters, see Streaming Design
├── resilience/                         # breakers, cache, retry, rate limit
├── routers/                             # chat, health, artifacts, conversations
└── utils/reasoning_merge.py              # OpenRouter streaming bugfix
```

## `AgentRuntime`

`backend/app/runtime.py` builds one dataclass at startup and holds it on
`app.state.runtime` -- nothing listed below is rebuilt per request:

```python
@dataclass
class AgentRuntime:
    graph: Any                              # the compiled LangGraph agent
    checkpointer: BaseCheckpointSaver        # per-thread conversation state
    store: BaseStore                         # user-scoped long-term memory
    http_client: httpx.AsyncClient           # shared, pooled
    caches: dict[str, TTLCache]              # per-tool result caches
    breakers: dict[str, CircuitBreaker]      # per-tool + "openrouter"
    tool_semaphores: dict[str, asyncio.Semaphore]
    artifacts: TTLCache                      # chart/image/doc binary store
```

Built in `lifespan()`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = await build_runtime(settings)
    await setup_conversations_table(settings.database_url)
    yield
    await app.state.runtime.http_client.aclose()
    await close_checkpointer()
    await close_store()
```

`build_runtime()` itself:

1. Waits for Postgres (`wait_for_postgres`, retry/backoff on top of
   Compose's own `pg_isready` healthcheck -- belt-and-suspenders against a
   startup race).
2. Builds the checkpointer and store (both call their own idempotent
   `.setup()`, safe to run on every boot).
3. Builds per-tool caches, circuit breakers, semaphores.
4. Loads external MCP tools (`load_mcp_tools`, never fails startup -- see
   [External MCP Servers](../tools/mcp.md)).
5. Builds the agent graph (`build_agent_graph`), passing in everything
   above.

See [Resilience](resilience.md) for the caches/breakers/semaphores in
detail, and [Agent & Model](agent.md) for the graph construction.
