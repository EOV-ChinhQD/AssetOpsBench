import json
import re
import uuid
import logging
import os
import asyncio
from typing import Optional, List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src.agent.state import AgentState
from src.agent.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)

# --- Phase 1: Tool Registry & Security Metadata ---
DEFAULT_MAX_TOOL_CONCURRENCY = int(os.getenv("HANOI_TOOL_MAX_CONCURRENCY", "3"))


class ToolMetadata(BaseModel):
    name: str
    is_concurrency_safe: bool = True
    category: str = "FETCH"  # FETCH, SEARCH, WRITE, DANGEROUS
    requires_permission: bool = False
    max_concurrent: Optional[int] = None

class WaterToolRegistry:
    """Central registry to manage water-specific tools and their metadata."""
    def __init__(self):
        self.tools = {}
        self.metadata = {}
    
    def register(self, tool: StructuredTool, is_safe: bool = True, category: str = "FETCH"):
        self.tools[tool.name] = tool
        self.metadata[tool.name] = ToolMetadata(
            name=tool.name, 
            is_concurrency_safe=is_safe,
            category=category,
            requires_permission=(category == "DANGEROUS")
        )

registry = WaterToolRegistry()

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

async def _get_dma_info_wrapper(dma_query=None, dma_id=None):
    if not (dma_query or dma_id):
        return "Lỗi: Bạn cần cung cấp tên trạm hoặc mã hiệu (Vd: 'Trạm Long Biên')."
    return await call_mcp_tool(HANOI_SERVER, "get_dma_info", {"dma_query": dma_query or dma_id})

mcp_dma_info = StructuredTool.from_function(
    name="get_dma_info",
    description="XÁC THỰC & THÔNG TIN TRẠM: Chuẩn hóa mã DMA (Vd: 'Long Biên' -> '01-LB'). LUÔN dùng tool này đầu tiên nếu chưa biết chính xác mã hiệu.",
    coroutine=_get_dma_info_wrapper,
    args_schema=DmaQueryInput
)

mcp_text_to_sql = StructuredTool.from_function(
    name="text_to_sql",
    description="PHÂN TÍCH TỔNG HỢP: Truy vấn dữ liệu thống kê, đếm số lượng DMA, so sánh bằng ngôn ngữ tự nhiên. Gợi ý bảng: 'silver.stg_water_demand' (lịch sử) và 'gold.fct_predictions_unified' (dự báo).",
    coroutine=lambda question=None, query=None: call_mcp_tool(HANOI_SERVER, "text_to_sql", {"question": question or query}),
    args_schema=SqlQueryInput
)

async def _get_history_wrapper(dma_id=None, dma_query=None, months=12, year=None, month=None):
    if not (dma_id or dma_query):
        return "Lỗi: Thiếu mã hiệu DMA chuẩn. Hãy dùng get_dma_info để tìm mã trước."
    return await call_mcp_tool(HANOI_SERVER, "get_history", {"dma_id": dma_id or dma_query, "months": months, "year": year, "month": month})

