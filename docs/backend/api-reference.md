# API Reference

All backend routes are mounted under `/api` and reached through the
frontend's nginx proxy (`http://localhost:8080/api/...`) -- `backend`
itself has no published host port.

## `GET /api/health`

Plain liveness check. `{"status": "ok"}`.

## `POST /api/chat/stream`

The main chat endpoint. Rate-limited to 20 requests/minute per client IP.
See [Streaming Design](../streaming.md) for the full SSE event model.

**Request:**
```json
{"thread_id": "string", "message": "string"}
```

**Response:** `text/event-stream`, named events `thinking`, `token`,
`tool_call`, `tool_result`, `done`, `error` -- see
[Streaming Design &rarr; SSE event model](../streaming.md#the-sse-event-model)
for the full payload shape of each.

```bash
curl -N -X POST http://localhost:8080/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"thread_id":"demo","message":"What is 2+2?"}'
```

## `GET /api/conversations`

Lists all tracked conversations, most recently updated first. Powers the
sidebar's date grouping (done client-side -- this endpoint just returns a
flat list).

**Response:**
```json
[{"thread_id": "...", "title": "...", "updated_at": "2026-10-08T07:04:04.459275+00:00"}]
```

## `GET /api/conversations/{thread_id}/messages`

Replays a thread's history as plain text (no tool-call detail -- see
[Conversations](conversations.md#deliberate-simplification-text-only-replay)).

**Response:**
```json
[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
```

Returns `[]` for a thread with no stored checkpoint (e.g. a brand-new
`thread_id` that hasn't sent a message yet).

## `GET /api/artifacts/{artifact_id}`

Serves binary tool output (charts, generated images, PDFs, HTML files)
with the correct `Content-Type`, read from the in-memory artifact store
(1-hour TTL). Returns `404` if the id doesn't exist or has expired. See
[Tools Overview &rarr; Artifacts](../tools/index.md#artifacts-how-binary-output-reaches-the-browser).

```bash
curl http://localhost:8080/api/artifacts/<id> -o chart.png
```

## `executor` service (internal only)

Not reachable from the browser or published on the host -- only from
`backend`, over the isolated `sandbox` network. Documented here for
completeness.

### `GET /health`

### `POST /execute`

**Request:** `{"code": "string", "timeout": 10}` (`timeout` in seconds, capped server-side)

**Response:** `{"output": "...", "exit_code": 0, "timed_out": false, "duration_seconds": 0.5}`

See [Sandboxed Code Execution](../tools/sandbox-exec.md) for the full
isolation model this endpoint sits behind.
