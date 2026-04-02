import json
import logging
from datetime import datetime
import pandas as pd
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from langchain_core.messages import SystemMessage, HumanMessage

from src.agent.llm_utils import get_llm_for_purpose
from src.deps import get_repo_dep

logger = logging.getLogger(__name__)

class TextToSqlInput(BaseModel):
    question: str = Field(description="Câu hỏi tự nhiên Tiếng Việt cần chuyển sang SQL (ví dụ: 'Tổng sản lượng tháng trước')")

def _format_month_variants(month: int, year: int) -> set[str]:
    padded = f"{month:02d}"
    return {
        f"{month}/{year}",
        f"{padded}/{year}",
        f"{year}-{padded}",
        f"tháng {month}/{year}",
        f"tháng {padded}/{year}",
    }


def _detect_tables(question: str) -> str:
    """Phân tích câu hỏi để xác định bảng nào cần query."""
    q_lower = question.lower()
    now = datetime.now()
    prev_month = now.month - 1 if now.month > 1 else 12
    prev_year = now.year if now.month > 1 else now.year - 1
    next_month = now.month + 1 if now.month < 12 else 1
    next_year = now.year if now.month < 12 else now.year + 1

    silver_keywords = {'lịch sử', 'thực tế', 'quý', 'năm', 'trung bình', 'tháng trước', 'tháng vừa rồi', 'trong năm'}
    gold_keywords = {'dự báo', 'tháng tới', 'tháng sau', 'horizon', 'dự đoán', 'tiếp theo'}

    silver_dynamic = _format_month_variants(prev_month, prev_year) | _format_month_variants(now.month, now.year)
    gold_dynamic = _format_month_variants(next_month, next_year)
    historical_years = {str(now.year), str(now.year - 1), str(now.year - 2)}

    needs_silver = any(kw in q_lower for kw in silver_keywords)
    needs_silver = needs_silver or any(kw in q_lower for kw in silver_dynamic)
    needs_silver = needs_silver or any(kw in q_lower for kw in historical_years)
    needs_silver = needs_silver or 'history' in q_lower

    needs_gold = any(kw in q_lower for kw in gold_keywords)
    needs_gold = needs_gold or any(kw in q_lower for kw in gold_dynamic)
    needs_gold = needs_gold or 'forecast' in q_lower

    if needs_silver and needs_gold:
        return "UNION_BOTH"
    elif needs_gold:
        return "gold"
    else:
        return "silver"

async def text_to_sql_async(question: str) -> str:
    """
    Chuyển đổi câu hỏi Tiếng Việt thành SQL và thực thi trên Database Hà Nội Water.
    Hỗ trợ: Tổng hệ thống, TOP N, Lọc theo thời gian, So sánh vùng, Tăng trưởng.
    """
    try:
        llm = get_llm_for_purpose()
        repo = get_repo_dep()
        
        # Auto-detect which tables are relevant
        table_hint = _detect_tables(question)
        logger.info(f"SQL_INPUT: question='{question}', table_hint={table_hint}")
        
        now_label = datetime.now().strftime("Tháng %m/%Y")
        system_prompt = f"""Bạn là chuyên gia SQL cho hệ thống cấp nước Hà Nội.
THỜI GIAN HIỆN TẠI: {now_label}.
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

### VÍ DỤ SQL CHUẨN:

-- Tổng Q4/2025:
SELECT SUM(tongsl) FROM silver.stg_water_demand WHERE year_month IN ('2025-10','2025-11','2025-12')

-- TOP 5 tháng 1/2026:
SELECT madma, tongsl FROM silver.stg_water_demand WHERE year_month = '2026-01' ORDER BY tongsl DESC LIMIT 5

-- DMA cụ thể tháng 12/2025:
SELECT madma, tongsl FROM silver.stg_water_demand WHERE madma = '17-TL' AND year_month = '2025-12'

-- Cross-horizon:
SELECT tongsl as val FROM silver.stg_water_demand WHERE madma = '17-TL' AND year_month = '2025-12'
UNION ALL
SELECT predicted_demand as val FROM gold.fct_predictions_unified WHERE madma = '17-TL' AND year_month = '2026-02'

CHỈ TRẢ VỀ CÂU LỆNH SQL, KHÔNG GIẢI THÍCH.
"""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Câu hỏi: {question}\nSQL:")
        ]
        
        response = await llm.ainvoke(messages)
        sql = response.content.strip()
        
        # Clean up Markdown if present
        if "```sql" in sql:
            sql = sql.split("```sql")[1].split("```")[0].strip()
        elif "```" in sql:
            sql = sql.split("```")[1].split("```")[0].strip()
            
        # Clean semicolon
        sql = sql.rstrip(';')
            
        logger.info(f"SQL_GENERATED: sql={sql}")
        
        # LOCAL GUARDRAIL: Pre-check for destructive commands
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER", "GRANT", "REVOKE", "CREATE"]
        sql_upper = sql.upper()
        if any(keyword in sql_upper for keyword in forbidden):
            logger.warning(f"SQL_GUARDRAIL: blocked destructive SQL: {sql}")
            return f"[SECURITY_BLOCKED] Lỗi bảo mật: Lệnh SQL chứa từ khóa cấm. Chỉ cho phép SELECT."

        # Execute SQL
        df = repo.query_safe(sql)
        
        if df.empty:
            logger.warning(f"SQL_EMPTY: no rows returned for sql={sql}")
            return f"Không tìm thấy dữ liệu. (SQL đã thực thi: {sql})"
            
        results = df.to_dict(orient="records")
        result_json = json.dumps(results, ensure_ascii=False)
        
        logger.info(f"SQL_RESULT: rows={len(results)}, columns={list(df.columns)}, preview={str(results[0])[:200] if results else 'empty'}")
        
        return f"Dữ liệu SQL trả về cho câu hỏi [{question}]: {result_json}"
        
    except Exception as e:
        err_msg = str(e)
        if "security" in err_msg.lower() or "guardrail" in err_msg.lower():
            return f"[SECURITY_BLOCKED] Lỗi bảo mật: {err_msg}"
        logger.error(f"SQL_ERROR: {e}", exc_info=True)
        return f"Lỗi truy vấn dữ liệu: {err_msg}"

text_to_sql_tool = StructuredTool.from_function(
    name="text_to_sql",
    description="Truy vấn dữ liệu nước Hà Nội bằng ngôn ngữ tự nhiên. Hỗ trợ: Tổng, TOP N, So sánh, Tăng trưởng, UNION ALL cross-horizon.",
    func=None, # Async only
    coroutine=text_to_sql_async,
    args_schema=TextToSqlInput
)
