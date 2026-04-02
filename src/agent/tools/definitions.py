import os
import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from src.agent.mcp_client import call_mcp_tool
from src.agent.services.registry import registry
from src.agent.tools.rag_search import rag_tool

logger = logging.getLogger(__name__)
HANOI_SERVER = "hanoi_water-mcp-server"

# --- Input Schemas (Models) ---
class DmaQueryInput(BaseModel):
    dma_query: Optional[str] = Field(default=None, description="Mã hiệu hoặc tên trạm cần tra cứu")
    dma_id: Optional[str] = Field(default=None, description="Mã hiệu chuẩn (alias)")

class SqlQueryInput(BaseModel):
    question: Optional[str] = Field(default=None, description="Câu hỏi tự nhiên cần tra cứu hệ thống")

class TemporalInput(BaseModel):
    dma_id: Optional[str] = Field(default=None, description="Mã DMA")
    dma_query: Optional[str] = Field(default=None, description="Tên trạm (alias)")
    months: int = Field(default=12, description="Số tháng lùi lại")
    horizon: int = Field(default=3, description="Số tháng dự báo")

# --- Tool Wrappers (Clean logic) ---

async def get_dma_info(dma_query=None, dma_id=None):
    """XÁC THỰC & THÔNG TIN TRẠM: Chuẩn hóa mã DMA (Vd: 'Long Biên' -> '01-LB')."""
    return await call_mcp_tool(HANOI_SERVER, "get_dma_info", {"dma_query": dma_query or dma_id})

async def text_to_sql(question=None):
    """PHÂN TÍCH TỔNG HỢP: Truy vấn dữ liệu thống kê, đếm số lượng qua SQL."""
    return await call_mcp_tool(HANOI_SERVER, "text_to_sql", {"question": question})

async def get_history(dma_id=None, dma_query=None, months=12):
    """DỮ LIỆU THỰC TẾ: Lấy sản lượng nước thực tế (silver)."""
    return await call_mcp_tool(HANOI_SERVER, "get_history", {"dma_id": dma_id or dma_query, "months": months})

async def get_forecast(dma_id=None, dma_query=None, horizon=3):
    """DỮ LIỆU DỰ BÁO: Lấy sản lượng nước dự báo (gold)."""
    return await call_mcp_tool(HANOI_SERVER, "get_forecast", {"dma_id": dma_id or dma_query, "horizon": horizon})

async def plot_dma(dma_id=None, dma_query=None, include_forecast=True):
    """TRỰC QUAN HÓA: Vẽ biểu đồ tiêu thụ."""
    return await call_mcp_tool(HANOI_SERVER, "plot_dma", {"dma_id": dma_id or dma_query, "include_forecast": include_forecast})

# --- Structured Tool Creation ---

t_dma_info = StructuredTool.from_function(name="get_dma_info", description="Lookup station code/meta.", coroutine=get_dma_info, args_schema=DmaQueryInput)
t_sql = StructuredTool.from_function(name="text_to_sql", description="Query complex stats via SQL.", coroutine=text_to_sql, args_schema=SqlQueryInput)
t_history = StructuredTool.from_function(name="get_history", description="Get historical demand.", coroutine=get_history, args_schema=TemporalInput)
t_forecast = StructuredTool.from_function(name="get_forecast", description="Get predicted demand.", coroutine=get_forecast, args_schema=TemporalInput)
t_plot = StructuredTool.from_function(name="plot_dma", description="Draw demand charts.", coroutine=plot_dma, args_schema=TemporalInput)

# --- Auto-Registry (Initialize on Import) ---
registry.register(t_dma_info, is_safe=True, category="FETCH")
registry.register(t_sql, is_safe=True, category="SEARCH")
registry.register(t_history, is_safe=True, category="FETCH")
registry.register(t_forecast, is_safe=True, category="FETCH")
registry.register(t_plot, is_safe=True, category="FETCH")
registry.register(rag_tool, is_safe=True, category="SEARCH")

# Unified access
tools = registry.list_tools()
