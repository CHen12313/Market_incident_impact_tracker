"""Persist resolved ticker symbols on disk so repeat lookups skip the network."""
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from Pipeline.utils.event_files import atomic_write

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE_PATH = MODULE_DIR / "symbol_cache.json"


class SymbolCache:
    """Loads `symbol_cache.json` on construction and atomically rewrites it on every `set()`."""

    def __init__(self, cache_path: Path = DEFAULT_CACHE_PATH):
        self.cache_path = cache_path
        self.entries: Dict[str, Any] = {}
        try:
            if self.cache_path.exists():
                self.entries = json.loads(self.cache_path.read_text())
        except Exception:
            self.entries = {}

    def has(self, cache_key: str) -> bool:
        return cache_key in self.entries

    def get(self, cache_key: str) -> Optional[str]:
        """Returns the cached symbol. May legitimately be None if a prior lookup found nothing."""
        cached = self.entries.get(cache_key)
        if isinstance(cached, str):
            return cached
        if isinstance(cached, dict):
            return cached.get("symbol")
        return None

    def set(self, cache_key: str, symbol: Optional[str]) -> None:
        self.entries[cache_key] = symbol or {"symbol": None, "as_of": int(time.time())}
        self._save()

    def _save(self) -> None:
        atomic_write(self.cache_path, lambda file: json.dump(self.entries, file, ensure_ascii=False, indent=2))
