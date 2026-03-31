import logging
import json
import pandas as pd
from fastmcp import FastMCP
from sqlalchemy import text
import os

from src.hanoi_water_db import get_engine
from src.llm.litellm import LiteLLMBackend

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hanoi_water_mcp")

mcp = FastMCP("Hanoi Water")
engine = get_engine()

def normalize_dma_id(dma_id: str) -> str:
    """Standardize DMA ID: uppercase and ensure hyphen if needed."""
    if not dma_id:
        return ""
    dma = dma_id.strip().upper()
    # Simple fix for common formats like '17TL' -> '17-TL'
    if len(dma) == 4 and dma[2].isalpha():
         dma = f"{dma[:2]}-{dma[2:]}"
    return dma

@mcp.tool()
async def get_dma_info(dma_query: str) -> str:
    """
    Xác thực mã hiệu DMA (madma) từ chuỗi nhập vào.
    TRẢ VỀ: dma_id chính xác để sử dụng cho các tool khác.
    """
    if not engine:
        return "Lỗi: Chưa cấu hình Database."
        
    clean_query = normalize_dma_id(dma_query)
    try:
        with engine.connect() as conn:
            sql = text("""
                SELECT DISTINCT madma 
                FROM silver.stg_water_demand 
                WHERE madma = :q
                   OR madma ILIKE :q_perc
                LIMIT 5
            """)
            df = pd.read_sql(sql, conn, params={"q": clean_query, "q_perc": f"%{clean_query}%"})
            
            if df.empty:
                return f"Không tìm thấy mã DMA nào khớp với '{dma_query}'."
                
            matches = df['madma'].tolist()
            dma_id = clean_query if clean_query in matches else matches[0]
            
            return f"XÁC NHẬN DMA: {dma_id}\nHãy dùng mã này cho các câu hỏi tiếp theo."
    except Exception as e:
        logger.error(f"Error in get_dma_info: {e}")
        return f"Lỗi hệ thống: {str(e)}"

    
def _detect_tables(question: str) -> str:
    """Xác định bảng cần truy vấn dựa trên câu hỏi."""
    q_lower = question.lower()
    needs_silver = any(kw in q_lower for kw in [
        '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018',
        'tháng 1/2026', '01/2026', '2026-01', 'q4/2025', 'q3/2025', 'q2/2025', 'q1/2025',
        'lịch sử', 'thực tế', 'quý 4', 'quý 3', 'năm 2025', 'trung bình năm'
    ])
    needs_gold = any(kw in q_lower for kw in [
        'dự báo', 'tháng 2/2026', 'tháng 3/2026', 'tháng 4/2026',
        '02/2026', '03/2026', '04/2026', '2026-02', '2026-03', '2026-04',
        'q1/2026', 'quý 1/2026'
    ])
    
    if needs_silver and needs_gold:
        return "UNION_BOTH"
    elif needs_gold:
        return "gold"
    else:
        return "silver"

@mcp.tool()
async def text_to_sql(question: str) -> str:
    """Truy vấn dữ liệu nước Hà Nội bằng ngôn ngữ tự nhiên."""
    if not engine:
        return "Lỗi: Chưa cấu hình Database."

    model_id = os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3-8B")
    llm = LiteLLMBackend(model_id)
    
    table_hint = _detect_tables(question)
    
    system_prompt = f"""Bạn là chuyên gia SQL cho hệ thống cấp nước Hà Nội.
THỜI GIAN HIỆN TẠI: Tháng 01/2026.
GỢI Ý BẢNG: {table_hint}

### SCHEMA:
1. `silver.stg_water_demand` — DỮ LIỆU THỰC TẾ (01/2018 → 01/2026)
   - madma TEXT (VIẾT HOA, VD: '17-TL', '05-BĐ')
   - year_month TEXT ('YYYY-MM', VD: '2025-12')
   - tongsl BIGINT (Sản lượng m³)
   - sokhcosd BIGINT (Số khách hàng)

2. `gold.fct_predictions_unified` — DỰ BÁO (02/2026 → 04/2026)
   - madma TEXT, year_month TEXT, predicted_demand INTEGER, horizon INTEGER

### QUY TẮC:
- CẢ HAI BẢNG đều dùng `year_month` định dạng 'YYYY-MM'.
- madma VIẾT HOA. Chỉ SELECT.

### VÍ DỤ:
-- TOP 5 tháng 1/2026:
SELECT madma, tongsl FROM silver.stg_water_demand WHERE year_month = '2026-01' ORDER BY tongsl DESC LIMIT 5

-- DMA 17-TL tháng 12/2025:
SELECT madma, tongsl FROM silver.stg_water_demand WHERE madma = '17-TL' AND year_month = '2025-12'

CHỈ TRẢ VỀ SQL, KHÔNG GIẢI THÍCH.
"""

    try:
        sql = llm.generate(f"{system_prompt}\n\nCâu hỏi: {question}\nSQL:")
        sql = sql.strip().replace("```sql", "").replace("```", "").rstrip(';')
        
        # Guardrail
        if any(kw in sql.upper() for kw in ["DROP", "DELETE", "UPDATE", "INSERT"]):
            return "Lỗi: Lệnh SQL không an toàn."

        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
            if df.empty:
                return f"Không tìm thấy dữ liệu. (SQL: {sql})"
            return df.to_json(orient="records", force_ascii=False)
    except Exception as e:
        return f"Lỗi truy vấn: {str(e)}"

