import logging
import asyncio
from typing import Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from src.api.server.deps import get_repo_dep

logger = logging.getLogger(__name__)

class CompareInput(BaseModel):
    dma_id: str = Field(description="Mã DMA chính xác (ví dụ: '17-TL')")
    period_a_start: str = Field(description="Bắt đầu kỳ A (YYYY-MM)")
    period_a_end: str = Field(description="Kết thúc kỳ A (YYYY-MM)")
    period_b_start: str = Field(description="Bắt đầu kỳ B (YYYY-MM)")
    period_b_end: str = Field(description="Kết thúc kỳ B (YYYY-MM)")

async def get_comparison_async(dma_id: str, period_a_start: str, period_a_end: str, 
                                period_b_start: str, period_b_end: str) -> str:
    """So sánh tiêu thụ của 1 DMA giữa hai kỳ thời gian."""
    try:
        from src.api.server.utils.normalization import normalize_dma_id
        dma_id = normalize_dma_id(dma_id)
        
        repo = get_repo_dep()
        
        def _get_stats(p_start, p_end):
            sql = """
            SELECT AVG(tongsl) as avg_val, MAX(tongsl) as max_val, MIN(tongsl) as min_val, SUM(tongsl) as sum_val
            FROM silver.stg_water_demand 
            WHERE madma = %(dma)s AND year_month BETWEEN %(start)s AND %(end)s
            """
            df = repo.query(sql, {"dma": dma_id, "start": p_start, "end": p_end})
            if df.empty or df['avg_val'].iloc[0] is None:
                return None
            return df.iloc[0].to_dict()

        stats_a = _get_stats(period_a_start, period_a_end)
        stats_b = _get_stats(period_b_start, period_b_end)
        
        if not stats_a or not stats_b:
            return f"Không đủ dữ liệu tại DMA {dma_id} để so sánh giữa hai kỳ này."
            
        diff_avg = stats_b['avg_val'] - stats_a['avg_val']
        diff_pct = (diff_avg / stats_a['avg_val'] * 100) if stats_a['avg_val'] > 0 else 0
        direction = "TĂNG" if diff_pct > 0 else "GIẢM"
        
        return (
            f"BÁO CÁO SO SÁNH DMA {dma_id}:\n"
            f"- Kỳ A ({period_a_start} đến {period_a_end}): TB {stats_a['avg_val']:,.1f} m³, Tổng {stats_a['sum_val']:,.0f} m³\n"
            f"- Kỳ B ({period_b_start} đến {period_b_end}): TB {stats_b['avg_val']:,.1f} m³, Tổng {stats_b['sum_val']:,.0f} m³\n"
            f"- KẾT LUẬN: Kỳ B {direction} {abs(diff_pct):.1f}% so với kỳ A."
        )

    except Exception as e:
        logger.error(f"Error in comparison tool: {e}", exc_info=True)
        return f"Lỗi thực hiện so sánh: {str(e)}"

def get_comparison_sync(*args, **kwargs):
    return asyncio.run(get_comparison_async(*args, **kwargs))

compare_tool = StructuredTool.from_function(
    name="compare_periods",
    description="So sánh tiêu thụ giữa hai khoảng thời gian. Bắt buộc: dma_id từ get_dma_info.",
    func=get_comparison_sync,
    coroutine=get_comparison_async,
    args_schema=CompareInput
)
