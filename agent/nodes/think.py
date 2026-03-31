import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from ..state import AgentState

logger = logging.getLogger(__name__)

THINK_PROMPT = """Bạn là chuyên gia phân tích dữ liệu cấp nước Hà Nội (ReActXen mode).
Nhiệm vụ: Suy luận bước tiếp theo và lên kế hoạch chạy công cụ (Tool Plan).

THÔNG TIN QUÁ KHỨ & NGỮ CẢNH:
- Intent: {intent}
- DMA đề cập: {mentioned_dmas}
- Lookup status: {resolved_dma_str}

CÁC CÔNG CỤ (TOOLS) KHẢ DỤNG:
1. `get_dma_info(dma_query)`: LUÔN sử dụng khi intent là SPECIFIC/HYBRID và chưa có ID chính xác trong cache.
2. `get_historical_analysis(dma_id, months)`: Dữ liệu thực tế quá khứ (đến 01/2026).
3. `get_forecast_analysis(dma_id, horizon)`: Dự báo (02-04/2026).
4. `text_to_sql(question)`: Chỉ dùng khi các tool trên không đáp ứng được (vd: Ranking, Aggregate phức tạp).
5. `plot(dma_id)`: Vẽ biểu đồ. Luôn chạy CUỐI CÙNG.

HƯỚNG DẪN SUY LUẬN (Thought):
1. Phân tích câu hỏi cần lấy dữ liệu gì và thời gian nào?
2. Có cần tra cứu mã DMA trước không? (Chưa có ID trong cache -> CẦN).
3. Sau khi lấy được dữ liệu, có cần vẽ biểu đồ không?

TRẢ VỀ JSON DUY NHẤT:
{{
  "thought": "Suy luận chi tiết từng bước bằng tiếng Việt",
  "tool_plan": [
    {{"tool": "tên_tool", "params": {{"p1": "v1"}}, "reason": "Tại sao dùng tool này?"}}
  ],
  "clarification_needed": false,
  "clarification_message": ""
}}
"""

def get_think_node(llm):
    async def think(state: AgentState) -> dict:
        intent = state.get("intent", "GLOBAL")
        mentioned_dmas = state.get("mentioned_dmas", [])
        resolved_dma = state.get("resolved_dma", {})
        messages = state.get("messages", [])
        
        user_msg = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_msg = msg.content
                break

        resolved_dma_str = json.dumps(resolved_dma, ensure_ascii=False) if resolved_dma else "Chưa có ID nào được cache"
        
        context_prompt = THINK_PROMPT.format(
            intent=intent,
            mentioned_dmas=", ".join(mentioned_dmas) if mentioned_dmas else "Không có",
            resolved_dma_str=resolved_dma_str
        )
        
        prompt = [
            SystemMessage(content=context_prompt),
            HumanMessage(content=f"Câu hỏi của người dùng: {user_msg}")
        ]
        
        try:
            response = await llm.ainvoke(prompt)
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            logger.info(f"THOUGHT: {data.get('thought')[:100]}...")
            logger.info(f"PLAN: {[t['tool'] for t in data.get('tool_plan', [])]}")
            
            return {
                "thought": data.get("thought", ""),
                "tool_plan": data.get("tool_plan", [])
            }
        except Exception as e:
            logger.error(f"Error in think node: {e}")
            return {"thought": "Lỗi suy luận, chuyển sang chạy mặc định.", "tool_plan": []}
            
    return think
