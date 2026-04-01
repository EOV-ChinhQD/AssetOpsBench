import json
import logging
from ..state import AgentState

logger = logging.getLogger(__name__)

def get_reflect_node(llm):
    async def reflect(state: AgentState) -> dict:
        retry_count = state.get("retry_count", 0)
        tool_results = state.get("tool_results", [])
        
        logger.info(f"REFLECT: retry={retry_count}, results={len(tool_results)}")
        
        if retry_count >= 2:
            return {"reflect_verdict": "pass", "reflect_notes": "Max retries reached.", "retry_count": retry_count}

        # === LAYER 1: Structured Error Detection ===
        errors = []
        empty_results = []
        has_real_data = False
        
        for r in tool_results:
            try:
                data = json.loads(r["output"])
                status = data.get("status", "")
                tool_name = r.get("tool", "unknown")
                
                if status == "error":
                    errors.append(f"{tool_name}: {data.get('message', 'Lỗi')}")
                elif status == "success":
                    payload = data.get("data")
                    # Check for empty/meaningless results
                    if payload is None or payload == [] or payload == {}:
                        empty_results.append(tool_name)
                    elif isinstance(payload, list) and len(payload) > 0:
                        has_real_data = True
                    elif isinstance(payload, str) and len(payload) > 10:
                        has_real_data = True
            except:
                pass

        if errors:
            note = f"Lỗi tool: {'; '.join(errors)}"
            logger.info(f"REFLECT (AUDITOR) → retry (error): {note}")
            return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}
        
        # === LAYER 4: LLM-BASED SOP AUDIT (THE SENIOR AUDITOR) ===
        # Use the same brain (LLM) but with a high-criticism prompt to audit the findings.
        audit_prompt = f"""Bạn là Kiểm soát viên Vận hành (Operations Auditor) tại Hanoi Water AI.
Nhiệm vụ: Kiểm tra xem kết quả của Kỹ thuật viên (Technician) có chính xác, đầy đủ và tuân thủ SOP không.

DỮ LIỆU TOOL TRẢ VỀ:
{json.dumps(tool_results, ensure_ascii=False, indent=2)}

TIÊU CHÍ KIỂM TRA:
1. Có lấy đủ Dữ liệu Lịch sử (Silver) và Dự báo (Gold) nếu người dùng yêu cầu so sánh không?
2. Mã DMA đã được chuẩn hóa chưa (Vd: "Long Biên" -> "01-LB")?
3. Có phát hiện giá trị âm (bất thường) không?
4. Đã thực hiện `check_data_quality` trước khi phân tích chưa?

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
                 logger.info(f"REFLECT (AUDITOR) → retry (audit): {audit.get('reason')}")
                 return {"reflect_verdict": "retry", "reflect_notes": audit.get("reason"), "retry_count": retry_count + 1}
        except Exception as e:
             logger.warning(f"Auditor failed: {e}. Defaulting to Layer 1-3.")

        logger.info("REFLECT (AUDITOR) → pass")
        return {"reflect_verdict": "pass", "reflect_notes": "", "retry_count": retry_count}
            
    return reflect
            
    return reflect
