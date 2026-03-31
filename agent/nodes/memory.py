import json
import logging
from ..state import AgentState
from src.hanoi_water_db import get_engine
from sqlalchemy import text

engine = get_engine()

logger = logging.getLogger(__name__)

async def load_memory(state: AgentState) -> dict:
    user_id = state.get("user_id", "default_user")
    logger.info(f"Loading user context for: {user_id}")
    
    if not engine:
        logger.warning("Database engine not initialized. Skipping memory load.")
        return {"long_term_context": ""}

    try:
        with engine.connect() as conn:
            query = text("SELECT pref_value FROM app.user_preferences WHERE user_id = :uid AND pref_key = 'profile'")
            val = conn.execute(query, {"uid": user_id}).scalar()
            
            if val:
                if isinstance(val, str): val = json.loads(val)
                context = f"THÔNG TIN NGƯỜI DÙNG: Tên: {val.get('name', 'Chưa rõ')}, Vai trò: {val.get('role', 'Quản lý')}, Vùng quản lý: {', '.join(val.get('managed_dmas', []))}"
                return {"long_term_context": context}
    except Exception as e:
        logger.warning(f"Could not load memory: {e}")
        
    return {"long_term_context": ""}

async def save_memory(state: AgentState) -> dict:
    user_id = state.get("user_id", "default_user")
    messages = state.get("messages", [])
    
    if len(messages) < 2: return state

    try:
        # Use a temporary LLM instance if needed, or pass it in state
        # In the new framework, we can import from src.llm
        from src.llm.litellm import LiteLLMBackend
        import os
        # We need a model ID, defaulting to a common one
        model_id = os.getenv("WATSONX_MODEL_ID", "watsonx/meta-llama/llama-4-maverick-17b-128e-instruct-fp8")
        llm = LiteLLMBackend(model_id)
        
        extract_prompt = f"""Phân tích hội thoại và trích xuất thông tin cá nhân người dùng.
        
Hội thoại: {messages[-4:]} 

Trả về DUY NHẤT JSON (nếu không có thông tin mới, trả về {{}}):
{{
  "name": "Tên người dùng (nếu có)",
  "role": "Chức vụ (ví dụ: Quản lý, Giám đốc)",
  "managed_dmas": ["Mã DMA họ quản lý - ví dụ: 17-TL"]
}}
"""
        res = llm.invoke(extract_prompt)
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
