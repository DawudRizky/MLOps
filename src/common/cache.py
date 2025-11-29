"""
Redis cache client for caching and deduplication.
"""
import redis
import json
from typing import Optional, Any
from datetime import timedelta
from .config import get_config
from .logging import get_logger
from .metrics import metrics

logger = get_logger(__name__)


class RedisCache:
    """Redis client for caching operations."""
    
    def __init__(self):
        """Initialize Redis client."""
        config = get_config()
        self.client = redis.from_url(
            config.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        self.config = config
        logger.info(f"Redis client initialized: {config.redis_host}:{config.redis_port}")
    
    def ping(self) -> bool:
        """
        Check if Redis is accessible.
        
        Returns:
            True if Redis responds to ping
        """
        try:
            return self.client.ping()
        except redis.RedisError as e:
            logger.error(f"Redis ping failed: {e}")
            metrics.record_error("redis_error", "ping")
            return False
    
    def get(self, key: str) -> Optional[str]:
        """
        Get a value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found
        """
        try:
            value = self.client.get(key)
            if value:
                logger.debug(f"Cache hit: {key}")
            else:
                logger.debug(f"Cache miss: {key}")
            return value
        except redis.RedisError as e:
            logger.error(f"Failed to get key {key}: {e}")
            metrics.record_error("redis_error", "get")
            return None
    
    def set(self, key: str, value: str, ttl: Optional[timedelta] = None) -> bool:
        """
        Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live (optional)
        
        Returns:
            True if successful
        """
        try:
            if ttl:
                self.client.setex(key, ttl, value)
            else:
                self.client.set(key, value)
            logger.debug(f"Cached: {key}")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to set key {key}: {e}")
            metrics.record_error("redis_error", "set")
            return False
    
    def get_json(self, key: str) -> Optional[dict]:
        """
        Get JSON value from cache.
        
        Args:
            key: Cache key
        
        Returns:
            Parsed JSON dict or None
        """
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON for key {key}: {e}")
                metrics.record_error("json_error", "get_json")
        return None
    
    def set_json(self, key: str, value: dict, ttl: Optional[timedelta] = None) -> bool:
        """
        Set JSON value in cache.
        
        Args:
            key: Cache key
            value: Dictionary to cache as JSON
            ttl: Time to live (optional)
        
        Returns:
            True if successful
        """
        try:
            json_str = json.dumps(value)
            return self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize JSON for key {key}: {e}")
            metrics.record_error("json_error", "set_json")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete a key from cache.
        
        Args:
            key: Cache key to delete
        
        Returns:
            True if key was deleted
        """
        try:
            result = self.client.delete(key)
            logger.debug(f"Deleted key: {key}")
            return bool(result)
        except redis.RedisError as e:
            logger.error(f"Failed to delete key {key}: {e}")
            metrics.record_error("redis_error", "delete")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.
        
        Args:
            key: Cache key
        
        Returns:
            True if key exists
        """
        try:
            return bool(self.client.exists(key))
        except redis.RedisError as e:
            logger.error(f"Failed to check existence of key {key}: {e}")
            metrics.record_error("redis_error", "exists")
            return False
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter.
        
        Args:
            key: Counter key
            amount: Amount to increment by
        
        Returns:
            New value or None if failed
        """
        try:
            return self.client.incrby(key, amount)
        except redis.RedisError as e:
            logger.error(f"Failed to increment key {key}: {e}")
            metrics.record_error("redis_error", "increment")
            return None
    
    def set_add(self, key: str, *values: str) -> bool:
        """
        Add values to a set.
        
        Args:
            key: Set key
            values: Values to add
        
        Returns:
            True if successful
        """
        try:
            self.client.sadd(key, *values)
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to add to set {key}: {e}")
            metrics.record_error("redis_error", "set_add")
            return False
    
    def set_is_member(self, key: str, value: str) -> bool:
        """
        Check if value is in set.
        
        Args:
            key: Set key
            value: Value to check
        
        Returns:
            True if value is in set
        """
        try:
            return bool(self.client.sismember(key, value))
        except redis.RedisError as e:
            logger.error(f"Failed to check set membership {key}: {e}")
            metrics.record_error("redis_error", "set_is_member")
            return False
    
    def set_members(self, key: str) -> set:
        """
        Get all members of a set.
        
        Args:
            key: Set key
        
        Returns:
            Set of members
        """
        try:
            return self.client.smembers(key)
        except redis.RedisError as e:
            logger.error(f"Failed to get set members {key}: {e}")
            metrics.record_error("redis_error", "set_members")
            return set()
    
    def expire(self, key: str, ttl: timedelta) -> bool:
        """
        Set expiration time for a key.
        
        Args:
            key: Cache key
            ttl: Time to live
        
        Returns:
            True if successful
        """
        try:
            return bool(self.client.expire(key, ttl))
        except redis.RedisError as e:
            logger.error(f"Failed to set expiration for key {key}: {e}")
            metrics.record_error("redis_error", "expire")
            return False
    
    def flush_db(self) -> bool:
        """
        Clear all keys in the current database.
        WARNING: This deletes all data!
        
        Returns:
            True if successful
        """
        try:
            self.client.flushdb()
            logger.warning("Flushed Redis database")
            return True
        except redis.RedisError as e:
            logger.error(f"Failed to flush database: {e}")
            metrics.record_error("redis_error", "flush_db")
            return False
