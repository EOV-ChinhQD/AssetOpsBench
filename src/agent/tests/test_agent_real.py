import os
import asyncio
import logging
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_agent")

async def run_agent(query: str, thread_id: str = None):
    if not thread_id:
        import time
        thread_id = f"test_{int(time.time())}"
    
    model_name = os.getenv("LLM_MODEL_NAME")
    print(f"\n--- Testing Agent with Query: '{query}' ---")
    print(f"Model: {model_name}")
    
    llm = LangchainLiteLLM(model_id=model_name)

    try:
        graph = await build_graph(llm)
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [HumanMessage(content=query)], "user_id": "test_user"}
        
        async for event in graph.astream(inputs, config=config, stream_mode="updates"):
            for node, state in event.items():
                print(f"\n[NODE]: {node}")
                if state and isinstance(state, dict) and "messages" in state:
                    messages = state["messages"]
                    if messages:
                        last_msg = messages[-1]
                        if hasattr(last_msg, "content") and last_msg.content:
                            print(f"Content: {last_msg.content[:300]}...")
                        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                             print(f"Tool Calls: {[tc['name'] for tc in last_msg.tool_calls]}")
                
    except Exception as e:
        import traceback
        print(f"\nAGENT FAILED: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_query = "Tôi cần tra cứu dữ liệu cho DMA 05-LB. Hãy lấy sản lượng 3 tháng gần nhất."
    asyncio.run(run_agent(test_query))
