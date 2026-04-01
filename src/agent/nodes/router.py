import json
import re
import uuid
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

logger = logging.getLogger(__name__)
from src.agent.state import AgentState
from src.agent.mcp_client import call_mcp_tool
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
    year: int = Field(default=None, description="Năm cụ thể")
    month: int = Field(default=None, description="Tháng cụ thể")

class ForecastInput(BaseModel):
    dma_id: str = Field(description="Mã DMA")
    horizon: int = Field(default=3, description="Số tháng dự báo")

class PlotInput(BaseModel):
    dma_id: str = Field(description="Mã hiệu DMA (ví dụ: 'DMA-HT-01')")
    include_forecast: bool = Field(default=True, description="Có bao gồm dữ liệu dự báo không")

# --- Optimized Tool Definitions (Claude-style LifeCycle) ---

mcp_dma_info = StructuredTool.from_function(
    name="get_dma_info",
    description="XÁC THỰC DMA: Chuyển đổi tên DMA không chuẩn hoặc mã hiệu thành mã chuẩn (DMA-XX-XX). LUÔN gọi tool này trước khi dùng các tool khác nếu chưa có mã chuẩn.",
    coroutine=lambda dma_query: call_mcp_tool(HANOI_SERVER, "get_dma_info", {"dma_query": dma_query}),
    args_schema=DmaQueryInput
)

mcp_text_to_sql = StructuredTool.from_function(
    name="text_to_sql",
    description="PHÂN TÍCH TỔNG HỢP: Truy vấn dữ liệu thống kê, liệt kê, so sánh bằng ngôn ngữ tự nhiên (Vd: 'Khu vực nào dùng nhiều nước nhất?').",
    coroutine=lambda question: call_mcp_tool(HANOI_SERVER, "text_to_sql", {"question": question}),
    args_schema=SqlQueryInput
)

mcp_history = StructuredTool.from_function(
    name="get_history",
    description="DỮ LIỆU THỰC TẾ: Lấy sản lượng nước thực tế của 1 DMA theo tháng.",
    coroutine=lambda dma_id, months=12, year=None, month=None: call_mcp_tool(
        HANOI_SERVER, "get_history", {"dma_id": dma_id, "months": months, "year": year, "month": month}
    ),
    args_schema=HistoricalInput
)

mcp_forecast = StructuredTool.from_function(
    name="get_forecast",
    description="DỮ LIỆU DỰ BÁO: Lấy sản lượng nước dự báo của 1 DMA cho các tháng tới.",
    coroutine=lambda dma_id, horizon=3: call_mcp_tool(HANOI_SERVER, "get_forecast", {"dma_id": dma_id, "horizon": horizon}),
    args_schema=ForecastInput
)

mcp_plot = StructuredTool.from_function(
    name="plot_dma",
    description="TRỰC QUAN HÓA: Vẽ biểu đồ tiêu thụ nước (Thực tế + Dự báo). Chỉ dùng cho 1 DMA cụ thể.",
    coroutine=lambda dma_id, include_forecast=True: call_mcp_tool(HANOI_SERVER, "plot_dma", {"dma_id": dma_id, "include_forecast": include_forecast}),
    args_schema=PlotInput
)

# Registry for ToolNode and AgentCore
tools = [mcp_text_to_sql, mcp_dma_info, mcp_history, mcp_forecast, mcp_plot]

# legacy route logic removed, moved to agent_core and graph.py logic
