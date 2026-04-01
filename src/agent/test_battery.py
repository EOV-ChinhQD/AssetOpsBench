import os
import asyncio
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def run_battery():
    model_name = os.getenv("LLM_MODEL_NAME")
    print(f"\n--- Running Battery Test ---")
    print(f"Model: {model_name}")
    llm = LangchainLiteLLM(model_id=model_name)
        
    graph = await build_graph(llm)
    
    test_cases = [
        {"id": "test_hist_06QM", "query": "Sản lượng 06-QM tháng 10 năm 2024 là bao nhiêu?", "expected": "8560 m3"},
        {"id": "test_norm_05LB", "query": "Mã khu vực 05-LB tháng 9/2024 ra bao nhiêu m3?", "expected": "95180 m3"},
        {"id": "test_forecast_01LB", "query": "Dự báo sản lượng DMA 01-LB vào tháng 4 năm 2026?", "expected": "34653 m3"},
        {"id": "test_sql_count", "query": "Trong hệ thống, có bao nhiêu DMA có mã bắt đầu bằng '01'?", "expected": "hàng dữ liệu"},
        {"id": "test_plot_01LB", "query": "Vẽ biểu đồ sản lượng cho DMA 01-LB.", "expected": "biểu đồ"}
    ]
    
    for tc in test_cases:
        print(f"\n{'='*50}\nRUNNING: {tc['id']}\nQUERY: {tc['query']}\nEXPECTED: ~{tc['expected']}\n{'='*50}")
        config = {"configurable": {"thread_id": f"battery_thread_{tc['id']}"}}
        inputs = {"messages": [HumanMessage(content=tc["query"])], "user_id": f"battery_user_{tc['id']}"}
        
        try:
             async for event in graph.astream(inputs, config=config, stream_mode="updates"):
                 for node, state in event.items():
                     if node == "synthesize" and state and "messages" in state:
                          print(f"\n[FINAL RESPONSE]: {state['messages'][-1].content}")
        except Exception as e:
             print(f"Error in test case {tc['id']}: {e}")

if __name__ == "__main__":
    asyncio.run(run_battery())
