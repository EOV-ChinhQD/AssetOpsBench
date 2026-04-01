import os
import json
import logging
from datetime import datetime
from src.agent.state import AgentState

logger = logging.getLogger(__name__)

async def log_transcript(state: AgentState, node_name: str):
    """
    Saves a detailed transcript of the agent's internal state to a JSONL file.
    Follows S75 Session Retrieval proposal.
    """
    log_dir = "logs/transcripts"
    os.makedirs(log_dir, exist_ok=True)
    
    # Use thread_id or generate a session ID
    session_id = state.get("thread_id", "default_session")
    log_file = os.path.join(log_dir, f"{session_id}.jsonl")
    
    # Extract latest message and internal monologue
    latest_msg = state["messages"][-1] if state["messages"] else None
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "node": node_name,
        "internal_monologue": state.get("internal_monologue", ""),
        "next_node": state.get("next_node", ""),
        "message_type": type(latest_msg).__name__ if latest_msg else "None",
        "content_snippet": str(latest_msg.content)[:200] if latest_msg else ""
    }
    
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to log transcript: {e}")
