import json
import logging
from src.hanoi_water_db import get_engine
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
engine = get_engine()

# Golden Trajectories DEFINITION
GOLDEN_DATA = [
    {
        "question_pattern": "Phân tích sản lượng quá khứ của vùng 34NB",
        "intent": "SPECIFIC",
        "thought": "1. Nhận diện DMA '34NB'. 2. Tra cứu ID chính xác qua get_dma_info. 3. Đã có ID, dùng get_historical_analysis để lấy báo cáo chuyên biệt.",
        "tool_chain": [
            {"tool": "get_dma_info", "params": {"dma_query": "34NB"}},
            {"tool": "get_historical_analysis", "params": {"dma_id": "34-NB", "months": 12}}
        ]
    },
    {
        "question_pattern": "Dự báo tiêu thụ nước 17-TL 3 tháng tới",
        "intent": "SPECIFIC",
        "thought": "1. Nhận diện DMA '17-TL'. 2. Tra cứu ID qua get_dma_info. 3. Đã có ID, dùng tool chuyên biệt get_forecast_analysis cho tương lai.",
        "tool_chain": [
            {"tool": "get_dma_info", "params": {"dma_query": "17-TL"}},
            {"tool": "get_forecast_analysis", "params": {"dma_id": "17-TL", "horizon": 3}}
        ]
    },
    {
        "question_pattern": "Tính sự tương quan giữa số khách hàng và sản lượng của 17-TL năm 2025",
        "intent": "SPECIFIC",
        "thought": "1. Xác định ID '17-TL'. 2. Toàn bộ data 2025 cần trích xuất thô trước. 3. Dùng text_to_sql lấy (year_month, tongsl, sokhcosd). 4. Dùng python_interpreter tính correlation từ data JSON.",
        "tool_chain": [
            {"tool": "get_dma_info", "params": {"dma_query": "17-TL"}},
            {"tool": "text_to_sql", "params": {"question": "Lấy tongsl và sokhcosd của 17-TL năm 2025"}},
            {"tool": "python_interpreter", "params": {"code": "df = pd.read_json(data); print(df.corr())"}}
        ]
    }
]

def seed():
    if not engine:
        print("DB Engine NOT initialized.")
        return
        
    try:
        with engine.connect() as conn:
            # Clear existing to refresh (for dev only)
            conn.execute(text("TRUNCATE TABLE app.golden_trajectories RESTART IDENTITY;"))
            
            sql = text("""
                INSERT INTO app.golden_trajectories (question_pattern, intent, thought, tool_chain)
                VALUES (:q, :i, :t, :c)
            """)
            
            for d in GOLDEN_DATA:
                conn.execute(sql, {
                    "q": d["question_pattern"],
                    "i": d["intent"],
                    "t": d["thought"],
                    "c": json.dumps(d["tool_chain"])
                })
            conn.commit()
            print("Successfully seeded Golden Trajectories! ✅")
    except Exception as e:
        print(f"Error seeding: {e}")

if __name__ == "__main__":
    seed()
