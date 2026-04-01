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
    next_node: str = Field(description="Node tiếp theo: 'tools' nếy cần dữ liệu từ hệ thống, 'synthesize' nếy đã có thông tin.")
    tool_calls: Optional[List[dict]] = Field(default_factory=list, description="Danh sách các hàm cần gọi: [{'name': '...', 'args': {...}}]. LUÔN điền nếu next_node='tools'.")

AGENT_CORE_PROMPT = """Bạn là Chuyên gia Vận hành hệ thống nước Hà Nội (Hanoi Water AI).
Nhiệm vụ: Phân tích yêu cầu, lập kế hoạch và quyết định hành động tiếp theo.

### QUY TẮC SUY LUẬN:
1. **Phân tích Ý định**: Greeting, General, hay Data Query?
2. **Lập kế hoạch Tool**: 
   - Nếu tra cứu DMA cụ thể: LUÔN gọi `get_dma_info` trước để xác thực.
   - Nếu phân tích số liệu: Dùng `text_to_sql`.
   - Nếu vẽ biểu đồ: Dùng `plot_dma`.
3. **Quyết định Node**: 
   - Cần dữ liệu -> `next_node = "tools"`.
   - Đã có câu trả lời -> `next_node = "synthesize"`.

### CẤU TRÚC PHẢN HỒI (MẪU):
```json
{{
  "internal_monologue": "Người dùng muốn biết sản lượng DMA 05-LB. Tôi cần tra cứu thông tin DMA này trước.",
  "tool_plan": ["1. Lấy thông tin DMA 05-LB để xác thực", "2. Lấy sản lượng"],
  "next_node": "tools",
  "tool_calls": [{{ "name": "get_dma_info", "args": {{ "dma_id": "05-LB" }} }}]
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
            
            if content is None:
                 print(f"[DEBUG] Content is None! Tool calls: {getattr(response, 'tool_calls', [])}")
                 raise ValueError("LLM returned empty content.")
                 
            # Fallback JSON parsing
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            next_node = data.get("next_node", "synthesize")
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
            logger.error(f"Error in AgentCore node: {e}")
            # Failsafe: route to synthesize
            return {
                "thought": f"Lỗi hệ thống: {str(e)}",
                "next_node": "synthesize"
            }
            
    return agent_core
