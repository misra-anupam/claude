# Roadmap

Deliberately not built, tracked explicitly rather than left implicit. This
page mirrors [`TODO.md`](https://github.com/misra-anupam/claude/blob/master/TODO.md)
at the repo root, with more detail where a design direction was already
discussed.

## File upload

Let the user attach files (images, PDFs, text) to a message for the agent
to read, not just generate. Today the agent can *produce* images/PDFs/HTML
([Charts & Diagrams](tools/charts-diagrams.md),
[Image Generation](tools/image-generation.md),
[Documents](tools/documents.md)) but can't accept them as input.

## MLflow tracing

Structured tracing/observability for agent runs -- token usage, tool-call
latency, per-turn cost -- beyond the current plain backend logs.

## Production hardening

Auth beyond the single-fixed-user model, secrets management, structured
logging/metrics, graceful shutdown, resource limits tuned for real load.
The current setup is demo-scoped throughout -- see
[Security &rarr; What's explicitly out of scope today](security.md#whats-explicitly-out-of-scope-today).

## Audio mode

Voice input/output for the chat.

## Caching

Broader than the existing per-tool `TTLCache`s (see
[Resilience](backend/resilience.md#caching)): prompt/response caching,
semantic caching across similar queries.

## Project segregation

Multi-tenant/workspace separation. Today everything is one fixed user
(`USER_ID = "default_user"`) with no isolation between conversations
beyond `thread_id` -- see [Long-Term Memory](tools/memory.md#user-scoped-not-thread-scoped).

## Kubernetes deployment guide

A `k8s/` manifest set. This isn't a lift-and-shift of
`docker-compose.yml` -- the sandbox executor's Docker-socket approach (see
[Sandboxed Code Execution](tools/sandbox-exec.md)) doesn't translate
directly, since mounting the **host's** container runtime socket into a
pod is a worse privilege-escalation vector in a multi-tenant cluster (it
would hand that pod control over every container on that node, not just
its own).

The K8s-native equivalent, mapped field-by-field against what
`executor/app/sandbox.py` actually does today:

| Compose/Docker concept | Kubernetes equivalent |
|---|---|
| Docker socket mount | A narrowly-scoped RBAC `Role` (not `ClusterRole`) in one dedicated namespace, granting only `create`/`get`/`delete` on `pods`/`jobs` -- `executor`'s `ServiceAccount` creates a `Job` per execution via the K8s API instead of a sibling container via the socket |
| `network_disabled=True` | A default-deny `NetworkPolicy` on the sandbox namespace (requires a CNI that enforces NetworkPolicy -- Calico/Cilium do, plain kubenet doesn't) |
| `read_only=True` + tmpfs `/tmp` | `securityContext.readOnlyRootFilesystem: true` + an `emptyDir` volume (`medium: Memory`) mounted at `/tmp` |
| `user="65534:65534"` | `securityContext.runAsUser/runAsGroup: 65534`, `runAsNonRoot: true` |
| `cap_drop=["ALL"]` | `securityContext.capabilities.drop: ["ALL"]` |
| `security_opt=["no-new-privileges"]` | `securityContext.allowPrivilegeEscalation: false` |
| `mem_limit` / `nano_cpus` | `resources.limits.memory` / `.cpu` |
| in-container `timeout` + SDK-level wait | in-container `timeout` (keep it) + `activeDeadlineSeconds` on the `Job` |
| `container.remove(force=True)` | `ttlSecondsAfterFinished` on the `Job` |
| `pids_limit=64` | **No clean per-Pod native equivalent** -- PID limiting in K8s is generally a kubelet-level flag (`--pod-max-pids`), not a Pod spec field. Flagged honestly as a gap rather than claiming parity. |

For genuinely untrusted/LLM-generated code in a multi-tenant cluster, the
hardening above (shared with every default Pod) still shares the host
kernel -- the same category of risk that's motivated real container-escape
CVEs historically. The production answer is usually
`spec.runtimeClassName: gvisor` (or Kata Containers) on the sandbox Job
template, adding a second, kernel-level isolation layer (gVisor intercepts
syscalls via a user-space kernel; Kata runs each pod in a lightweight VM)
specifically because this is the "I don't trust this input at all" use
case.

## SSO login with Google

Real authentication, replacing the single-fixed-user assumption
throughout -- the memory store, conversation list, and rate limiter would
all need to become user-scoped rather than globally shared.

## Access memories

A UI to browse/edit/delete what's been saved via `save_memory`, instead of
only the agent reading/writing them -- see
[Long-Term Memory](tools/memory.md#verified-behavior).

## Scheduled runs

Let the agent (or a specific prompt) run on a schedule rather than only in
response to a live chat message.

## Remote access/execution

Expose the agent (or the sandbox executor) for programmatic/remote
invocation beyond the chat UI.
