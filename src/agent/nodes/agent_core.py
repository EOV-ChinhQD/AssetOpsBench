import json
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from ..state import AgentState

logger = logging.getLogger(__name__)

# --- Structured Output Schema (Claude Style) ---
class AgentDecision(BaseModel):
    internal_monologue: str = Field(description="Suy nghĩ nội bộ về yêu cầu của người dùng và kế hoạch hành động.")
    tool_plan: List[str] = Field(default_factory=list, description="Danh sách các công cụ dự kiến sẽ sử dụng.")
    next_node: str = Field(description="Node tiếp theo: 'tools' nếy cần gọi công cụ, 'synthesize' nếu đã có câu trả lời hoặc là câu hỏi xã giao.")

AGENT_CORE_PROMPT = """Bạn là Chuyên gia Vận hành hệ thống nước Hà Nội (Hanoi Water AI), được xây dựng trên kiến trúc Claude-style Unified Loop.

### NHIỆM VỤ:
Phân tích yêu cầu của người dùng, lập kế hoạch và quyết định hành động tiếp theo.

### QUY TẮC SUY LUẬN [INTERNAL_MONOLOGUE]:
Trước khi quyết định, bạn PHẢI thực hiện suy luận nội bộ:
1. **Phân tích Ý định**: Đây là câu hỏi xã giao (Greeting), câu hỏi chung (General), hay truy vấn dữ liệu nước (Data Query)?
2. **Xác định Phạm vi**: Nếu là dữ liệu nước, nó áp dụng cho Toàn hệ thống (Global) hay Khu vực cụ thể (Specific)?
3. **Lập kế hoạch Tool**: 
   - Nếu là Specific: LUÔN bắt đầu bằng `get_dma_info` để xác thực mã hiệu.
   - Nếu là Global/Analytical: Dùng `text_to_sql`.
   - Nếu là vẽ biểu đồ: Dùng `plot_dma`.
4. **Quyết định Node**: 
   - Nếu chỉ là chào hỏi -> `next_node = "synthesize"`.
   - Nếu cần tra cứu dữ liệu -> `next_node = "tools"`.

### BỐI CẢNH NGƯỜI DÙNG:
{long_term_context}

### DANH SÁCH CÔNG CỤ CÓ SẴN:
{tool_descriptions}

TRẢ VỀ KẾT QUẢ THEO ĐỊNH DẠNG CẤU TRÚC (STRUCTURED OUTPUT).
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
        
        # Assemble professional system prompt
        sys_msg = SystemMessage(content=AGENT_CORE_PROMPT.format(
            long_term_context=long_term_context,
            tool_descriptions=tool_descriptions
        ))
        
        # We include the last few messages for context
        prompt_messages = [sys_msg] + messages[-5:]
        
        try:
            # Note: We assume the adapter supports with_structured_output or we handle JSON parsing
            # For Qwen2.5-Coder with LiteLLM, we might need to handle raw output.
            response = await llm.ainvoke(prompt_messages)
            content = response.content
            
            # Fallback JSON parsing if LLM didn't use tool calling for structure
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            
            logger.info(f"AGENT_CORE DECISION: node={data.get('next_node')} | plan={data.get('tool_plan')}")
            
            return {
                "thought": data.get("internal_monologue", ""),
                "tool_plan": data.get("tool_plan", []),
                "next_node": data.get("next_node", "synthesize")
            }
        except Exception as e:
            logger.error(f"Error in AgentCore node: {e}")
            # Failsafe: route to synthesize
            return {
                "thought": f"Lỗi hệ thống: {str(e)}",
                "next_node": "synthesize"
            }
            
    return agent_core
