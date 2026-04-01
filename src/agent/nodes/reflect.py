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
            logger.info(f"REFLECT → retry (error): {note}")
            return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}

        # === LAYER 2: Content Quality Check ===
        # If we ONLY got DMA validation but no actual data → need to fetch data
        tool_names = [r.get("tool", "") for r in tool_results]
        only_dma = all(t == "get_dma_info" for t in tool_names) and len(tool_names) > 0
        
        if only_dma and not has_real_data:
            note = "Chỉ xác thực DMA mà chưa lấy dữ liệu. Cần gọi get_history/get_forecast."
            logger.info(f"REFLECT → retry (incomplete): {note}")
            return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}

        if empty_results and not has_real_data:
            note = f"Kết quả rỗng từ: {', '.join(empty_results)}. Thử query khác."
            logger.info(f"REFLECT → retry (empty): {note}")
            return {"reflect_verdict": "retry", "reflect_notes": note, "retry_count": retry_count + 1}

        # === LAYER 3: Data Anomaly Check ===
        for r in tool_results:
            try:
                data = json.loads(r["output"])
                payload = data.get("data", [])
                if isinstance(payload, list):
                    for row in payload:
                        if isinstance(row, dict):
                            tongsl = row.get("tongsl", row.get("predicted_demand"))
                            if tongsl is not None and (int(tongsl) < 0):
                                logger.warning(f"REFLECT: Negative value detected: {row}")
                                return {
                                    "reflect_verdict": "retry",
                                    "reflect_notes": f"Giá trị âm bất thường: {row}",
                                    "retry_count": retry_count + 1
                                }
            except:
                pass

        logger.info("REFLECT → pass")
        return {"reflect_verdict": "pass", "reflect_notes": "", "retry_count": retry_count}
            
    return reflect
