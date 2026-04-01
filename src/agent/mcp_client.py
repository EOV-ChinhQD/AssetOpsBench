import logging
from typing import Any
from pathlib import Path
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp import StdioServerParameters

logger = logging.getLogger(__name__)

# Root of the repo for uv run commands (should be the directory containing pyproject.toml)
REPO_ROOT = Path(__file__).parent.parent.parent

async def call_mcp_tool(server_name: str, tool_name: str, args: dict) -> str:
    """
    Connects to an MCP server and calls a tool, with Redis caching DISABLED.
    """
    # 🟢 REDIS: Temporarily disabled by user request
    # from src.agent.utils.cache import get_tool_cache, set_tool_cache
    # cached_res = get_tool_cache(tool_name, args)
    # if cached_res:
    #      return cached_res

    # Default script path for Hanoi Water server
    script_path = "src/servers/hanoi_water/main.py" if server_name == "hanoi_water-mcp-server" else server_name

    import os
    params = StdioServerParameters(
        command="uv",
        args=["run", script_path],
        cwd=str(REPO_ROOT),
        env=dict(os.environ),
    )
    
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, args)
                text_res = "\n".join(getattr(item, "text", str(item)) for item in result.content)
                
                # 🔵 REDIS: Store valid results (1h TTL) - Disabled
                # if text_res and "error" not in text_res.lower() and "lỗi" not in text_res.lower():
                #     set_tool_cache(tool_name, args, text_res, ttl=3600)
                    
                return text_res
    except Exception as e:
        logger.error(f"Error calling MCP tool {tool_name} on {server_name}: {e}")
        return f"Error: {str(e)}"
