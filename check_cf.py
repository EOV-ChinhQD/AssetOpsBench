import os
import sys
import requests

# Add current dir to path
sys.path.append(os.getcwd())

from src.config.settings import settings

def check_cloudflare():
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    api_key = os.getenv("CLOUDFLARE_API_KEY")
    model_id = os.getenv("CLOUDFLARE_MODEL_ID", "@cf/qwen/qwen3-30b-a3b-fp8")
    
    print(f"\n--- Testing Cloudflare ---")
    print(f"Account ID: {account_id}")
    print(f"API Key: {'SET' if api_key else 'NOT SET'}")
    
    if not account_id or not api_key:
        print("Missing Cloudflare credentials in environment or .env")
        return
        
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_id}"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    payload = {
        "messages": [{"role": "user", "content": "Hi"}],
        "temperature": 0.1
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_cloudflare()
