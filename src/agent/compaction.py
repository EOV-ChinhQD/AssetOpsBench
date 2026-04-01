import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from .state import AgentState

logger = logging.getLogger(__name__)

COMPACT_PROMPT = """Bạn là chuyên gia nén ngữ cảnh. 
Nhiệm vụ của bạn là tóm tắt các cuộc hội thoại cũ thành một đoạn văn ngắn gọn nhưng đầy đủ các chi tiết kỹ thuật (Mã DMA, kết quả truy vấn, các bước đã thực hiện).

Hãy viết tóm tắt dưới dạng: "[CONTEXT_SUMMARY]: <Nội dung tóm tắt>"
"""

async def auto_compact(state: AgentState, llm, threshold: int = 15) -> dict:
    """Tự động nén tin nhắn nếu số lượng tin nhắn vượt quá threshold."""
    messages = state.get("messages", [])
    
    if len(messages) <= threshold:
        return {}

    # Xác định phần cần nén (ví dụ nén 1/2 số tin nhắn cũ)
    to_compact = messages[:-5] # Giữ lại 5 tin nhắn cuối cùng để làm bối cảnh trực tiếp
    keep = messages[-5:]
    
    logger.info(f"COMPACTION: Compressing {len(to_compact)} messages. Threshold={threshold}")
    
    # Gọi LLM để tóm tắt
    summary_response = await llm.ainvoke([
        SystemMessage(content=COMPACT_PROMPT),
        HumanMessage(content=str(to_compact))
    ])
    
    summary_content = summary_response.content
    if "[CONTEXT_SUMMARY]:" not in summary_content:
        summary_content = f"[CONTEXT_SUMMARY]: {summary_content}"
        
    # Tạo tin nhắn System đại diện cho boundary
    compact_boundary_msg = SystemMessage(content=summary_content)
    
    # Trả về state mới với danh sách tin nhắn đã nén
    return {
        "messages": [compact_boundary_msg] + keep,
        "compact_boundary": len(messages) # Đánh dấu vị trí đã nén
    }
