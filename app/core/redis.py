import redis
from redis.connection import ConnectionPool
from typing import Optional
import json
from app.core.config import settings

class RedisClient:
    """Redis client for caching and session management"""

    _client: Optional[redis.Redis] = None
    _pool: Optional[ConnectionPool] = None
    _is_available: bool = False

    @classmethod
    def get_client(cls) -> Optional[redis.Redis]:
        """Get or create Redis client instance with connection pooling"""
        if cls._client is None:
            try:
                # Use connection pool for better performance with AWS ElastiCache
                cls._pool = ConnectionPool(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                    db=settings.REDIS_DB,
                    decode_responses=True,
                    socket_connect_timeout=2,  # Reduced from 5s
                    socket_timeout=2,          # Reduced from 5s
                    retry_on_timeout=True,
                    max_connections=20,        # Connection pool size
                    health_check_interval=15,  # More frequent health checks
                )

                cls._client = redis.Redis(connection_pool=cls._pool)

                # Test connection
                cls._client.ping()
                cls._is_available = True
                print("✅ Redis connected successfully")
            except Exception as e:
                print(f"❌ Redis connection failed: {e}")
                cls._client = None
                cls._pool = None
                cls._is_available = False
                raise

        return cls._client

    @classmethod
    def is_available(cls) -> bool:
        """Check if Redis is available"""
        return cls._is_available

    @classmethod
    def close(cls):
        """Close Redis connection"""
        if cls._client:
            cls._client.close()
            cls._client = None
        if cls._pool:
            cls._pool.disconnect()
            cls._pool = None
        print("🔌 Redis connection closed")


def get_redis() -> Optional[redis.Redis]:
    """Dependency to get Redis client"""
    try:
        return RedisClient.get_client()
    except Exception:
        return None


# Cache key generators
class CacheKeys:
    """Redis cache key patterns"""

    @staticmethod
    def otp(user_id: str) -> str:
        """OTP cache key"""
        return f"otp:{user_id}"

    @staticmethod
    def otp_attempts(user_id: str) -> str:
        """OTP attempts counter key"""
        return f"otp:attempts:{user_id}"

    @staticmethod
    def user_verification(user_id: str) -> str:
        """User verification status key"""
        return f"user:verification:{user_id}"

    @staticmethod
    def pending_video(user_id: str) -> str:
        """Pending video job key"""
        return f"video:pending:{user_id}"

    @staticmethod
    def rate_limit(identifier: str, action: str) -> str:
        """Rate limiting key"""
        return f"rate_limit:{action}:{identifier}"


# Redis operations helper
class RedisOps:
    """Common Redis operations"""

    @staticmethod
    def set_with_expiry(key: str, value: str, expire_seconds: int) -> bool:
        """Set a key with expiration time"""
        client = get_redis()
        if not client:
            return False
        return client.setex(key, expire_seconds, value)

    @staticmethod
    def get(key: str) -> Optional[str]:
        """Get value by key"""
        client = get_redis()
        if not client:
            return None
        return client.get(key)

    @staticmethod
    def delete(key: str) -> int:
        """Delete a key"""
        client = get_redis()
        if not client:
            return 0
        return client.delete(key)

    @staticmethod
    def exists(key: str) -> bool:
        """Check if key exists"""
        client = get_redis()
        if not client:
            return False
        return client.exists(key) > 0

    @staticmethod
    def incr(key: str) -> int:
        """Increment counter"""
        client = get_redis()
        if not client:
            return 0
        return client.incr(key)

    @staticmethod
    def expire(key: str, seconds: int) -> bool:
        """Set expiration on existing key"""
        client = get_redis()
        if not client:
            return False
        return client.expire(key, seconds)

    @staticmethod
    def ttl(key: str) -> int:
        """Get time to live for key"""
        client = get_redis()
        if not client:
            return -1
        return client.ttl(key)


