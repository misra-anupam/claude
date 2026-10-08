# Security

A consolidated view of every trust boundary in this project -- what's
isolated from what, why, and what was actually verified rather than just
configured. Individual tool pages go deeper on their own boundary; this
page is the map.

## Threat model, briefly

The main source of untrusted input is **the LLM's own output** -- not
because the model is adversarial, but because its tool-call arguments and
generated text are effectively user-influenced (a user can ask it to run
arbitrary code, fetch arbitrary URLs, or generate arbitrary markdown/HTML)
and should be treated with the same caution as direct user input at every
point they reach something with real capability.

## Boundary 1: the sandbox executor

The single highest-capability boundary in the system. Full detail:
[Sandboxed Code Execution](tools/sandbox-exec.md). Summary:

- The Docker socket (root-equivalent host access) is mounted into exactly
  one container, `executor`, never into `backend`.
- `executor` sits on an `internal: true` Docker network reachable only from
  `backend` -- confirmed live (`backend` &rarr; `executor` succeeds,
  `frontend` &rarr; `executor` fails to resolve the hostname at all).
- Every code execution runs in a throwaway container with no network, a
  read-only filesystem (except a 16MB tmpfs `/tmp`), a non-root user,
  dropped Linux capabilities, and CPU/memory/PID limits -- each property
  individually confirmed against the real Docker daemon before trusting it
  (see the sandbox page for the actual test output).

## Boundary 2: external MCP servers

Full detail: [External MCP Servers](tools/mcp.md). A connected MCP server
defines real tools the LLM calls with LLM-generated arguments -- the server
author, not the user running this app, decides what that tool actually
does. The bundled default (`mcp_demo_server.py`) is a local, no-network,
two-trivial-tools server specifically so the out-of-box config carries no
real risk. Adding a real external server is an explicit, deliberate step
(editing `mcp_servers.json`), not something that happens by default.

## Boundary 3: rendered markdown (XSS)

Full detail: [Frontend &rarr; Markdown rendering](frontend.md#markdown-rendering).
Model-generated text is rendered as HTML in the browser (headings, code
blocks, etc.) -- `DOMPurify` sanitizes the output of `marked.js` before
insertion via `innerHTML`, confirmed to strip `<script>` tags, event-handler
attributes (`onerror`), and `javascript:` URLs, while leaving legitimate
markdown formatting intact.

## Boundary 4: the calculator's `numexpr` leak

A real, if lower-severity, bug caught during development: `numexpr`'s
default name resolution reads the **calling Python process's own
variables** for any unrecognized identifier in the expression. Full detail
and the fix (`local_dict={}, global_dict={}`):
[Calculator](tools/calculator.md).

## Network segmentation summary

See [Architecture](architecture.md#containers-and-networks) for the full
diagram. The short version: `frontend` only talks to `backend`,
`backend` is the only thing with a path to both `postgres` and `executor`,
and `executor` has no path to anything except the Docker socket it needs
and the requests `backend` sends it.

## What's explicitly out of scope today

This is a single-fixed-user demo (`USER_ID = "default_user"`, no login
system) -- there's no authentication, no per-user data isolation, and the
rate limiter is per-IP rather than per-account. See
[Roadmap](roadmap.md#production-hardening) and
[Roadmap &rarr; SSO login with Google](roadmap.md#sso-login-with-google)
for what a real multi-user deployment would need to add.
