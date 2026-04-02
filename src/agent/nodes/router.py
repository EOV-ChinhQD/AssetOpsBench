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

        lookup_candidates = self._collect_lookup_candidates(last_msg.tool_calls, state)
        lookup_results = await self._run_auto_lookup(state, lookup_candidates)
        normalized_tool_calls = self._normalize_tool_calls(last_msg.tool_calls, state)

        tasks = []
        for tool_call in normalized_tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            logger.info(f"PARALLEL_EXEC: Tool {name} called with args: {args}")
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
        gathered = await asyncio.gather(*tasks) if tasks else []
        return {"messages": lookup_results + gathered}

    def _collect_lookup_candidates(self, tool_calls: List[dict], state: AgentState) -> List[str]:
        resolved_dma = state.get("resolved_dma") or {}
        known_keys = {key.upper() for key in resolved_dma.keys()}
        lookup_names = {"get_history", "get_forecast", "plot_dma"}
        candidates = []
        seen = set()

        for tool_call in tool_calls:
            name = tool_call.get("name")
            if name not in lookup_names:
                continue

            args = tool_call.get("args", {})
            candidate = args.get("dma_id") or args.get("dma_query")
            if not candidate:
                continue

            candidate_str = str(candidate).strip()
            if not candidate_str:
                continue

            candidate_key = candidate_str.upper()
            if candidate_key in known_keys or candidate_key in seen:
                continue

            seen.add(candidate_key)
            candidates.append(candidate_str)

        return candidates

    def _normalize_tool_calls(self, tool_calls: List[dict], state: AgentState) -> List[dict]:
        normalized = []
        fallback_dma = self._find_dma_from_lookup(tool_calls, state)
        for tc in tool_calls:
            normalized.append({
                "name": tc.get("name"),
                "args": self._normalize_args(tc.get("args", {}), state, fallback_dma),
                "id": tc.get("id")
            })
        return normalized

    def _normalize_args(self, args: dict, state: AgentState, fallback_dma: Optional[str]) -> dict:
        normalized_args = dict(args)
        canonical = self._resolve_canonical_dma(normalized_args, state)
        if not canonical:
            canonical = fallback_dma
        if canonical and not normalized_args.get("dma_id"):
            normalized_args["dma_id"] = canonical

        normalized_args.pop("dma_code", None)
        if normalized_args.get("dma_query") == canonical:
            normalized_args.pop("dma_query", None)

        return normalized_args

    def _resolve_canonical_dma(self, args: dict, state: AgentState) -> Optional[str]:
        resolved = state.get("resolved_dma", {})
        if not resolved:
            return None

        for key in ("dma_id", "dma_query", "dma_code"):
            value = args.get(key)
            if not value:
                continue
            value_str = str(value).strip()
            if not value_str:
                continue
            upper = value_str.upper()
            if upper in resolved:
                return resolved[upper]
            return value_str

        # Fallback to any known canonical DMA
        for val in resolved.values():
            if val:
                return val

        return None

    def _find_dma_from_lookup(self, tool_calls: List[dict], state: AgentState) -> Optional[str]:
        resolved = state.get("resolved_dma", {})
        for tc in tool_calls:
            if tc.get("name") != "get_dma_info":
                continue
            args = tc.get("args", {})
            for key in ("dma_id", "dma_query", "dma_code"):
                value = args.get(key)
                if not value:
                    continue
                value_str = str(value).strip()
                if not value_str:
                    continue
                upper = value_str.upper()
                if upper in resolved:
                    return resolved[upper]
                return value_str
        return None

    async def _run_auto_lookup(self, state: AgentState, candidates: List[str]) -> List[ToolMessage]:
        if not candidates:
            return []

        lookup_tool = self.registry.tools.get("get_dma_info")
        if not lookup_tool:
            return []

        meta = self.registry.metadata.get("get_dma_info")
        limit = (meta.max_concurrent if meta and meta.max_concurrent else self.default_max_concurrency)
        results = []

        for candidate in candidates:
            logger.info(f"AUTO_LOOKUP: Ensuring DMA info for '{candidate}'")
            lookup_msg = await self._run_tool(lookup_tool, {"dma_query": candidate}, str(uuid.uuid4()), concurrency_limit=limit)
            self._merge_resolved(state, candidate, lookup_msg)
            results.append(lookup_msg)

        return results

    def _merge_resolved(self, state: AgentState, query: str, tool_message: ToolMessage):
        resolved = state.setdefault("resolved_dma", {})
        query_key = str(query).strip()
        if not query_key:
            return

        query_upper = query_key.upper()
        canonical = None

        try:
            payload = json.loads(str(tool_message.content))
            if payload.get("status") == "success":
                canonical = str(payload.get("data", {}).get("dma_id", "")).strip()
        except Exception:
            pass

        if canonical:
            canonical_key = canonical.upper()
            resolved[canonical_key] = canonical
            resolved[query_upper] = canonical
        else:
            resolved[query_upper] = query_key

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
async def route_after_core_with_permissions(state: AgentState) -> str:
    """Unified router: Action-First logic. Determines node AND checks permissions."""
    messages = state.get("messages", [])
    if not messages: return "synthesize"
    
    last_msg = messages[-1]
    
    # 🟢 ACTION-FIRST GUARD: If there are tool calls, we MUST execute them or review them.
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        safety = classify_tool_calls(state)
        logger.info(f"ROUTE: Tool calls detected. Safety={safety}")
        return "human_review" if safety == "review" else "tool_node"

    # Default to next_node from LLM if no actions
    next_node = state.get("next_node", "synthesize")
    
    # Architecture alignment
    if next_node == "executor": return "executor"
    if next_node in {"tools", "tool_node"}:
         # Fallback in case tool_calls was missed but LLM requested it
         return "tool_node"

    logger.info(f"ROUTE: No actions detected. Moving to {next_node}")
    return next_node if next_node != "response" else "synthesize"
