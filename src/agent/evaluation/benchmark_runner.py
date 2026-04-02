import logging
import asyncio
import uuid
import datetime
import os
import traceback
from typing import List, Dict, Any

# Fix path
import sys
sys.path.append(os.getcwd())

from src.agent.graph import build_graph
from src.agent.evaluation.test_suite import get_minimal_test_suite
from src.agent.evaluation.trajectory_eval import TrajectoryEvaluator
from src.llm.langchain_adapter import LangchainLiteLLM

# 🟢 CONFIG LOGGING TO CONSOLE
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
async def cleanup_database():
    """Cleans up the LangGraph checkpointer and User Preferences for a fresh run."""
    from src.hanoi_water_db import get_engine
    from sqlalchemy import text
    engine = get_engine()
    if not engine:
        print("⚠️  Warning: DB engine not available for cleanup.")
        return
    
    print("🧹 CLEANING: Purging checkpointer and user memory for a fresh benchmark...")
    try:
        with engine.connect() as conn:
            # Clean LangGraph persistence tables
            conn.execute(text("TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes CASCADE"))
            # Clean User Preferences (DMA Cache, etc)
            conn.execute(text("TRUNCATE app.user_preferences CASCADE"))
            conn.commit()
            print("✨ CLEANUP SUCCESS: Database is fresh.")
    except Exception as e:
        print(f"❌ CLEANUP FAILED: {e}")

async def run_benchmark():
    await cleanup_database()
    llm = LangchainLiteLLM()
    agent = await build_graph(llm)
    evaluator = TrajectoryEvaluator(llm)
    test_cases = get_minimal_test_suite()
    results = []

    print("\n" + "🚀" * 15)
    print("STARTING VERBOSE BENCHMARK (V2.5)")
    print(f"Total scenarios: {len(test_cases)}")
    print("🚀" * 15 + "\n")

    for idx, tc in enumerate(test_cases):
        print(f"\n{'='*20} [{idx+1}/{len(test_cases)}] CASE {tc['id']} {'='*20}")
        print(f"QUESTION: {tc['question']}")
        
        # Small delay for UI readability (Local LLM has no rate limits!)
        if idx > 0:
            await asyncio.sleep(1)

        thread_id = f"bench_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [tc["question"]], "user_id": f"bench_{tc['id']}"}
        
        trajectory = []
        final_answer = "No response"

        try:
            # 🟢 STREAMING UPDATES FOR VERBOSE PROCESS & RESULTS
            print(f"\n--- PROCESS FLOW ---")
            async for event in agent.astream(inputs, config, stream_mode="updates"):
                for node_name, update in event.items():
                    print(f"\n[NODE: {node_name.upper()}]")
                    
                    # 1. Log Monologue
                    if "internal_monologue" in update:
                        print(f"💭 {update['internal_monologue']}")
                    
                    # 2. Log Tool Calls from AI
                    if "messages" in update:
                        last_msg = update["messages"][-1]
                        if last_msg.type == "ai":
                            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                for tc_call in last_msg.tool_calls:
                                    print(f"🛠️  REQUEST: {tc_call['name']}({json.dumps(tc_call['args'], ensure_ascii=False)})")
                            elif last_msg.content:
                                print(f"🤖 AGENT: {last_msg.content}")
                        
                        # 3. Log Tool Results (When tool_node or collect_results runs)
                        elif last_msg.type == "tool":
                            content_preview = str(last_msg.content)
                            if len(content_preview) > 500:
                                content_preview = content_preview[:500] + "..."
                            print(f"✅ RESULT [{last_msg.name}]: {content_preview}")
                    
                    # 4. Log Reflection Verdicts
                    if "reflect_verdict" in update:
                        print(f"🧐 AUDIT: {update['reflect_verdict'].upper()} - {update.get('reflect_notes', '')}")
                    if "meta_instructions" in update and update["meta_instructions"]:
                        print(f"🎯 META: {update['meta_instructions']}")
            
            # Get final state for evaluation
            final_state = await agent.aget_state(config)
            output = final_state.values
            final_answer = output["messages"][-1].content if output.get("messages") else "No response"
            trajectory = output.get("tool_results", [])

            # --- EVALUATE ---
            print(f"\n--- JUDGE EVALUATION ---")
            eval_result = await evaluator.evaluate(
                question=tc["question"],
                expected_intent=tc["expected_intent"],
                trajectory=trajectory,
                final_answer=final_answer
            )
            
            results.append({
                "tc_id": tc["id"],
                "question": tc["question"],
                "verdict": eval_result.get("verdict", "FAIL"),
                "total_score": eval_result.get("total", 0),
                "reason": eval_result.get("reason", "Unknown"),
                "trajectory": trajectory
            })

            color = "\033[92m" if eval_result.get("verdict") == "PASS" else "\033[91m"
            print(f"\nVERDICT: {color}{eval_result.get('verdict')}\033[0m (Score: {eval_result.get('total')}/18)")
            print(f"REASON: {eval_result.get('reason')}")
        
        except Exception as e:
            traceback.print_exc()
            print(f"\n❌ ERROR running agent: {e}")
            results.append({"tc_id": tc["id"], "question": tc["question"], "verdict": "ERROR", "reason": str(e)})

    # Generate Report
    report_name = f"benchmark_report_verbose_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md"
    with open(report_name, "w", encoding="utf-8") as f:
        f.write(f"# VERBOSE REPORT\n- Pass: {sum(1 for r in results if r['verdict'] == 'PASS')}/{len(results)}\n")
        for r in results:
            f.write(f"## {r['tc_id']}: {r['verdict']}\n{r['reason']}\n\n")

    print(f"\n✅ Benchmark completed! Report: {report_name}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
