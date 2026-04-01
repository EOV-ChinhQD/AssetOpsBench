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
    description="XÁC THỰC DMA: Chuyển đổi tên DMA không chuẩn hoặc mã hiệu thành mã chuẩn (DMA-XX-XX). LUÔN gọi tool này trước khi dùng các tool khác nếu chưa có mã chuẩn.",
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
    description="DỮ LIỆU THỰC TẾ: Lấy sản lượng nước thực tế của 1 DMA theo tháng.",
    coroutine=lambda dma_id=None, dma_query=None, months=12, year=None, month=None: call_mcp_tool(
        HANOI_SERVER, "get_history", {"dma_id": dma_id or dma_query, "months": months, "year": year, "month": month}
    ),
    args_schema=HistoricalInput
)

mcp_forecast = StructuredTool.from_function(
    name="get_forecast",
    description="DỮ LIỆU DỰ BÁO: Lấy sản lượng nước dự báo của 1 DMA cho các tháng tới.",
    coroutine=lambda dma_id=None, dma_query=None, horizon=3: call_mcp_tool(HANOI_SERVER, "get_forecast", {"dma_id": dma_id or dma_query, "horizon": horizon}),
    args_schema=ForecastInput
)

mcp_plot = StructuredTool.from_function(
    name="plot_dma",
    description="TRỰC QUAN HÓA: Vẽ biểu đồ tiêu thụ nước (Thực tế + Dự báo). Chỉ dùng cho 1 DMA cụ thể.",
    coroutine=lambda dma_id=None, dma_query=None, include_forecast=True: call_mcp_tool(HANOI_SERVER, "plot_dma", {"dma_id": dma_id or dma_query, "include_forecast": include_forecast}),
    args_schema=PlotInput
)

# Registry for ToolNode and AgentCore
tools = [mcp_text_to_sql, mcp_dma_info, mcp_history, mcp_forecast, mcp_plot]
