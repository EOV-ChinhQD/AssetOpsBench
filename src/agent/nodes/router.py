import json
import re
import uuid
import logging
from typing import Optional, List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src.agent.state import AgentState
from src.agent.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)

# Constants for MCP Server and tools
HANOI_SERVER = "hanoi_water-mcp-server"

class DmaQueryInput(BaseModel):
    dma_query: Optional[str] = Field(default=None, description="Mã hiệu DMA cần tra cứu")
    dma_id: Optional[str] = Field(default=None, description="Mã hiệu DMA (alias)")

class SqlQueryInput(BaseModel):
    question: Optional[str] = Field(default=None, description="Câu hỏi tự nhiên cần chuyển sang SQL")
    query: Optional[str] = Field(default=None, description="Câu hỏi tự nhiên (alias)")

class HistoricalInput(BaseModel):
    dma_id: Optional[str] = Field(default=None, description="Mã DMA")
    dma_query: Optional[str] = Field(default=None, description="Mã DMA (alias)")
    months: int = Field(default=12, description="Số tháng lùi lại")
    year: Optional[int] = Field(default=None, description="Năm cụ thể")
    month: Optional[int] = Field(default=None, description="Tháng cụ thể")

class ForecastInput(BaseModel):
    dma_id: Optional[str] = Field(default=None, description="Mã DMA")
    dma_query: Optional[str] = Field(default=None, description="Mã DMA (alias)")
    horizon: int = Field(default=3, description="Số tháng dự báo")

class PlotInput(BaseModel):
    dma_id: Optional[str] = Field(default=None, description="Mã hiệu DMA")
    dma_query: Optional[str] = Field(default=None, description="Mã hiệu DMA (alias)")
    include_forecast: bool = Field(default=True, description="Có bao gồm dữ liệu dự báo không")

class TaskInput(BaseModel):
    tasks: list[str] = Field(description="Danh sách các nhiệm vụ cụ thể.")

class TaskUpdateInput(BaseModel):
    task_index: int = Field(description="Vị trí nhiệm vụ (0-indexed).")
    status: str = Field(description="Trạng thái: 'todo', 'doing', 'done'.")

# --- Optimized Tool Definitions ---

mcp_dma_info = StructuredTool.from_function(
    name="get_dma_info",
    description="XÁC THỰC & THÔNG TIN TRẠM: Chuẩn hóa mã DMA (Vd: 'Long Biên' -> '01-LB') và lấy thông tin chi tiết (quận, vùng, công suất). LUÔN dùng tool này đầu tiên.",
    coroutine=lambda dma_query=None, dma_id=None: call_mcp_tool(HANOI_SERVER, "get_dma_info", {"dma_query": dma_query or dma_id}),
    args_schema=DmaQueryInput
)

mcp_text_to_sql = StructuredTool.from_function(
    name="text_to_sql",
    description="PHÂN TÍCH TỔNG HỢP: Truy vấn dữ liệu thống kê, đếm số lượng DMA, so sánh bằng ngôn ngữ tự nhiên. Gợi ý bảng: 'silver.stg_water_demand' (lịch sử) và 'gold.fct_predictions_unified' (dự báo).",
    coroutine=lambda question=None, query=None: call_mcp_tool(HANOI_SERVER, "text_to_sql", {"question": question or query}),
    args_schema=SqlQueryInput
)

mcp_history = StructuredTool.from_function(
    name="get_history",
    description="DỮ LIỆU THỰC TẾ: Lấy sản lượng nước thực tế (silver) theo tháng.",
    coroutine=lambda dma_id=None, dma_query=None, months=12, year=None, month=None: call_mcp_tool(
        HANOI_SERVER, "get_history", {"dma_id": dma_id or dma_query, "months": months, "year": year, "month": month}
    ),
    args_schema=HistoricalInput
)

mcp_forecast = StructuredTool.from_function(
    name="get_forecast",
    description="DỮ LIỆU DỰ BÁO: Lấy sản lượng nước dự báo (gold) cho các tháng tới.",
    coroutine=lambda dma_id=None, dma_query=None, horizon=3: call_mcp_tool(HANOI_SERVER, "get_forecast", {"dma_id": dma_id or dma_query, "horizon": horizon}),
    args_schema=ForecastInput
)

mcp_plot = StructuredTool.from_function(
    name="plot_dma",
    description="TRỰC QUAN HÓA: Vẽ biểu đồ tiêu thụ nước (Thực tế + Dự báo). Chỉ dùng cho 1 DMA cụ thể.",
    coroutine=lambda dma_id=None, dma_query=None, include_forecast=True: call_mcp_tool(HANOI_SERVER, "plot_dma", {"dma_id": dma_id or dma_query, "include_forecast": include_forecast}),
    args_schema=PlotInput
)

# --- Phase 3.1: Data Quality ---
class DataQualityInput(BaseModel):
    dma_id: str = Field(description="Mã DMA cần kiểm tra")
    year: int = Field(default=2024, description="Năm")
    month: int = Field(default=10, description="Tháng")

mcp_data_quality = StructuredTool.from_function(
    name="check_data_quality",
    description="KIỂM TRA CHẤT LƯỢNG: Phân tích bảng dữ liệu thực tế (silver) để phát hiện giá trị âm hoặc đột biến (±2σ) trước khi phân tích/dự báo.",
    coroutine=lambda dma_id, year=2024, month=10: call_mcp_tool(HANOI_SERVER, "check_data_quality", {"dma_id": dma_id, "year": year, "month": month}),
    args_schema=DataQualityInput
)

# --- Phase 2.2: RAG Search ---
from src.agent.tools.rag_search import rag_tool

# Registry for ToolNode and AgentCore
tools = [mcp_text_to_sql, mcp_dma_info, mcp_history, mcp_forecast, mcp_plot, mcp_data_quality, rag_tool]

import asyncio
from langchain_core.messages import ToolMessage

class ParallelToolNode:
    """Optimized ToolNode that runs concurrent-safe tools in parallel."""
    def __init__(self, tools: List[StructuredTool]):
        self.tool_map = {t.name: t for t in tools}

    async def __call__(self, state: AgentState) -> dict:
        messages = state.get("messages", [])
        if not messages:
            return {}
        
        last_msg = messages[-1]
        if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
            return {}
        
        tasks = []
        for tool_call in last_msg.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tool = self.tool_map.get(name)
            
            if tool:
                logger.info(f"PARALLEL_EXEC: Adding tool task for {name}")
                tasks.append(self._run_tool(tool, args, tool_call["id"]))
            else:
                logger.error(f"PARALLEL_EXEC: Tool {name} not found")
                tasks.append(asyncio.sleep(0, result=ToolMessage(
                    content=f"Error: Tool {name} not found.",
                    tool_call_id=tool_call["id"]
                )))

        # 🟢 THE PERFORMANCE BOOSTER: Parallel execution!
        results = await asyncio.gather(*tasks)
        return {"messages": results}

    async def _run_tool(self, tool, args, tc_id):
        try:
            # Using ainvoke for async execution
            res = await tool.ainvoke(args)
            return ToolMessage(content=str(res), tool_call_id=tc_id, name=tool.name)
        except Exception as e:
            logger.error(f"Error executing tool {tool.name}: {e}")
            return ToolMessage(content=f"Error: {e}", tool_call_id=tc_id, name=tool.name)

