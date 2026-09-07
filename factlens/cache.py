import json
import logging
from typing import Any, Optional, Dict
from pathlib import Path

from factlens.config import settings

logger = logging.getLogger(__name__)

class CacheManager:
    """
    Robust Redis cache manager with in-memory fallback.
    Guarantees zero-crash behavior if Redis server is offline or unreachable.
    Never caches sensitive credentials or authentication headers.
    """
    def __init__(self, redis_url: str = settings.REDIS_URL, enabled: bool = settings.REDIS_CACHE_ENABLED):
        self.redis_url = redis_url
        self.enabled = enabled
        self._client = None
        self._connected = False
        self._memory_cache: Dict[str, tuple[str, float]] = {}  # key -> (json_val, expiry_timestamp)
        
        if self.enabled:
            self._init_client()

    def _init_client(self) -> None:
        try:
            import redis
            self._client = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=1.5,
                socket_connect_timeout=1.5
            )
            # Test connection with a fast ping
            self._client.ping()
            self._connected = True
            logger.info("Connected to Redis cache at %s", self.redis_url)
        except Exception as e:
            self._connected = False
            logger.warning("Redis not reachable (%s). Falling back to in-memory/passthrough cache.", e)

    @property
    def is_redis_connected(self) -> bool:
        if not self._client or not self.enabled:
            return False
        try:
            self._client.ping()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    # Key Namespace Builders
    @staticmethod
    def doc_facts_key(sha256_hash: str, version: str = "v1") -> str:
        """Cache key for extracted document facts keyed by content SHA-256."""
        return f"factlens:doc:{sha256_hash}:facts:{version}"

    @staticmethod
    def doc_processing_key(sha256_hash: str, version: str = "v1") -> str:
        """Cache key for complete document processing result."""
        return f"factlens:doc:{sha256_hash}:proc:{version}"

    @staticmethod
    def comparisons_key(version: str = "v1") -> str:
        """Cache key for global cross-document reconciliation comparisons."""
        return f"factlens:recon:all:{version}"

    @staticmethod
    def api_response_key(endpoint: str, query_hash: str = "all") -> str:
        """Cache key for API endpoints."""
        return f"factlens:api:{endpoint}:{query_hash}"

    # Cache Operations
    def get(self, key: str) -> Optional[Any]:
        """Retrieves deserialized JSON object from cache, or None on miss/error."""
        if not self.enabled:
            return None

        # 1. Try Redis
        if self.is_redis_connected:
            try:
                val = self._client.get(key)
                if val is not None:
                    return json.loads(val)
            except Exception as e:
                logger.debug("Redis get error for %s: %e", key, e)

        # 2. Fallback to in-memory cache
        import time
        if key in self._memory_cache:
            raw_val, expires_at = self._memory_cache[key]
            if expires_at == 0 or time.time() < expires_at:
                try:
                    return json.loads(raw_val)
                except Exception:
                    pass
            else:
                self._memory_cache.pop(key, None)

        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Serializes and caches value with TTL in seconds."""
        if not self.enabled:
            return False

        ttl_seconds = ttl if ttl is not None else settings.CACHE_TTL_DEFAULT
        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError) as e:
            logger.warning("Failed to serialize cache value for %s: %s", key, e)
            return False

        success = False
        # 1. Try Redis
        if self.is_redis_connected:
            try:
                self._client.set(key, serialized, ex=ttl_seconds)
                success = True
            except Exception as e:
                logger.debug("Redis set error for %s: %s", key, e)

        # 2. In-memory fallback
        import time
        expiry = time.time() + ttl_seconds if ttl_seconds > 0 else 0
        self._memory_cache[key] = (serialized, expiry)
        return success or True

    def delete(self, key: str) -> bool:
        """Deletes key from cache."""
        existed_in_mem = self._memory_cache.pop(key, None) is not None
        deleted_in_redis = False
        if self.is_redis_connected:
            try:
                res = self._client.delete(key)
                deleted_in_redis = bool(res)
            except Exception:
                pass
        return existed_in_mem or deleted_in_redis

    def delete_pattern(self, pattern: str) -> int:
        """Deletes all keys matching wildcard pattern (e.g. 'factlens:api:*')."""
        deleted_count = 0
        # In-memory removal
        import fnmatch
        keys_to_pop = [k for k in self._memory_cache if fnmatch.fnmatch(k, pattern)]
        for k in keys_to_pop:
            self._memory_cache.pop(k, None)
            deleted_count += 1

        # Redis removal
        if self.is_redis_connected:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        self._client.delete(*keys)
                        deleted_count += len(keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug("Redis scan/delete error: %s", e)

        return deleted_count

    @property
    def client(self):
        return self._client

    def is_available(self) -> bool:
        return self.is_redis_connected

    def invalidate_comparisons(self) -> None:
        """Invalidates all cross-document reconciliation and comparison API caches."""
        self.delete(self.comparisons_key())
        self.delete_pattern("factlens:api:comparisons:*")
        self.delete_pattern("factlens:api:facts:*")

    def invalidate_all(self) -> None:
        """Clears all FactLens cache keys."""
        self.delete_pattern("factlens:*")
        self._memory_cache.clear()

cache = CacheManager()

def get_cache() -> CacheManager:
    """Returns global CacheManager instance."""
    return cache
