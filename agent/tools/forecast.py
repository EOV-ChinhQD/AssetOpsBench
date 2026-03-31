import json
import asyncio
from langchain_core.tools import Tool
from src.api.server.agent.tools.historical import parse_tool_input
from src.api.server.tools.executors.forecast_executor import execute_forecast
from src.api.server.tools.contracts import ForecastRequest
from src.api.server.deps import get_forecasting_service_dep, get_long_term_service_dep, get_model_dep, get_repo_dep

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

class ForecastInput(BaseModel):
    dma_id: str = Field(description="Mã DMA cụ thể (ví dụ: 17-TL)")
    horizon_months: int = Field(default=1, description="Số tháng dự báo tới")

async def get_forecast_async(dma_id: str, horizon_months: int = 1) -> dict:
    """Lấy dữ liệu DỰ BÁO (tương lai) và TRẢ VỀ bản tóm tắt phân tích (summary, capacity_pct, warning_level)."""
    try:
        from src.api.server.utils.normalization import normalize_dma_id
        import logging
        logger = logging.getLogger(__name__)
        
        dma_clean = normalize_dma_id(dma_id)
        repo = get_repo_dep()
        
        # Query unified table directly
        from src.core.constants import GOLD_PREDICTIONS_UNIFIED_TABLE
        sql = f"""
            SELECT madma, predicted_demand, year_month, source 
            FROM gold.{GOLD_PREDICTIONS_UNIFIED_TABLE}
            WHERE madma = %(dma)s
            ORDER BY year_month ASC
            LIMIT %(limit)s
        """
        params = {"dma": dma_clean, "limit": horizon_months}
        df = repo.query(sql, params)
        
        logger.info(f"Forecast query for {dma_clean} (horizon={horizon_months}) returned {len(df)} rows")
        
        if df.empty:
            logger.warning(f"No forecast data found for DMA {dma_clean} in gold.v_forecasts")
            return {"summary": f"Không có dữ liệu dự báo cụ thể cho DMA {dma_id} trong hệ thống.", "capacity_pct": 0, "warning_level": "NORMAL"}

        # Estimate capacity for alerts
        df_cap = repo.query("SELECT MAX(tongsl) as max_val FROM silver.stg_water_demand WHERE madma = %(dma)s", {"dma": dma_id})
        max_hist = float(df_cap['max_val'].iloc[0]) if not df_cap.empty and df_cap['max_val'].iloc[0] is not None else 100000
        capacity = max_hist * 1.2

        summary_lines = [f"DỮ LIỆU DỰ BÁO (Tương lai) - DMA {dma_id}:", f"(Dự báo trong {horizon_months} tháng tới)"]
        max_pct = 0
        warnings = []

        for _, r in df.iterrows():
            val = float(r["predicted_demand"])
            month = r["year_month"]
            src = r["source"]
            pct_cap = (val / capacity * 100) if capacity > 0 else 0
            max_pct = max(max_pct, pct_cap)
            
            line = f"- {month} ({src}): {val:,.1f} m³"
            summary_lines.append(line)
            
            if pct_cap > 90:
                warnings.append(f"Tháng {month} dự kiến vượt 90% công suất")

        warning_level = "NORMAL"
        if max_pct > 100: warning_level = "CRITICAL"
        elif max_pct > 90: warning_level = "WARNING"

        if warnings:
            summary_lines.append(f"CẢNH BÁO: {'; '.join(warnings)}")
            
        return {
            "summary": "\n".join(summary_lines),
            "capacity_pct": round(max_pct, 1),
            "warning_level": warning_level,
            "dma_id": dma_id
        }

    except Exception as e:
        import logging
        logging.error(f"Error in Forecast Tool Summary: {e}", exc_info=True)
        return {"summary": f"Lỗi phân tích dự báo: {str(e)}", "capacity_pct": 0, "warning_level": "ERROR"}

def get_forecast_sync(dma_id: str, horizon_months: int = 1) -> str:
    return asyncio.run(get_forecast_async(dma_id, horizon_months))

forecast_tool = StructuredTool.from_function(
    name="get_forecast",
    description="Lấy dự báo tiêu thụ nước cho 1 DMA cụ thể.",
    func=get_forecast_sync,
    coroutine=get_forecast_async,
    args_schema=ForecastInput
)
