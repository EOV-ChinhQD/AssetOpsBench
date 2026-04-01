import json
import logging
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from ..state import AgentState

logger = logging.getLogger(__name__)

# --- Structured Output Schema (Claude Style) ---
class AgentDecision(BaseModel):
    internal_monologue: str = Field(description="Suy nghĩ nội bộ về yêu cầu của người dùng.")
    tool_plan: List[str] = Field(default_factory=list, description="Kế hoạch hành động từng bước.")
    next_node: str = Field(description="Node tiếp theo: 'tools' nếu cần dữ liệu, 'synthesize' nếu đã có tin. CHỈ DÙNG 'tools' hoặc 'synthesize'.")
    tool_calls: Optional[List[dict]] = Field(default_factory=list, description="Danh sách các hàm cần gọi: [{'name': '...', 'args': {...}}]. LUÔN điền nếu next_node='tools'.")

AGENT_CORE_PROMPT = """Bạn là Chuyên gia Vận hành hệ thống nước Hà Nội (Hanoi Water AI).
Nhiệm vụ: Phân tích yêu cầu, lập kế hoạch và quyết định hành động tiếp theo.

### QUY TẮC SUY LUẬN:
1. **Phân tích Ý định**: Greeting, General, hay Data Query?
2. **Lập kế hoạch Tool**: 
    - Nếu tra cứu DMA (Vd: 01-LB, 06-QM): Bạn có thể gọi `get_dma_info` và `get_forecast`/`get_history` ĐỒNG THỜI trong một lượt gọi tool để tối ưu tốc độ.
    - Nếu phân tích số liệu, đếm số lượng hoặc thống kê: Dùng `text_to_sql`. (VD: Để đếm số DMA, dùng `SELECT COUNT(DISTINCT madma) FROM silver.stg_water_demand`).
    - **QUY TẮC MẶC ĐỊNH**: Nếu thiếu thời gian, mặc định dùng năm 2024 và tháng 10.
    - Nếu vẽ biểu đồ: Dùng `plot_dma`.
    - **TUYỆT ĐỐI KHÔNG GIẢ ĐỊNH KẾT QUẢ**: Bạn không có kiến thức về sản lượng DMA cụ thể. Phải gọi tool lấy số liệu mới được Synthesize.

### CẤU TRÚC PHẢN HỒI (BẮT BUỘC JSON):
```json
{{
  "internal_monologue": "Người dùng muốn biết... Tôi chưa có dữ liệu nên cần gọi tool...",
  "tool_plan": ["1. Xác thực DMA", "2. Lấy dữ liệu"],
  "next_node": "tools",
  "tool_calls": [{{ "name": "get_dma_info", "args": {{ "dma_id": "..." }} }}]
}}
```

### DANH SÁCH CÔNG CỤ:
{tool_descriptions}

### BỐI CẢNH:
{long_term_context}

TRẢ VỀ JSON TRONG NHÃN ```json.
"""

def get_agent_core_node(llm, tools):
    # Prepare tool descriptions for the prompt
    tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])
    
    # Bind structured output if the LLM supports it, otherwise use prompt instructions
    # For now, we'll use prompt-based JSON as a fallback for models without native structured output
    # but we'll try to use the schema-driven approach.
    
    async def agent_core(state: AgentState) -> dict:
        messages = state.get("messages", [])
        long_term_context = state.get("long_term_context", "Không có thông tin profile.")
        
        sys_msg = SystemMessage(content=AGENT_CORE_PROMPT.format(
            long_term_context=long_term_context,
            tool_descriptions=tool_descriptions
        ))
        
        prompt_messages = [sys_msg] + messages[-5:]
        
        try:
            response = await llm.ainvoke(prompt_messages)
            content = response.content
            logger.info(f"DEBUG LLM RAW: {content}")
            
            if content is None: raise ValueError("LLM returned empty content.")
            
            # Robust JSON extraction
            json_str = content
            if "```json" in json_str:
                json_str = json_str.split("```json")[-1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[-1].split("```")[0].strip()
            
            # Remove any leading text before the first '{'
            if "{" in json_str:
                json_str = json_str[json_str.find("{"):]
            if "}" in json_str:
                json_str = json_str[:json_str.rfind("}")+1]
            
            data = json.loads(json_str)
            next_node = data.get("next_node", "tools") # DEFAULT TO TOOLS for data queries
            tool_calls_raw = data.get("tool_calls", [])
            
            # Convert JSON tool_calls to real AIMessage tool_calls
            lc_tool_calls = []
            if next_node == "tools" and tool_calls_raw:
                 for tc in tool_calls_raw:
                      lc_tool_calls.append({
                           "name": tc.get("name"),
                           "args": tc.get("args", {}),
                           "id": f"call_{uuid.uuid4().hex[:8]}"
                      })
            
            ai_msg = AIMessage(
                 content=data.get("internal_monologue", ""),
                 tool_calls=lc_tool_calls
            )
            
            logger.info(f"AGENT_CORE DECISION: node={next_node} | calls={len(lc_tool_calls)}")
            
            return {
                "messages": [ai_msg],
                "thought": data.get("internal_monologue", ""),
                "tool_plan": data.get("tool_plan", []),
                "next_node": next_node
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Error in AgentCore node: {e}")
            # Failsafe: route to synthesize
            return {
                "thought": f"Lỗi hệ thống: {str(e)}",
                "next_node": "synthesize"
            }
            
    return agent_core
