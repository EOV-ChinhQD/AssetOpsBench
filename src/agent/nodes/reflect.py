import json
import logging
import re
from datetime import datetime

from ..state import AgentState

logger = logging.getLogger(__name__)


def get_reflect_node(llm):
    async def reflect(state: AgentState) -> dict:
        retry_count = state.get("retry_count", 0)
        tool_results = state.get("tool_results", [])
        history = list(state.get("reflection_history", []))

        logger.info(f"REFLECT: retry={retry_count}, tool_outputs={len(tool_results)}")

        if retry_count == 0:
            logger.info("REFLECT: First pass bypass.")
            return {
                "reflect_verdict": "pass",
                "reflect_notes": "First pass shortcut",
                "retry_count": 0,
                "last_verdict": "pass"
            }
        
        verdict = "pass"
        note = ""
        severity = "info"
        should_retry = False
        errors = []
        empty_results = []
        has_real_data = False

        if retry_count >= 2:
            note = "Max retries reached."
            history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "verdict": verdict,
                "reason": note,
                "severity": severity,
                "tool_errors": errors,
                "empty_tools": empty_results
            })
            return {
                "reflect_verdict": verdict,
                "reflect_notes": note,
                "retry_count": retry_count,
                "reflection_history": history,
                "meta_instructions": note,
                "last_verdict": verdict
            }

        for r in tool_results:
            try:
                data = json.loads(r["output"])
                status = data.get("status", "")
                tool_name = r.get("tool", "unknown")

                if status == "error":
                    errors.append(f"{tool_name}: {data.get('message', 'Lỗi')}")
                elif status == "success":
                    payload = data.get("data")
                    if payload is None or payload == [] or payload == {}:
                        empty_results.append(tool_name)
                    elif isinstance(payload, list) and len(payload) > 0:
                        has_real_data = True
                    elif isinstance(payload, str) and len(payload) > 10:
                        has_real_data = True
            except Exception:
                continue

        if errors:
            note = f"Lỗi tool: {'; '.join(errors)}"
            severity = "error"
            should_retry = True
        elif empty_results and not has_real_data:
            note = f"Dữ liệu rỗng từ {', '.join(empty_results)}."
            severity = "warning"
            should_retry = True
        else:
            audit_prompt = f"""Bạn là Kiểm soát viên Vận hành (Operations Auditor) tại Hanoi Water AI.
Nhiệm vụ: Kiểm tra xem kết quả của Kỹ thuật viên (Technician) có chính xác, đầy đủ và tuân thủ SOP không.

DỮ LIỆU TOOL TRẢ VỀ:
{json.dumps(tool_results, ensure_ascii=False, indent=2)}

TIÊU CHÍ KIỂM TRA:
1. **Mức độ phù hợp**: Kỹ thuật viên đã lấy đủ dữ liệu để trả lời câu hỏi CHƯA? (Vd: Nếu hỏi 'thông tin trạm' thì chỉ cần `get_dma_info`, KHÔNG bắt buộc history/forecast).
2. **Dữ liệu so sánh**: CHỈ yêu cầu có cả Lịch sử (Silver) và Dự báo (Gold) NẾU người dùng hỏi về "so sánh", "xu hướng" hoặc "biến động".
3. **Mã DMA**: Đã được chuẩn hóa chưa (Vd: "01-LB")?
4. **Trực quan hóa**: Có gọi `plot_dma` nếu người dùng hỏi về đồ thị không?

Trả về DUY NHẤT JSON:
{{
  "verdict": "pass" hoặc "retry",
  "reason": "Lý do chi tiết nếu yêu cầu làm lại."
}}
"""
            try:
                res = await llm.ainvoke(audit_prompt)
                content = res.content
                match = re.search(r"\{.*\}", content, re.DOTALL)
                audit = json.loads(match.group(0)) if match else {"verdict": "pass"}

                if audit.get("verdict") == "retry":
                    note = audit.get("reason", "Auditor yêu cầu chạy lại.")
                    severity = "warning"
                    should_retry = True
            except Exception as e:
                logger.warning(f"Auditor failed: {e}. Defaulting to structured checks.")

        if should_retry:
            verdict = "retry"
            retry_count += 1
            logger.info(f"REFLECT → retry ({severity}): {note}")
        else:
            note = note or "Nội dung kiểm tra sạch."
            verdict = "pass"
            logger.info("REFLECT → pass")

        history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": verdict,
            "reason": note,
            "severity": severity,
            "tool_errors": errors,
            "empty_tools": empty_results
        })

        return {
            "reflect_verdict": verdict,
            "reflect_notes": note,
            "retry_count": retry_count,
            "reflection_history": history,
            "meta_instructions": note,
            "last_verdict": verdict
        }

    return reflect
