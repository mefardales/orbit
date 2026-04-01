"""Caching service with TTL, LRU eviction, and optional disk persistence."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry with value and metadata."""
    key: str
    value: Any
    created_at: float
    ttl: float
    access_count: int = 0
    last_accessed: float = 0.0

    @property
    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return (time.time() - self.created_at) > self.ttl


class CacheService:
    """Thread-safe caching service with TTL and LRU eviction."""

    def __init__(
        self,
        default_ttl: float = 3600.0,
        max_size: int = 1000,
        persist_dir: Optional[Path] = None,
    ):
        self._entries: Dict[str, CacheEntry] = {}
        self._access_order: list[str] = []
        self._lock = threading.RLock()
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.persist_dir = persist_dir
        self._hits = 0
        self._misses = 0

        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the cache. Returns default if missing or expired."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return default
            if entry.is_expired:
                self._remove(key)
                self._misses += 1
                return default
            entry.access_count += 1
            entry.last_accessed = time.time()
            self._touch(key)
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Store a value in the cache with optional TTL override."""
        with self._lock:
            if key in self._entries:
                self._remove(key)

            if len(self._entries) >= self.max_size:
                self._evict()

            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl=ttl if ttl is not None else self.default_ttl,
                last_accessed=time.time(),
            )
            self._entries[key] = entry
            self._access_order.append(key)

            if self.persist_dir:
                self._persist_entry(entry)

    def invalidate(self, key: str) -> bool:
        """Remove a specific key from the cache. Returns True if it existed."""
        with self._lock:
            if key in self._entries:
                self._remove(key)
                return True
            return False

    def clear(self) -> int:
        """Clear all entries. Returns the number removed."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            self._access_order.clear()
            if self.persist_dir:
                for f in self.persist_dir.glob("*.cache"):
                    f.unlink(missing_ok=True)
            return count

    def has(self, key: str) -> bool:
        """Check if a non-expired key exists."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            if entry.is_expired:
                self._remove(key)
                return False
            return True

    def keys(self) -> list[str]:
        """Return all non-expired keys."""
        with self._lock:
            self._prune_expired()
            return list(self._entries.keys())

    def _touch(self, key: str) -> None:
        """Move key to end of access order (most recently used)."""
        try:
            self._access_order.remove(key)
        except ValueError:
            pass
        self._access_order.append(key)

    def _remove(self, key: str) -> None:
        """Remove entry by key."""
        self._entries.pop(key, None)
        try:
            self._access_order.remove(key)
        except ValueError:
            pass
        if self.persist_dir:
            path = self.persist_dir / f"{self._hash_key(key)}.cache"
            path.unlink(missing_ok=True)

    def _evict(self) -> None:
        """Evict the least recently used entry."""
        if self._access_order:
            lru_key = self._access_order[0]
            self._remove(lru_key)

    def _prune_expired(self) -> None:
        """Remove all expired entries."""
        expired = [k for k, v in self._entries.items() if v.is_expired]
        for k in expired:
            self._remove(k)

    def _hash_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _persist_entry(self, entry: CacheEntry) -> None:
        """Write a cache entry to disk."""
        if not self.persist_dir:
            return
        path = self.persist_dir / f"{self._hash_key(entry.key)}.cache"
        try:
            data = {
                "key": entry.key,
                "value": entry.value,
                "created_at": entry.created_at,
                "ttl": entry.ttl,
            }
            path.write_text(json.dumps(data))
        except (TypeError, OSError) as e:
            logger.warning("Failed to persist cache entry %s: %s", entry.key, e)

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": self.size,
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }
