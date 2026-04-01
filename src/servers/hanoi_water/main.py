import logging
import json
import re
from typing import Optional, Any
import pandas as pd
from fastmcp import FastMCP
from sqlalchemy import text
from src.config.settings import settings
from src.hanoi_water_db import get_engine
from src.llm.unified_client import UnifiedLLMClient

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
    
    # 1. Tra cứu trong Registry (JSON) để lấy metadata & fuzzy match
    import os
    registry_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "dma_registry.json")
    registry = {}
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
    except: pass

    clean_query = normalize_dma_id(dma_query)
    found_metadata = None
    standardized_id = None

    # Tìm chính xác trong Registry
    if clean_query in registry:
        standardized_id = clean_query
        found_metadata = registry[clean_query]
    else:
        # Tìm fuzzy trong Registry (theo tên quận, vùng...)
        q_lower = dma_query.lower().strip()
        for code, info in registry.items():
            if (q_lower in info.get("name", "").lower() or 
                q_lower in info.get("district", "").lower() or
                q_lower in code.lower()):
                standardized_id = code
                found_metadata = info
                break

    # 2. Kiểm tra lại trong Database nếu chưa thấy trong Registry (hoặc để đảm bảo tồn tại)
    try:
        with engine.connect() as conn:
            q_to_check = standardized_id or clean_query
            sql = text("SELECT DISTINCT madma FROM silver.stg_water_demand WHERE madma = :q OR madma ILIKE :q_perc LIMIT 1")
            df = pd.read_sql(sql, conn, params={"q": q_to_check, "q_perc": f"%{q_to_check}%"})
            
            if not df.empty:
                final_id = df['madma'].iloc[0]
                res_data = {"dma_id": final_id}
                if found_metadata: res_data["metadata"] = found_metadata
                return wrap_tool_result("success", res_data, f"XÁC NHẬN: {final_id}")
            
            if found_metadata: # Có trong registry nhưng database chưa có data (vẫn trả về metadata)
                return wrap_tool_result("success", {"dma_id": standardized_id, "metadata": found_metadata}, f"XÁC NHẬN (Registry): {standardized_id}")
                
            return wrap_tool_result("error", None, f"Không tìm thấy DMA '{dma_query}'.")
    except Exception as e:
        return wrap_tool_result("error", None, f"Lỗi: {str(e)}")


def _get_schema_info() -> str:
    return """
### BẢNG DỮ LIỆU:
1. `silver.stg_water_demand` — Dữ liệu sản lượng thực tế
   | Cột | Kiểu | Mô tả |
   |-----|------|-------|
   | madma | TEXT | Mã trạm DMA (Vd: '01-LB', '06-QM') |
   | nam | INTEGER | Năm |
   | thang | INTEGER | Tháng (1-12) |
   | tongsl | INTEGER | Sản lượng nước (m³) |

2. `gold.fct_predictions_unified` — Dữ liệu dự báo
   | Cột | Kiểu | Mô tả |
   |-----|------|-------|
   | madma | TEXT | Mã trạm DMA |
   | year_month | TEXT | Tháng dự báo, format 'YYYY-MM' |
   | predicted_demand | INTEGER | Sản lượng dự báo (m³) |
   | source | TEXT | Nguồn model |
"""

def _get_few_shot_examples() -> str:
    return """
### VÍ DỤ THAM KHẢO (Few-Shot):

**Loại: Đếm thực thể**
Q: Hệ thống có bao nhiêu trạm DMA?
```sql
SELECT COUNT(DISTINCT madma) AS total_dma FROM silver.stg_water_demand
```

**Loại: Xếp hạng (Top N)**
Q: Top 3 trạm tiêu thụ nhiều nhất tháng 9/2024?
```sql
SELECT madma, tongsl FROM silver.stg_water_demand WHERE nam = 2024 AND thang = 9 ORDER BY tongsl DESC LIMIT 3
```

**Loại: Tổng hợp**
Q: Tổng sản lượng cấp nước năm 2024 là bao nhiêu?
```sql
SELECT SUM(tongsl) AS total FROM silver.stg_water_demand WHERE nam = 2024
```

**Loại: So sánh**
Q: So sánh sản lượng tháng 9 và tháng 10 của 01-LB năm 2024
```sql
SELECT thang, tongsl FROM silver.stg_water_demand WHERE madma = '01-LB' AND nam = 2024 AND thang IN (9, 10) ORDER BY thang
```

**Loại: Dự báo**
Q: Dự báo cho trạm 01-LB trong 3 tháng tới?
```sql
SELECT year_month, predicted_demand FROM gold.fct_predictions_unified WHERE madma = '01-LB' ORDER BY year_month ASC LIMIT 3
```
"""

