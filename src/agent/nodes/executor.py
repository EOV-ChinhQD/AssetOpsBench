import json
import logging
import re
import uuid
from typing import List, Optional
from langchain_core.messages import SystemMessage, AIMessage
from ..state import AgentState
from ..utils import parse_json_from_llm

logger = logging.getLogger(__name__)

# --- The Technician (Executor) Node ---
# Focuses exclusively on tactical tool selection and high-precision execution.

EXECUTOR_PROMPT = """Bạn là Kỹ thuật viên Vận hành (Senior Operations Technician) tại Hanoi Water AI.
Nhiệm vụ: Thực hiện các bước trong kế hoạch (task_list) bằng cách gọi các công cụ (tools) một cách chính xác.

### NHIỆM VỤ HIỆN TẠI (TASK_LIST):
{task_list_str}

### QUY TRÌNH HÀNH ĐỘNG:
1. **Phân tích Nhiệm vụ**: Xem mục tiêu hiện tại là gì? 
2. **Chọn Tool**: Chọn các tool phù hợp nhất để trả lời các phần còn thiếu. 
3. **Thực thi Song song**: Tận dụng `asyncio.gather` bằng cách gọi nhiều tool cùng lúc nếu chúng độc lập.

### NGUYÊN TẮC:
- **KHÔNG LẬP KẾ HOẠCH MỚI**: Chỉ thực hiện kế hoạch của Architect (Planner).
- **Tuyệt đối không bịa Tool**: CHỈ sử dụng các công cụ có tên trong danh sách [CÔNG CỤ] bên dưới. KHÔNG tự ý gọi `get_status` hay bất kỳ tool nào khác.
- **Đầy đủ Tham số**: KHÔNG BAO GIỜ gọi một tool mà phần `args` để trống. Bạn phải trích xuất mã hiệu (Vd: '01-LB') từ task.
- **Tool-Only Intelligence**: Tập trung 100% vào việc sử dụng tool chính xác (mã DMA chuẩn, tháng/năm chuẩn). 
- **Dữ liệu**: Nếu có lỗi từ tool, hãy thử sửa tham số 1 lần.

### VÍ DỤ MẪU:
Task: "Tra cứu 01-LB"
```json
{{
  "internal_monologue": "Tôi cần xác thực mã hiệu 01-LB.",
  "tool_calls": [{{ "name": "get_dma_info", "args": {{ "dma_query": "01-LB" }} }}],
  "next_node": "tools"
}}
```

### ĐỊNH DẠNG (JSON):
```json
{{
  "internal_monologue": "Suy nghĩ kỹ thuật...",
  "tool_calls": [{{ "name": "...", "args": {{ "dma_query": "..." }} }}],
  "next_node": "tools"
}}
```

### CÔNG CỤ:
{tool_descriptions}

### TRẠM ĐÃ XÁC THỰC (RESOLVED DMAS):
{resolved_dmas}
"""

def get_executor_node(llm, tools):
    async def executor_node(state: AgentState) -> dict:
        tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])
        task_list_str = json.dumps(state.get("task_list", []), ensure_ascii=False, indent=2)
        resolved_dmas = list(state.get("resolved_dma", {}).keys())
        
        prompt = EXECUTOR_PROMPT.format(
            tool_descriptions=tool_descriptions,
            task_list_str=task_list_str,
            resolved_dmas=resolved_dmas
        )
        
        try:
            # 🟢 Tactical Execution
            response = await llm.ainvoke([
                SystemMessage(content=prompt),
                *state["messages"]
            ])
            
            raw_text = response.content
            try:
                data = parse_json_from_llm(raw_text)
            except Exception as e:
                logger.error(f"Failed to parse Executor output: {e}")
                return {"next_node": "synthesize"}

            raw_tool_calls = data.get("tool_calls", [])
            lc_tool_calls = []
            for tc in raw_tool_calls:
                lc_tool_calls.append({
                    "name": tc["name"],
                    "args": tc.get("args", {}),
                    "id": str(uuid.uuid4())
                })
            
            ai_msg = AIMessage(content=raw_text, tool_calls=lc_tool_calls)
            
            return {
                "messages": [ai_msg],
                "thought": data.get("internal_monologue", ""),
                "next_node": data.get("next_node", "tools")
            }
            
        except Exception as e:
            logger.error(f"Error in ExecutorNode: {e}")
            return {"next_node": "synthesize"}
            
    return executor_node
