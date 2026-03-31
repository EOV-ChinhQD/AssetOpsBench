import os
import asyncio
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

load_dotenv()
# SET ROOT LOGGING
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

os.environ["LITELLM_API_KEY"] = "EMPTY"
os.environ["LITELLM_BASE_URL"] = "http://localhost:8001/v1"

async def run_debug():
    model_name = "openai//media/chinh303/New Volume2/ai_models/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct-AWQ/snapshots/8e8ed243bbe6f9a5aff549a0924562fc719b2b8a"
    llm = LangchainLiteLLM(model_id=model_name)
    graph = await build_graph(llm)
    
    query = "Dự báo sản lượng DMA 01-LB vào tháng 4 năm 2026?"
    config = {"configurable": {"thread_id": "debug_forecast_99"}}
    inputs = {"messages": [HumanMessage(content=query)], "user_id": "debug_user"}
    
    async for event in graph.astream(inputs, config=config):
        for node, state in event.items():
            print(f"\n[NODE]: {node}")
            if "messages" in state:
                last_msg = state["messages"][-1]
                if hasattr(last_msg, "content"):
                    print(f"Content: {last_msg.content[:500]}...")
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    print(f"Tool Calls: {last_msg.tool_calls}")

if __name__ == "__main__":
    asyncio.run(run_debug())
