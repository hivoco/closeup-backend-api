"""
OTP Service with Redis caching
Handles OTP generation, validation, and caching
"""

import json
import logging
from datetime import timedelta
from typing import Optional, Dict, Any
from uuid import uuid4

from app.core.config import settings
from app.core.otp import generate_otp, hash_otp, send_otp
from app.core.redis import get_redis, CacheKeys, RedisOps
from app.core.timezone import get_ist_now
from app.models.user_otp import UserOTP
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OTPService:
    """Service for OTP operations with Redis caching"""

    @staticmethod
    def generate_and_cache_otp(
        user_id: str,
        mobile_number: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Generate OTP and cache it in Redis + Database

        Returns:
            dict with otp (for testing) and expiry info
        """
        # Check if OTP already exists in Redis (not expired)
        cache_key = CacheKeys.otp(user_id)
        cached_otp_data = RedisOps.get(cache_key)

        if cached_otp_data:
            # OTP still valid in cache
            ttl = RedisOps.ttl(cache_key)
            raise ValueError(f"OTP already sent. Please wait {ttl} seconds before requesting a new one.")

        # Generate new OTP
        otp = generate_otp()
        otp_hash = hash_otp(otp)

        # Calculate expiry
        expiry_seconds = settings.OTP_EXPIRY_MINUTES * 60
        expires_at = get_ist_now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

        # Save to Redis (faster access)
        otp_data = {
            "otp_hash": otp_hash,
            "mobile_number": mobile_number,
            "created_at": get_ist_now().isoformat(),
            "expires_at": expires_at.isoformat()
        }
        RedisOps.set_with_expiry(cache_key, json.dumps(otp_data), expiry_seconds)

        # Also save to database (persistent backup)
        db_otp = UserOTP(
            id=str(uuid4()),
            user_id=user_id,
            otp_hash=otp_hash,
            expires_at=expires_at,
            attempts=0,
            is_used=False,
        )
        db.add(db_otp)
        db.commit()

        # Send OTP
        try:
            send_otp(mobile_number, otp)
            logger.info("OTP sent to %s", mobile_number)
        except Exception as e:
            logger.warning("Failed to send OTP: %s", str(e))

        return {
            "otp": otp,  # For testing - remove in production
            "expires_in_seconds": expiry_seconds,
            "expires_at": expires_at.isoformat()
        }

    @staticmethod
    def verify_otp(
        user_id: str,
        otp_input: str,
        db: Session
    ) -> bool:
        """
        Verify OTP from Redis cache (fast) or Database (fallback)

        Returns:
            True if valid, False otherwise
        """
        # Try Redis first (fastest)
        cache_key = CacheKeys.otp(user_id)
        cached_otp_data = RedisOps.get(cache_key)

        otp_hash_input = hash_otp(otp_input)

        if cached_otp_data:
            # Found in cache
            otp_data = json.loads(cached_otp_data)

            if otp_data["otp_hash"] == otp_hash_input:
                # Valid OTP - delete from cache
                RedisOps.delete(cache_key)

                # Mark as used in database
                db.query(UserOTP).filter(
                    UserOTP.user_id == user_id,
                    UserOTP.otp_hash == otp_hash_input,
                    UserOTP.is_used == False
                ).update({
                    "is_used": True,
                    "used_at": get_ist_now()
                })
                db.commit()

                return True
            else:
                # Wrong OTP - track attempts
                OTPService._track_failed_attempt(user_id)
                return False

        # Fallback to database (if Redis fails or OTP expired in Redis but not in DB)
        db_otp = (
            db.query(UserOTP)
            .filter(
                UserOTP.user_id == user_id,
                UserOTP.is_used == False,
                UserOTP.expires_at > get_ist_now(),
            )
            .order_by(UserOTP.created_at.desc())
            .first()
        )

        if db_otp and db_otp.otp_hash == otp_hash_input:
            # Valid OTP
            db_otp.is_used = True
            db_otp.used_at = get_ist_now()
            db.commit()

            # Delete from cache if exists
            RedisOps.delete(cache_key)

            return True

        # Invalid or expired OTP
        OTPService._track_failed_attempt(user_id)
        return False

    @staticmethod
    def get_remaining_time(user_id: str) -> Optional[int]:
        """
        Get remaining time in seconds for current OTP

        Returns:
            Seconds remaining or None if no valid OTP
        """
        cache_key = CacheKeys.otp(user_id)
        return RedisOps.ttl(cache_key) if RedisOps.exists(cache_key) else None

    @staticmethod
    def _track_failed_attempt(user_id: str) -> int:
        """
        Track failed OTP attempts in Redis

        Returns:
            Current attempt count
        """
        attempts_key = CacheKeys.otp_attempts(user_id)
        attempts = RedisOps.incr(attempts_key)

        # Set expiry for attempts counter (reset after 1 hour)
        if attempts == 1:
            RedisOps.expire(attempts_key, 3600)

        # Block user if too many attempts
        if attempts >= 5:
            logger.warning("User %s has %s failed OTP attempts", user_id, attempts)
            # TODO: Implement blocking logic

        return attempts

    @staticmethod
    def get_failed_attempts(user_id: str) -> int:
        """Get number of failed OTP attempts"""
        attempts_key = CacheKeys.otp_attempts(user_id)
        attempts = RedisOps.get(attempts_key)
        return int(attempts) if attempts else 0

    @staticmethod
    def clear_failed_attempts(user_id: str):
        """Clear failed attempts counter"""
        attempts_key = CacheKeys.otp_attempts(user_id)
        RedisOps.delete(attempts_key)


class CacheService:
    """General caching service using Redis"""

    @staticmethod
    def cache_user_verification(user_id: str, is_verified: bool, ttl: int = 3600):
        """Cache user verification status (1 hour default)"""
        cache_key = CacheKeys.user_verification(user_id)
        RedisOps.set_with_expiry(cache_key, str(is_verified), ttl)

    @staticmethod
    def get_cached_verification(user_id: str) -> Optional[bool]:
        """Get cached verification status"""
        cache_key = CacheKeys.user_verification(user_id)
        value = RedisOps.get(cache_key)
        if value:
            return value.lower() == "true"
        return None

    @staticmethod
    def cache_pending_video(user_id: str, job_id: int, ttl: int = 1800):
        """Cache pending video job info (30 minutes default)"""
        cache_key = CacheKeys.pending_video(user_id)
        RedisOps.set_with_expiry(cache_key, str(job_id), ttl)

    @staticmethod
    def get_cached_pending_video(user_id: str) -> Optional[int]:
        """Get cached pending video job ID"""
        cache_key = CacheKeys.pending_video(user_id)
        value = RedisOps.get(cache_key)
        return int(value) if value else None

    @staticmethod
    def clear_pending_video(user_id: str):
        """Clear pending video cache"""
        cache_key = CacheKeys.pending_video(user_id)
        RedisOps.delete(cache_key)

    @staticmethod
    def check_rate_limit(identifier: str, action: str, max_requests: int, window_seconds: int) -> bool:
        """
        Check rate limiting

        Args:
            identifier: User ID, IP, etc.
            action: Action name (e.g., 'otp_request', 'video_submit')
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds

        Returns:
            True if allowed, False if rate limited
        """
        cache_key = CacheKeys.rate_limit(identifier, action)

        current_count = RedisOps.get(cache_key)

        if current_count is None:
            # First request in window
            RedisOps.set_with_expiry(cache_key, "1", window_seconds)
            return True

        count = int(current_count)

        if count >= max_requests:
            # Rate limit exceeded
            return False

        # Increment counter
        RedisOps.incr(cache_key)
        return True
