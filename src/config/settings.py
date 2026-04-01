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

    # Primary LLM (FastWork / OpenAI Compatible)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://aiapi.fastwork.vn/llm/v1")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3-8B")

    # Cloudflare Config (Fallback)
    CF_ACCOUNT_ID: Optional[str] = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    CF_API_KEY: Optional[str] = os.getenv("CLOUDFLARE_API_KEY")
    CF_MODEL_ID: str = os.getenv("CLOUDFLARE_MODEL_ID", "@cf/qwen/qwen3-30b-a3b-fp8")

    # Local LLM Config (Fallback)
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://localhost:8001/v1")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "Qwen2.5-Coder-7B-Instruct-AWQ")

settings = Settings()
