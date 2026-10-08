# External MCP Servers

`backend/app/mcp_tools.py` + `backend/mcp_servers.json` + bundled
`backend/mcp_demo_server.py`

The agent can connect to external [Model Context Protocol](https://modelcontextprotocol.io)
servers and treat their tools as real tools the LLM can call -- via the
official `langchain-mcp-adapters` package
(`MultiServerMCPClient(connections).get_tools()`), which converts MCP
tools directly into LangChain `BaseTool` objects.

## Security note

!!! danger "Trust boundary -- read this before adding a real external server"
    Each connected MCP server defines real tools the LLM will call **with
    LLM-generated arguments**. This is the same trust category as the
    sandbox executor: the server author, not you, decides what that tool
    actually does when invoked. Only point `mcp_servers.json` at servers
    you trust. A bad or unreachable entry is caught and skipped with a
    logged warning rather than crashing backend startup -- confirmed by
    testing with an invalid server command.

## Configuration

```json title="backend/mcp_servers.json"
{
  "servers": {
    "demo": {
      "transport": "stdio",
      "command": "python",
      "args": ["mcp_demo_server.py"]
    }
  }
}
```

Three transports are supported (whatever `langchain-mcp-adapters` supports):
`stdio` (local subprocess), `sse`, `streamable_http` (remote, over
network). Adding a real external server means adding an entry with
`transport: "streamable_http"` (or `"sse"`) and a `url`, optionally
`headers` for auth.

## The bundled demo server

Ships with one default entry pointing at `mcp_demo_server.py`, a tiny
local server (via the official `mcp` SDK's `FastMCP`) with two trivial
tools:

```python
@mcp.tool()
def roll_dice(sides: int = 6, count: int = 1) -> str: ...

@mcp.tool()
def get_server_time() -> str: ...
```

This exists so MCP connectivity works with **zero external setup** --
nothing to configure, no API key, no network call, just to prove the
integration is real rather than theoretical.

## Loading: graceful by design

```python
async def load_mcp_tools(settings: Settings) -> list[BaseTool]:
    if not settings.mcp_enabled:
        return []
    ...
    try:
        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()
    except Exception as exc:
        logger.warning("Failed to load MCP tools (%s) -- continuing without them.", exc)
        return []
    return tools
```

A connection failure here never takes down the backend -- it's caught,
logged, and the agent simply starts with one fewer tool.

## Result shape: content blocks, not plain strings

MCP tool results come back through `langchain-mcp-adapters` as a list of
typed content blocks (`[{"type": "text", "text": "...", "id": "..."}]`),
not a plain string like every other tool in this project. The frontend's
`tool_result` handler detects this shape specifically and joins the
`.text` fields for display, rather than dumping raw JSON -- see
[Frontend](../frontend.md#structured-tool-results).

## Verified behavior

A real turn asked the agent to use both bundled tools at once ("roll three
20-sided dice, and tell me what time the MCP server thinks it is") -- the
model called both in parallel, both results came back in the expected
content-block shape, and the model correctly interpreted and presented
both.

Before wiring anything into the main app, the exact same
`MultiServerMCPClient` flow was verified standalone (connect, list tools,
invoke each) against the real installed `mcp==1.30.0` /
`langchain-mcp-adapters==0.3.2` packages.
