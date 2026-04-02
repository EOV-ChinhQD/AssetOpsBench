import os
import json
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(os.getcwd(), "data", "dma_registry.json")

class GlobalDMARegistry:
    """Persistent DMA cache to avoid redundant lookups across sessions."""
    def __init__(self):
        self.cache: Dict[str, str] = {}
        self._load()

    def _load(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.info(f"GLOBAL_REGISTRY: Loaded {len(self.cache)} mappings.")
            except Exception as e:
                logger.error(f"GLOBAL_REGISTRY: Load error: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"GLOBAL_REGISTRY: Save error: {e}")

    def get(self, query: str) -> Optional[str]:
        return self.cache.get(query.upper())

    def update(self, query: str, dma_id: str):
        q_up = query.upper()
        if self.cache.get(q_up) != dma_id:
            logger.info(f"GLOBAL_REGISTRY: Updating {q_up} -> {dma_id}")
            self.cache[q_up] = dma_id
            # Also map the ID to itself if it's not there
            self.cache[dma_id.upper()] = dma_id
            self._save()

# Singleton instance
global_dma_registry = GlobalDMARegistry()
