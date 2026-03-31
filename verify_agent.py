import asyncio
import os
import logging
from dotenv import load_dotenv

# Set PYTHONPATH to include src and .
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).parent.resolve()
sys.path.append(str(REPO_ROOT / "src"))
sys.path.append(str(REPO_ROOT))

from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

load_dotenv()

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Use the model from environment or default
    model_id = os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3-8B")
    llm = LangchainLiteLLM(model_id=model_id)
    
    print(f"Building LangGraph agent with model: {model_id}...")
    graph = await build_graph(llm)
    
    query = "Top 3 DMA tiêu thụ cao nhất tháng 1/2026 là gì?"
    print(f"\nUser query: {query}")
    
    inputs = {"messages": [("human", query)], "user_id": "test_user"}
    config = {"configurable": {"thread_id": "test_thread_1"}}
    
    async for event in graph.astream(inputs, config=config):
        for node_name, output in event.items():
             print(f"--- Node: {node_name} ---")
             if "messages" in output:
                 print(output["messages"][-1].content)
             else:
                 print(output)

if __name__ == "__main__":
    asyncio.run(main())
