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

TRẢ VỀ JSON:
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
  "reason": "Giải thích ngắn gọn lý do"
}}
"""

class TrajectoryEvaluator:
    def __init__(self, judge_llm):
        self.llm = judge_llm

    async def evaluate(self, question, expected_intent, trajectory, final_answer) -> dict:
        # Format trajectory for prompt
        traj_text = ""
        for i, step in enumerate(trajectory):
            traj_text += f"\nStep {i+1}: [{step.get('type')}] {step.get('tool', '')} -> {str(step.get('output', ''))[:200]}..."

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
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(content)
            return data
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            return {"total": 0, "verdict": "ERROR", "reason": str(e)}
