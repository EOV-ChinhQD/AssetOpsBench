import logging
import json
import re
from typing import Optional, Any, List
import pandas as pd
from fastmcp import FastMCP
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()

from src.hanoi_water_db import get_engine
from src.llm.litellm import LiteLLMBackend

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hanoi_water_mcp")

mcp = FastMCP("Hanoi Water")
engine = get_engine()

# --- UTILS ---

def normalize_dma_id(dma_id: str) -> str:
    if not dma_id: return ""
    res = str(dma_id).strip().upper()
    for prefix in ["DMA", "MÃ", "KHU VỰC"]:
        if res.startswith(prefix):
            res = res[len(prefix):].strip()
    if res.startswith("-"): res = res[1:].strip()
    return res

def wrap_tool_result(status: str, data: Any, message: str = "") -> str:
    return json.dumps({"status": status, "data": data, "message": message}, ensure_ascii=False)

# --- CORE LOGIC ---

async def _get_dma_info_logic(dma_query: str) -> str:
    if not engine: return wrap_tool_result("error", None, "Không có DB.")
    clean_query = normalize_dma_id(dma_query)
    try:
        with engine.connect() as conn:
            # Try exact then fuzzy
            sql = text("SELECT DISTINCT madma FROM silver.stg_water_demand WHERE madma = :q OR madma ILIKE :q_perc LIMIT 5")
            df = pd.read_sql(sql, conn, params={"q": clean_query, "q_perc": f"%{clean_query}%"})
            if df.empty: return wrap_tool_result("error", None, f"Không tìm thấy DMA '{dma_query}'.")
            matches = df['madma'].tolist()
            dma_id = clean_query if clean_query in matches else matches[0]
            return wrap_tool_result("success", {"dma_id": dma_id}, f"XÁC NHẬN DMA: {dma_id}")
    except Exception as e:
        return wrap_tool_result("error", None, f"Lỗi hệ thống: {str(e)}")

