import json
import asyncio
import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.tools.executors.history_executor import execute_history
from src.tools.contracts import HistoryRequest
from src.deps import get_repo_dep

def parse_tool_input(input_str: str) -> dict:
    input_str = input_str.strip().strip("'").strip('"')
    params = {}
    for pair in input_str.split(','):
        if '=' in pair:
            key, val = pair.split('=', 1)
            params[key.strip()] = val.strip()
    
    # Fallback: if no key-value pairs but string has content, assume it's dma_id
    if not params and input_str:
        return {"dma_id": input_str}
    return params

class HistoricalInput(BaseModel):
    dma_id: str = Field(description="Mã DMA cụ thể (ví dụ: 17-TL)")
    months: int = Field(default=12, description="Số tháng lùi lại")

async def get_historical_async(dma_id: str, months: int = 12) -> str:
    """Lấy dữ liệu LỊCH SỬ (đã xảy ra) và TRẢ VỀ bản tóm tắt phân tích (avg, max, min, trend, bất thường)."""
    try:
        from src.utils.normalization import normalize_dma_id
        dma_id = normalize_dma_id(dma_id)
        
        req = HistoryRequest(dma_id=dma_id, months=months, audit_id="langgraph")
        repo = get_repo_dep()
        res = await execute_history(req, repo)
        
        if not res.success:
            return f"Lỗi lấy lịch sử: {res.error.message if res.error else 'Unknown'}"
        
        data = res.data.get("content", [])[0].get("data", [])
        if not data:
            return f"Không có dữ liệu lịch sử cho DMA {dma_id}."

        # Calculation logic for Summary
        values = [float(r["actual"]) for r in data if r.get("actual") is not None]
        if not values:
            return f"Dữ liệu cho DMA {dma_id} rỗng hoặc không có chỉ số tiêu thụ."

        avg_val = sum(values) / len(values)
        max_val = max(values)
        min_val = min(values)
        
        # Simple trend
        trend = "tăng" if values[-1] > values[0] else "giảm"
        change_pct = ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0
        
        # Anomalies (>20% deviation)
        anomalies = [
            f"{r['year_month']}: {r['actual']} m³" 
            for r in data 
            if abs(float(r["actual"]) - avg_val) / avg_val > 0.20
        ]

        summary = (
            f"DỮ LIỆU THỰC TẾ (Lịch sử) - DMA {dma_id}:\n"
            f"(Dữ liệu đã xác minh trong {len(values)} tháng qua)\n"
            f"- Trung bình: {avg_val:,.1f} m³\n"
            f"- Cao nhất: {max_val:,.1f} m³ | Thấp nhất: {min_val:,.1f} m³\n"
            f"- Xu hướng: {trend} ({abs(change_pct):.1f}% so với thời điểm bắt đầu kỳ tra cứu)\n"
        )
        if anomalies:
            summary += f"- CẢNH BÁO Bất thường (>20%): {', '.join(anomalies)}\n"
        
        return summary

    except Exception as e:
        logging.error(f"Error in Historical Tool Summary: {e}", exc_info=True)
        return f"Lỗi phân tích lịch sử: {str(e)}"

def get_historical_sync(dma_id: str, months: int = 12) -> str:
    return asyncio.run(get_historical_async(dma_id, months))

historical_tool = StructuredTool.from_function(
    name="get_historical",
    description="Lấy báo cáo phân tích lịch sử tiêu thụ. Bắt buộc: phải có dma_id chính xác (từ get_dma_info).",
    func=get_historical_sync,
    coroutine=get_historical_async,
    args_schema=HistoricalInput
)
