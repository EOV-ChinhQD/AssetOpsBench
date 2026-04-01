import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from src.agent.state import AgentState

logger = logging.getLogger(__name__)

THINK_PROMPT = """Bạn là chuyên gia phân tích dữ liệu cấp nước Hà Nội (Hanoi Water AI Analyst).
Nhiệm vụ: Phân tích yêu cầu và lập kế hoạch thực thi công cụ (Tool Plan).

--- 
### NGỮ CẢNH HỆ THỐNG:
- Thông tin người dùng: {long_term_context}
- Intent: {intent}
- DMA hiện tại: {mentioned_dmas}
- ID xác minh: {resolved_dma_str}

---
### QUY TẮC PHẢI TUÂN THỦ (CRITICAL):
Hệ thống chạy theo 2 GIAI ĐOẠN (Phải tách biệt):

GIAI ĐOẠN 1: XÁC THỰC DMA
- LUÔN gọi `get_dma_info(dma_query)` đầu tiên nếu người dùng hỏi về MỘT khu vực/DMA cụ thể duy nhất.
- NGOẠI LỆ: Nếu là câu hỏi tổng hợp (đếm số lượng, tìm danh sách nhiều DMA): Dùng ngay `text_to_sql`.
- KHÔNG ĐƯỢC gọi `get_history` hay `plot_dma` nếu chưa có mã hiệu chuẩn từ tool này.

GIAI ĐOẠN 2: TRÍCH XUẤT & XỬ LÝ
- DỮ LIỆU LỊCH SỬ: Dùng `get_history(dma_id, months, year, month)`.
- DỮ LIỆU DỰ BÁO: Dùng `get_forecast(dma_id, horizon)`.
- SQL PHỨC TẠP: Dùng `text_to_sql(question)`.
- VẼ BIỂU ĐỒ: Dùng `plot_dma(dma_id, include_forecast=True)`. LƯU Ý: Tool này TỰ LẤY DỮ LIỆU từ database, bạn KHÔNG cần gọi `get_history` trước khi gọi cái này.

VÍ DỤ 1: Q: "Sản lượng 06-QM tháng 10/2024?" -> Plan: ["get_dma_info", "get_history"]
VÍ DỤ 2: Q: "Dự báo 01-LB tháng 4/2026?" -> Plan: ["get_dma_info", "get_forecast"]
VÍ DỤ 3: Q: "Vẽ biểu đồ cho 01-LB." -> Plan: ["plot_dma"]
VÍ DỤ 4: Q: "Có bao nhiêu DMA mã 01?" -> Plan: ["text_to_sql"]

TRẢ VỀ JSON:
{{
  "thought": "Suy luận...",
  "tool_plan": ["get_dma_info", "get_forecast"]
}}
"""

def get_golden_examples():
    """Fetch recent successful examples from the DB for few-shot learning."""
    from src.hanoi_water_db import get_engine
    from sqlalchemy import text
    engine = get_engine()
    if not engine: return ""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT question_pattern, thought, tool_chain FROM app.golden_trajectories LIMIT 3"))
            examples = []
            for r in rows:
                examples.append(f"VÍ DỤ:\nQ: {r[0]}\nThought: {r[1]}\nPlan: {json.dumps(r[2], ensure_ascii=False)}")
            return "\n\n".join(examples)
    except: return ""

def get_think_node(llm):
    async def think(state: AgentState) -> dict:
        from src.agent.utils.cache import get_thought_cache, set_thought_cache
        
        intent = state.get("intent", "GLOBAL")
        mentioned_dmas = state.get("mentioned_dmas", [])
        resolved_dma = state.get("resolved_dma", {})
        long_term_context = state.get("long_term_context", "Profile chưa sẵn sàng.")
        user_id = state.get("user_id", "default_user")
        messages = state.get("messages", [])
        
        user_msg = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_msg = msg.content
                break
        
        # 🟢 REDIS: Check for cached thought plan
        cached_plan = get_thought_cache(user_id, user_msg)
        if cached_plan and state.get("retry_count", 0) == 0:
             return cached_plan

        resolved_dma_str = json.dumps(resolved_dma, ensure_ascii=False) if resolved_dma else "Trống"
        examples = get_golden_examples()
        
        context_prompt = THINK_PROMPT.format(
            long_term_context=long_term_context,
            intent=intent,
            mentioned_dmas=", ".join(mentioned_dmas) if mentioned_dmas else "Không có",
            resolved_dma_str=resolved_dma_str
        )
        
        prompt = [
            SystemMessage(content=f"{context_prompt}\n\n### CÁC TÌNH HUỐNG MẪU (GOLDEN TRAJECTORIES):\n{examples}"),
            HumanMessage(content=f"Yêu cầu: {user_msg}")
        ]
        
        try:
            response = await llm.ainvoke(prompt)
            content = response.content
            # JSON parsing logic...
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            logger.info(f"THOUGHT: {data.get('thought')[:100]}...")
            
            result = {
                "thought": data.get("thought", ""),
                "tool_plan": data.get("tool_plan", [])
            }
            
            # 🔵 REDIS: Store the successful plan
            if result["tool_plan"] and state.get("retry_count", 0) == 0:
                set_thought_cache(user_id, user_msg, result)
                
            return result
        except Exception as e:
            logger.error(f"Error in think node: {e}")
            return {"thought": "Lỗi suy luận, chờ phản hồi hệ thống.", "tool_plan": []}
            
    return think
