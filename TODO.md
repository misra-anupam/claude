# Future work

Not implemented yet -- tracked here deliberately, not built.

- **File upload** -- let the user attach files (images, PDFs, text) to a
  message for the agent to read, not just generate.
- **MLflow tracing** -- structured tracing/observability for agent runs
  (token usage, tool-call latency, per-turn cost) beyond the current
  backend logs.
- **Production hardening** -- auth beyond the single-fixed-user model,
  secrets management, structured logging/metrics, graceful shutdown,
  resource limits tuned for real load (current setup is demo-scoped).
- **Audio mode** -- voice input/output for the chat.
- **Caching** -- broader than the existing per-tool TTL caches: e.g.
  prompt/response caching, semantic caching across similar queries.
- **Project segregation** -- multi-tenant/workspace separation (today
  everything is one fixed user with no isolation between conversations
  beyond thread_id).
- **Kubernetes deployment guide** -- a `k8s/` manifest set (the sandbox
  executor's Docker-socket approach would need to become a Jobs-via-RBAC
  model instead -- see earlier design discussion in this session).
- **SSO login with Google** -- real authentication, replacing the
  single-fixed-user assumption throughout (memory store, conversation
  list, rate limiting).
- **Access memories** -- a UI to browse/edit/delete what's been saved via
  `save_memory`, instead of only the agent reading/writing them.
- **Scheduled runs** -- let the agent (or a specific prompt) run on a
  schedule rather than only in response to a live chat message.
- **Remote access/execution** -- expose the agent (or the sandbox
  executor) for programmatic/remote invocation beyond the chat UI.
