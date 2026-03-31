import json
import logging
from ..state import AgentState

logger = logging.getLogger(__name__)

def get_reflect_node(llm):
    async def reflect(state: AgentState) -> dict:
        retry_count = state.get("retry_count", 0)
        tool_results = state.get("tool_results", [])
        
        logger.info(f"REFLECT_INPUT: retry_count={retry_count}, tool_results={len(tool_results)}")
        
        if retry_count >= 2:
            logger.info("REFLECT_DECISION: pass (max retries reached)")
            return {"reflect_verdict": "pass", "reflect_notes": "", "retry_count": retry_count}

        # Heuristic checks before LLM
        results_str = str(tool_results).lower()
        
        # Check SQL execution errors
        if "lỗi thực thi sql" in results_str or "lỗi truy vấn" in results_str:
            if "madma" in results_str or "mdma" in results_str:
                note = "Sửa lỗi cột: madma (không phải mdma), tongsl, predicted_demand."
            else:
                note = "SQL bị lỗi, hãy thử viết lại câu lệnh đơn giản hơn."
            logger.info(f"REFLECT_DECISION: retry (SQL error) — {note}")
            return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}
        
        # Check if 'no data found' from SQL (contains the SQL for debugging)
        if "không tìm thấy dữ liệu" in results_str and "sql" in results_str:
            note = "SQL trả về 0 rows. Kiểm tra year_month format ('YYYY-MM') và tên bảng (silver vs gold)."
            logger.info(f"REFLECT_DECISION: retry (empty SQL result) — {note}")
            return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}
        
        # Check if plot was requested but no data available yet
        first_msg = state["messages"][0].content.lower() if state["messages"] else ""
        if ("vẽ" in first_msg or "biểu đồ" in first_msg) and not state.get("chart_json"):
            if not tool_results:
                note = "Hãy lấy dữ liệu từ database trước khi gọi tool vẽ biểu đồ."
                logger.info(f"REFLECT_DECISION: retry (plot requested but no data) — {note}")
                return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}
        
        # LLM-based verdict for non-obvious cases
        # Summarize tool results compactly
        results_summary = []
        for r in tool_results[-3:]:
            out = str(r.get("output", ""))[:500]
            results_summary.append(f"- {r.get('tool')}: {out}")
        
        prompt = f"""Đánh giá xem tool_results đã ĐỦ DỮ LIỆU để trả lời câu hỏi chưa.
Input question: {first_msg[:200]}
Tool results:
{chr(10).join(results_summary)}

Rules:
1. Nếu kết quả CHỈ LÀ `XÁC NHẬN DMA: ...` (từ get_dma_info) mà CHƯA có dữ liệu số để trả lời câu hỏi -> retry, suggestion: "Đã xác nhận DMA, bây giờ hãy gọi text_to_sql hoặc get_forecast/historical để lấy số liệu".
2. Nếu tool báo lỗi hoặc 'không tìm thấy dữ liệu' -> retry, suggestion hint lổi.
3. Nếu dữ liệu hiện tại ĐÃ ĐỦ trả lời câu hỏi -> pass.
Return JSON: {{"verdict": "pass" | "retry", "suggestion": "..."}}
"""
        try:
            result = await llm.ainvoke(prompt)
            content = result.content.replace("```json", "").replace("```", "").strip()
            
            try:
                verdict_data = json.loads(content)
            except json.JSONDecodeError:
                import re
                verdict_match = re.search(r'"verdict"\s*:\s*"(\w+)"', content)
                suggest_match = re.search(r'"suggestion"\s*:\s*"(.*?)"', content, re.DOTALL)
                verdict_data = {
                    "verdict": verdict_match.group(1) if verdict_match else "pass",
                    "suggestion": suggest_match.group(1) if suggest_match else ""
                }
            
            verdict = verdict_data.get("verdict", "pass")
            notes = verdict_data.get("suggestion", verdict_data.get("reason", ""))
            
            logger.info(f"REFLECT_DECISION: {verdict} (LLM) — {notes[:100]}")
            
            return {
                "reflect_verdict": verdict,
                "reflect_notes": notes,
                "retry_count": retry_count + 1,
            }
        except Exception as e:
            logger.error(f"REFLECT_ERROR: {e}")
            return {
                "reflect_verdict": "pass",
                "reflect_notes": "",
                "retry_count": retry_count + 1,
            }
    return reflect
