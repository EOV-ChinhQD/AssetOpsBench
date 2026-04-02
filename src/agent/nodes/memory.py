import json
import logging
from src.agent.state import AgentState
from src.hanoi_water_db import get_engine
from sqlalchemy import text

engine = get_engine()

logger = logging.getLogger(__name__)

async def load_memory(state: AgentState) -> dict:
    """Loads operational context and persistent user profile from DB."""
    user_id = state.get("user_id", "default_user")
    logger.info(f"LOADING_MEMORY: User={user_id}")
    print(f"📂 LOADING: Initializing session memory for {user_id}...")
    
    # Base system instructions that form the 'long-term context'
    system_context = "VAI TRÒ: Chuyên viên vận hành hệ thống cấp nước Hà Nội. NHIỆM VỤ: Đảm bảo an ninh nguồn nước và tối ưu hóa phân phối."
    
    if not engine:
        return {"long_term_context": system_context}

    try:
        loaded_dma = {}
        with engine.connect() as conn:
            # 1. Fetch Profile
            query = text("SELECT pref_value FROM app.user_preferences WHERE user_id = :uid AND pref_key = 'profile'")
            val = conn.execute(query, {"uid": user_id}).scalar()
            
            if val:
                if isinstance(val, str): val = json.loads(val)
                user_desc = f" (Người dùng: {val.get('name', 'Ẩn danh')}, Vai trò: {val.get('role', 'Nhân viên')})"
                system_context += user_desc
            
            # 2. Fetch DMA Cache (Long-term memory of station mapping)
            query_dma = text("SELECT pref_value FROM app.user_preferences WHERE user_id = :uid AND pref_key = 'dma_cache'")
            cached_dma = conn.execute(query_dma, {"uid": user_id}).scalar()
            if cached_dma:
                if isinstance(cached_dma, str): 
                    loaded_dma = json.loads(cached_dma)
        
        return {"long_term_context": system_context, "resolved_dma": loaded_dma}
    except Exception as e:
        logger.warning(f"Memory load partial failure: {e}")
        
    return {"long_term_context": system_context}

async def save_memory(state: AgentState) -> dict:
    """Persists key session state variables (like resolved DMAs) to the DB."""
    user_id = state.get("user_id", "default_user")
    resolved_dma = state.get("resolved_dma", {})
    
    logger.info(f"SAVING_MEMORY: User={user_id}, CacheSize={len(resolved_dma)}")
    print(f"💾 SAVING: Recording session cache for {user_id}...")
    
    if not engine or not resolved_dma:
        return state

    try:
        with engine.connect() as conn:
            # We save the 'resolved_dma' as a preference so the agent remembers normalized IDs
            upsert = text("""
                INSERT INTO app.user_preferences (user_id, pref_key, pref_value, source, updated_at)
                VALUES (:uid, 'dma_cache', :val, 'langgraph', now())
                ON CONFLICT (user_id, pref_key) DO UPDATE SET
                    pref_value = :val,
                    updated_at = now()
            """)
            conn.execute(upsert, {"uid": user_id, "val": json.dumps(resolved_dma)})
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to persist memory cache: {e}")
        
    return state