class RateLimiter:
    """Rate limiting using Redis"""

    @staticmethod
    def check_rate_limit(
        identifier: str,
        action: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check if request is within rate limit.
        Uses pipeline for single round-trip to Redis (optimized for AWS).

        Returns:
            (is_allowed, remaining_requests)
            - is_allowed: True if request should be allowed
            - remaining_requests: How many requests left in window
        """
        if not RedisClient.is_available():
            # If Redis not available, allow request (fallback)
            return True, max_requests

        key = CacheKeys.rate_limit(identifier, action)
        client = get_redis()

        if not client:
            return True, max_requests

        try:
            # Use pipeline for single round-trip (faster for AWS)
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            results = pipe.execute()

            current = results[0]  # Result of INCR
            remaining = max(0, max_requests - current)
            is_allowed = current <= max_requests

            return is_allowed, remaining
        except Exception:
            # On error, allow request
            return True, max_requests

    @staticmethod
    def get_remaining_time(identifier: str, action: str) -> int:
        """Get seconds until rate limit resets"""
        key = CacheKeys.rate_limit(identifier, action)
        return max(0, RedisOps.ttl(key))

    @staticmethod
    def check_global_limit(
        action: str,
        max_requests: int = 1000,
        window_seconds: int = 60
    ) -> tuple[bool, int]:
        """
        Global rate limit for entire API (all users combined).
        Use this to protect server from overload.

        Example: max 1000 requests/minute for video_submit
        """
        return RateLimiter.check_rate_limit(
            identifier="global",
            action=action,
            max_requests=max_requests,
            window_seconds=window_seconds
        )


class Cache:
    """Caching helpers"""

    @staticmethod
    def get_pending_video(user_id: str) -> Optional[str]:
        """Get cached pending video job_id for user"""
        return RedisOps.get(CacheKeys.pending_video(user_id))

    @staticmethod
    def set_pending_video(user_id: str, job_id: str, ttl: int = 600) -> bool:
        """Cache pending video job_id (default 10 min)"""
        return RedisOps.set_with_expiry(
            CacheKeys.pending_video(user_id),
            job_id,
            ttl
        )

    @staticmethod
    def clear_pending_video(user_id: str) -> int:
        """Clear pending video cache when job completes"""
        return RedisOps.delete(CacheKeys.pending_video(user_id))

    @staticmethod
    def get_user_verification(user_id: str) -> Optional[str]:
        """Get cached verification status"""
        return RedisOps.get(CacheKeys.user_verification(user_id))

    @staticmethod
    def set_user_verification(user_id: str, is_verified: bool, ttl: int = 3600) -> bool:
        """Cache user verification status (default 1 hour)"""
        return RedisOps.set_with_expiry(
            CacheKeys.user_verification(user_id),
            "1" if is_verified else "0",
            ttl
        )


class GroqKeyManager:
    """
    Manages multiple Groq API keys with load balancing and automatic failover.

    Features:
    - Round-robin distribution across keys
    - Per-key rate limiting (100 RPM each)
    - Automatic failover when key hits limit
    - 3x capacity with 3 keys (300 RPM total)
    """

    RPM_LIMIT_PER_KEY = 100  # Requests per minute per key
    WINDOW_SECONDS = 60

    @staticmethod
    def _get_key_rate_limit_key(key_index: int) -> str:
        """Redis key for tracking rate limit per API key"""
        return f"groq:rate_limit:key_{key_index}"

    @staticmethod
    def _get_round_robin_key() -> str:
        """Redis key for round-robin counter"""
        return "groq:round_robin_counter"

    @classmethod
    def get_available_key(cls) -> Optional[tuple[str, int]]:
        """
        Get an available Groq API key using round-robin with failover.

        Returns:
            (api_key, key_index) if available, None if all keys exhausted
        """
        keys = settings.groq_api_keys_list
        if not keys:
            return None

        num_keys = len(keys)
        client = get_redis()

        if not client:
            # Redis unavailable, return first key
            return keys[0], 0

        try:
            # Get current round-robin position
            counter = client.incr(cls._get_round_robin_key())
            client.expire(cls._get_round_robin_key(), 3600)  # Reset hourly

            # Try each key starting from round-robin position
            for i in range(num_keys):
                key_index = (counter + i - 1) % num_keys
                rate_key = cls._get_key_rate_limit_key(key_index)

                # Check if this key has capacity
                current = client.get(rate_key)
                current_count = int(current) if current else 0

                if current_count < cls.RPM_LIMIT_PER_KEY:
                    # This key has capacity, increment and use it
                    pipe = client.pipeline()
                    pipe.incr(rate_key)
                    pipe.expire(rate_key, cls.WINDOW_SECONDS)
                    pipe.execute()

                    print(f"🔑 Using Groq key #{key_index + 1} ({current_count + 1}/{cls.RPM_LIMIT_PER_KEY})")
                    return keys[key_index], key_index

            # All keys exhausted
            print("⚠️ All Groq API keys at rate limit")
            return None

        except Exception as e:
            print(f"❌ GroqKeyManager error: {e}")
            return keys[0], 0  # Fallback to first key

    @classmethod
    def get_total_remaining(cls) -> int:
        """Get total remaining requests across all keys"""
        keys = settings.groq_api_keys_list
        client = get_redis()

        if not client:
            return cls.RPM_LIMIT_PER_KEY * len(keys)

        total_remaining = 0
        try:
            for i in range(len(keys)):
                rate_key = cls._get_key_rate_limit_key(i)
                current = client.get(rate_key)
                current_count = int(current) if current else 0
                total_remaining += max(0, cls.RPM_LIMIT_PER_KEY - current_count)
        except Exception:
            total_remaining = cls.RPM_LIMIT_PER_KEY * len(keys)

        return total_remaining

    @classmethod
    def get_retry_after(cls) -> int:
        """Get seconds until at least one key becomes available"""
        keys = settings.groq_api_keys_list
        client = get_redis()

        if not client or not keys:
            return 60

        min_ttl = 60
        try:
            for i in range(len(keys)):
                rate_key = cls._get_key_rate_limit_key(i)
                ttl = client.ttl(rate_key)
                if ttl > 0:
                    min_ttl = min(min_ttl, ttl)
        except Exception:
            pass

        return max(1, min_ttl)


class PhotoValidationQueue:
    """
    Queue system for handling burst traffic in photo validation.

    When all Groq API keys are exhausted, requests are queued
    and processed when capacity becomes available.
    """

    QUEUE_KEY = "photo_validation:queue"
    RESULT_PREFIX = "photo_validation:result:"
    RESULT_TTL = 300  # 5 minutes
    MAX_QUEUE_SIZE = 500  # Max queued requests

    @classmethod
    def enqueue(cls, validation_id: str, image_data: str) -> bool:
        """
        Add a photo validation request to the queue.

        Args:
            validation_id: Unique ID for this validation request
            image_data: Base64 encoded image data URL

        Returns:
            True if queued successfully
        """
        client = get_redis()
        if not client:
            return False

        try:
            # Check queue size
            queue_size = client.llen(cls.QUEUE_KEY)
            if queue_size >= cls.MAX_QUEUE_SIZE:
                print(f"⚠️ Queue full ({queue_size}/{cls.MAX_QUEUE_SIZE})")
                return False

            # Add to queue
            item = json.dumps({
                "validation_id": validation_id,
                "image_data": image_data,
                "queued_at": str(get_redis().time()[0])  # Unix timestamp
            })
            client.rpush(cls.QUEUE_KEY, item)

            # Set initial status
            cls.set_status(validation_id, "queued", position=queue_size + 1)

            print(f"📥 Queued validation {validation_id} (position: {queue_size + 1})")
            return True

        except Exception as e:
            print(f"❌ Queue error: {e}")
            return False

    @classmethod
    def dequeue(cls) -> Optional[dict]:
        """Get next item from queue"""
        client = get_redis()
        if not client:
            return None

        try:
            item = client.lpop(cls.QUEUE_KEY)
            if item:
                return json.loads(item)
            return None
        except Exception:
            return None

    @classmethod
    def set_status(cls, validation_id: str, status: str, **kwargs) -> bool:
        """Set validation status with optional data"""
        client = get_redis()
        if not client:
            return False

        try:
            data = {"status": status, **kwargs}
            key = f"{cls.RESULT_PREFIX}{validation_id}"
            client.setex(key, cls.RESULT_TTL, json.dumps(data))
            return True
        except Exception:
            return False

    @classmethod
    def get_status(cls, validation_id: str) -> Optional[dict]:
        """Get validation status and result"""
        client = get_redis()
        if not client:
            return None

        try:
            key = f"{cls.RESULT_PREFIX}{validation_id}"
            data = client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None

    @classmethod
    def set_result(cls, validation_id: str, result: dict) -> bool:
        """Store validation result"""
        return cls.set_status(validation_id, "completed", result=result)

    @classmethod
    def get_queue_size(cls) -> int:
        """Get current queue size"""
        client = get_redis()
        if not client:
            return 0

        try:
            return client.llen(cls.QUEUE_KEY)
        except Exception:
            return 0
