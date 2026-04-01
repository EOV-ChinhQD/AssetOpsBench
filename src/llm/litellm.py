import os
import json
import logging
import requests
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from .base import LLMBackend

logger = logging.getLogger(__name__)

class LiteLLMBackend(LLMBackend):
    def __init__(self, model_id: Optional[str] = None) -> None:
        # Use local vLLM if available/requested, else fallback
        self._base_url = os.environ.get("LOCAL_LLM_URL", "http://localhost:8001/v1")
        self._model_id = model_id or os.environ.get("LLM_MODEL_NAME", "Qwen2.5-Coder-7B-Instruct-AWQ")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def generate(self, prompt: str, temperature: float = 0.0) -> str:
        # Check if we should use Cloudflare or Local vLLM
        if "cloudflare" in self._model_id.lower():
             return self._generate_cloudflare(prompt, temperature)
        else:
             return self._generate_vllm(prompt, temperature)

    def _generate_vllm(self, prompt: str, temperature: float) -> str:
        payload = {
            "model": self._model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": 2048
        }
        try:
            resp = requests.post(f"{self._base_url}/chat/completions", json=payload, timeout=120)
            result = resp.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"vLLM Local Error: {e}")
            # Try to see if it's the model name issue
            logger.info("Retrying with 'default' model name...")
            payload["model"] = "default"
            try:
                 resp = requests.post(f"{self._base_url}/chat/completions", json=payload, timeout=60)
                 return resp.json()["choices"][0]["message"]["content"]
            except:
                 return f"Error Local LLM: {str(e)}"

    def _generate_cloudflare(self, prompt: str, temperature: float) -> str:
        account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        api_key = os.environ.get("LITELLM_API_KEY")
        pure_model_id = self._model_id.replace("cloudflare/", "")
        
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{pure_model_id}"
        payload = {"messages": [{"role": "user", "content": prompt}], "temperature": temperature}
        try:
            resp = requests.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=120)
            res_json = resp.json()
            if res_json.get("success"):
                 return res_json["result"]["response"]
            return f"Cloudflare Error: {res_json.get('errors')}"
        except Exception as e:
            return f"Error Cloudflare: {str(e)}"
