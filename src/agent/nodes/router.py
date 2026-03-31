import json
import re
import uuid
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

logger = logging.getLogger(__name__)
from ..state import AgentState
from ..mcp_client import call_mcp_tool
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# Constants for MCP Server and tools
HANOI_SERVER = "hanoi_water-mcp-server"

class DmaQueryInput(BaseModel):
    dma_query: str = Field(description="Mã hiệu DMA cần tra cứu")

class SqlQueryInput(BaseModel):
    question: str = Field(description="Câu hỏi tự nhiên cần chuyển sang SQL")

class HistoricalInput(BaseModel):
    dma_id: str = Field(description="Mã DMA")
    months: int = Field(default=12, description="Số tháng lùi lại")

class ForecastInput(BaseModel):
    dma_id: str = Field(description="Mã DMA")
    horizon: int = Field(default=3, description="Số tháng dự báo")

# Wrap MCP tools into LangChain tools
mcp_dma_info = StructuredTool.from_function(
    name="get_dma_info",
    description="Xác thực mã hiệu DMA (madma). GỌI ĐẦU TIÊN.",
    coroutine=lambda dma_query: call_mcp_tool(HANOI_SERVER, "get_dma_info", {"dma_query": dma_query}),
    args_schema=DmaQueryInput
)

mcp_text_to_sql = StructuredTool.from_function(
    name="text_to_sql",
    description="Truy vấn dữ liệu nước Hà Nội bằng ngôn ngữ tự nhiên.",
    coroutine=lambda question: call_mcp_tool(HANOI_SERVER, "text_to_sql", {"question": question}),
    args_schema=SqlQueryInput
)

mcp_historical = StructuredTool.from_function(
    name="get_historical_analysis",
    description="Phân tích lịch sử tiêu thụ nước.",
    coroutine=lambda dma_id, months=12: call_mcp_tool(HANOI_SERVER, "get_historical_analysis", {"dma_id": dma_id, "months": months}),
    args_schema=HistoricalInput
)

mcp_forecast = StructuredTool.from_function(
    name="get_forecast_analysis",
    description="Lấy dự báo tiêu thụ nước.",
    coroutine=lambda dma_id, horizon=3: call_mcp_tool(HANOI_SERVER, "get_forecast_analysis", {"dma_id": dma_id, "horizon": horizon}),
    args_schema=ForecastInput
)

mcp_plot = StructuredTool.from_function(
    name="plot_dma",
    description="Vẽ biểu đồ tiêu thụ nước (thực tế + dự báo). Gọi sau khi đã có mã DMA.",
    coroutine=lambda dma_id, include_forecast=True: call_mcp_tool(HANOI_SERVER, "plot_dma", {"dma_id": dma_id, "include_forecast": include_forecast}),
)

# Placeholder tools for now, can be expanded
tools = [mcp_dma_info, mcp_text_to_sql, mcp_historical, mcp_forecast, mcp_plot]

from ..trajectory_store import trajectory_store

