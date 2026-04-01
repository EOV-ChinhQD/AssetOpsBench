import json
import logging
from src.agent.state import AgentState
from src.hanoi_water_db import get_engine
from sqlalchemy import text

engine = get_engine()

logger = logging.getLogger(__name__)

async def load_memory(state: AgentState) -> dict:
    user_id = state.get("user_id", "default_user")
    logger.info(f"Loading user context for: {user_id}")
    
    if not engine:
        logger.warning("Database engine not initialized. Skipping memory load.")
        return {"long_term_context": "Không có dữ liệu người dùng (DB Offline)."}

    try:
        with engine.connect() as conn:
            query = text("SELECT pref_value FROM app.user_preferences WHERE user_id = :uid AND pref_key = 'profile'")
            val = conn.execute(query, {"uid": user_id}).scalar()
            
            if val:
                if isinstance(val, str): val = json.loads(val)
                # Format into a professional context string for the LLM
                context = (
                    f"DANH TÍNH: {val.get('name', 'Ẩn danh')}. "
                    f"VAI TRÒ: {val.get('role', 'Nhân viên vận hành')}. "
                    f"PHẠM VI QUẢN LÝ: {', '.join(val.get('managed_dmas', [])) if val.get('managed_dmas') else 'Toàn hệ thống'}."
                )
                return {"long_term_context": context}
    except Exception as e:
        logger.warning(f"Could not load memory: {e}")
        
    return {"long_term_context": "Người dùng mới (Chưa có Profile)."}

async def save_memory(state: AgentState) -> dict:
    user_id = state.get("user_id", "default_user")
    messages = state.get("messages", [])
    
    if len(messages) < 2: return state

    try:
        from src.llm.langchain_adapter import LangchainLiteLLM
        import os
        
        # Skip for mock users to avoid API errors during tests
        if user_id.startswith("mock_"):
            logger.info("Skipping real memory save for mock user.")
            return state
            
        model_id = os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3-8B")
        # Ensure API key is set for LiteLLM (it often expects OPENAI_API_KEY for custom endpoints)
        if "LITELLM_API_KEY" in os.environ and "OPENAI_API_KEY" not in os.environ:
             os.environ["OPENAI_API_KEY"] = os.environ["LITELLM_API_KEY"]
             
        llm = LangchainLiteLLM(model_id=model_id)
        
        # Serialize messages to plain text for the LLM
        history_text = "\n".join([f"{m.type}: {m.content}" for m in messages[-4:]])
        
        extract_prompt = f"""Phân tích hội thoại và trích xuất thông tin cá nhân người dùng.
        
Hội thoại:
{history_text}

Trả về DUY NHẤT JSON (nếu không có thông tin mới, trả về {{}}):
{{
  "name": "Tên người dùng (nếu có)",
  "role": "Chức vụ (ví dụ: Quản lý, Giám đốc)",
  "managed_dmas": ["Mã DMA họ quản lý - ví dụ: 17-TL"]
}}
"""
        res = await llm.ainvoke(extract_prompt)
        try:
             import re
             content = res.content
             blocks = re.findall(r"\{.*\}", content, re.DOTALL)
             extract = json.loads(blocks[0]) if blocks else {}
        except: extract = {}

        if extract and any(extract.values()):
            with engine.connect() as conn:
                upsert = text("""
                    INSERT INTO app.user_preferences (user_id, pref_key, pref_value, source, updated_at)
                    VALUES (:uid, 'profile', :val, 'langgraph', now())
                    ON CONFLICT (user_id, pref_key) DO UPDATE SET
                        pref_value = app.user_preferences.pref_value || :val,
                        updated_at = now()
                """)
                conn.execute(upsert, {"uid": user_id, "val": json.dumps(extract)})
                conn.commit()
    except Exception as e:
        logger.error(f"Failed to save profile: {e}")
        
    return state
