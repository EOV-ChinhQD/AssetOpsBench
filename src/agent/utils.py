import json
import re
import logging

logger = logging.getLogger(__name__)

def clean_keys(obj):
    """Recursively strips whitespace and extra quotes from dictionary keys."""
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            # 🧹 THE KEY CLEANER: Remove \n, spaces, and extra quotes from keys
            clean_k = str(k).strip().strip('"').strip("'").strip()
            new_dict[clean_k] = clean_keys(v)
        return new_dict
    elif isinstance(obj, list):
        return [clean_keys(x) for x in obj]
    else:
        return obj

def parse_json_from_llm(text: str) -> dict:
    """Robustly extracts and parses JSON from LLM output, handling recursion and junk keys."""
    if not text:
        return {"internal_monologue": "Trình khởi tạo trả về rỗng", "next_node": "synthesize"}
        
    text = text.strip()
    
    # 1. Extract JSON block
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if not json_match:
        return {"internal_monologue": f"Raw text: {text[:50]}", "next_node": "synthesize"}
        
    data_str = json_match.group(0).strip()
    
    def try_parse(s: str):
        try:
            res = json.loads(s)
            if isinstance(res, str) and (res.strip().startswith('{') or res.strip().startswith('[')):
                return try_parse(res)
            return res
        except Exception:
            # Cleanup for trailing commas
            s_clean = re.sub(r',\s*\}', '}', s)
            s_clean = re.sub(r',\s*\]', ']', s_clean)
            try:
                return json.loads(s_clean)
            except:
                raise ValueError(f"Malformed JSON: {s[:100]}")

    try:
        data = try_parse(data_str)
        # 🟢 CRITICAL: Clean all keys to prevent KeyError or missing keys!
        data = clean_keys(data)
        
        if not isinstance(data, dict):
            return {"internal_monologue": str(data), "next_node": "synthesize"}
        return data
    except Exception as e:
        print(f"FAILED_PARSE_DEBUG: {text[:300]}")
        return {"internal_monologue": f"Error: {str(e)}", "next_node": "synthesize"}
