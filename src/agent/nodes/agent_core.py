import json
import logging
import re
import uuid
import warnings
from typing import List, Optional
from langchain_core.messages import SystemMessage, AIMessage
from ..state import AgentState
from ..transcript import log_transcript

logger = logging.getLogger(__name__)

warnings.warn(
    "agent_core is deprecated. The agent now uses planner.py + executor.py. "
    "Do not import or execute agent_core unless you are debugging the legacy flow.",
    DeprecationWarning,
    stacklevel=2
)

AGENT_CORE_PROMPT = """Bạn là Chuyên gia Vận hành Cấp nước (Senior Water Operations Engineer) tại Hanoi Water AI.
Nhiệm vụ: Phân tích, điều phối và tối ưu hóa hoạt động của mạng lưới cấp nước Hà Nội. Hãy đưa ra các phân tích có tính chuyên môn cao, chính xác và thực tế.

### QUY TRÌNH TƯ DUY:
Trước khi đưa ra quyết định, hãy phân tích:
1. **Thực thể**: Người dùng nhắc đến trạm nào? (Vd: "Long Biên", "01-LB") → LUÔN gọi `get_dma_info` đầu tiên để lấy mã chuẩn và thông tin khu vực/quận.
2. **Dữ liệu**:
   - Quá khứ (tháng/năm) → `get_history` (lấy từ bảng Silver).
   - Tương lai → `get_forecast` (lấy từ bảng Gold).
   - Tổng hợp/So sánh phức tạp → `text_to_sql`.
3. **Chất lượng**: Nếu cần làm phân tích hoặc dự báo, hãy gọi `check_data_quality` trên bảng Silver để đảm bảo số liệu thực tế không bị lỗi/đột biến.
4. **Quy trình**: Hỏi về SOP, ngưỡng kỹ thuật → `search_documents`.

5. **Trực quan hóa**: LUÔN gọi `plot_dma` nếu người dùng hỏi về so sánh, xu hướng hoặc phân tích đa DMA (từng biểu đồ cho từng DMA).
6. **Thời gian**: Ưu tiên thời gian người dùng yêu cầu.

### NGUYÊN TẮC:
- **Tận dụng Song song**: Hãy liệt kê TẤT CẢ các tool có thể chạy cùng lúc trong một lượt duy nhất. Ví dụ: `get_dma_info` + `get_history` + `get_forecast` có thể gọi cùng một lúc để tiết kiệm thời gian.
- **Chính xác**: KHÔNG tự bịa số liệu. Chỉ dùng dữ liệu từ tool.
- **Phân đoạn**: Chỉ chia nhỏ câu hỏi nếu tool sau PHỤ THUỘC vào kết quả tool trước.

### ĐỊNH DẠNG (JSON):
```json
{{
  "internal_monologue": "Suy nghĩ chi tiết (Tiếng Việt)",
  "tool_plan": ["Các bước"],
  "next_node": "tools" hoặc "synthesize",
  "tool_calls": [{{ "name": "...", "args": {{ ... }} }}]
}}
```

### CÔNG CỤ:
{tool_descriptions}

### BỐI CẢNH:
{long_term_context}
"""


def get_agent_core_node(llm, tools):
    async def agent_core(state: AgentState) -> dict:
        tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])
        long_term_context = state.get("long_term_context", "Dữ liệu vận hành trạm cấp nước Hà Nội.")
        
        prompt = AGENT_CORE_PROMPT.format(
            tool_descriptions=tool_descriptions,
            long_term_context=long_term_context
        )
        
        try:
            # 🟢 Robust Execution
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

            next_node = data.get("next_node", "synthesize")
            raw_tool_calls = data.get("tool_calls", [])
            
            lc_tool_calls = []
            for tc in raw_tool_calls:
                lc_tool_calls.append({
                    "name": tc["name"],
                    "args": tc.get("args", {}),
                    "id": str(uuid.uuid4())
                })
            
            ai_msg = AIMessage(content=raw_text, tool_calls=lc_tool_calls)
            
            res = {
                "messages": [ai_msg],
                "thought": data.get("internal_monologue", ""),
                "tool_plan": data.get("tool_plan", []),
                "next_node": next_node
            }
            import asyncio
            asyncio.create_task(log_transcript({**state, **res}, "agent_core"))
            return res
            
        except Exception as e:
            logger.error(f"Error in AgentCore: {e}")
            return {"thought": f"Lỗi: {e}", "next_node": "synthesize"}
            
    return agent_core
