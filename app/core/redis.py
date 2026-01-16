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
