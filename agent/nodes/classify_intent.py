import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import AgentState

logger = logging.getLogger(__name__)

INTENT_CLASSIFIER_PROMPT = """Bạn là chuyên gia phân tích dữ liệu cấp nước Hà Nội.
Nhiệm vụ của bạn là phân loại câu hỏi của người dùng vào đúng 1 trong 3 nhóm ý định (intent):

1. **GLOBAL**: Hỏi về toàn hệ thống, thống kê chung, không liên quan đến một DMA/khu vực cụ thể.
   - Ví dụ: "Có bao nhiêu DMA?", "Vùng nào tiêu thụ cao nhất?", "Tổng sản lượng tháng 3?"
2. **SPECIFIC**: Hỏi về một hoặc nhiều DMA/vùng có tên hoặc mã cụ thể.
   - Ví dụ: "DMA Hoàng Mai tiêu thụ bao nhiêu?", "So sánh Cầu Giấy và Đống Đa", "Dự báo của 17-TL?"
3. **HYBRID**: Câu hỏi tổng quát nhưng có điều kiện lọc (filter) hoặc cần tra cứu diện rộng.
   - Ví dụ: "Có DMA nào vượt ngưỡng không?", "Các vùng ở quận Ba Đình thế nào?"

HƯỚNG DẪN TRÍCH XUẤT:
- `mentioned_dmas`: Danh sách tên các DMA hoặc khu vực được nhắc đến (ví dụ: ["Hoàng Mai", "Cầu Giấy"]). Bỏ trống nếu là GLOBAL.
- `requires_lookup`: Luôn là TRUE nếu intent là SPECIFIC hoặc HYBRID (để tra cứu ID chính xác).

TRẢ VỀ JSON DUY NHẤT (không giải thích):
{
  "intent": "GLOBAL" | "SPECIFIC" | "HYBRID",
  "mentioned_dmas": ["tên 1", "tên 2"],
  "requires_lookup": true | false,
  "reason": "giải thích ngắn gọn lý do phân loại"
}
"""

def get_classify_intent_node(llm):
    async def classify_intent(state: AgentState) -> dict:
        # Get the original user message (first one in conversation)
        # In a multi-turn, we classify the LATEST human message
        messages = state.get("messages", [])
        user_msg = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_msg = msg.content
                break
        
        if not user_msg:
            return {"intent": "GLOBAL", "requires_lookup": False}

        prompt = [
            SystemMessage(content=INTENT_CLASSIFIER_PROMPT),
            HumanMessage(content=f"Câu hỏi: {user_msg}")
        ]
        
        try:
            response = await llm.ainvoke(prompt)
            # Remove markdown blocks if present
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            logger.info(f"INTENT: {data.get('intent')} | DMAs: {data.get('mentioned_dmas')} | SQL: {data.get('requires_lookup')}")
            
            return {
                "intent": data.get("intent", "GLOBAL"),
                "mentioned_dmas": data.get("mentioned_dmas", []),
                "requires_lookup": data.get("requires_lookup", False)
            }
        except Exception as e:
            logger.error(f"Error in classify_intent: {e}")
            # Fallback to SPECIFIC if uncertain
            return {"intent": "SPECIFIC", "requires_lookup": True, "mentioned_dmas": []}
            
    return classify_intent
