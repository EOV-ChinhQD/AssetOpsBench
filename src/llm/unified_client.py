import logging
import requests
import json
import os
from typing import List, Dict, Any, Optional
from src.config.settings import settings
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class UnifiedLLMClient:
    def __init__(self, model_id: Optional[str] = None):
        self.model_id = model_id or settings.LLM_MODEL_NAME
        self.provider = settings.LLM_PROVIDER
        self.api_key = settings.LLM_API_KEY
        
        # Log basic info (masked key)
        logger.info(f"LLM_CLIENT: provider={self.provider}, model={self.model_id}")

    def generate(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        if self.provider == "GOOGLE":
            return self._call_google_gemini(messages, temperature)
        elif self.provider == "CLOUDFLARE" or self.model_id.startswith("@cf/"):
            return self._call_cloudflare(messages, temperature)
        else:
            return self._call_openai_compatible(messages, temperature)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_google_gemini(self, messages: List[Dict[str, str]], temperature: float) -> str:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            
            # Simple conversion to flat prompt (Gemma/Gemini prompt-tuning style)
            prompt = ""
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                prompt += f"{role.upper()}: {content}\n\n"
            
            # Clean model name if it doesn't have prefix
            m_name = self.model_id
            if not m_name.startswith("models/"):
                m_name = f"models/{m_name}"

            model = genai.GenerativeModel(m_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=temperature)
            )
            
            if not response.text:
                logger.warning(f"Google Model {m_name} returned empty text.")
                return ""
                
            return response.text
        except Exception as e:
            logger.error(f"Google Gemini/Gemma Error: {str(e)}")
            raise

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
            # Note: settings.LLM_BASE_URL is handled by Computed Properties in Settings class
            resp = requests.post(f"{settings.LLM_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=120)
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
