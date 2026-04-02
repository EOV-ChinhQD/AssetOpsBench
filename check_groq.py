import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

def check_groq():
    api_key = os.getenv("GROQ_API_KEY")
    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    model_name = os.getenv("GROQ_MODEL_NAME", "llama3-8b-8192")
    
    print(f"\n--- 🚀 TESTING GROQ ({model_name}) ---")
    print(f"URL: {base_url}")
    print(f"API Key: {'SET' if api_key else 'NOT SET'}")
    
    if not api_key:
        print("Missing Groq API Key!")
        return
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Say 'Groq is ready' if you hear me."}],
        "max_tokens": 50,
        "temperature": 0.1
    }
    
    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            print(f"\n✅ THÀNH CÔNG!")
            print(f"Phản hồi từ Groq: {content.strip()}")
        else:
            print(f"\n❌ LỖI KẾT NỐI (Status: {resp.status_code})")
            print(f"Chi tiết: {resp.text}")
            
    except Exception as e:
        print(f"\n❌ LỖI HỆ THỐNG: {e}")

if __name__ == "__main__":
    check_groq()
