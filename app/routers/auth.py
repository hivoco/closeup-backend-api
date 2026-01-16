import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import timedelta

from app.core.database import get_db
from app.core.security import hash_phone
from app.core.otp import generate_otp, hash_otp, send_otp
from app.core.timezone import get_ist_now
from app.core.config import settings

from app.models.user import User
from app.models.user_otp import UserOTP
from app.models.user_verification import UserVerification
from app.models.video_job import VideoJob

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.post("/verify-otp")
def verify_otp(payload: dict, db: Session = Depends(get_db)):
    # Validate payload
    if "mobile_number" not in payload or "otp" not in payload:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: mobile_number and otp"
        )

    phone_hash = hash_phone(payload["mobile_number"])
    otp_input = payload["otp"]

    user = db.query(User).filter(User.phone_hash == phone_hash).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please submit the form first."
        )

    otp = (
        db.query(UserOTP)
        .filter(
            UserOTP.user_id == user.id,
            UserOTP.is_used == False,
            UserOTP.expires_at > get_ist_now(),
        )
        .order_by(UserOTP.created_at.desc())
        .first()
    )

    if not otp:
        raise HTTPException(
            status_code=400,
            detail="No valid OTP found. Please request a new OTP."
        )

    if otp.otp_hash != hash_otp(otp_input):
        raise HTTPException(
            status_code=400,
            detail="Invalid OTP. Please check and try again."
        )

    otp.is_used = True
    otp.used_at = get_ist_now()

    verification = db.query(UserVerification).filter_by(user_id=user.id).first()

    if not verification:
        raise HTTPException(
            status_code=500,
            detail="Verification record not found. Please contact support."
        )

    verification.is_verified = True
    verification.verified_at = get_ist_now()
    verification.verification_method = "otp"

    # Check if user has a pending video job
    pending_job = db.query(VideoJob).filter(
        VideoJob.user_id == user.id,
        VideoJob.status == "queued"
    ).first()

    if pending_job:
        # Increment video count for the pending job
        user.video_count += 1
        db.commit()
        return {
            "status": "verified",
            "job_id": pending_job.id,
            "message": "OTP verified successfully. Your video is being processed."
        }

    db.commit()
    return {
        "status": "verified",
        "message": "OTP verified successfully."
    }


@router.post("/resend-otp")
def resend_otp(payload: dict, db: Session = Depends(get_db)):
    """
    Resend OTP to user's mobile number.
    Only works if previous OTP has expired or been used.
    """
    # Validate payload
    if "mobile_number" not in payload:
        raise HTTPException(
            status_code=400,
            detail="Missing required field: mobile_number"
        )

    mobile_number = payload["mobile_number"]
    phone_hash = hash_phone(mobile_number)

    # Find user
    user = db.query(User).filter(User.phone_hash == phone_hash).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please submit the form first."
        )

    # Check if user already verified
    verification = db.query(UserVerification).filter_by(user_id=user.id).first()
    if verification and verification.is_verified:
        raise HTTPException(
            status_code=400,
            detail="User is already verified. No OTP needed."
        )

    # Check for existing valid OTP
    existing_otp = (
        db.query(UserOTP)
        .filter(
            UserOTP.user_id == user.id,
            UserOTP.is_used == False,
            UserOTP.expires_at > get_ist_now(),
        )
        .order_by(UserOTP.created_at.desc())
        .first()
    )

    if existing_otp:
        # Calculate remaining time
        remaining_seconds = (existing_otp.expires_at - get_ist_now()).total_seconds()
        raise HTTPException(
            status_code=400,
            detail=f"OTP is still valid. Please wait {int(remaining_seconds)} seconds before requesting a new one."
        )

    # Generate new OTP
    otp = generate_otp()
    logger.info("RESEND OTP for %s: %s", mobile_number, otp)

    # Save OTP to database
    new_otp = UserOTP(
        id=str(uuid4()),
        user_id=user.id,
        otp_hash=hash_otp(otp),
        expires_at=get_ist_now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        attempts=0,
        is_used=False,
    )
    db.add(new_otp)
    db.commit()

    # Send OTP (implement this based on your SMS/WhatsApp provider)
    try:
        send_otp(mobile_number, otp)
        logger.info("OTP sent to %s", mobile_number)
    except Exception as e:
        logger.warning("Failed to send OTP: %s", str(e))
        # Continue anyway - OTP is saved in database

    return {
        "status": "success",
        "message": "New OTP sent successfully",
        "mobile_number": mobile_number,
        "expires_in_minutes": settings.OTP_EXPIRY_MINUTES
    }
