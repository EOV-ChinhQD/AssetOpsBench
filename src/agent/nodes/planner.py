import json
import logging
import re
from typing import List, Optional
from langchain_core.messages import SystemMessage, AIMessage
from ..state import AgentState
from ..transcript import log_transcript

logger = logging.getLogger(__name__)

# --- The Architect (Planner) Node ---
# Focuses exclusively on strategic planning and mission oversight.

PLANNER_PROMPT = """Bạn là Kiến trúc sư Vận hành (Senior Operations Architect) tại Hanoi Water AI.
Nhiệm vụ của bạn là phân tích yêu cầu của người dùng, phá vỡ nó thành các nhiệm vụ cụ thể (task_list) và điều phối các bước thực hiện.

### QUY TRÌNH HÀNH ĐỘNG:
1. **Phân tích Mục tiêu**: Người dùng muốn biết điều gì về mạng lưới cấp nước Hà Nội?
2. **Quản lý Nhiệm vụ (task_list)**: 
   - CẬP NHẬT danh sách các nhiệm vụ cần làm.
   - Mỗi nhiệm vụ phải cụ thể (Vd: "Tra cứu thông tin trạm Long Biên", "Lấy dữ liệu sản lượng thực tế tháng 10").
3. **Chỉ định Hành động**: Sau khi lập kế hoạch, hãy chuyển sang node `executor` để thực hiện nhiệm vụ đầu tiên.

### NGUYÊN TẮC:
- **KHÔNG gọi tool trực tiếp**: Bạn chỉ lập kế hoạch. Node `executor` sẽ gọi tool.
- **Tư duy Mission-First**: Tập trung vào việc hoàn thành toàn bộ yêu cầu của người dùng.

### ĐỊNH DẠNG (JSON):
```json
{{
  "internal_monologue": "Suy nghĩ chiến lược...",
  "updated_task_list": [{{ "task": "...", "status": "todo"|"doing"|"done" }}],
  "next_node": "executor" hoặc "synthesize"
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
            # Extract JSON
            json_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
            data_str = json_match.group(1).strip() if json_match else raw_text.strip()
            
            try:
                 data = json.loads(data_str)
            except:
                 data = json.loads(re.search(r"\{.*\}", data_str, re.DOTALL).group(0))

            res = {
                "messages": [AIMessage(content=f"[PLANNER]: {data.get('internal_monologue', '')}")],
                "task_list": data.get("updated_task_list", state.get("task_list", [])),
                "thought": data.get("internal_monologue", ""),
                "next_node": data.get("next_node", "executor")
            }
            return res
            
        except Exception as e:
            logger.error(f"Error in PlannerNode: {e}")
            return {"next_node": "executor"}
            
    return planner_node
