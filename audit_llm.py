import requests
import os
import sys
from dotenv import load_dotenv

# Path handling
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT_DIR)

load_dotenv()

from src.config.settings import settings

def check_endpoint(name, url, model=None, api_key=None):
    print(f"\n--- Testing Endpoint: {name} ---")
    print(f"URL: {url}")
    if model: print(f"Model: {model}")
    
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    # Try a simple models list first to see if the server is up
    try:
        # Most OpenAI-compatible APIs have /models
        models_url = f"{url}/models"
        print(f"Checking models at: {models_url}...")
        resp = requests.get(models_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            print(f"  [OK] Server is UP. Models available: {[m['id'] for m in resp.json().get('data', [])[:3]]}...")
        else:
            print(f"  [WARN] Server responded with status {resp.status_code} on /models.")
    except Exception as e:
        print(f"  [ERROR] Server seems DOWN or unreachable on /models: {e}")

    # Now try a simple completion and use the correct chat endpoint
    chat_url = f"{url}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 5
    }
    
    try:
        print(f"Testing completion at: {chat_url}...")
        resp = requests.post(chat_url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            print(f"  [SUCCESS] LLM responded: {resp.json()['choices'][0]['message']['content']}")
            return True
        else:
            print(f"  [FAILED] LLM responded with status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [ERROR] Failed to send completion request: {e}")
    
    return False

def main():
    print("Starting LLM Connection Audit...")
    
    # 1. Test Unified Setting (from .env)
    check_endpoint(
        "Current .env configuration (UnifiedLLMClient)", 
        settings.LLM_BASE_URL, 
        settings.LLM_MODEL_NAME, 
        settings.LLM_API_KEY
    )
    
    # 2. Test Local vLLM
    check_endpoint(
        "Local vLLM (Fallback)", 
        "http://localhost:8001/v1", 
        "Qwen2.5-Coder-7B-Instruct-AWQ"
    )

if __name__ == "__main__":
    main()
