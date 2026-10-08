# Troubleshooting

Real problems hit during this project's own development, and how they were
diagnosed and fixed -- not a generic checklist.

## "Missing Authentication header" from `/api/chat/stream`

The OpenRouter API key being used is wrong or missing. Check two things:

1. **Which `.env` is actually in play.** Docker Compose reads the
   **root-level** `.env` (`env_file: .env` in `docker-compose.yml`) --
   not any `.env` inside `backend/`, which (if present) is only a leftover
   from running the backend directly outside Docker during development and
   is never read by Compose.
2. Confirm the key actually reached the container:
   ```bash
   docker compose exec backend env | grep OPENROUTER_API_KEY
   ```
   If you just edited `.env`, the running container won't pick it up
   automatically -- force a recreate:
   ```bash
   docker compose up -d --force-recreate backend
   ```

## 502 Bad Gateway from nginx

The `backend` container isn't actually listening yet (still starting, or
crashed). Check:

```bash
docker compose ps
docker compose logs --tail=50 backend
```

If `backend` shows as healthy moments later, this can be transient
container-restart flakiness rather than a real problem -- re-check once
more before digging further.

## Port 8080 already allocated

Something else on the host (possibly an unrelated project, possibly a
leftover container from a renamed project directory -- see
[Deployment &rarr; renaming the project directory](deployment.md#a-note-on-renaming-the-project-directory))
is holding the port:

```bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
docker ps --format '{{.Names}}: {{.Ports}}' | grep 8080
```

Either stop whatever's holding it, or change `frontend`'s published port
in `docker-compose.yml` (`"8080:80"` &rarr; `"8081:80"`, etc.).

## SSE events arrive all at once instead of streaming live

Almost always a buffering problem somewhere in the chain, not an
application bug. Check, in order:

1. Is a reverse proxy in front of nginx also buffering? (Not applicable in
   the default local setup, but relevant if you've added one.)
2. Confirm nginx's own config has `proxy_buffering off;` on the `/api/`
   location (see [Deployment](deployment.md#nginx-sse-critical-configuration)).
3. Confirm no compression middleware (gzip) is wrapping the SSE response --
   gzip needs the full body before it can flush a compressed frame, which
   defeats live streaming entirely.

## `run_sandboxed_code` always returns "temporarily unavailable"

The circuit breaker for `sandbox_exec` has tripped (3 consecutive
failures) and is in its 30-second cooldown. Usually means `executor` isn't
reachable -- check:

```bash
docker compose ps executor
docker compose logs --tail=50 executor
docker compose exec backend python3 -c "import httpx; print(httpx.get('http://executor:8000/health').json())"
```

If `executor` itself is unhealthy, check it has access to the Docker
socket (`docker compose exec executor ls -la /var/run/docker.sock`).

## MCP tools aren't showing up

Check the backend startup logs for the load outcome -- a failure here never
crashes the backend, it just logs and continues with one fewer tool:

```bash
docker compose logs backend | grep -i mcp
```

```text
INFO:app.mcp_tools:Loaded 2 MCP tool(s) from 1 server(s): ['roll_dice', 'get_server_time']
```

vs.

```text
WARNING:app.mcp_tools:Failed to load MCP tools (...) -- continuing without them.
```

If it's the warning, check `backend/mcp_servers.json` for a typo, and that
the `command` (for a `stdio` server) actually resolves inside the
container -- e.g. `python` (not `python3`, or a path that doesn't exist in
`python:3.12-slim`).

## Markdown isn't rendering (raw `**bold**`/`#`/`` ``` `` showing up)

Check the browser console for a failed script load -- `marked.min.js` or
`purify.min.js` not loading (404, wrong path) causes `renderMarkdown()` to
fall back to plain escaped text rather than throwing, so this fails
silently rather than with an obvious error. Confirm both files are present
in the frontend image:

```bash
docker compose exec frontend ls /usr/share/nginx/html/*.min.js
```
