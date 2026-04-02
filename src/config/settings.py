import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class Settings:
    # Database
    DB_URL: str = os.getenv("HANOI_WATER_DB_URL", "postgresql://user:pass@localhost:5433/hanoiwatertb")
    
    # Storage (MinIO)
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "admin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "password123")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "hanoi-water-images")
    IMAGE_BASE_URL: str = os.getenv("IMAGE_STORAGE_BASE_URL", "http://localhost:9000/hanoi-water-images")

    # LLM Switcher
    # Options: "GOOGLE", "GROQ", "FASTWORK", "CLOUDFLARE", "LOCAL"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "GOOGLE")

    # 0. Google Gemini / Gemma
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_MODEL_NAME: str = os.getenv("GOOGLE_MODEL_NAME", "gemma-3-12b-it")

    # 1. FastWork (OpenAI Compatible)
    FW_API_KEY: str = os.getenv("LLM_API_KEY", "")
    FW_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://aiapi.fastwork.vn/llm/v1")
    FW_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3.5-9B")

    # 2. Groq (OpenAI Compatible)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_MODEL_NAME: str = os.getenv("GROQ_MODEL_NAME", "llama-3.1-8b-instant")

    # 3. Cloudflare Config
    CF_ACCOUNT_ID: Optional[str] = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    CF_API_KEY: Optional[str] = os.getenv("CLOUDFLARE_API_KEY")
    CF_MODEL_ID: str = os.getenv("CLOUDFLARE_MODEL_ID", "@cf/meta/llama-3.1-8b-instruct")

    # 4. Local LLM Config
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://localhost:8001/v1")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "Qwen2.5-Coder-7B-Instruct-AWQ")

    # Computed Properties for UnifiedLLMClient
    @property
    def LLM_API_KEY(self) -> str:
        if self.LLM_PROVIDER == "GOOGLE": return self.GOOGLE_API_KEY
        if self.LLM_PROVIDER == "GROQ": return self.GROQ_API_KEY
        if self.LLM_PROVIDER == "CLOUDFLARE": return self.CF_API_KEY or ""
        return self.FW_API_KEY

    @property
    def LLM_BASE_URL(self) -> str:
        if self.LLM_PROVIDER == "GROQ": return self.GROQ_BASE_URL
        if self.LLM_PROVIDER == "LOCAL": return self.LOCAL_LLM_URL
        return self.FW_BASE_URL

    @property
    def LLM_MODEL_NAME(self) -> str:
        if self.LLM_PROVIDER == "GOOGLE": return self.GOOGLE_MODEL_NAME
        if self.LLM_PROVIDER == "GROQ": return self.GROQ_MODEL_NAME
        if self.LLM_PROVIDER == "CLOUDFLARE": return self.CF_MODEL_ID
        if self.LLM_PROVIDER == "LOCAL": return self.LOCAL_LLM_MODEL
        return self.FW_MODEL_NAME

settings = Settings()
