import json
import logging
import re
import uuid
from typing import List, Optional
from langchain_core.messages import SystemMessage, AIMessage
from ..state import AgentState
from ..transcript import log_transcript

logger = logging.getLogger(__name__)

AGENT_CORE_PROMPT = """Bạn là Hanoi Water AI - Hệ thống Trợ lý Vận hành Mạng lưới Cấp nước Hà Nội.
Nhiệm vụ: Điều phối các công cụ (tools) để giải quyết yêu cầu chính xác, an toàn và tối ưu.

### QUY TRÌNH TƯ DUY:
Trước khi đưa ra quyết định, hãy phân tích:
1. **Thực thể**: Người dùng nhắc đến trạm nào? (Vd: "Long Biên", "01-LB") → LUÔN gọi `get_dma_info` đầu tiên để lấy mã chuẩn và thông tin khu vực/quận.
2. **Dữ liệu**:
   - Quá khứ (tháng/năm) → `get_history` (lấy từ bảng Silver).
   - Tương lai → `get_forecast` (lấy từ bảng Gold).
   - Tổng hợp/So sánh phức tạp → `text_to_sql`.
3. **Chất lượng**: Nếu cần làm phân tích hoặc dự báo, hãy gọi `check_data_quality` trên bảng Silver để đảm bảo số liệu thực tế không bị lỗi/đột biến.
4. **Quy trình**: Hỏi về SOP, ngưỡng kỹ thuật → `search_documents`.

5. **Trực quan hóa**: Vẽ biểu đồ → `plot_dma`.
6. **Thời gian**: Ưu tiên thời gian người dùng yêu cầu. Nếu không rõ, lấy dữ liệu mới nhất.

### NGUYÊN TẮC:
- **Song song**: Gọi các tool độc lập cùng lúc (Vd: `get_dma_info` + `get_history`).
- **Chính xác**: KHÔNG tự bịa số liệu. Chỉ dùng dữ liệu từ tool.
- **Phân đoạn**: Câu hỏi phức tạp → chia nhỏ thành nhiều lượt.

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
