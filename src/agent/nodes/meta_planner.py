import logging

from ..compaction import auto_compact
from ..state import AgentState

logger = logging.getLogger(__name__)


def should_recompact(state: AgentState) -> bool:
    messages = state.get("messages", [])
    if len(messages) > 25:
        return True
    if state.get("reflect_verdict") == "retry" and len(messages) > 18:
        return True
    return False


def get_meta_planner_node(llm):
    async def meta_planner(state: AgentState) -> dict:
        verdict = state.get("reflect_verdict", "pass")
        notes = state.get("reflect_notes", "")
        hints = dict(state.get("planner_hints", {}))
        instructions = notes or "Không phát hiện vấn đề mới."

        if verdict == "retry":
            hints["retry_reason"] = notes or "Không rõ lỗi"
            if "không có dữ liệu" in instructions.lower() or "trống" in instructions.lower() or "rỗng" in instructions.lower():
                hints["focus"] = "thu thập lại dữ liệu thực tế"
            elif "lỗi tool" in instructions.lower() or "timeout" in instructions.lower():
                hints["focus"] = "tăng thẩm định kết quả"
            else:
                hints.setdefault("focus", "tái kiểm tra dữ liệu và tham số")
            hints.setdefault("strategy", "giảm concurrency hoặc kiểm tra tham số")
            next_node = "planner"
        else:
            hints.setdefault("status", "check-passed")
            next_node = "synthesize"

        update = {
            "planner_hints": hints,
            "meta_instructions": instructions,
            "meta_next_node": next_node,
            "last_verdict": verdict
        }

        if should_recompact(state):
            logger.info("META_PLANNER: Triggering additional compaction")
            compact = await auto_compact(state, llm, threshold=20)
            update.update(compact)
            update["meta_instructions"] = f"{instructions} (context compacted)"

        return update

    return meta_planner
