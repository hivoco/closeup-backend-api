import logging

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import timedelta
import os

from app.core.database import get_db
from app.core.security import hash_phone, encrypt_phone
from app.core.otp import generate_otp, hash_otp, send_otp, send_thank_you
from app.core.config import settings
from app.core.s3 import upload_fileobj_to_s3
from app.core.timezone import get_ist_now
from app.core.redis import RateLimiter, Cache

from app.models.user import User
from app.models.user_verification import UserVerification
from app.models.user_otp import UserOTP
from app.models.video_job import VideoJob
from app.models.video_assets import VideoAssets

router = APIRouter(prefix="/api/v1/video", tags=["video"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Whitelisted numbers with unlimited video generation
UNLIMITED_NUMBERS = {
    "7507069000",
    "8619763089",
    "9820099301",
    "9411795829",
    "9118720778",
    "8252261004",
    "7982592365",
    "8650856237",
    "8285022022",
    "8851260538",
    "9711129700",
    "9810009341",
    "8447663057",
    "9560370095",
}


@router.post("/submit")
async def submit_video_form(
    mobile_number: str = Form(...),
    gender: str = Form(...),
    relationship_status: str = Form(...),
    attribute_love: str = Form(...),
    vibe: str = Form(...),
    terms_accepted: bool = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Global rate limit: max 500 requests/minute for entire API (all users)
    # Protects server from overload during high traffic
    is_allowed_global, _ = RateLimiter.check_global_limit(
        action="video_submit_global",
        max_requests=500,  # Adjust based on server capacity
        window_seconds=60
    )

    if not is_allowed_global:
        raise HTTPException(
            status_code=503,
            detail="Server is busy. Please try again in a few seconds.",
            headers={"Retry-After": "5"}
        )

    # Rate limit by phone number: max 5 requests per 5 minutes
    is_allowed, _ = RateLimiter.check_rate_limit(
        identifier=mobile_number.strip(),
        action="video_submit",
        max_requests=5,
        window_seconds=300  # 5 minutes
    )

    if not is_allowed:
        retry_after = RateLimiter.get_remaining_time(mobile_number.strip(), "video_submit")
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )

    # Validate mobile number
    if not mobile_number or len(mobile_number.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="Invalid mobile number. Please provide a valid 10-digit mobile number."
        )

    # Validate required fields - gender, attribute_love, relationship_status, vibe
    if not gender or not gender.strip():
        raise HTTPException(
            status_code=400,
            detail="Gender is required. Please select a gender."
        )

    if not attribute_love or not attribute_love.strip():
        raise HTTPException(
            status_code=400,
            detail="Attribute love is required. Please select what you love about your partner."
        )

    if not relationship_status or not relationship_status.strip():
        raise HTTPException(
            status_code=400,
            detail="Relationship status is required. Please select your relationship status."
        )

    if not vibe or not vibe.strip():
        raise HTTPException(
            status_code=400,
            detail="Vibe is required. Please select a vibe."
        )

    # Validate enum values
    valid_genders = {"male", "female", "other", "unspecified"}
    if gender.lower() not in valid_genders:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid gender. Must be one of: {', '.join(valid_genders)}"
        )

    valid_attribute_love = {"Smile", "Eyes", "Hair", "Face", "Vibe", "Sense of Humor", "Heart"}
    if attribute_love not in valid_attribute_love:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid attribute_love. Must be one of: {', '.join(valid_attribute_love)}"
        )

    valid_relationship_status = {"Married", "Situationship", "Nanoship", "Crushing", "Long-Distance", "Dating"}
    if relationship_status not in valid_relationship_status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relationship_status. Must be one of: {', '.join(valid_relationship_status)}"
        )

    valid_vibes = {"romantic", "rock", "rap"}
    if vibe not in valid_vibes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vibe. Must be one of: {', '.join(valid_vibes)}"
        )

    # Validate terms_accepted
    if not terms_accepted:
        raise HTTPException(
            status_code=400,
            detail="You must accept the terms and conditions to continue."
        )

    # Validate photo
    if not photo.filename:
        raise HTTPException(
            status_code=400,
            detail="No photo uploaded. Please upload a selfie."
        )

    # Validate file type
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    ext = os.path.splitext(photo.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
        )

    phone_hash = hash_phone(mobile_number)
    user = db.query(User).filter(User.phone_hash == phone_hash).first()

    cleaned_number = mobile_number.strip().replace("+", "").replace(" ", "").replace("-", "")
    if cleaned_number.startswith("91") and len(cleaned_number) == 12:
        cleaned_number = cleaned_number[2:]

    if user and user.video_count >= 2 and cleaned_number not in UNLIMITED_NUMBERS:
        raise HTTPException(
            status_code=403,
            detail="You have already generated the maximum number of videos"
        )

    if not user:
        user = User(
            id=str(uuid4()),
            phone_hash=phone_hash,
            phone_encrypted=encrypt_phone(mobile_number),
            video_count=0,
            terms_accepted=terms_accepted,
        )
        db.add(user)
    elif not user.terms_accepted and terms_accepted:
        # Update terms_accepted if user exists but hadn't accepted before
        user.terms_accepted = True
        db.flush()

        db.add(UserVerification(
            user_id=user.id,
            is_verified=False,
            verification_method="otp",
        ))
        db.flush()

    verification = db.query(UserVerification).filter_by(user_id=user.id).first()

    # If verification record doesn't exist, create it
    if not verification:
        verification = UserVerification(
            user_id=user.id,
            is_verified=False,
            verification_method="otp",
        )
        db.add(verification)
        db.flush()

    if not verification.is_verified:
        # Check if user already has a waiting job (not verified yet)
        existing_job = db.query(VideoJob).filter(
            VideoJob.user_id == user.id,
            VideoJob.status == "wait"  # Check for "wait" status, not "queued"
        ).first()

        if existing_job:
            # User already submitted, just send new OTP
            otp = generate_otp()
            logger.info("OTP for %s: %s", mobile_number, otp)

            db.add(UserOTP(
                id=str(uuid4()),
                user_id=user.id,
                otp_hash=hash_otp(otp),
                expires_at=get_ist_now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
                attempts=0,
                is_used=False,
            ))
            db.commit()
            send_otp(mobile_number, otp)

            return {
                "status": "otp_sent",
                "job_id": existing_job.id,
                "message": "OTP sent. Please verify to process your video."
            }

        # Create the video job and upload photo for first time submission
        # Status is "wait" until user verifies OTP, then it becomes "queued"
        try:
            job = VideoJob(
                user_id=user.id,
                gender=gender,
                relationship_status=relationship_status,
                attribute_love=attribute_love,
                vibe=vibe,
                status="wait",  # Will change to "queued" after OTP verification
            )
            db.add(job)
            db.flush()

            ext = os.path.splitext(photo.filename)[1].lower()
            key = f"closeup_user_raw_image/{user.id}_{job.id}{ext}"

            print(f"📤 Uploading photo to S3: {key}")
            url = upload_fileobj_to_s3(photo.file, key, photo.content_type)
            print(f"✅ Photo uploaded successfully: {url}")

            db.add(VideoAssets(job_id=job.id, raw_selfie_url=url))

            # Generate and send OTP
            otp = generate_otp()
            logger.info("OTP for %s: %s", mobile_number, otp)

            db.add(UserOTP(
                id=str(uuid4()),
                user_id=user.id,
                otp_hash=hash_otp(otp),
                expires_at=get_ist_now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
                attempts=0,
                is_used=False,
            ))
            db.commit()
            send_otp(mobile_number, otp)

            return {
                "status": "otp_sent",
                "job_id": job.id,
                "message": "OTP sent. Please verify to process your video."
            }
        except Exception as e:
            print(f"❌ Error in video submission: {str(e)}")
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process your request: {str(e)}"
            )

    # User is verified - check cache first for pending job
    cached_job_id = Cache.get_pending_video(user.id)
    if cached_job_id:
        return {
            "status": "pending",
            "job_id": int(cached_job_id),
            "message": "Your previous video is still being processed. Please wait for it to complete before creating a new one."
        }

    # Cache miss - check database
    pending_job = db.query(VideoJob).filter(
        VideoJob.user_id == user.id,
        VideoJob.status.notin_(["sent", "failed"])
    ).first()

    if pending_job:
        # Cache the pending job for future requests
        Cache.set_pending_video(user.id, str(pending_job.id))
        return {
            "status": "pending",
            "job_id": pending_job.id,
            "message": "Your previous video is still being processed. Please wait for it to complete before creating a new one."
        }

    # No pending job - create new one
    try:
        job = VideoJob(
            user_id=user.id,
            gender=gender,
            relationship_status=relationship_status,
            attribute_love=attribute_love,
            vibe=vibe,
            status="queued",
        )
        db.add(job)
        db.flush()

        ext = os.path.splitext(photo.filename)[1].lower()
        key = f"closeup_user_raw_image/{user.id}_{job.id}{ext}"

        print(f"📤 Uploading photo to S3: {key}")
        url = upload_fileobj_to_s3(photo.file, key, photo.content_type)
        print(f"✅ Photo uploaded successfully: {url}")

        db.add(VideoAssets(job_id=job.id, raw_selfie_url=url))
        user.video_count += 1
        db.commit()

        # Cache the new pending job
        Cache.set_pending_video(user.id, str(job.id))

        # Send thank you WhatsApp message
        try:
            send_thank_you(mobile_number)
        except Exception as e:
            logger.warning("Failed to send thank you message: %s", str(e))

        return {
            "status": "video_created",
            "job_id": job.id,
            "message": "Your video is being processed."
        }
    except Exception as e:
        print(f"❌ Error in video creation: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process video request: {str(e)}"
        )
