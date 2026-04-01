import json
import logging
import re
import uuid
from typing import List, Optional
from langchain_core.messages import SystemMessage, AIMessage
from ..state import AgentState

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
   - Ví dụ: `get_dma_info` + `get_history` + `get_forecast` cho cùng 1 DMA.

### NGUYÊN TẮC:
- **KHÔNG LẬP KẾ HOẠCH MỚI**: Chỉ thực hiện kế hoạch của Architect (Planner).
- **Tool-Only Intelligence**: Tập trung 100% vào việc sử dụng tool chính xác (mã DMA chuẩn, tháng/năm chuẩn).
- **Dữ liệu**: Nếu có lỗi từ tool, hãy thử sửa tham số 1 lần trước khi báo cáo.

### ĐỊNH DẠNG (JSON):
```json
{{
  "internal_monologue": "Suy nghĩ kỹ thuật (Vd: 'Cần tra cứu lịch sử 01-LB cho 12 tháng qua...')",
  "tool_calls": [{{ "name": "...", "args": {{ ... }} }}],
  "next_node": "tools" hoặc "synthesize"
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
            json_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
            data_str = json_match.group(1).strip() if json_match else raw_text.strip()
            
            try:
                data = json.loads(data_str)
            except:
                data = json.loads(re.search(r"\{.*\}", data_str, re.DOTALL).group(0))

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
