# LangGraph + OpenRouter streaming agent

A study project: a LangGraph agent (Claude via OpenRouter) wrapped in FastAPI,
streamed live to a vanilla-JS frontend over SSE -- tokens, "thinking"
(reasoning), and tool-call events all arrive as they happen, not just at the
end. Backed by Postgres for per-thread conversation history and long-term
memory for a single user.

## Run it

```
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
# verify OPENROUTER_MODEL against https://openrouter.ai/models first --
# model slugs on OpenRouter drift; this was built against anthropic/claude-sonnet-4.5
docker compose up --build
```

Open http://localhost:8080.

## What's in it

- **backend/** -- FastAPI + LangGraph (`create_agent`), `ChatOpenRouter` model,
  7 tools (web search, calculator, stock analysis, summarization, sandboxed
  Python execution, and agent-managed long-term memory via
  `save_memory`/`search_memory`), Postgres-backed checkpointing + memory
  store, circuit breakers / retries / caching / rate limiting around
  external calls.
- **executor/** -- a separate, isolated FastAPI service that runs untrusted
  code from the `run_sandboxed_code` tool in short-lived, hardened sibling
  containers (no network, read-only filesystem except a tmpfs `/tmp`,
  non-root, capped CPU/memory/pids). It's the *only* service holding the
  Docker socket mount; the main backend never touches it directly, and
  `executor` sits on its own internal-only network reachable solely from
  `backend` -- `frontend`/`postgres` have no path to it. All of this was
  verified live, not just configured: outbound network calls fail with DNS
  resolution errors, writes outside `/tmp` fail with read-only/permission
  errors, fork bombs get capped by `pids_limit`, and memory hogs get
  OOM-killed.
- **frontend/** -- plain HTML/CSS/JS chat UI, no framework, no build step.
  Talks to the backend via a hand-rolled SSE parser over `fetch()` (native
  `EventSource` can't POST a JSON body).
- **docker-compose.yml** -- 4 containers: `backend`, `executor`, `frontend`
  (nginx, serves the static files and reverse-proxies `/api/*` to
  `backend`), `postgres`.

## Try it

- "Search the web for the latest news about the James Webb Space Telescope"
  (tool call)
- "What is (482 * 37) - 19**2 / 4?" (tool call)
- "How has TSLA performed over the last month?" (tool call)
- "Summarize this: https://en.wikipedia.org/wiki/Retrieval-augmented_generation"
  (tool call)
- "Remember that my favorite language is Rust and I'm vegetarian" then,
  later (even after `docker compose restart backend`), "what do you know
  about my dietary preferences?" (long-term memory, survives restarts)
- Ask something that plausibly needs two tools in one turn to see two tool
  cards running at once.
- "Use run_sandboxed_code to compute the sum of squares from 1 to 50" (real
  code execution in an isolated container)
- "Use run_sandboxed_code to try reaching google.com and writing a file
  outside /tmp, show me the exact errors" (watch the sandbox's isolation
  fail safely, in the model's own words)

## Notes

- `STREAMING_API_VERSION=v2` in `.env` switches to a fallback streaming
  adapter if the (experimental) LangGraph v3 event-streaming API ever
  misbehaves on a future langgraph version.
- The backend is not published on the host -- only reachable through the
  frontend's nginx proxy. For direct debugging:
  `docker compose exec frontend wget -qO- http://backend:8000/api/health`
