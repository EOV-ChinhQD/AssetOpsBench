import logging
import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from src.agent.state import AgentState
from src.agent.nodes.planner import get_planner_node
from src.agent.nodes.executor import get_executor_node
from src.agent.nodes.reflect import get_reflect_node
from src.agent.nodes.synthesize import get_synthesize_node
from src.agent.nodes.human_review import human_review
from src.agent.nodes.memory import load_memory, save_memory
from src.agent.nodes.meta_planner import get_meta_planner_node
from src.agent.nodes.router import ToolExecutorNode, route_after_core_with_permissions
from src.agent.nodes.graph_logic import collect_results, route_after_meta
from src.agent.tools.definitions import tools

logger = logging.getLogger(__name__)

async def build_graph(llm, db_path=None):
    """
    CLEAN ARCHITECTURE: LangGraph Orchestration entry point.
    """
    workflow = StateGraph(AgentState)

    # 1. Register Core Nodes
    workflow.add_node("load_memory", load_memory)
    workflow.add_node("planner", get_planner_node(llm))
    workflow.add_node("executor", get_executor_node(llm, tools))
    workflow.add_node("tool_node", ToolExecutorNode())
    workflow.add_node("collect_results", collect_results)
    workflow.add_node("reflect", get_reflect_node(llm))
    workflow.add_node("meta_planner", get_meta_planner_node(llm))
    workflow.add_node("synthesize", get_synthesize_node(llm))
    workflow.add_node("save_memory", save_memory)
    workflow.add_node("human_review", human_review)

    # 2. Sequential Edges
    workflow.set_entry_point("load_memory")
    workflow.add_edge("load_memory", "planner")
    workflow.add_edge("human_review", "tool_node")
    workflow.add_edge("tool_node", "collect_results")
    workflow.add_edge("collect_results", "reflect")
    workflow.add_edge("reflect", "meta_planner")
    workflow.add_edge("synthesize", "save_memory")
    workflow.add_edge("save_memory", END)

    # 3. Dynamic Conditional Edges
    workflow.add_conditional_edges(
        "planner",
        route_after_core_with_permissions,
        {
            "executor": "executor",
            "tool_node": "tool_node",
            "human_review": "human_review",
            "synthesize": "synthesize"
        }
    )

    workflow.add_conditional_edges(
        "executor",
        route_after_core_with_permissions,
        {
            "tool_node": "tool_node",
            "human_review": "human_review",
            "synthesize": "synthesize"
        }
    )

    workflow.add_conditional_edges(
        "meta_planner",
        route_after_meta,
        {
            "synthesize": "synthesize", 
            "planner": "planner"
        }
    )

    # 4. Persistence (Postgres)
    connection_string = os.getenv("HANOI_WATER_DB_URL") or "postgresql://user:pass@localhost:5433/hanoiwatertb"
    pool = AsyncConnectionPool(conninfo=connection_string, max_size=10, kwargs={"autocommit": True}, open=False)
    await pool.open()
    
    cp = AsyncPostgresSaver(pool)
    await cp.setup()
    
    return workflow.compile(checkpointer=cp)
