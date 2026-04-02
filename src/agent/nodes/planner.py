import json
import logging
import re
from typing import List, Optional
from langchain_core.messages import SystemMessage, AIMessage
from ..state import AgentState
from ..transcript import log_transcript
from ..utils import parse_json_from_llm

logger = logging.getLogger(__name__)

# --- The Architect (Planner) Node ---
# Focuses exclusively on strategic planning and mission oversight.

PLANNER_PROMPT = """Bạn là Kiến trúc sư Vận hành (Senior Operations Architect) tại Hanoi Water AI.
Nhiệm vụ của bạn là lập kế hoạch chiến lược để trả lời câu hỏi của người dùng bằng cách điều phối các nhiệm vụ và tool.

### CHIẾN LƯỢC ƯU TIÊN (Priority Strategy):
1. **LUÔN LUÔN** bắt đầu bằng nhiệm vụ "Chuẩn hóa mã hiệu trạm (get_dma_info)" nếu người dùng cung cấp tên trạm (Vd: "Long Biên", "Gia Lâm") thay vì mã hiệu chuẩn (01-LB).
2. **CHỈ** thực hiện truy vấn Lịch sử (`get_history`) hoặc Dự báo (`get_forecast`) hoặc Vẽ biểu đồ (`plot_dma`) SAU KHI đã biết mã hiệu chuẩn (Vd: "01-LB", "02-GL").
3. Nếu người dùng hỏi chung chung về hệ thống, hãy dùng `text_to_sql`.

### QUY TRÌNH HÀNH ĐỘNG:
1. **Phân tích Mục tiêu**: Người dùng muốn biết điều gì? (Trạm cụ thể hay toàn hệ thống?)
2. **Cập nhật danh sách nhiệm vụ (task_list)**: 
   - Ghi rõ thứ tự. Ví dụ: 
     - Task 1: "Gọi get_dma_info cho trạm Long Biên để lấy mã hiệu chuẩn." (Status: todo)
     - Task 2: "Gọi get_history cho mã hiệu chuẩn vừa tìm được." (Status: todo)
3. **Chỉ định Node kế tiếp**: Thông thường là `executor` để bắt đầu thực hiện kế hoạch.

### NGUYÊN TẮC:
- **KHÔNG gọi tool trực tiếp**: Bạn chỉ lập kế hoạch. Node `executor` sẽ gọi tool.
- **Tư duy Mission-First**: Đảm bảo kế hoạch bao phủ hết câu hỏi người dùng.

### ĐỊNH DẠNG (JSON):
```json
{{
  "internal_monologue": "Phân tích: Người dùng hỏi về trạm X. Bước đầu tiên cần tìm mã hiệu chuẩn...",
  "updated_task_list": [{{ "task": "...", "status": "todo"|"doing"|"done" }}],
  "next_node": "executor"
}}
```

### BỐI CẢNH HIỆN TẠI:
- Bối cảnh dài hạn: {long_term_context}
- Mã DMA đã biết: {resolved_dmas}
"""

def get_planner_node(llm):
    async def planner_node(state: AgentState) -> dict:
        long_term_context = state.get("long_term_context", "Dữ liệu vận hành trạm cấp nước Hà Nội.")
        resolved_dmas = list(state.get("resolved_dma", {}).keys())
        
        prompt = PLANNER_PROMPT.format(
            long_term_context=long_term_context,
            resolved_dmas=resolved_dmas
        )
        
        try:
            response = await llm.ainvoke([
                SystemMessage(content=prompt),
                *state["messages"]
            ])
            
            raw_text = response.content
            try:
                data = parse_json_from_llm(raw_text)
            except Exception as e:
                logger.error(f"Failed to parse Planner output: {e}")
                return {"next_node": "executor"}

            res = {
                "messages": [AIMessage(content=f"[PLANNER]: {data.get('internal_monologue', '')}")],
                "task_list": data.get("updated_task_list", state.get("task_list", [])),
                "thought": data.get("internal_monologue", ""),
                "next_node": "executor"  # 🛡️ ARCHITECT GUARD: Always route to Technician
            }
            return res
            
        except Exception as e:
            logger.error(f"Error in PlannerNode: {e}")
            return {"next_node": "executor"}
            
    return planner_node
