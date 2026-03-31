from typing import TypedDict, Annotated, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

def add_results(left: list, right: list):
    if not left: return right
    if not right: return left
    return left + right

class AgentState(TypedDict):
    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]
    thread_id: str
    user_id: str

    # Intent Classification (New from ReActXen)
    intent: Optional[str]           # GLOBAL | SPECIFIC | HYBRID
    mentioned_dmas: list[str]       # Raw names from query
    requires_lookup: bool           # True if lookup tool needed
    
    # Reasoning (Think-before-Act)
    thought: Optional[str]          # Explicit reasoning
    tool_plan: list[dict]           # Sequence of tools to execute

    # Tool execution
    tool_results: list[dict]
    pending_confirm: bool       # flag cho human-in-loop
    pending_sql: Optional[str]   # SQL generated/pending for review
    pending_question: Optional[str] # Original question for pending SQL
    plot_url: Optional[str]
    chart_json: Optional[dict]   # Vega-Lite / Plotly JSON
    chart_type: Optional[str]    # "vegalite" | "plotly"

    # Reflection
    retry_count: int            # số lần reflect đã chạy
    reflect_verdict: str        # "pass" | "retry"
    reflect_notes: str          # lý do retry, hint cho router

    # Context từ long-term memory
    long_term_context: str      # inject vào đầu conversation
    resolved_dma: dict          # Cache mã DMA đã xác thực: {query: id}

    # Error handling
    error: Optional[str]
