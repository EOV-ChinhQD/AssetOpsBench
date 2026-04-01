import os
import asyncio
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def run_debug():
    model_name = os.getenv("LLM_MODEL_NAME")
    print(f"\n--- Debugging Forecast ---")
    print(f"Model: {model_name}")
    llm = LangchainLiteLLM(model_id=model_name)
    
    graph = await build_graph(llm)
    
    query = "Dự báo sản lượng DMA 01-LB vào tháng 4 năm 2026?"
    config = {"configurable": {"thread_id": "debug_forecast_99"}}
    inputs = {"messages": [HumanMessage(content=query)], "user_id": "debug_user"}
    
    async for event in graph.astream(inputs, config=config, stream_mode="updates"):
        for node, state in event.items():
            print(f"\n[NODE]: {node}")
            if state and isinstance(state, dict) and "messages" in state:
                last_msg = state["messages"][-1]
                if hasattr(last_msg, "content"):
                    print(f"Content: {last_msg.content[:500]}...")
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    print(f"Tool Calls: {last_msg.tool_calls}")

if __name__ == "__main__":
    asyncio.run(run_debug())
