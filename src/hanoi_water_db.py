import os
import logging
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Fallback to a local sqlite if no URL is provided, but aim for Postgres
DB_URL = os.getenv("HANOI_WATER_DB_URL", "sqlite:///./hanoi_water.db")

try:
    engine = create_engine(DB_URL)
    logger.info(f"Hanoi Water DB Engine initialized with: {DB_URL.split('@')[-1] if '@' in DB_URL else DB_URL}")
except Exception as e:
    logger.error(f"Failed to initialize DB engine: {e}")
    engine = None

def get_engine():
    return engine
