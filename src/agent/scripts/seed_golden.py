from src.hanoi_water_db import get_engine
from sqlalchemy import text
import json

engine = get_engine()

def seed_golden():
    with engine.connect() as conn:
        print("Ensuring app.golden_trajectories exists...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app.golden_trajectories (
                id SERIAL PRIMARY KEY,
                question_pattern TEXT,
                thought TEXT,
                tool_chain JSONB
            );
        """))
        
        print("Clearing old trajectories...")
        conn.execute(text("TRUNCATE app.golden_trajectories RESTART IDENTITY;"))
        
        print("Inserting golden shots...")
        examples = [
            ("Có bao nhiêu DMA có mã hiệu bắt đầu bằng '01'?", 
             "Đây là một câu hỏi thống kê số lượng lớn trên toàn hệ thống. Tôi sẽ sử dụng công cụ text_to_sql để đếm chính xác mà không cần xác thực từng mã hiệu.", 
             ["text_to_sql"]),
            
            ("Hãy vẽ biểu đồ so sánh sản lượng cho DMA 01-LB.", 
             "Người dùng yêu cầu hình ảnh biểu đồ. Tôi có công cụ plot_dma chuyên dụng tự động lấy dữ liệu và hiển thị.", 
             ["get_dma_info", "plot_dma"])
        ]
        
        for q, t, p in examples:
            conn.execute(text("""
                INSERT INTO app.golden_trajectories (question_pattern, thought, tool_chain)
                VALUES (:q, :t, :p)
            """), {"q": q, "t": t, "p": json.dumps(p)})
            
        conn.commit()
        print("Golden trajectories seeded successfully!")

if __name__ == "__main__":
    seed_golden()
