import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import AgentState

logger = logging.getLogger(__name__)

INTENT_CLASSIFIER_PROMPT = """Bạn là trợ lý ảo hỗ trợ vận hành mạng lưới nước Hà Nội. 
Nhiệm vụ: Phân loại ý định của người dùng để điều hướng xử lý chính xác.

### BỐI CẢNH NÀY QUAN TRỌNG:
{long_term_context}

---
### DANH MỤC Ý ĐỊNH:
1. **GREETING**: Chào hỏi xã giao, cảm ơn, tạm biệt.
2. **GENERAL**: Các câu hỏi chung không liên quan đến dữ liệu (VD: "Bạn là ai?", "Bạn làm được gì?").
3. **GLOBAL**: Hỏi về toàn bộ hệ thống (VD: "Tổng sản lượng?", "Vùng tốt nhất?").
4. **SPECIFIC**: Truy vấn dữ liệu cho 1-3 DMA cụ thể (VD: "Sản lượng 01-LB?").
5. **ANALYTICAL**: Đếm số lượng, thống kê, so sánh nhiều vùng (VD: "Có bao nhiêu DMA?", "Danh sách vùng mã 01?").
6. **HYBRID**: Kết hợp nhiều loại tinh vi.

### QUY TẮC TRẢ VỀ JSON:
{{
  "intent": "GREETING" | "GENERAL" | "GLOBAL" | "SPECIFIC" | "HYBRID",
  "mentioned_dmas": ["tên 1", "tên 2"],
  "requires_lookup": true | false,
  "reason": "Giải thích ngắn gọn"
}}
"""

def get_classify_intent_node(llm):
    async def classify_intent(state: AgentState) -> dict:
        messages = state.get("messages", [])
        long_term_context = state.get("long_term_context", "Không có thông tin profile.")
        user_msg = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_msg = msg.content
                break
        
        if not user_msg:
            return {"intent": "GENERAL", "requires_lookup": False}

        prompt = [
            SystemMessage(content=INTENT_CLASSIFIER_PROMPT.format(long_term_context=long_term_context)),
            HumanMessage(content=f"Câu hỏi: {user_msg}")
        ]
        
        try:
            response = await llm.ainvoke(prompt)
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            logger.info(f"INTENT: {data.get('intent')} | DMAs: {data.get('mentioned_dmas')}")
            
            return {
                "intent": data.get("intent", "GENERAL"),
                "mentioned_dmas": data.get("mentioned_dmas", []),
                "requires_lookup": data.get("requires_lookup", False)
            }
        except Exception as e:
            logger.error(f"Error in classify_intent: {e}")
            return {"intent": "GENERAL", "requires_lookup": False}
            
    return classify_intent