@mcp.tool()
async def get_historical_analysis(dma_id: str, months: int = 12) -> str:
    """Phân tích dữ liệu lịch sử tiêu thụ nước cho 1 DMA (avg, max, min, xu hướng)."""
    if not engine: return "Lỗi: Chưa cấu hình DB."
    
    dma = normalize_dma_id(dma_id)
    try:
        with engine.connect() as conn:
            sql = text("""
                SELECT year_month, tongsl as actual 
                FROM silver.stg_water_demand 
                WHERE madma = :dma 
                ORDER BY year_month DESC LIMIT :limit
            """)
            df = pd.read_sql(sql, conn, params={"dma": dma, "limit": months})
            
            if df.empty: return f"Không có dữ liệu cho DMA {dma}."
            
            vals = df['actual'].tolist()
            avg_v, max_v, min_v = sum(vals)/len(vals), max(vals), min(vals)
            trend = "tăng" if vals[0] > vals[-1] else "giảm"
            
            return f"BÁO CÁO DMA {dma}:\n- TB: {avg_v:,.0f} m³\n- Cao: {max_v:,.0f}, Thấp: {min_v:,.0f}\n- Xu hướng: {trend}."
    except Exception as e:
        return f"Lỗi: {str(e)}"

@mcp.tool()
async def get_forecast_analysis(dma_id: str, horizon: int = 3) -> str:
    """Lấy dự báo tiêu thụ nước (tháng 02/2026 trở đi) cho 1 DMA."""
    if not engine: return "Lỗi: Chưa cấu hình DB."
    
    dma = normalize_dma_id(dma_id)
    try:
        with engine.connect() as conn:
            sql = text("""
                SELECT year_month, predicted_demand 
                FROM gold.fct_predictions_unified 
                WHERE madma = :dma 
                ORDER BY year_month ASC LIMIT :limit
            """)
            df = pd.read_sql(sql, conn, params={"dma": dma, "limit": horizon})
            
            if df.empty: return f"Không có dự báo cho DMA {dma}."
            
            lines = [f"DỰ BÁO DMA {dma}:"]
            for _, r in df.iterrows():
                lines.append(f"- {r['year_month']}: {r['predicted_demand']:,.0f} m³")
            return "\n".join(lines)
    except Exception as e:
        return f"Lỗi: {str(e)}"

@mcp.tool()
async def plot_dma(dma_id: str, include_forecast: bool = True) -> str:
    """Vẽ biểu đồ tiêu thụ nước cho 1 DMA (Lịch sử + Dự báo)."""
    import matplotlib.pyplot as plt
    import uuid
    import os
    
    if not engine: return "Lỗi: Chưa cấu hình DB."
    dma = normalize_dma_id(dma_id)
    
    try:
        # 1. Get Historical Data
        with engine.connect() as conn:
            hist_sql = text("SELECT year_month, tongsl FROM silver.stg_water_demand WHERE madma = :dma ORDER BY year_month DESC LIMIT 12")
            df_hist = pd.read_sql(hist_sql, conn, params={"dma": dma})
            
        if df_hist.empty: return f"Không có dữ liệu lịch sử để vẽ cho DMA {dma}."
        df_hist = df_hist.sort_values("year_month")
        
        # 2. Get Forecast Data
        df_fore = pd.DataFrame()
        if include_forecast:
            with engine.connect() as conn:
                fore_sql = text("SELECT year_month, predicted_demand FROM gold.fct_predictions_unified WHERE madma = :dma ORDER BY year_month ASC")
                df_fore = pd.read_sql(fore_sql, conn, params={"dma": dma})
        
        # 3. Plotting
        plt.figure(figsize=(10, 6))
        plt.plot(df_hist['year_month'], df_hist['tongsl'], marker='o', label='Thực tế', color='blue')
        
        if not df_fore.empty:
            # Connect the last historical point to the first forecast point
            last_hist_x = df_hist['year_month'].iloc[-1]
            last_hist_y = df_hist['tongsl'].iloc[-1]
            
            x_fore = [last_hist_x] + df_fore['year_month'].tolist()
            y_fore = [last_hist_y] + df_fore['predicted_demand'].tolist()
            
            plt.plot(x_fore, y_fore, marker='s', linestyle='--', label='Dự báo', color='orange')

        plt.title(f"Tiêu thụ nước DMA {dma}")
        plt.xlabel("Tháng")
        plt.ylabel("Sản lượng (m³)")
        plt.xticks(rotation=45)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # 4. Save
        plot_id = uuid.uuid4().hex[:8]
        filename = f"plot_{dma}_{plot_id}.png"
        filepath = f"/home/chinh303/AssetOpsBench/plots/{filename}"
        plt.savefig(filepath)
        plt.close()
        
        url = f"file://{filepath}"
        return f"BIỂU ĐỒ DMA {dma}: {url}\n(Lưu ý: Mời bạn mở đường dẫn trên để xem ảnh)"
        
    except Exception as e:
        return f"Lỗi khi vẽ biểu đồ: {str(e)}"

def main():
    mcp.run()

if __name__ == "__main__":
    main()
