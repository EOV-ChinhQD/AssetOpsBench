import json
import asyncio
from langchain_core.tools import Tool
from src.api.server.tools.executors.preference_executor import update_user_preference
from src.api.server.tools.contracts import PreferenceUpdateRequest
from src.api.server.deps import get_repo_dep

async def update_preference_async(input_str: str) -> str:
    """Input: key=...,value=..."""
    from src.api.server.agent.tools.historical import parse_tool_input
    params = parse_tool_input(input_str)
    
    key = params.get("key", "").strip()
    value = params.get("value", "")
    
    if not key or not value:
        return "Cần cung cấp key và value."
        
    # Standardize input for known keys (Avoid double wrapping)
    if key == "managed_dmas":
        if isinstance(value, str):
            value = [v.strip().strip("'").strip('"') for v in value.replace("[", "").replace("]", "").split(",")]
        elif isinstance(value, list) and value and isinstance(value[0], str) and "[" in value[0]:
             # Handle nested string from LLM mistakes
             import ast
             try: value = ast.literal_eval(value[0])
             except: pass
        
    req = PreferenceUpdateRequest(key=key, value=value, audit_id="langgraph")
    repo = get_repo_dep()
    
    # We pass allow_write=True for the agent
    res = await update_user_preference(req, repo, user_id="default_user", allow_write=True)
    
    if not res.success:
        return f"Lỗi cập nhật preference: {res.error.message if res.error else 'Unknown'}"
    
    return f"Đã cập nhật preference: {key}={value}"

def update_preference_sync(input_str: str) -> str:
    return asyncio.run(update_preference_async(input_str))

preference_tool = Tool(
    name="update_user_preference",
    description=(
        "Cập nhật sở thích hoặc thông tin định danh của người dùng. "
        "Dùng khi người dùng nói 'Hãy nhớ...', 'Tôi là...', 'Vùng tôi quản lý là...'. "
        "Input: key=...,value=..."
    ),
    func=update_preference_sync,
    coroutine=update_preference_async,
)
