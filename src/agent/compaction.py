import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from .state import AgentState

logger = logging.getLogger(__name__)

# Structured compaction prompt for better summary quality
COMPACT_PROMPT = """Bạn là chuyên gia nén ngữ cảnh cho Agent Cấp nước Hà Nội.
Tóm tắt hội thoại bên dưới theo đúng format:

[DMA ĐÃ TRA CỨU]: Liệt kê các mã DMA đã được đề cập (Vd: 01-LB, 06-QM)
[DỮ LIỆU ĐÃ LẤY]: Tóm tắt kết quả chính (sản lượng, dự báo, biểu đồ)
[TÓM TẮT]: Tóm tắt ngắn gọn nội dung hội thoại (2-3 câu)
[VẤN ĐỀ CÒN MỞ]: Câu hỏi nào chưa được trả lời?
"""

# Estimate ~4 chars per token for Vietnamese text
CHARS_PER_TOKEN = 4
MAX_CONTEXT_CHARS = 12000  # ~3000 tokens, safe for most models

def _estimate_chars(messages) -> int:
    """Estimate total character count of messages."""
    return sum(len(str(m.content)) for m in messages if hasattr(m, 'content'))

def truncate_tool_outputs(messages: list, max_len: int = 5000) -> list:
    """Layer 1: Truncate large tool results to save context window."""
    new_messages = []
    for m in messages:
        if isinstance(m, ToolMessage) and len(str(m.content)) > max_len:
            logger.info(f"TRUNCATION: Shortening output for tool {m.name}")
            new_content = str(m.content)[:max_len] + "... [TRUNCATED]"
            new_messages.append(ToolMessage(content=new_content, tool_call_id=m.tool_call_id, name=m.name))
        else:
            new_messages.append(m)
    return new_messages

def micro_compact(messages: list, keep_recent: int = 10) -> list:
    """Layer 2: A 'cheap' no-LLM compaction that removes tool outputs older than keep_recent."""
    if len(messages) <= keep_recent + 5:
        return messages
    
    logger.info(f"MICRO_COMPACT: Dropping details from {len(messages) - keep_recent} older messages")
    # Keep the first message (usually System) and the last N messages
    return [messages[0]] + messages[-keep_recent:]

async def auto_compact(state: AgentState, llm, threshold: int = 15) -> dict:
    """Token-aware compaction with structured summaries."""
    messages = state.get("messages", [])
    if not messages:
        return {}
    
    total_chars = _estimate_chars(messages)
    msg_count = len(messages)
    
    # Layer 1: Strategic Truncation (Always apply to very large messages)
    messages = truncate_tool_outputs(messages)
    
    # Trigger compaction based on EITHER message count OR estimated token usage
    if msg_count <= threshold and total_chars <= MAX_CONTEXT_CHARS:
        return {"messages": messages} # Return messages even if not summarized (for truncation)

    # Layer 2: Micro-compaction (Fast, no-LLM)
    # If we are just slightly over threshold, try micro-compact first
    if msg_count > threshold and msg_count < threshold * 2:
        return {"messages": micro_compact(messages, keep_recent=threshold)}
    keep_count = 5
    to_compact = messages[:-keep_count]
    keep = messages[-keep_count:]
    
    trigger = f"msgs={msg_count}" if msg_count > threshold else f"chars={total_chars}"
    logger.info(f"COMPACTION triggered ({trigger}): compressing {len(to_compact)} messages")
    
    try:
        # Serialize messages for LLM summarization
        compact_text = []
        for m in to_compact:
            role = getattr(m, 'type', 'unknown')
            content = str(m.content)[:500]  # Cap individual message length
            compact_text.append(f"[{role}]: {content}")
        
        summary_response = await llm.ainvoke([
            SystemMessage(content=COMPACT_PROMPT),
            HumanMessage(content="\n".join(compact_text))
        ])
        
        summary = summary_response.content or ""
        
        # Ensure proper format
        if "[TÓM TẮT]:" not in summary:
            summary = f"[TÓM TẮT]: {summary}"
            
        compact_msg = SystemMessage(content=f"[CONTEXT_COMPACTED]\n{summary}")
        
        logger.info(f"COMPACTION done: {len(to_compact)} msgs → 1 summary ({len(summary)} chars)")
        return {
            "messages": [compact_msg] + keep,
            "compact_boundary": len(messages)
        }
    except Exception as e:
        logger.error(f"Compaction failed: {e}")
        # Fallback: simple truncation if LLM fails
        if msg_count > threshold * 2:
            logger.warning("Fallback: hard truncation")
            return {"messages": messages[-threshold:], "compact_boundary": len(messages)}
        return {}
