"""Redis cache service for Company Intelligence data."""
import json
import logging
from datetime import datetime
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisCacheService:
    """
    Generic async Redis caching service.

    Provides get/set/delete operations with TTL support and automatic
    JSON serialization/deserialization.
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize cache service.

        Args:
            redis_client: Async Redis client from redis.asyncio
        """
        self.redis = redis_client

    async def get(self, key: str) -> dict | None:
        """
        Get cached data.

        Args:
            key: Cache key

        Returns:
            Cached data as dict, or None if not found/expired/invalid
        """
        try:
            value = await self.redis.get(key)
            if value is None:
                logger.debug(f"Cache miss: {key}")
                return None

            # Deserialize JSON
            data = json.loads(value)
            logger.debug(f"Cache hit: {key}")
            return data

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode cached JSON for key {key}: {e}")
            await self.delete(key)  # Clean up corrupted cache entry
            return None
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: dict | list,
        ttl_seconds: int
    ) -> bool:
        """
        Store data in cache with TTL.

        Args:
            key: Cache key
            value: Data to cache (dict or list)
            ttl_seconds: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            # Add fetched_at timestamp if not present
            if isinstance(value, dict) and "fetched_at" not in value:
                value["fetched_at"] = datetime.utcnow().isoformat()

            # Serialize to JSON
            serialized = json.dumps(value, default=str)

            # Store with TTL
            await self.redis.setex(key, ttl_seconds, serialized)
            logger.debug(f"Cache set: {key} (TTL: {ttl_seconds}s)")
            return True

        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete a cache key.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        try:
            result = await self.redis.delete(key)
            logger.debug(f"Cache delete: {key} (existed: {result > 0})")
            return result > 0
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if a cache key exists.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking cache key {key}: {e}")
            return False

    def make_key(self, *parts: str) -> str:
        """
        Build cache key from parts.

        Args:
            *parts: Key components

        Returns:
            Formatted cache key

        Example:
            make_key("ci", "AAPL", "overview") -> "ci:AAPL:overview"
        """
        return ":".join(str(p) for p in parts)
