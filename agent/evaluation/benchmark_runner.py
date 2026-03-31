import json
import logging
import asyncio
import uuid
import datetime
from src.api.server.tools.llm_provider import get_langchain_llm
from src.api.server.agent.graph import build_graph
from src.api.server.agent.evaluation.trajectory_eval import TrajectoryEvaluator
from src.api.server.agent.evaluation.test_suite import get_all_test_cases

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_benchmark():
    # Setup LLM and Judge
    llm = get_langchain_llm(temperature=0)
    agent = await build_graph(llm)
    evaluator = TrajectoryEvaluator(llm)

    test_cases = get_all_test_cases()
    results = []

    print(f"\n🚀 Đang chạy Benchmark cho {len(test_cases)} Test Cases...\n")

    for tc in test_cases:
        print(f"CASE {tc['id']}: {tc['question']}")
        
        # 1. Run Agent
        config = {"configurable": {"thread_id": f"bench_{uuid.uuid4().hex[:8]}"}}
        output = await agent.ainvoke({"messages": [tc["question"]], "user_id": f"bench_{tc['id']}"}, config)
        
        # 2. Extract results
        final_answer = output["messages"][-1].content
        trajectory = output.get("tool_results", [])
        
        # 3. Evaluate
        eval_result = await evaluator.evaluate(
            question=tc["question"],
            expected_intent=tc["expected_intent"],
            trajectory=trajectory,
            final_answer=final_answer
        )
        
        results.append({
            "tc_id": tc["id"],
            "question": tc["question"],
            "verdict": eval_result.get("verdict"),
            "total_score": eval_result.get("total"),
            "reason": eval_result.get("reason"),
            "scores": eval_result.get("scores")
        })

        print(f"  Result: {eval_result.get('verdict')} (Score: {eval_result.get('total')}/18) - {eval_result.get('reason')}\n")

    # Final Summary
    pass_count = sum(1 for r in results if r["verdict"] == "PASS")
    pass_rate = (pass_count / len(results)) * 100
    avg_score = sum(r["total_score"] for r in results) / len(results)

    report = f"""
# BENCHMARK REPORT: Hanoi Water AI Agent
- Ngày chạy: {datetime.datetime.now().isoformat()}
- Tổng số Test Case: {len(test_cases)}
- Pass Rate: {pass_rate:.1f}% ({pass_count}/{len(results)})
- Avg Score: {avg_score:.2f} / 18

## Chi tiết Kết quả:
"""
    for r in results:
        report += f"\n### {r['tc_id']}: {r['verdict']} ({r['total_score']}/18)\n"
        report += f"- Question: {r['question']}\n"
        report += f"- Reason: {r['reason']}\n"
        report += f"- Scores: {json.dumps(r['scores'], ensure_ascii=False)}\n"

    # Save report
    report_file = f"benchmark_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md"
    with open(report_file, "w") as f:
        f.write(report)
    
    print(f"\n✅ Benchmark hoàn thành! Báo cáo đã lưu tại: {report_file}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