mcp_history = StructuredTool.from_function(
    name="get_history",
    description="DỮ LIỆU THỰC TẾ: Lấy sản lượng nước thực tế (silver) theo tháng. Cần mã hiệu chuẩn (Vd: '01-LB').",
    coroutine=_get_history_wrapper,
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
registry.register(mcp_text_to_sql, is_safe=True, category="SEARCH")
registry.register(mcp_dma_info, is_safe=True, category="FETCH")
registry.register(mcp_history, is_safe=True, category="FETCH")
registry.register(mcp_forecast, is_safe=True, category="FETCH")
registry.register(mcp_plot, is_safe=True, category="FETCH")
registry.register(mcp_data_quality, is_safe=True, category="FETCH")
registry.register(rag_tool, is_safe=True, category="SEARCH")

tools = list(registry.tools.values())

import asyncio
from langchain_core.messages import ToolMessage

class ParallelToolNode:
    """Optimized ToolNode that runs concurrent-safe tools in parallel."""
    def __init__(self, registry: WaterToolRegistry, default_max_concurrency: int = DEFAULT_MAX_TOOL_CONCURRENCY):
        self.registry = registry
        self.default_max_concurrency = default_max_concurrency
        self._semaphores: dict[int, asyncio.Semaphore] = {}

    async def __call__(self, state: AgentState) -> dict:
        messages = state.get("messages", [])
        if not messages:
            return {}
        
        last_msg = messages[-1]
        if not (hasattr(last_msg, "tool_calls") and last_msg.tool_calls):
            return {}
        
        tasks = []
        for tool_call in last_msg.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tool = self.registry.tools.get(name)
            meta = self.registry.metadata.get(name)
            
            if tool and (meta.is_concurrency_safe if meta else True):
                logger.info(f"PARALLEL_EXEC: Adding task for water-tool {name}")
                limit = (meta.max_concurrent if meta and meta.max_concurrent else self.default_max_concurrency)
                tasks.append(self._run_tool(tool, args, tool_call["id"], concurrency_limit=limit))
            elif tool:
                # Sequential tool (not concurrency safe or metadata missing)
                logger.warning(f"PARALLEL_EXEC: Tool {name} not marked as safe. Executing sequentially.")
                tasks.append(self._run_tool(tool, args, tool_call["id"], concurrency_limit=None))
            else:
                logger.error(f"PARALLEL_EXEC: Tool {name} not found")
                tasks.append(asyncio.sleep(0, result=ToolMessage(
                    content=f"Error: Tool {name} not found.",
                    tool_call_id=tool_call["id"]
                )))

        # 🟢 THE PERFORMANCE BOOSTER: Parallel execution of multiple water queries!
        results = await asyncio.gather(*tasks)
        return {"messages": results}

    def _get_semaphore(self, limit: Optional[int]):
        if not limit or limit <= 0:
            return None
        if limit not in self._semaphores:
            self._semaphores[limit] = asyncio.Semaphore(limit)
        return self._semaphores[limit]

    async def _run_tool(self, tool, args, tc_id, concurrency_limit: Optional[int]):
        semaphore = self._get_semaphore(concurrency_limit)
        if semaphore:
            if semaphore._value <= 0:
                logger.warning(f"PARALLEL_EXEC: waiting for concurrency slot (limit={concurrency_limit}) for {tool.name}")
            async with semaphore:
                return await self._invoke_tool(tool, args, tc_id)
        return await self._invoke_tool(tool, args, tc_id)

    async def _invoke_tool(self, tool, args, tc_id):
        try:
            res = await tool.ainvoke(args)
            return ToolMessage(content=str(res), tool_call_id=tc_id, name=tool.name)
        except Exception as e:
            logger.error(f"Error executing tool {tool.name}: {e}")
            return ToolMessage(content=f"Error: {e}", tool_call_id=tc_id, name=tool.name)

# --- Phase 4: Permission Classifier Helper ---
def classify_tool_calls(state: AgentState) -> str:
    """Classifies if the latest tool calls are SAFE or require HUMAN_REVIEW."""
    messages = state.get("messages", [])
    if not messages: return "safe"
    
    last_msg = messages[-1]
    if not (hasattr(last_msg, "tool_calls") and last_msg.tool_calls):
        return "safe"
    
    for tool_call in last_msg.tool_calls:
        name = tool_call["name"]
        meta = registry.metadata.get(name)
        
        # 🛡️ SECURITY GUARD: Block any tool marked as dangerous or requiring permission
        if meta and meta.requires_permission:
            logger.warning(f"SECURITY_ALERT: Tool '{name}' requires human review!")
            return "review"
            
        # SEMANTIC CHECK: If SQL contains non-SELECT keywords (DML), trigger a review
        if name == "text_to_sql":
            query = str(tool_call["args"].get("question", "")).lower()
            dangerous_keywords = ["drop", "delete", "insert", "update", "truncate", "alter", "create"]
            if any(k in query for k in dangerous_keywords):
                logger.warning(f"SECURITY_ALERT: Potential DML detected in SQL question: {query}!")
                return "review"
                
    return "safe"

# --- Phase 4: Unified Router (Permission + Logic) ---
def route_after_core_with_permissions(state: AgentState) -> str:
    """Unified router: Determines node AND checks permissions."""
    next_node = state.get("next_node", "synthesize")
    
    # If the LLM wants tools, check if they are safe
    if next_node == "tools":
        safety = classify_tool_calls(state)
        # If unsafe, go to review. If safe, go to tool_node
        return "human_review" if safety == "review" else "tool_node"
    
    # NEW: Architect (Planner) routes to the Technician (Executor)
    if next_node == "executor":
        return "executor"
    
    # Failsafe for syntax variations
    if next_node == "response": return "synthesize"
    
    return next_node
