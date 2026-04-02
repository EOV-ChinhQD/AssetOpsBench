import os
import sys
import json
import requests
import logging

# Add current dir to path
sys.path.append(os.getcwd())

from src.config.settings import settings

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("llm_check")

def check_llm():
    print(f"\n--- 🚀 KIỂM TRA KẾT NỐI LLM ({settings.LLM_MODEL_NAME}) ---")
    print(f"Provider: {settings.LLM_PROVIDER}")
    print(f"URL: {settings.LLM_BASE_URL}")
    print(f"API Key present: {'Yes' if settings.LLM_API_KEY else 'No'}")
    
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": "Hello! Groq is working?"}],
        "max_tokens": 50,
        "temperature": 0.1
    }
    
    try:
        response = requests.post(
            f"{settings.LLM_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            print(f"\n✅ THÀNH CÔNG!")
            print(f"Phản hồi từ LLM: {content.strip()}")
        else:
            print(f"\n❌ LỖI KẾT NỐI (Status: {response.status_code})")
            print(f"Chi tiết: {response.text}")
            
    except Exception as e:
        print(f"\n❌ LỖI HỆ THỐNG: {e}")

if __name__ == "__main__":
    check_llm()
