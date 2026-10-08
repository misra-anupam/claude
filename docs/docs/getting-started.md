# Getting Started

## Prerequisites

- Docker and Docker Compose
- An [OpenRouter](https://openrouter.ai) API key (covers both the chat model
  and image generation -- see [Image Generation](tools/image-generation.md)
  for why a separate Gemini key isn't needed)

## Run it

```bash
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
docker compose up --build
```

Open <http://localhost:8080>.

!!! warning "Verify the model slug"
    `OPENROUTER_MODEL` defaults to `anthropic/claude-sonnet-4.5`. OpenRouter's
    model catalog drifts -- check [openrouter.ai/models](https://openrouter.ai/models)
    before your first run if things don't work.

## What happens on startup

1. `postgres` starts and waits for a healthy `pg_isready`.
2. `backend` waits for Postgres, then:
      - builds the `AgentRuntime` (checkpointer, long-term memory store,
        artifact store, circuit breakers, caches, HTTP client)
      - creates the `conversations` tracking table if it doesn't exist
      - connects to any MCP servers listed in `mcp_servers.json` (ships with
        one bundled local demo server, so this always succeeds out of the box)
      - builds the LangGraph agent graph with all 13 tools
3. `executor` starts independently -- it doesn't depend on `backend`, and
   `backend` doesn't block startup waiting for it (a tool call to
   `run_sandboxed_code` will just fail gracefully via its circuit breaker if
   `executor` isn't up yet).
4. `frontend` (nginx) starts, serving the static files and proxying `/api/*`
   to `backend`.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required)* | Used for both the chat model and image generation |
| `OPENROUTER_MODEL` | `anthropic/claude-sonnet-4.5` | Verify against the live OpenRouter catalog |
| `REASONING_EFFORT` | `high` | `low`\|`medium`\|`high` -- **not** a token-budget number; see [Streaming Design](streaming.md#the-reasoning-parameter-gotcha) for why |
| `STREAMING_API_VERSION` | `v3` | `v2` switches to the fallback adapter -- see [Streaming Design](streaming.md) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `appuser` / `changeme` / `chatdb` | |
| `EXECUTOR_URL` | `http://executor:8000` | Internal, rarely needs changing |

## Try it

A quick tour of what's built, one message each:

```text
Search the web for the latest news about the James Webb Space Telescope
What is (482 * 37) - 19**2 / 4?
How has TSLA performed over the last month?
Summarize this: https://en.wikipedia.org/wiki/Retrieval-augmented_generation
Remember that my favorite language is Rust and I'm vegetarian
Use run_sandboxed_code to compute the sum of squares from 1 to 50
Generate a bar chart of Q1-Q4 revenue: 100, 150, 130, 180
Generate a Mermaid flowchart of a user login flow
Generate an image of a red fox in a snowy forest, cartoon style
Generate a PDF report titled Q1 Highlights with two paragraphs
Roll three 20-sided dice
```

The last one calls the bundled demo MCP server's tool -- see
[External MCP Servers](tools/mcp.md).

Ask something that plausibly needs two tools in one turn (e.g. "search for
X and also calculate Y") to see two tool cards running simultaneously, each
resolving independently.

## Debugging directly

The backend isn't published on the host -- only reachable through the
frontend's nginx proxy, same-origin, no CORS needed:

```bash
docker compose exec frontend wget -qO- http://backend:8000/api/health
```

Raw SSE stream, to see the actual wire protocol:

```bash
curl -N -X POST http://localhost:8080/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"debug","message":"What is 2+2?"}'
```

## Building this documentation site

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Open <http://localhost:8000> (mkdocs' own dev server -- a different port
than the app itself).
