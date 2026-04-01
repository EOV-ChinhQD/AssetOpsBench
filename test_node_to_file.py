import os
import asyncio
import json
from langchain_core.messages import HumanMessage
from src.agent.nodes.agent_core import get_agent_core_node
from src.llm.langchain_adapter import LangchainLiteLLM

os.environ["LITELLM_API_KEY"] = "sk-fake"
os.environ["LITELLM_BASE_URL"] = "http://localhost:8001/v1"
os.environ["OPENAI_API_KEY"] = "sk-fake"

model_name = "openai//media/chinh303/New Volume3/ai_models/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct-AWQ/snapshots/8e8ed243bbe6f9a5aff549a0924562fc719b2b8a"

async def test_node_to_file():
    llm = LangchainLiteLLM(model_id=model_name)
    node_fn = get_agent_core_node(llm, [])
    state = {"messages": [HumanMessage(content="Chào bạn")], "long_term_context": "Test"}
    
    with open("test_node_iso.log", "w") as f:
        f.write("Starting test...\n")
        try:
            result = await node_fn(state)
            f.write(f"RESULT: {json.dumps(result, indent=2)}\n")
        except Exception as e:
            f.write(f"ERROR: {e}\n")
    print("Done writing to test_node_iso.log")

if __name__ == "__main__":
    asyncio.run(test_node_to_file())
