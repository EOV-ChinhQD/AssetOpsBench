import json
import logging
import sqlite3
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class TinyTrajectoryStore:
    """
    Lưu các trajectory PASS để dùng làm few-shot examples (IBM ReActXen).
    Sử dụng SQLite đơn giản thay vì ChromaDB để dễ deploy.
    """
    def __init__(self, db_path=None):
        if db_path is None:
            log_dir = os.path.join(os.getcwd(), "logs")
            os.makedirs(log_dir, exist_ok=True)
            db_path = os.path.join(log_dir, "water_ai_trajectories.db")
            
        self.db_path = db_path
        self._init_db()
        
        # Hardcode 2 successful baseline trajectories to bootstrap the few-shot context
        self._bootstrap_default_trajectories()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trajectories (
                    id TEXT PRIMARY KEY,
                    question TEXT,
                    trajectory_json TEXT,
                    score INTEGER,
                    created_at TEXT
                )
            ''')
            conn.commit()

    def _bootstrap_default_trajectories(self):
        # Insert 2 high-quality examples if the table is empty
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM trajectories")
            if cur.fetchone()[0] == 0:
                logger.info("Bootstrapping default trajectories into SQLite")
                # Example 1: Multi-step Specific DMA query
                t1 = [
                    {"type": "thought", "content": "Người dùng hỏi về 'khu Cầu Giấy' và tháng 02/2026. Cần gọi get_dma_info trước để lấy ID, sau đó get_forecast để lấy dự báo."},
                    {"type": "tool_call", "tool": "get_dma_info", "params": {"dma_name": "Cầu Giấy"}},
                    {"type": "observation", "content": "XÁC NHẬN DMA: DMA_CG_01"},
                    {"type": "thought", "content": "Tiếp tục gửi dma_id DMA_CG_01 vào get_forecast tháng 02/2026."},
                    {"type": "tool_call", "tool": "get_forecast", "params": {"dma_id": "DMA_CG_01", "months_ahead": 1}},
                    {"type": "observation", "content": "Dự báo tháng tới là 1200 m3"}
                ]
                # Example 2: Global/SQL Query
                t2 = [
                    {"type": "thought", "content": "Hỏi 'Top 3 DMA tiêu thụ cao nhất tháng 1/2026'. Đây là câu hỏi GLOBAL cần phân tích số liệu thực tế. Gọi text_to_sql trên bảng silver."},
                    {"type": "tool_call", "tool": "text_to_sql", "params": {"question": "Top 3 DMA tiêu thụ cao nhất tháng 1/2026"}},
                    {"type": "observation", "content": "SQL_RESULT: 1: DMA 17-TL (430356 m3), 2: DMA 12-PL (111703 m3)..."}
                ]
                self.save("tiêu thụ khu Cầu Giấy tháng tới dự báo bao nhiêu", t1, {"pass": True, "total": 18})
                self.save("Top 3 vùng cao nhất tháng 1/2026", t2, {"pass": True, "total": 18})

    def save(self, question: str, trajectory: list, score: dict):
        """Lưu trajectory vào store nếu pass (total >= 14)."""
        if not score.get("pass", False) and score.get("total", 0) < 14:
            return
            
        traj_id = f"traj_{abs(hash(question))}"
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO trajectories (id, question, trajectory_json, score, created_at) VALUES (?, ?, ?, ?, ?)",
                    (traj_id, question, json.dumps(trajectory, ensure_ascii=False), score.get("total", 18), datetime.now().isoformat())
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Error saving trajectory: {e}")

    def retrieve(self, question: str, limit=2) -> str:
        """Lấy 2 trajectory mặc định/tương tự nhất làm few-shot examples (sử dụng LIKE đơn giản cho SQLite)."""
        with sqlite3.connect(self.db_path) as conn:
            # Lấy 2 dòng có điểm cao nhất (ví dụ đơn giản vì sqlite không có vector search)
            cur = conn.cursor()
            cur.execute("SELECT question, trajectory_json, score FROM trajectories ORDER BY score DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            
        if not rows:
            return ""

        examples = []
        for doc_q, traj_str, score in rows:
            try:
                traj = json.loads(traj_str)
                traj_text = "\n".join([f"[{s['type']}] {s['tool'] if s['type']=='tool_call' else ''} {s.get('content') or s.get('params') or ''}" for s in traj])
                examples.append(
                    f"Ví dụ (score={score}/18):\n"
                    f"Câu hỏi: {doc_q}\n"
                    f"Trajectory:\n{traj_text}\n"
                )
            except Exception as e:
                logger.warning(f"Failed to parse trajectory log: {e}")
                
        return "\n---\n".join(examples)

trajectory_store = TinyTrajectoryStore()
