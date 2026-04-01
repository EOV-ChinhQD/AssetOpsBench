import redis
import os
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

# Redis Connection
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping()
    # logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
    redis_client = None # FORCE DISABLE AS PER USER REQUEST

def get_cache_key(*args):
    """Generates a unique MD5 hash for a set of arguments."""
    payload = ":".join([str(a) for a in args])
    return f"hanoi_water_agent:{hashlib.md5(payload.encode()).hexdigest()}"

def get_tool_cache(tool_name: str, params: dict):
    if not redis_client: return None
    key = get_cache_key("tool", tool_name, json.dumps(params, sort_keys=True))
    val = redis_client.get(key)
    if val:
        logger.info(f"Redis Cache Hit (Tool): {tool_name}")
        return json.loads(val)
    return None

def set_tool_cache(tool_name: str, params: dict, result: str, ttl: int = 3600):
     if not redis_client or not result: return
     # Don't cache errors
     if "lỗi" in result.lower() or "error" in result.lower(): return
     
     key = get_cache_key("tool", tool_name, json.dumps(params, sort_keys=True))
     redis_client.setex(key, ttl, json.dumps(result))

def get_thought_cache(user_id: str, question: str):
    if not redis_client: return None
    # Key includes user_id to respect profile nuances
    key = get_cache_key("thought", user_id, question)
    val = redis_client.get(key)
    if val:
        logger.info(f"Redis Cache Hit (Thought): {question[:30]}...")
        return json.loads(val)
    return None

def set_thought_cache(user_id: str, question: str, plan: dict, ttl: int = 86400):
     if not redis_client or not plan: return
     key = get_cache_key("thought", user_id, question)
     redis_client.setex(key, ttl, json.dumps(plan))
