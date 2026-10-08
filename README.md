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
  6 tools (web search, calculator, stock analysis, summarization, and
  agent-managed long-term memory via `save_memory`/`search_memory`),
  Postgres-backed checkpointing + memory store, circuit breakers / retries /
  caching / rate limiting around external calls.
- **frontend/** -- plain HTML/CSS/JS chat UI, no framework, no build step.
  Talks to the backend via a hand-rolled SSE parser over `fetch()` (native
  `EventSource` can't POST a JSON body).
- **docker-compose.yml** -- 3 containers: `backend`, `frontend` (nginx,
  serves the static files and reverse-proxies `/api/*` to `backend`),
  `postgres`.

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

## Notes

- `STREAMING_API_VERSION=v2` in `.env` switches to a fallback streaming
  adapter if the (experimental) LangGraph v3 event-streaming API ever
  misbehaves on a future langgraph version.
- The backend is not published on the host -- only reachable through the
  frontend's nginx proxy. For direct debugging:
  `docker compose exec frontend wget -qO- http://backend:8000/api/health`
