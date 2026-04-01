from typing import TypedDict, Annotated, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

def add_results(left: list, right: list):
    if not left: return right
    if not right: return left
    return left + right

class AgentState(TypedDict):
    # Core Loop (Message-centric)
    messages: Annotated[list[BaseMessage], add_messages]
    thread_id: str
    user_id: str

    # Planning & Task System (s03 / s07 style)
    is_planning: bool               # True if agent is in "Plan Mode"
    task_list: list[dict]           # [{ "task": str, "status": "todo"|"doing"|"done" }]
    current_task_id: int            # Pointer to the current task
    
    # Decision & Thinking (Replaces hardcoded intent/think stages)
    thought: Optional[str]          # [INTERNAL_MONOLOGUE] - Hidden reasoning for the agent
    tool_plan: list[str]            # Sequence of tools to execute (optional hint)
    next_node: str                  # Dynamically decided by LLM: 'tools' | 'synthesize' | 'human_review'
    
    # Tool execution & Data
    tool_results: list[dict]
    plot_url: Optional[str]
    chart_json: Optional[dict]
    chart_type: Optional[str]

    # Context & Persistent Memory
    long_term_context: str
    resolved_dma: dict              # Cache: {query: id}
    
    # Compaction & Boundary
    compact_boundary: int           # Index for context compaction
    
    # State Management
    retry_count: int
    reflect_verdict: str            # "pass" | "retry"
    reflect_notes: str
    
    # Error handling
    error: Optional[str]
