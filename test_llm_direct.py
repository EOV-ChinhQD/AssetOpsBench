import os
import json
import litellm

# Point to local server
os.environ["LITELLM_API_KEY"] = "sk-fake"
os.environ["OPENAI_API_KEY"] = "sk-fake"
# Try single slash
model_name = "openai/media/chinh303/New Volume3/ai_models/huggingface/hub/models--Qwen--Qwen2.5-Coder-7B-Instruct-AWQ/snapshots/8e8ed243bbe6f9a5aff549a0924562fc719b2b8a"

print(f"Testing LiteLLM with model: {model_name}")
try:
    response = litellm.completion(
        model=model_name,
        messages=[{"role": "user", "content": "Say hello"}],
        api_base="http://localhost:8001/v1",
        temperature=0.0
    )
    print("SUCCESS!")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"FAILED: {e}")
