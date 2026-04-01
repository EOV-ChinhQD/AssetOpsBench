import logging
import requests
import json
import os
from typing import List, Dict, Any, Optional
from src.config.settings import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class UnifiedLLMClient:
    """
    A unified client to handle OpenAI-compatible and Cloudflare APIs.
    """
    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id or settings.LLM_MODEL_NAME
        self.base_url = settings.LLM_BASE_URL
        self.api_key = settings.LLM_API_KEY

    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        """
        Generates a response using the configured provider.
        """
        if "cloudflare" in self.model_id.lower() or self.model_id.startswith("@cf/"):
            return self._call_cloudflare(messages, temperature)
        else:
            return self._call_openai_compatible(messages, temperature)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_openai_compatible(self, messages: List[Dict[str, str]], temperature: float) -> str:
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = requests.post(f"{self.base_url}/chat/completions", json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"OpenAI-Compatible Error: {e}")
            raise

    def _call_cloudflare(self, messages: List[Dict[str, str]], temperature: float) -> str:
        url = f"https://api.cloudflare.com/client/v4/accounts/{settings.CF_ACCOUNT_ID}/ai/run/{self.model_id.replace('cloudflare/', '')}"
        headers = {"Authorization": f"Bearer {settings.CF_API_KEY}"}
        try:
            resp = requests.post(url, headers=headers, json={"messages": messages, "temperature": temperature}, timeout=120)
            res_json = resp.json()
            if res_json.get("success"):
                return res_json["result"]["response"]
            raise Exception(f"Cloudflare Error: {res_json.get('errors')}")
        except Exception as e:
            logger.error(f"Cloudflare Error: {e}")
            raise
