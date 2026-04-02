import asyncio
import json

from src.agent.nodes.meta_planner import get_meta_planner_node
from src.agent.nodes.reflect import get_reflect_node


class DummyLLM:
    def __init__(self, response: str):
        self.response = response

    async def ainvoke(self, prompt):
        class Response:
            def __init__(self, content):
                self.content = content
        return Response(self.response)


def test_reflect_detects_tool_errors_and_records_history():
    llm = DummyLLM('{"verdict": "pass"}')
    node = get_reflect_node(llm)
    state = {
        "retry_count": 0,
        "tool_results": [
            {"tool": "get_history", "output": json.dumps({"status": "error", "message": "Timeout"})}
        ],
        "reflection_history": []
    }

    result = asyncio.run(node(state))

    assert result["reflect_verdict"] == "retry"
    assert result["retry_count"] == 1
    assert result["meta_instructions"].startswith("Lỗi tool")
    assert len(result["reflection_history"]) == 1
    entry = result["reflection_history"][-1]
    assert entry["verdict"] == "retry"
    assert "get_history" in entry["reason"]


def test_meta_planner_marks_retry_and_routes_to_planner():
    llm = DummyLLM("")
    node = get_meta_planner_node(llm)
    state = {
        "reflect_verdict": "retry",
        "reflect_notes": "Dữ liệu rỗng từ get_history.",
        "planner_hints": {},
        "messages": [],
    }

    result = asyncio.run(node(state))

    assert result["meta_next_node"] == "planner"
    assert result["planner_hints"]["retry_reason"] == state["reflect_notes"]
    assert "focus" in result["planner_hints"]
