import os
import asyncio
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

os.environ["LITELLM_API_KEY"] = "EMPTY"
os.environ["LITELLM_BASE_URL"] = "http://localhost:8001/v1"

async def run_isolated_test():
    model_name = "openai//media/chinh303/New Volume2/ai_models/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct-AWQ/snapshots/8e8ed243bbe6f9a5aff549a0924562fc719b2b8a"
    llm = LangchainLiteLLM(model_id=model_name)
    graph = await build_graph(llm)
    
    test_cases = [
        {"id": "sql_count", "query": "Trong hệ thống, có bao nhiêu DMA có mã hiệu bắt đầu bằng '01'?"},
        {"id": "plot_01LB", "query": "Hãy vẽ biểu đồ so sánh sản lượng cho DMA 01-LB ngay lập tức."}
    ]
    
    for tc in test_cases:
        print(f"\n{'='*50}\nRUNNING: {tc['id']}\nQUERY: {tc['query']}\n{'='*50}")
        user_id = f"iso_user_{tc['id']}"
        config = {"configurable": {"thread_id": f"iso_thread_{tc['id']}"}}
        inputs = {"messages": [HumanMessage(content=tc["query"])], "user_id": user_id}
        
        async for event in graph.astream(inputs, config=config):
            for node, state in event.items():
                if node == "synthesize":
                     print(f"\n[FINAL RESPONSE]: {state['messages'][-1].content}")

if __name__ == "__main__":
    asyncio.run(run_isolated_test())
