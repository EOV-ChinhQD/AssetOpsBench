import json
import logging
from langchain_core.messages import ToolMessage
from src.agent.state import AgentState

logger = logging.getLogger(__name__)

def collect_results(state: AgentState) -> dict:
    """Consolidates ToolMessage results from the latest turn into state."""
    results = []
    messages = state["messages"]
    
    # 1. Backtrack to find all ToolMessages from the latest interaction
    idx = len(messages) - 1
    while idx >= 0 and isinstance(messages[idx], ToolMessage):
        msg = messages[idx]
        tool_name = getattr(msg, 'name', 'unknown') or "unknown"
        results.insert(0, {"tool": tool_name, "output": str(msg.content)})
        idx -= 1
        
    # 2. Extract resolved DMA IDs to the cache
    resolved_dma = state.get("resolved_dma", {})
    for res in results:
        if res["tool"] == "get_dma_info":
            try:
                data = json.loads(res["output"])
                if data.get("status") == "success" and "dma_id" in data.get("data", {}):
                    d_id = data["data"]["dma_id"]
                    resolved_dma[d_id.upper()] = d_id
            except: pass

    logger.info(f"GRAPH_LOGIC: Collected {len(results)} tool outputs")
    return {"tool_results": results, "resolved_dma": resolved_dma}

def route_after_meta(state: AgentState) -> str:
    """Routes after meta-planning: deciding if a retry or synthesis is needed."""
    meta_next = state.get("meta_next_node")
    if meta_next in {"planner", "synthesize"}:
        return meta_next

    verdict = state.get("reflect_verdict", "pass")
    retry_count = state.get("retry_count", 0)

    if verdict == "pass" or retry_count >= 2:
        return "synthesize"
    return "planner"
