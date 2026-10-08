"""
Connects to external MCP servers configured in mcp_servers.json and exposes
their tools to the agent, via the official langchain-mcp-adapters package
(verified against the real installed mcp==1.30.0 / langchain-mcp-adapters==
0.3.2 with a bundled demo stdio server before wiring this in).

Security note (also in the README): each connected MCP server defines real
tools the LLM will call with LLM-generated arguments -- the same trust
category as the sandbox executor or any other tool with side effects. Only
point this at MCP servers you trust. mcp_servers.json ships with a single
bundled "demo" entry (a trivial local stdio server with no network access)
so this works with zero setup; add real external servers deliberately.
"""

import json
import logging
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import Settings

logger = logging.getLogger(__name__)


async def load_mcp_tools(settings: Settings) -> list[BaseTool]:
    if not settings.mcp_enabled:
        return []

    config_path = Path(settings.mcp_config_path)
    if not config_path.exists():
        logger.warning("MCP enabled but config file %s not found -- skipping.", config_path)
        return []

    try:
        raw = json.loads(config_path.read_text())
        servers = {k: v for k, v in raw.get("servers", {}).items() if not k.startswith("_")}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not parse %s (%s) -- skipping MCP tools.", config_path, exc)
        return []

    if not servers:
        return []

    try:
        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()
    except Exception as exc:  # noqa: BLE001 - a bad server config must not crash backend startup
        logger.warning("Failed to load MCP tools (%s) -- continuing without them.", exc)
        return []

    logger.info("Loaded %d MCP tool(s) from %d server(s): %s", len(tools), len(servers), [t.name for t in tools])
    return tools
