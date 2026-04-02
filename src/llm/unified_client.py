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
        self.default_model_id = model_id or settings.LLM_MODEL_NAME
        self.default_provider = settings.LLM_PROVIDER
        
        # Priority order for fallback
        self.provider_priority = [self.default_provider, "GOOGLE", "CLOUDFLARE", "GROQ", "FASTWORK"]
        # Remove duplicates while preserving order
        self.provider_priority = list(dict.fromkeys(self.provider_priority))
        
        logger.info(f"LLM_CLIENT: Initialized with default_provider={self.default_provider}, priority={self.provider_priority}")

    async def generate(self, messages: List[Dict[str, str]], temperature: float = 0.1) -> str:
        """
        AI-ML ENGINEER WORKFLOW: Inference phase with auto-fallback resilience.
        """
        last_error = None
        
        for provider in self.provider_priority:
            try:
                logger.info(f"LLM_CLIENT: Attempting generation with provider={provider}")
                if provider == "GOOGLE":
                    return await self._call_google_gemini(messages, temperature)
                elif provider == "CLOUDFLARE":
                    return await self._call_cloudflare(messages, temperature)
                elif provider == "GROQ":
                    return await self._call_groq(messages, temperature)
                elif provider == "FASTWORK":
                    return await self._call_fastwork(messages, temperature)
                elif provider == "LOCAL":
                    return await self._call_local(messages, temperature)
            except Exception as e:
                logger.warning(f"LLM_CLIENT: Provider {provider} failed: {e}. Trying fallback...")
                last_error = e
                continue
        
        logger.error("LLM_CLIENT: All providers failed.")
        raise last_error or Exception("All LLM providers failed and no specific error was captured.")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def _call_google_gemini(self, messages: List[Dict[str, str]], temperature: float) -> str:
        api_key = settings.GOOGLE_API_KEY
        model_id = settings.GOOGLE_MODEL_NAME
        if not api_key: raise ValueError("GOOGLE_API_KEY not set")

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            
            prompt = ""
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                prompt += f"{role.upper()}: {content}\n\n"
            
            if not model_id.startswith("models/"):
                model_id = f"models/{model_id}"

            model = genai.GenerativeModel(model_id)
            # generate_content is blocking, should ideally be wrapped in run_in_executor but for now keep it simple
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=temperature)
            )
            return response.text or ""
        except Exception as e:
            logger.error(f"Google Error: {e}")
            raise

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def _call_cloudflare(self, messages: List[Dict[str, str]], temperature: float) -> str:
        account_id = settings.CF_ACCOUNT_ID
        api_key = settings.CF_API_KEY
        model_id = settings.CF_MODEL_ID
        if not account_id or not api_key: raise ValueError("Cloudflare credentials not set")

        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_id.replace('cloudflare/', '')}"
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.post(url, headers=headers, json={"messages": messages, "temperature": temperature}, timeout=60)
        res_json = resp.json()
        if res_json.get("success"):
            return res_json["result"]["response"]
        raise Exception(f"Cloudflare API Error: {res_json.get('errors')}")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def _call_groq(self, messages: List[Dict[str, str]], temperature: float) -> str:
        return await self._call_openai_compatible(
            settings.GROQ_BASE_URL, 
            settings.GROQ_API_KEY, 
            settings.GROQ_MODEL_NAME, 
            messages, 
            temperature
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def _call_fastwork(self, messages: List[Dict[str, str]], temperature: float) -> str:
        return await self._call_openai_compatible(
            settings.FW_BASE_URL, 
            settings.FW_API_KEY, 
            settings.FW_MODEL_NAME, 
            messages, 
            temperature
        )
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=5))
    async def _call_local(self, messages: List[Dict[str, str]], temperature: float) -> str:
        return await self._call_openai_compatible(
            settings.LOCAL_LLM_URL, 
            "", 
            settings.LOCAL_LLM_MODEL, 
            messages, 
            temperature
        )

    async def _call_openai_compatible(self, base_url: str, api_key: str, model: str, messages: List[Dict[str, str]], temperature: float) -> str:
        if not base_url: raise ValueError("LLM Base URL not set")
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048
        }
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
