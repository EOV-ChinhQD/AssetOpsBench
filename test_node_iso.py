import os
import asyncio
from langchain_core.messages import HumanMessage
from src.agent.nodes.agent_core import get_agent_core_node
from src.llm.langchain_adapter import LangchainLiteLLM
from langchain_core.tools import StructuredTool

# Point to local server
os.environ["LITELLM_API_KEY"] = "sk-fake"
os.environ["LITELLM_BASE_URL"] = "http://localhost:8001/v1"
os.environ["OPENAI_API_KEY"] = "sk-fake"

model_name = "openai//media/chinh303/New Volume3/ai_models/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct-AWQ/snapshots/8e8ed243bbe6f9a5aff549a0924562fc719b2b8a"

async def test_node_isolated():
    llm = LangchainLiteLLM(model_id=model_name)
    tools = [] # Empty for test
    node_fn = get_agent_core_node(llm, tools)
    
    state = {
        "messages": [HumanMessage(content="Chào bạn")],
        "long_term_context": "Test user"
    }
    
    print("Calling AgentCore isolated...")
    result = await node_fn(state)
    print("\nRESULT:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_node_isolated())