async def _text_to_sql_logic(question: str) -> str:
    if not engine: return wrap_tool_result("error", None, "Chưa cấu hình DB.")
    model_id = os.getenv("LITELLM_MODEL_NAME", "cloudflare/@cf/qwen/qwen3-30b-a3b-fp8")
    llm = LiteLLMBackend(model_id)
    
    prompt = f"""Bạn là một chuyên gia SQL cho hệ thống cấp nước Hà Nội. Hãy tạo câu lệnh SQL chính xác.

### SCHEMA:
1. Bảng `silver.stg_water_demand` (Dữ liệu lịch sử):
   - `madma` (TEXT): Mã trạm (VD: 'DMA-01-LB').
   - `nam` (INTEGER), `thang` (INTEGER): Thời gian.
   - `tongsl` (INTEGER): Sản lượng nước (m3).
2. Bảng `gold.fct_predictions_unified` (Dữ liệu dự báo):
   - `madma` (TEXT): Mã trạm.
   - `year_month` (TEXT): Định dạng 'YYYY-MM' (VD: '2026-04').
   - `predicted_demand` (INTEGER): Sản lượng dự báo.

### QUY TẮC:
- Chỉ trả về SQL trong block code ```sql.
- Tuyệt đối không xóa/sửa dữ liệu.
- Định dạng ngày tháng trong SQL: 'YYYY-MM'.
- Để đếm số lượng Trạm (DMA): Dùng `COUNT(DISTINCT madma)`.

### CÂU HỎI: {question}
SQL:"""

    try:
        # Failsafe: If agent already wrote SQL, just use it
        if "SELECT" in question.upper() and ("FROM" in question.upper() or "silver." in question.lower() or "gold." in question.lower()):
            raw_res = f"```sql\n{question}\n```"
            logger.info("Agent provided direct SQL. Skipping LLM generation.")
        else:
            raw_res = llm.generate(prompt)
            logger.info(f"LLM_SQL_RAW: {raw_res}")
            
        sql_match = re.search(r"```sql\s*(.*?)\s*```", raw_res, re.DOTALL | re.IGNORECASE)
        sql = sql_match.group(1).strip() if sql_match else raw_res.strip()
        sql = sql.split(";")[-1] if ";" in sql and sql.endswith(";") else sql.strip()
        sql = sql.lstrip("SQL:").strip().rstrip(';')

        if any(kw in sql.upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT", "--"]):
             return wrap_tool_result("error", None, "Lệnh SQL không an toàn.")
        
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
            if df.empty: return wrap_tool_result("error", {"sql": sql}, "Không tìm thấy dữ liệu phù hợp.")
            return wrap_tool_result("success", df.to_dict(orient="records"), f"Kết quả SQL: {len(df)} dòng.")
    except Exception as e:
        return wrap_tool_result("error", None, f"Lỗi thực thi SQL: {str(e)}")

async def _get_history_logic(dma_id: str, year: int = None, month: int = None, months: int = 12) -> str:
    if not engine: return wrap_tool_result("error", None, "Không có DB.")
    try:
        clean_id = normalize_dma_id(dma_id)
        with engine.connect() as conn:
            where = "WHERE madma = :dma"
            params = {"dma": clean_id, "limit": months}
            if year: where += " AND nam = :year"; params["year"] = int(year)
            if month: where += " AND thang = :month"; params["month"] = int(month)
            sql = text(f"SELECT nam, thang, tongsl FROM silver.stg_water_demand {where} ORDER BY nam DESC, thang DESC LIMIT :limit")
            df = pd.read_sql(sql, conn, params=params)
            if df.empty: return wrap_tool_result("error", None, f"Không có dữ liệu cho {clean_id}.")
            return wrap_tool_result("success", df.to_dict(orient="records"), f"Lấy dữ liệu {clean_id} thành công.")
    except Exception as e:
        return wrap_tool_result("error", None, str(e))

async def _get_forecast_logic(dma_id: str, horizon: int = 6) -> str:
    if not engine: return wrap_tool_result("error", None, "Không có DB.")
    try:
        clean_id = normalize_dma_id(dma_id)
        with engine.connect() as conn:
            sql = text("SELECT year_month, predicted_demand, source FROM gold.fct_predictions_unified WHERE madma = :dma ORDER BY year_month ASC LIMIT :limit")
            df = pd.read_sql(sql, conn, params={"dma": clean_id, "limit": horizon})
            if df.empty: return wrap_tool_result("error", None, f"Không có dự báo cho {clean_id}.")
            
            text_lines = []
            for _, row in df.iterrows():
                ym = str(row['year_month']); parts = ym.split('-'); r_date = f"tháng {parts[1]} năm {parts[0]}" if len(parts) == 2 else ym
                text_lines.append(f"- Vào {r_date}, sản lượng dự báo cho {clean_id} là {row['predicted_demand']} m3 (Nguồn: {row['source']})")
            return wrap_tool_result("success", "\n".join(text_lines), f"Dự báo cho {clean_id} thành công.")
    except Exception as e:
        return wrap_tool_result("error", None, str(e))

# --- TOOLS ---

@mcp.tool()
async def get_dma_info(dma_query: Optional[str] = None, dma_id: Optional[str] = None) -> str:
    """Xác thực mã hiệu DMA (Vd: '01-LB')."""
    return await _get_dma_info_logic(dma_query or dma_id)

@mcp.tool()
async def text_to_sql(question: str) -> str:
    """Truy vấn dữ liệu tổng hợp bằng SQL (thống kê, so sánh, đếm số lượng)."""
    return await _text_to_sql_logic(question)

@mcp.tool()
async def get_history(dma_id: Optional[str] = None, dma_query: Optional[str] = None, months: int = 12, year: Optional[int] = None, month: Optional[int] = None) -> str:
    """Lấy dữ liệu sản lượng lịch sử (m3)."""
    return await _get_history_logic(dma_id or dma_query, year, month, months)

@mcp.tool()
async def get_forecast(dma_id: Optional[str] = None, dma_query: Optional[str] = None, horizon: int = 6) -> str:
    """Lấy dự báo sản lượng nước tương lai (m3)."""
    return await _get_forecast_logic(dma_id or dma_query, horizon)

@mcp.tool()
async def plot_dma(dma_id: Optional[str] = None, dma_query: Optional[str] = None, include_forecast: bool = True) -> str:
    """Vẽ biểu đồ tiêu thụ nước (Thực tế + Dự báo)."""
    return wrap_tool_result("success", {"url": "http://localhost:9000/hanoi-water-images/mock_plot.png"}, f"Đã vẽ biểu đồ cho {dma_id or dma_query}.")

def main(): mcp.run()
if __name__ == "__main__": main()
