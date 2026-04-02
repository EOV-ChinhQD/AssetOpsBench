import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

EVAL_PROMPT = """Bạn là chuyên gia đánh giá AI agent trong lĩnh vực cấp nước (IBM AssetOpsBench methodology).
Nhiệm vụ của bạn là chấm điểm chuỗi hành động (trajectory) của Agent theo 6 chiều (0-3 điểm mỗi chiều).

THÔNG TIN ĐẦU VÀO:
- Câu hỏi gốc: {question}
- Ý định mong đợi: {expected_intent}
- Trajectory thực tế: {trajectory}
- Câu trả lời cuối: {final_answer}

6 CHIỀU ĐÁNH GIÁ (Thang điểm 0-3):
1. **INTENT_ACCURACY**: Phân loại intent (GLOBAL/SPECIFIC/HYBRID) có đúng không?
2. **TOOL_SELECTION**: Chọn tool có phù hợp và đầy đủ không?
3. **TRAJECTORY_EFFICIENCY**: Số bước có tối ưu không? (Thừa bước = trừ điểm).
4. **LOOKUP_COMPLIANCE**: Có gọi `get_dma_info` trước khi hỏi data của SPECIFIC/HYBRID DMA không? (KHÔNG GỌI = 0 điểm CS).
5. **ANSWER_CORRECTNESS**: Câu trả lời cuối có đúng số liệu từ Observation không?
6. **INSIGHT_QUALITY**: Có cung cấp thêm insight (xu hướng, bất thường) hữu ích không?

LƯU Ý QUAN TRỌNG:
- Nếu bỏ qua `get_dma_info` cho SPECIFIC query -> Điểm LOOKUP_COMPLIANCE = 0.
- Nếu bịa số liệu (hallucination) -> Điểm ANSWER_CORRECTNESS = 0.

### ĐỊNH DẠNG TRẢ VỀ (BẮT BUỘC):
Bạn CHỈ ĐƯỢC trả về duy nhất một khối JSON hợp lệ. KHÔNG giải thích, KHÔNG chào hỏi, KHÔNG có văn bản tự do bên ngoài JSON.

```json
{{
  "scores": {{
    "intent_accuracy": 0-3,
    "tool_selection": 0-3,
    "trajectory_efficiency": 0-3,
    "lookup_compliance": 0-3,
    "answer_correctness": 0-3,
    "insight_quality": 0-3
  }},
  "total": 0-18,
  "verdict": "PASS" | "PARTIAL" | "FAIL",
  "reason": "Giải thích ngắn gọn lý do tại đây"
}}
```
"""

class TrajectoryEvaluator:
    def __init__(self, judge_llm):
        self.llm = judge_llm

    async def evaluate(self, question, expected_intent, trajectory, final_answer) -> dict:
        # Format trajectory for prompt
        traj_text = ""
        for i, step in enumerate(trajectory):
            tool = step.get('tool', 'unknown_tool')
            output = str(step.get('output', ''))[:500]
            traj_text += f"\nRound {i+1}: AI called {tool}\nObservation: {output}...\n"

        logger.info(f"EVAL_DEBUG - Evaluating trajectory for: {question[:50]}...")
        prompt = [
            SystemMessage(content=EVAL_PROMPT.format(
                question=question,
                expected_intent=expected_intent,
                trajectory=traj_text,
                final_answer=final_answer
            ))
        ]

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content
            
            # Advanced extraction - find the OUTERMOST { } even if it's not the only content
            import re
            json_block = re.search(r"(\{.*\})", content, re.DOTALL)
            if json_block:
                content = json_block.group(1).strip()

            from src.agent.utils import parse_json_from_llm
            try:
                data = parse_json_from_llm(content)
            except Exception:
                # 🛡️ HEURISTIC FALLBACK: If JSON parsing fails, try to extract scores from numbered text
                logger.warning(f"EVAL_DEBUG - JSON parse failed. Attempting heuristic extraction from:\n{content[:200]}...")
                data = self._heuristic_parse(content)
            
            if "scores" not in data:
                # Handle cases where heuristic also fails or result was just an error dict
                logger.error(f"EVAL_DEBUG - JSON/Heuristic missing 'scores'. Content preview:\n{response.content[:500]}")
                return {"total": 0, "verdict": "ERROR", "reason": "Judge response was not parseable as JSON or heuristic scores"}
                
            return data
        except Exception as e:
            logger.error(f"Evaluation error: {e}\nRaw content preview: {response.content[:500] if 'response' in locals() else 'None'}")
            return {"total": 0, "verdict": "ERROR", "reason": f"System Error: {str(e)}"}

    def _heuristic_parse(self, text: str) -> dict:
        """Attempts to extract scores if the judge returned a numbered list instead of JSON."""
        scores = {}
        patterns = {
            "intent_accuracy": r"INTENT_ACCURACY.*?(\d)",
            "tool_selection": r"TOOL_SELECTION.*?(\d)",
            "trajectory_efficiency": r"TRAJECTORY_EFFICIENCY.*?(\d)",
            "lookup_compliance": r"LOOKUP_COMPLIANCE.*?(\d)",
            "answer_correctness": r"ANSWER_CORRECTNESS.*?(\d)",
            "insight_quality": r"INSIGHT_QUALITY.*?(\d)"
        }
        
        import re
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.I | re.DOTALL)
            if match:
                scores[key] = int(match.group(1))
            else:
                scores[key] = 0
                
        total = sum(scores.values())
        verdict = "PASS" if total >= 12 else ("PARTIAL" if total >= 6 else "FAIL")
        
        # Extract verdict and reason if possible
        v_match = re.search(r"VERDICT:?\s*(\w+)", text, re.I)
        r_match = re.search(r"REASON:?\s*(.*)", text, re.I)
        
        return {
            "scores": scores,
            "total": total,
            "verdict": v_match.group(1).upper() if v_match else verdict,
            "reason": r_match.group(1).strip() if r_match else "Heuristic extraction from text response."
        }