def get_router_node(llm):
    async def router(state: AgentState) -> dict:
        llm_with_tools = llm.bind_tools(tools)
        
        # --- Collect context for prompt ---
        resolved_dma = state.get('resolved_dma', {})
        long_term_ctx = state.get('long_term_context', 'Chưa có')
        reflect_notes = state.get('reflect_notes', '')
        retry_count = state.get('retry_count', 0)
        
        # Build retry hint section
        retry_section = ""
        if reflect_notes and retry_count > 0:
            retry_section = f"""
### LẦN THỬ LẠI (lần {retry_count}):
Gợi ý từ lần trước: {reflect_notes}
Hãy bù đắp thiếu sót bằng cách thay đổi query hoặc table.
"""
        
        # Inject Few-shot from Trajectory Store if query is available
        query = state["messages"][-1].content if state.get("messages") else ""
        few_shot_examples = trajectory_store.retrieve(query, limit=2) if query else ""
        few_shot_section = f"\n### VÍ DỤ CHUẨN XÁC TỪ LỊCH SỬ:\n{few_shot_examples}\n" if few_shot_examples else ""

        system_prompt = f"""Bạn là trợ lý vận hành hệ thống nước Hà Nội.
THỜI GIAN HIỆN TẠI: Tháng 01/2026. LƯU Ý: 01/2026 = Thực tế. 02-04/2026 = Dự báo.

### BẮT BUỘC (ReAct Mechanism):
Kế hoạch suy luận của bạn đã được xác định ở bước TRƯỚC:
[DỰ ĐỊNH]: {state.get('thought', 'Chưa xác định')}
[KẾ HOẠCH TOOL]: {json.dumps(state.get('tool_plan', []), ensure_ascii=False)}

Hãy thực hiện theo kế hoạch này. BẠN PHẢI GỌI TOOL để lấy dữ liệu!
- Nếu người dùng muốn XEM BIỂU ĐỒ hoặc VẼ: Luôn gọi `plot_dma`.
- Nếu cần tra cứu SQL phức tạp: Dùng `text_to_sql`.
- Nếu cần thông tin DMA: Dùng `get_dma_info`.

### TRẠNG THÁI:
- Ý định: {state.get('intent', 'GLOBAL')}
- DMAs liên quan: {", ".join(state.get('mentioned_dmas', [])) if state.get('mentioned_dmas') else 'Không có'}
- DMA Cache: {json.dumps(resolved_dma, ensure_ascii=False) if resolved_dma else 'Trống'}
- Ngữ cảnh: {long_term_ctx}
{retry_section}{few_shot_section}
"""
        messages = state.get("history", []) + state.get("messages", [])
        
        # --- Structured Logging ---
        logger.info(f"ROUTER_INPUT: messages={len(messages)}, retry={retry_count}, reflect_notes='{reflect_notes[:100] if reflect_notes else ''}'")

        # 1. Truncate large content in messages
        processed_messages = []
        for msg in messages:
            content = msg.content
            if isinstance(content, str) and len(content) > 1500:
                content = content[:1500] + "... [Cắt giảm]"
            
            if isinstance(msg, HumanMessage): processed_messages.append(HumanMessage(content=content))
            elif isinstance(msg, AIMessage): processed_messages.append(AIMessage(content=content, tool_calls=msg.tool_calls))
            elif isinstance(msg, ToolMessage): processed_messages.append(ToolMessage(content=content, tool_call_id=msg.tool_call_id))
            elif isinstance(msg, SystemMessage): processed_messages.append(SystemMessage(content=content))
            else: processed_messages.append(msg)

        # 2. Strategic Trimming
        max_history = 10
        start_idx = max(0, len(processed_messages) - max_history)
        while start_idx > 0 and isinstance(processed_messages[start_idx], ToolMessage):
            start_idx -= 1
        trimmed_history = processed_messages[start_idx:]
        
        messages = [SystemMessage(content=system_prompt)] + trimmed_history
        
        logger.info(f"ROUTER_CONTEXT: final_msgs={len(messages)}, start_idx={start_idx}, total_raw={len(processed_messages)}")
        
        response = await llm_with_tools.ainvoke(messages)
        
        # --- Normalize tool calls ---
        final_tool_calls = []
        source_calls = response.tool_calls or []
        
        # Fallback: extract JSON blocks if native tool calling failed
        if not source_calls and response.content:
            blocks = re.findall(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", response.content, re.DOTALL)
            for b in blocks:
                try:
                    data = json.loads(b.strip())
                    source_calls.extend(data if isinstance(data, list) else [data])
                except: pass

        for call in source_calls:
            if not isinstance(call, dict): continue
            name = call.get("name")
            if not name: continue
            
            raw_args = call.get("args") or call.get("arguments") or {}
            if name == "text_to_sql":
                q = raw_args.get("question") or raw_args.get("query") or str(raw_args)
                normalized_args = {"question": q}
            else:
                normalized_args = raw_args

            final_tool_calls.append({
                "name": name,
                "args": normalized_args,
                "id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                "type": "tool_call"
            })
        
        # --- Structured Decision Logging ---
        if final_tool_calls:
            tool_summary = [f"{tc['name']}({json.dumps(tc['args'], ensure_ascii=False)[:80]})" for tc in final_tool_calls]
            logger.info(f"ROUTER_DECISION: tools_selected={tool_summary}")
        else:
            logger.info(f"ROUTER_DECISION: NO_TOOLS — synthesize. Response preview: '{str(response.content)[:120]}'")
            
        response.tool_calls = final_tool_calls
        return {"messages": [response]}
    return router
