import json
import logging
from typing import Iterable, Union

import pandas as pd
from sqlalchemy import text

from src.hanoi_water_db import get_engine

logger = logging.getLogger(__name__)


def normalize_dma_id(dma_id: str) -> str:
    if not dma_id:
        return ""
    res = str(dma_id).strip().upper()
    for prefix in ["DMA", "MÃ", "KHU VỰC"]:
        if res.startswith(prefix):
            res = res[len(prefix) :].strip()
    if res.startswith("-"):
        res = res[1:].strip()
    return res


def _format_spec(all_data, dma_list):
    num_dmas = len(dma_list)
    has_anomalies = any(d.get("is_anomaly") for d in all_data)
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
        "data": {"values": all_data},
    }

    if template_name == "time_series_single":
        spec.update(
            {
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": {
                        "field": "time",
                        "type": "ordinal",
                        "title": "Thời gian",
                        "axis": {"labelAngle": -45},
                    },
                    "y": {"field": "value", "type": "quantitative", "title": "Sản lượng (m³)"},
                    "color": {"field": "type", "type": "nominal", "title": "Phân loại"},
                    "tooltip": [{"field": "time"}, {"field": "value"}, {"field": "type"}],
                },
            }
        )
    elif template_name == "time_series_multi_dma":
        spec.update(
            {
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": {"field": "time", "type": "ordinal", "title": "Thời gian"},
                    "y": {"field": "value", "type": "quantitative", "title": "Sản lượng (m³)"},
                    "color": {"field": "dma", "type": "nominal", "title": "DMA"},
                    "strokeDash": {"field": "type", "type": "nominal", "title": "Loại dữ liệu"},
                    "tooltip": [{"field": "dma"}, {"field": "time"}, {"field": "value"}],
                },
            }
        )
    else:
        spec.update(
            {
                "layer": [
                    {
                        "mark": {"type": "line", "point": True},
                        "encoding": {
                            "x": {"field": "time", "type": "ordinal"},
                            "y": {"field": "value", "type": "quantitative"},
                        },
                    },
                    {
                        "mark": {"type": "point", "size": 100, "color": "red"},
                        "transform": [{"filter": "datum.is_anomaly == true"}],
                        "encoding": {
                            "x": {"field": "time", "type": "ordinal"},
                            "y": {"field": "value", "type": "quantitative"},
                            "tooltip": [{"field": "time"}, {"field": "value"}, {"field": "reason"}],
                        },
                    },
                ]
            }
        )

    return spec, template_name


def build_plot_payload(
    dma_id: Union[str, Iterable[str], None], include_forecast: bool = False, question: str = ""
) -> dict:
    engine = get_engine()
    if not engine:
        raise RuntimeError("Database engine is not initialized.")

    dma_list = []
    if isinstance(dma_id, str):
        candidates = [d.strip() for d in dma_id.split(",") if d.strip()]
    elif dma_id is None:
        candidates = []
    else:
        candidates = list(dma_id)

    for item in candidates:
        norm = normalize_dma_id(item)
        if norm:
            dma_list.append(norm)

    if not dma_list:
        raise ValueError("Thiếu mã DMA để vẽ biểu đồ.")

    all_data = []
    for dma in dma_list:
        limit_hist = 12 if len(dma_list) == 1 else 3
        hist_query = text(
            """
            SELECT year_month, tongsl as val
            FROM silver.stg_water_demand
            WHERE madma = :dma
            ORDER BY year_month DESC
            LIMIT :limit
            """
        )
        df_hist = pd.read_sql(hist_query, engine, params={"dma": dma, "limit": limit_hist})
        for _, row in df_hist.iterrows():
            all_data.append({"time": str(row["year_month"]), "value": row["val"], "type": "Thực tế", "dma": dma})

        if include_forecast:
            fore_query = text(
                """
                SELECT year_month, predicted_demand as val
                FROM gold.fct_predictions_unified
                WHERE madma = :dma
                ORDER BY year_month ASC
                LIMIT 3
                """
            )
            df_fore = pd.read_sql(fore_query, engine, params={"dma": dma})
            for _, row in df_fore.iterrows():
                all_data.append({"time": str(row["year_month"]), "value": row["val"], "type": "Dự báo", "dma": dma})

    if not all_data:
        raise ValueError(f"Không tìm thấy dữ liệu cho các DMA: {', '.join(dma_list)}")

    spec, template = _format_spec(all_data, dma_list)
    return {
        "chart_json": spec,
        "chart_type": "vegalite",
        "template": template,
        "message": f"Đã tạo biểu đồ '{template}' cho {len(dma_list)} vùng.",
        "question": question,
    }
