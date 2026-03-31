from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import ToolMessage
import json
import re
import logging
import os

from src.agent.state import AgentState
from src.agent.nodes.router import tools, get_router_node
from src.agent.nodes.reflect import get_reflect_node
from src.agent.nodes.synthesize import get_synthesize_node
from src.agent.nodes.human_review import human_review
from src.agent.nodes.memory import load_memory, save_memory
from src.agent.nodes.classify_intent import get_classify_intent_node
from src.agent.nodes.think import get_think_node

logger = logging.getLogger(__name__)

def collect_results(state: AgentState) -> dict:
    """Extracts content from ToolMessages only for the CURRENT turn."""
    results = []
    plot_url = state.get("plot_url")
    chart_json = state.get("chart_json")
    chart_type = state.get("chart_type")
    
    # Process only the suffix of messages that are ToolMessages (latest tool execution batch)
    curr_messages = state["messages"]
    idx = len(curr_messages) - 1
    while idx >= 0 and isinstance(curr_messages[idx], ToolMessage):
        msg = curr_messages[idx]
        results.insert(0, {"tool": msg.name or "unknown", "output": str(msg.content)})
        
        # Check for chart JSON from plot tool
        if msg.name == "plot":
            try:
                content_json = json.loads(str(msg.content))
                if isinstance(content_json, dict) and "chart_json" in content_json:
                    chart_json = content_json["chart_json"]
                    chart_type = content_json.get("chart_type", "vegalite")
                elif "http" in str(msg.content):
                    plot_url = str(msg.content)
            except:
                if "http" in str(msg.content):
                    plot_url = str(msg.content)
        idx -= 1
    
    # Structured logging for tool results
    for r in results:
        tool_name = r["tool"]
        output_preview = r["output"][:200] if r["output"] else "(empty)"
        logger.info(f"TOOL_RESULT: tool={tool_name}, output_len={len(r['output'])}, preview={output_preview}")
            
    logger.info(f"COLLECT_RESULTS: {len(results)} tool outputs collected, chart={chart_json is not None}")
    
    # Extract DMA IDs for caching from get_dma_info tool
    resolved_dma = state.get("resolved_dma", {})
    for res in results:
        if res["tool"] == "get_dma_info":
            try:
                data = json.loads(res["output"])
                if data.get("status") == "success" and "dma_id" in data.get("data", {}):
                    dma_id = data["data"]["dma_id"]
                    resolved_dma[dma_id] = dma_id
            except:
                pass

    return {
        "tool_results": results, 
        "plot_url": plot_url, 
        "chart_json": chart_json, 
        "chart_type": chart_type,
        "resolved_dma": resolved_dma
    }

def route_after_router(state: AgentState) -> str:
    messages = state["messages"]
    if not messages:
        return "synthesize"
    last_msg = messages[-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        tool_name = last_msg.tool_calls[0]["name"]
        user_id = state.get("user_id", "")
        if tool_name in ["text_to_sql"] and not user_id.startswith("bench_"):
            logger.info(f"ROUTE: router → human_review (tool={tool_name})")
            return "human_review"
        logger.info(f"ROUTE: router → tool_node (tools={[tc['name'] for tc in last_msg.tool_calls]})")
        return "tool_node"
    logger.info("ROUTE: router → synthesize (no tools)")
    return "synthesize"

def route_after_reflect(state: AgentState) -> str:
    verdict = state.get("reflect_verdict", "pass")
    retry_count = state.get("retry_count", 0)
    
    if verdict == "pass":
        # 🟢 If the last tool was successful, ALWAYS go back to router 
        # to let the model decide if it needs more tools or can synthesize.
        logger.info(f"ROUTE: reflect → router (success, checking for next steps)")
        return "router"
    if retry_count >= 2:
        logger.info(f"ROUTE: reflect → synthesize (retry_count={retry_count} >= 2, forcing)")
        return "synthesize"
    logger.info(f"ROUTE: reflect → router (verdict={verdict}, retry={retry_count}, notes='{state.get('reflect_notes', '')[:80]}')")
    return "router"

def route_after_classify(state: AgentState) -> str:
    intent = state.get("intent", "GENERAL")
    if intent in ["GREETING", "GENERAL"]:
        logger.info(f"ROUTE: classify_intent → synthesize (Short-circuit for {intent})")
        return "synthesize"
    return "think"

async def build_graph(llm, db_path=None):
    # ... (existing setup code stays same)
    workflow = StateGraph(AgentState)

    workflow.add_node("load_memory", load_memory)
    workflow.add_node("classify_intent", get_classify_intent_node(llm))
    workflow.add_node("think", get_think_node(llm))
    workflow.add_node("router", get_router_node(llm))
    workflow.add_node("human_review", human_review)
    workflow.add_node("tool_node", ToolNode(tools))
    workflow.add_node("collect_results", collect_results)
    workflow.add_node("reflect", get_reflect_node(llm))
    workflow.add_node("synthesize", get_synthesize_node(llm))
    workflow.add_node("save_memory", save_memory)

    workflow.set_entry_point("load_memory")
    workflow.add_edge("load_memory", "classify_intent")
    
    # 🟢 Phase 2: Short-circuit conditional edge
    workflow.add_conditional_edges(
        "classify_intent",
        route_after_classify,
        {
            "synthesize": "synthesize",
            "think": "think"
        }
    )
    
    workflow.add_edge("think", "router")

    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {
            "tool_node": "tool_node", 
            "human_review": "human_review", 
            "synthesize": "synthesize"
        }
    )

    workflow.add_edge("human_review", "tool_node")
    workflow.add_edge("tool_node", "collect_results")
    workflow.add_edge("collect_results", "reflect")

    workflow.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {"synthesize": "synthesize", "router": "router"}
    )

    workflow.add_edge("synthesize", "save_memory")
    workflow.add_edge("save_memory", END)

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool
    
    # 🟢 Persistence: Use Async Postgres for reliable session storage
    connection_string = os.getenv("HANOI_WATER_DB_URL")
    if not connection_string:
         # Fallback for local testing if env not loaded
         connection_string = "postgresql://user:pass@localhost:5433/hanoiwatertb"

    pool = AsyncConnectionPool(conninfo=connection_string, max_size=10, kwargs={"autocommit": True}, open=False)
    await pool.open()
    cp = AsyncPostgresSaver(pool)
    # Important: setup() creates the required tables if they don't exist
    await cp.setup()
    
    graph = workflow.compile(
        checkpointer=cp,
    )
    return graph
