"""
A tiny bundled MCP server (stdio transport) with two trivial tools, used as
the default entry in mcp_servers.json so MCP connectivity works out of the
box with zero external setup. Demonstrates the integration genuinely works
-- real usage means pointing mcp_servers.json at an actual external MCP
server instead (see README: external MCP servers are a trust boundary, the
server defines tools the LLM calls with LLM-generated arguments).
"""

import random
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-server")


@mcp.tool()
def roll_dice(sides: int = 6, count: int = 1) -> str:
    """Roll one or more dice with the given number of sides."""
    rolls = [random.randint(1, sides) for _ in range(count)]
    return f"Rolled {count}d{sides}: {rolls} (total: {sum(rolls)})"


@mcp.tool()
def get_server_time() -> str:
    """Get the current UTC time from this MCP server (not the main backend)."""
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    mcp.run(transport="stdio")
