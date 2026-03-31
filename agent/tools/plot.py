import json
import os
import time
import asyncio
import pandas as pd
import matplotlib.pyplot as plt
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import Union
import logging

async def plot_async(dma_id: Union[str, list], include_forecast: bool = False, question: str = "") -> str:
    """
    Tạo cấu hình biểu đồ Vega-Lite (JSON) hỗ trợ một hoặc nhiều DMA.
    Tự động chọn Bar Chart nếu so sánh nhiều vùng, Line Chart nếu theo thời gian.
    """
    from src.api.server.deps import get_repo_dep
    from src.api.server.utils.normalization import normalize_dma_id
    
    try:
        repo = get_repo_dep()
        
        # 1. Normalize input DMA(s)
        if isinstance(dma_id, str):
            # Handle comma separated string
            dma_list = [normalize_dma_id(d.strip()) for d in dma_id.split(",") if d.strip()]
        else:
            dma_list = [normalize_dma_id(d) for d in dma_id]
        
        if not dma_list:
            return "Thiếu mã DMA để vẽ biểu đồ."
            
        all_data = []
        
        for dma in dma_list:
            # Fetch Historical (Last 6 months for comparisons, or more if single)
            limit_hist = 12 if len(dma_list) == 1 else 3
            sql_hist = """
            SELECT year_month, tongsl as val
            FROM silver.stg_water_demand 
            WHERE madma = %(dma)s 
            ORDER BY year_month DESC LIMIT %(limit)s
            """
            df_hist = repo.query(sql_hist, {"dma": dma, "limit": limit_hist})
            
            if not df_hist.empty:
                for _, r in df_hist.iterrows():
                    all_data.append({"time": r["year_month"], "value": r["val"], "type": "Thực tế", "dma": dma})
            
            # Fetch Forecast
            if include_forecast:
                sql_fore = """
                SELECT year_month, predicted_demand as val 
                FROM gold.fct_predictions_unified 
                WHERE madma = %(dma)s 
                ORDER BY year_month ASC LIMIT 3
                """
                df_fore = repo.query(sql_fore, {"dma": dma})
                if not df_fore.empty:
                    for _, r in df_fore.iterrows():
                        all_data.append({"time": r["year_month"], "value": r["val"], "type": "Dự báo", "dma": dma})

        if not all_data:
            return f"Không tìm thấy dữ liệu cho các DMA: {', '.join(dma_list)}"

        # 2. Template Selection & Injection
        num_dmas = len(dma_list)
        # Check if there are anomalies in data
        has_anomalies = any(d.get("is_anomaly") for d in all_data)
        
        # Decide template
        template_name = "time_series_single"
        if num_dmas > 1:
            template_name = "time_series_multi_dma"
        elif has_anomalies:
            template_name = "anomaly_highlight"
            
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": f"Biểu đồ tiêu thụ: {', '.join(dma_list)}",
            "width": "container",
            "height": 300,
            "data": {"values": all_data}
        }
        
        if template_name == "time_series_single":
            spec.update({
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": {"field": "time", "type": "ordinal", "title": "Thời gian", "axis": {"labelAngle": -45}},
                    "y": {"field": "value", "type": "quantitative", "title": "Sản lượng (m³)"},
                    "color": {"field": "type", "type": "nominal", "title": "Phân loại"},
                    "tooltip": [{"field": "time"}, {"field": "value"}, {"field": "type"}]
                }
            })
        elif template_name == "time_series_multi_dma":
            spec.update({
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": {"field": "time", "type": "ordinal", "title": "Thời gian"},
                    "y": {"field": "value", "type": "quantitative", "title": "Sản lượng (m³)"},
                    "color": {"field": "dma", "type": "nominal", "title": "DMA"},
                    "strokeDash": {"field": "type", "type": "nominal", "title": "Loại dữ liệu"},
                    "tooltip": [{"field": "dma"}, {"field": "time"}, {"field": "value"}]
                }
            })
        elif template_name == "anomaly_highlight":
            spec.update({
                "layer": [
                    {
                        "mark": {"type": "line", "point": True},
                        "encoding": {
                            "x": {"field": "time", "type": "ordinal"},
                            "y": {"field": "value", "type": "quantitative"}
                        }
                    },
                    {
                        "mark": {"type": "point", "size": 100, "color": "red"},
                        "transform": [{"filter": "datum.is_anomaly == true"}],
                        "encoding": {
                            "x": {"field": "time", "type": "ordinal"},
                            "y": {"field": "value", "type": "quantitative"},
                            "tooltip": [{"field": "time"}, {"field": "value"}, {"field": "reason"}]
                        }
                    }
                ]
            })

        return json.dumps({
            "chart_json": spec,
            "chart_type": "vegalite",
            "template": template_name,
            "message": f"Đã tạo biểu đồ '{template_name}' cho {num_dmas} vùng."
        }, ensure_ascii=False)

    except Exception as e:
        logging.error(f"Error in Plot Tool: {e}", exc_info=True)
        return f"Lỗi tạo biểu đồ: {str(e)}"

class PlotInput(BaseModel):
    dma_id: str = Field(description="Mã DMA chính xác, hoặc danh sách các mã cách nhau bằng dấu phẩy để vẽ biểu đồ so sánh (ví dụ: '17-TL, 12-PL, 05-BĐ')")
    include_forecast: bool = Field(default=False, description="Có bao gồm dữ liệu dự báo không?")
    question: str = Field(default="", description="Câu hỏi gốc (tùy chọn)")

def plot_sync(dma_id: str, include_forecast: bool = False, question: str = "") -> str:
    return asyncio.run(plot_async(dma_id, include_forecast, question))

plot_tool = StructuredTool.from_function(
    name="plot",
    description="Vẽ biểu đồ tiêu thụ (lịch sử/dự báo). Bắt buộc: dma_id từ get_dma_info. Hỗ trợ biểu đồ Cột (Bar Chart) tự động nếu truyền nhiều DMA.",
    func=plot_sync,
    coroutine=plot_async,
    args_schema=PlotInput
)
