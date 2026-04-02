import json
import uuid
import logging
import asyncio
from typing import List, Optional
from langchain_core.messages import ToolMessage
from src.agent.state import AgentState
from src.agent.services.registry import registry
from src.agent.tools.definitions import tools

logger = logging.getLogger(__name__)

class ToolExecutorNode:
    """
    ROUTER (Node): Executes multiple tools in parallel with auto-canonicalization.
    """
    def __init__(self, registry=registry):
        self.registry = registry
        self._semaphores = {}

    async def __call__(self, state: AgentState) -> dict:
        messages = state.get("messages", [])
        if not messages or not hasattr(messages[-1], "tool_calls") or not messages[-1].tool_calls:
            return {}

        last_msg = messages[-1]
        
        # 1. Normalization (DMA ID Synchronization)
        lookup_candidates = self._get_lookup_candidates(last_msg.tool_calls, state)
        lookup_results = await self._auto_lookup(state, lookup_candidates)
        normalized_calls = self._normalize_calls(last_msg.tool_calls, state)

        # 2. Parallel Execution
        tasks = []
        for tc in normalized_calls:
            tool = self.registry.get_tool(tc["name"])
            if tool:
                tasks.append(self._invoke_tool(tool, tc["args"], tc["id"]))
            else:
                logger.error(f"ROUTER: Tool {tc['name']} not found.")

        gathered = await asyncio.gather(*tasks) if tasks else []
        return {"messages": lookup_results + gathered}

    async def _invoke_tool(self, tool, args, tc_id):
        try:
            res = await tool.ainvoke(args)
            return ToolMessage(content=str(res), tool_call_id=tc_id, name=tool.name)
        except Exception as e:
            return ToolMessage(content=f"Error: {e}", tool_call_id=tc_id, name=tool.name)

    def _get_lookup_candidates(self, calls, state) -> List[str]:
        resolved = state.get("resolved_dma", {})
        from src.agent.services.global_registry import global_dma_registry
        
        candidates = []
        for tc in calls:
            q = tc.get("args", {}).get("dma_query") or tc.get("args", {}).get("dma_id")
            if not q: continue
            
            q_str = str(q).upper()
            if q_str not in resolved:
                # Check Global Cache
                global_id = global_dma_registry.get(q_str)
                if global_id:
                    logger.info(f"ROUTER: Global cache hit for {q_str} -> {global_id}")
                    resolved[q_str] = global_id
                else:
                    candidates.append(str(q))
        return list(set(candidates))

    async def _auto_lookup(self, state, candidates) -> List[ToolMessage]:
        if not candidates: return []
        tool = self.registry.get_tool("get_dma_info")
        results = []
        for q in candidates:
            msg = await self._invoke_tool(tool, {"dma_query": q}, str(uuid.uuid4()))
            self._update_state_cache(state, q, msg)
            results.append(msg)
        return results

    def _update_state_cache(self, state, query, msg):
        resolved = state.setdefault("resolved_dma", {})
        from src.agent.services.global_registry import global_dma_registry
        try:
            data = json.loads(str(msg.content))
            if data.get("status") == "success":
                dma_id = data.get("data", {}).get("dma_id")
                if dma_id:
                    resolved[query.upper()] = dma_id
                    resolved[dma_id.upper()] = dma_id
                    # Update Global Registry
                    global_dma_registry.update(query, dma_id)
        except: pass

    def _normalize_calls(self, calls, state) -> List[dict]:
        resolved = state.get("resolved_dma", {})
        normalized = []
        for tc in calls:
            args = dict(tc.get("args", {}))
            # Inject canonical ID if found in cache
            q = args.get("dma_id") or args.get("dma_query")
            if q and q.upper() in resolved:
                args["dma_id"] = resolved[q.upper()]
            normalized.append({"name": tc["name"], "args": args, "id": tc["id"]})
        return normalized

# Dynamic Routing logic
def route_after_core_with_permissions(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages: return "synthesize"
    
    last_msg = messages[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        # Check permissions
        for tc in last_msg.tool_calls:
            meta = registry.get_metadata(tc["name"])
            if meta and meta.requires_permission:
                return "human_review"
        return "tool_node"

    next_node = state.get("next_node", "synthesize")
    if next_node in {"tools", "tool_node"}: return "tool_node"
    if next_node in {"end", "response"}: return "synthesize"
    return next_node
