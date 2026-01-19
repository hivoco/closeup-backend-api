import redis
from typing import Optional
from app.core.config import settings

class RedisClient:
    """Redis client for caching and session management"""

    _client: Optional[redis.Redis] = None
    _is_available: bool = False

    @classmethod
    def get_client(cls) -> Optional[redis.Redis]:
        """Get or create Redis client instance"""
        if cls._client is None:
            try:
                cls._client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                    db=settings.REDIS_DB,
                    decode_responses=True,  # Automatically decode bytes to strings
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )

                # Test connection
                cls._client.ping()
                cls._is_available = True
                print("✅ Redis connected successfully")
            except Exception as e:
                print(f"❌ Redis connection failed: {e}")
                cls._client = None
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

        Returns:
            (is_allowed, remaining_requests)
            - is_allowed: True if request should be allowed
            - remaining_requests: How many requests left in window
        """
        if not RedisClient.is_available():
            # If Redis not available, allow request (fallback)
            return True, max_requests

        key = CacheKeys.rate_limit(identifier, action)

        try:
            current = RedisOps.incr(key)

            # Set expiry on first request
            if current == 1:
                RedisOps.expire(key, window_seconds)

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
