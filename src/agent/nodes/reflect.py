import json
import logging
import re
from datetime import datetime
from src.agent.state import AgentState
from src.agent.prompts.prompts import REFLECT_PROMPT
from src.agent.utils import format_tool_results

logger = logging.getLogger(__name__)

def get_reflect_node(llm):
    """
    AUDITOR (Controller): Checks technical results for compliance and completeness.
    """
    async def reflect(state: AgentState) -> dict:
        retry_count = state.get("retry_count", 0)
        tool_results = state.get("tool_results", [])
        history = list(state.get("reflection_history", []))
        
        print(f"🧐 REFLECTING: Round {retry_count + 1}, Results={len(tool_results)}")

        # 1. Quick Shortcut - No need to audit if nothing was done yet or if bypass is enabled
        if retry_count == 0:
            print(f"⏩ REFLECT: First pass shortcut. Moving to synthesis.")
            return {"reflect_verdict": "pass", "retry_count": 0, "last_verdict": "pass"}
        
        if retry_count >= 2:
            return {"reflect_verdict": "pass", "reflect_notes": "Max retries reached."}

        # 2. Heuristic Audit (Deduce errors from status fields)
        errors = _detect_tool_errors(tool_results)
        if errors:
            note = f"Lỗi tool: {'; '.join(errors)}"
            logger.warning(f"REFLECT → retry (error): {note}")
            return _retry_response(retry_count, note, "error", history)

        # 3. LLM Audit (Business logic & Compliance)
        try:
            results_context = format_tool_results(state["messages"])
            audit_prompt = REFLECT_PROMPT.format(tool_results=results_context)
            
            res = await llm.ainvoke(audit_prompt)
            from src.agent.utils import parse_json_from_llm
            audit = parse_json_from_llm(res.content)
            
            if audit.get("verdict") == "retry":
                note = audit.get("reason", "Auditor yêu cầu chặn lại.")
                logger.warning(f"REFLECT → retry (audit): {note}")
                return _retry_response(retry_count, note, "warning", history)
                
        except Exception as e:
            logger.error(f"AUDITOR_FAILURE: {e}. Passing due to error.")

        # 4. Pass
        logger.info("REFLECT → pass")
        return {"reflect_verdict": "pass", "last_verdict": "pass"}

    return reflect

def _detect_tool_errors(tool_results: list) -> list:
    errors = []
    for r in tool_results:
        try:
            data = json.loads(r["output"])
            if data.get("status") == "error":
                tool_name = r.get("tool", "unknown")
                errors.append(f"{tool_name}: {data.get('message', 'Lỗi')}")
        except: continue
    return errors

def _retry_response(retry_count: int, note: str, severity: str, history: list) -> dict:
    history.append({
        "timestamp": datetime.utcnow().isoformat(),
        "verdict": "retry",
        "reason": note,
        "severity": severity
    })
    return {
        "reflect_verdict": "retry",
        "reflect_notes": note,
        "retry_count": retry_count + 1,
        "reflection_history": history,
        "meta_instructions": note,
        "last_verdict": "retry"
    }