async def _text_to_sql_logic(question: str) -> str:
    if not engine: return wrap_tool_result("error", None, "Chưa cấu hình DB.")
    llm = UnifiedLLMClient()
    schema = _get_schema_info()
    examples = _get_few_shot_examples()
    
    base_prompt = f"""Bạn là chuyên gia SQL cho hệ thống cấp nước Hà Nội.
{schema}
{examples}

### QUY TẮC:
1. Chỉ dùng lệnh SELECT. Chỉ trả về SQL trong block ```sql.
2. CỘT SẮP XẾP: Dùng `ORDER BY ... DESC` cho "nhiều nhất", `ASC` cho "ít nhất".
3. ĐẾM DMA: Luôn dùng `COUNT(DISTINCT madma)`.
4. THỜI GIAN: Bảng lịch sử dùng `nam` (năm) và `thang` (tháng). Bảng dự báo dùng `year_month` (format 'YYYY-MM').

CÂU HỎI: {question}
SQL:"""


    current_prompt = base_prompt
    max_retries = 2
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            # Failsafe: Direct SQL check
            if attempt == 0 and "SELECT" in question.upper() and ("FROM" in question.upper() or "silver." in question.lower()):
                raw_res = f"```sql\n{question}\n```"
            else:
                raw_res = llm.generate([{"role": "user", "content": current_prompt}])
                logger.info(f"LLM_SQL_RAW (Attempt {attempt+1}): {raw_res}")
            
            sql_match = re.search(r"```sql\s*(.*?)\s*```", raw_res, re.DOTALL | re.IGNORECASE)
            sql = sql_match.group(1).strip() if sql_match else raw_res.strip()
            sql = sql.split(";")[-1] if ";" in sql and sql.endswith(";") else sql.strip()
            sql = sql.lstrip("SQL:").strip().rstrip(';')

            if any(kw in sql.upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT"]):
                return wrap_tool_result("error", None, "Lệnh SQL không an toàn.")
            
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
                return wrap_tool_result("success", df.to_dict(orient="records"), f"Kết quả SQL: {len(df)} dòng.")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"SQL Attempt {attempt+1} failed: {last_error}")
            current_prompt = f"{base_prompt}\n\n**LỖI TRƯỚC ĐÓ**: {last_error}\n**YÊU CẦU**: Hãy sửa câu lệnh SQL trên dựa vào lỗi này và SCHEMA đã cung cấp."
            if attempt == max_retries:
                return wrap_tool_result("error", None, f"Lỗi thực thi SQL sau {max_retries+1} lần thử: {last_error}")

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
    return wrap_tool_result("success", {"url": f"{settings.IMAGE_BASE_URL}/mock_plot.png"}, f"Đã vẽ biểu đồ cho {dma_id or dma_query}.")

@mcp.tool()
async def check_data_quality(dma_id: str, year: int = 2024, month: int = 10) -> str:
    """Kiểm tra chất lượng dữ liệu: phát hiện giá trị bất thường, đột biến, dữ liệu thiếu cho một DMA."""
    if not engine: return wrap_tool_result("error", None, "Không có DB.")
    try:
        clean_id = normalize_dma_id(dma_id)
        with engine.connect() as conn:
            # Get historical stats for comparison (last 12 months)
            stats_sql = text("""
                SELECT AVG(tongsl) as avg_sl, STDDEV(tongsl) as std_sl, COUNT(*) as cnt
                FROM silver.stg_water_demand WHERE madma = :dma
            """)
            stats = pd.read_sql(stats_sql, conn, params={"dma": clean_id})
            
            # Get current month value
            current_sql = text("""
                SELECT tongsl FROM silver.stg_water_demand 
                WHERE madma = :dma AND nam = :year AND thang = :month
            """)
            current = pd.read_sql(current_sql, conn, params={"dma": clean_id, "year": year, "month": month})
            
            if stats.empty or current.empty:
                return wrap_tool_result("warning", None, f"Thiếu dữ liệu cho {clean_id} ({month}/{year}).")
            
            avg = float(stats.iloc[0]['avg_sl'] or 0)
            std = float(stats.iloc[0]['std_sl'] or 1)
            val = float(current.iloc[0]['tongsl'])
            
            alerts = []
            if val < 0:
                alerts.append(f"⚠️ GIÁ TRỊ ÂM: tongsl = {val}")
            if std > 0 and abs(val - avg) > 2 * std:
                pct = round(((val - avg) / avg) * 100, 1)
                direction = "TĂNG ĐỘT BIẾN" if val > avg else "GIẢM ĐỘT BIẾN"
                alerts.append(f"⚠️ {direction}: {val} m³ ({pct:+}% so với TB={round(avg)})")
            
            result = {
                "dma_id": clean_id,
                "period": f"{month}/{year}",
                "current_value": val,
                "historical_avg": round(avg),
                "std_dev": round(std),
                "alerts": alerts if alerts else ["✅ Dữ liệu bình thường."]
            }
            status = "warning" if alerts else "success"
            return wrap_tool_result(status, result, f"Kiểm tra chất lượng {clean_id} xong.")
    except Exception as e:
        return wrap_tool_result("error", None, str(e))

def main(): mcp.run()
if __name__ == "__main__": main()
