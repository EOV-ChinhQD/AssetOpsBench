import os
import asyncio
import logging
import json
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test_agent")

# Map local vLLM server
os.environ["LITELLM_API_KEY"] = "EMPTY"
os.environ["LITELLM_BASE_URL"] = "http://localhost:8001/v1"

async def run_test(query: str, thread_id: str = None):
    # Use a unique thread_id if not provided
    if not thread_id:
        import time
        thread_id = f"victory_{int(time.time())}"
    # Correct model name based on vLLM ps aux output
    model_name = "openai//media/chinh303/New Volume3/ai_models/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct-AWQ/snapshots/8e8ed243bbe6f9a5aff549a0924562fc719b2b8a"
    
    print(f"\n--- Testing Agent with Query: '{query}' ---")
    
    try:
        # 1. Initialize LLM
        llm = LangchainLiteLLM(model_id=model_name)
        
        # 2. Build Graph
        graph = await build_graph(llm)
        
        # 3. Execute
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [HumanMessage(content=query)], "user_id": "test_user"}
        
        async for event in graph.astream(inputs, config=config):
            for node, state in event.items():
                print(f"\n[NODE]: {node}")
                if "messages" in state:
                    last_msg = state["messages"][-1]
                    if hasattr(last_msg, "content") and last_msg.content:
                        print(f"Content: {last_msg.content[:200]}...")
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                         print(f"Tool Calls: {[tc['name'] for tc in last_msg.tool_calls]}")
                
    except Exception as e:
        print(f"\nREAL LLM FAILED: {e}")
        print("\n--- FAILING OVER TO MOCK TEST ---")
        await run_mock_test(query)

async def run_mock_test(query: str):
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatResult, ChatGeneration
    from langchain_core.messages import AIMessage
    
    class MockLLM(BaseChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            text = messages[-1].content.lower()
            if "chào" in text or "dma" in text:
                decision = {
                    "internal_monologue": "Người dùng muốn biết thông tin về DMA. Tôi sẽ tổng hợp câu trả lời.",
                    "tool_plan": [],
                    "next_node": "synthesize"
                }
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps(decision)))])
            # Default fallback
            decision = {
                "internal_monologue": "Tôi chưa hiểu rõ yêu cầu, tôi sẽ trả lời trực tiếp.",
                "tool_plan": [],
                "next_node": "synthesize"
            }
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps(decision)))])
        def bind_tools(self, tools, **kwargs): return self
        @property
        def _llm_type(self): return "mock"

    llm = MockLLM()
    graph = await build_graph(llm)
    config = {"configurable": {"thread_id": "mock_thread"}}
    inputs = {"messages": [HumanMessage(content=query)]}
    
    async for event in graph.astream(inputs, config=config):
        for node, _ in event.items():
            print(f"Node: {node}")

if __name__ == "__main__":
    # Test a full data query (Think -> SQL -> Reflection -> Synthesize)
    test_query = "Sản lượng DMA 03-LB tháng 3 năm 2024 là bao nhiêu?"
    asyncio.run(run_test(test_query))
