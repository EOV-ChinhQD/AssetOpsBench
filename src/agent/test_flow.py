import os
import asyncio
import logging
import uuid
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agent.graph import build_graph
from src.llm.langchain_adapter import LangchainLiteLLM

# Configure logging
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Point to local LLM server
os.environ["LITELLM_API_KEY"] = "sk-any"
os.environ["LITELLM_BASE_URL"] = "http://localhost:8001/v1"

async def run_multi_step_flow():
    """
    INDUSTRIAL TEST: REAL DATA get_info -> get_history -> plot_dma
    Using REAL DMA IDs found in DB: 05-LB, 01-LT
    """
    # Correct model name based on vLLM ps aux output
    model_name = "openai//media/chinh303/New Volume3/ai_models/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct-AWQ/snapshots/8e8ed243bbe6f9a5aff549a0924562fc719b2b8a"
    llm = LangchainLiteLLM(model_id=model_name)
    graph = await build_graph(llm)
    
    # Use a unique thread ID for full session persistence
    thread_id = f"real_flow_{uuid.uuid4().hex[:6]}"
    config = {"configurable": {"thread_id": thread_id}}
    user_id = f"real_user_{thread_id}"
    
    # --- STEP 1: Identification ---
    logger.info("\n" + "="*50 + "\nSTEP 1: Identification (REAL)\n" + "="*50)
    # The user asks for a specific DMA that exists: 05-LB
    q1 = "Tôi muốn tìm mã hiệu của DMA khu vực 05-LB."
    logger.info(f"USER: {q1}")
    
    inputs1 = {"messages": [HumanMessage(content=q1)], "user_id": user_id}
    async for event in graph.astream(inputs1, config=config):
        for node, data in event.items():
            logger.info(f"NODE: {node}")

    # --- STEP 2: Data Retrieval ---
    logger.info("\n" + "="*50 + "\nSTEP 2: Data Retrieval (REAL)\n" + "="*50)
    # User refers back to "that DMA"
    q2 = "Lấy cho tôi 6 tháng sản lượng lịch sử gần nhất của DMA vừa tìm được."
    logger.info(f"USER: {q2}")
    
    inputs2 = {"messages": [HumanMessage(content=q2)], "user_id": user_id}
    async for event in graph.astream(inputs2, config=config):
        for node, data in event.items():
            logger.info(f"NODE: {node}")

    # --- STEP 3: Analytical/Visual ---
    logger.info("\n" + "="*50 + "\nSTEP 3: Analytical / Visual (REAL)\n" + "="*50)
    # User asks for plot based on history and forecast
    q3 = "Bây giờ hãy vẽ biểu đồ so sánh sản lượng lịch sử vừa rồi với dự báo 3 tháng tới."
    logger.info(f"USER: {q3}")
    
    inputs3 = {"messages": [HumanMessage(content=q3)], "user_id": user_id}
    async for event in graph.astream(inputs3, config=config):
        for node, data in event.items():
            if "messages" in data:
                last_msg = data["messages"][-1].content
                if node == "synthesize":
                     print(f"\n[FINAL RESPONSE]: {last_msg}")
                else:
                     logger.info(f"NODE {node} executed.")

if __name__ == "__main__":
    asyncio.run(run_multi_step_flow())
