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
            return {"reflect_verdict": "pass", "reflect_notes": "", "retry_count": retry_count}

        # 🟢 Parse JSON outputs for errors
        errors = []
        for r in tool_results:
            try:
                data = json.loads(r["output"])
                if data.get("status") == "error":
                    errors.append(f"{r['tool']}: {data.get('message', 'Lỗi không xác định')}")
            except:
                pass

        if errors:
            note = f"Phát hiện lỗi từ tool: {', '.join(errors)}."
            logger.info(f"REFLECT_DECISION: retry (Structured Error) — {note}")
            return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}
        
        # 🔵 LLM-based verification
        first_msg = state["messages"][0].content if state["messages"] else ""
        results_summary = [f"- {r.get('tool')}: {r.get('output')[:100]}" for r in tool_results[-3:]]

        prompt = f"""Bạn là chuyên gia kiểm định cho hệ thống Hanoi Water.
Câu hỏi: {first_msg}
Kết quả Tool:
{chr(10).join(results_summary)}

Quy tắc:
1. Nếu CHỈ 'XÁC NHẬN DMA' mà chưa có số liệu -> retry ("Cần lấy số liệu").
2. Nếu đủ dữ liệu -> pass.
Trả về JSON: {{"verdict": "pass" | "retry", "suggestion": "..."}}
"""
        try:
            result = await llm.ainvoke(prompt)
            content = result.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            verdict = data.get("verdict", "pass")
            notes = data.get("suggestion", "")
            
            logger.info(f"REFLECT_DECISION: {verdict} (LLM) — {notes}")
            return {"reflect_verdict": verdict, "reflect_notes": notes, "retry_count": retry_count + 1}
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"REFLECT_ERROR: {e}")
            return {"reflect_verdict": "pass", "reflect_notes": "", "retry_count": retry_count + 1}
            
    return reflect
    return reflect
