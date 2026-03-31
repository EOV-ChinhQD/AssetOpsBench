import logging
from typing import Any
from pathlib import Path
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters

logger = logging.getLogger(__name__)

# Root of the repo for uv run commands
REPO_ROOT = Path(__file__).parent.parent

async def call_mcp_tool(server_name: str, tool_name: str, args: dict) -> str:
    """
    Connects to an MCP server and calls a tool.
    server_name: name registered in pyproject.toml (e.g. 'hanoi_water-mcp-server')
    """
    params = StdioServerParameters(
        command="uv",
        args=["run", server_name],
        cwd=str(REPO_ROOT),
    )
    
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                return "\n".join(getattr(item, "text", str(item)) for item in result.content)
    except Exception as e:
        logger.error(f"Error calling MCP tool {tool_name} on {server_name}: {e}")
        return f"Error: {str(e)}"
