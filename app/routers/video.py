import logging

from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import timedelta
import os

from app.core.database import get_db
from app.core.security import hash_phone, encrypt_phone
from app.core.otp import generate_otp, hash_otp, send_otp
from app.core.config import settings
from app.core.s3 import upload_fileobj_to_s3
from app.core.timezone import get_ist_now

from app.models.user import User
from app.models.user_verification import UserVerification
from app.models.user_otp import UserOTP
from app.models.video_job import VideoJob
from app.models.video_assets import VideoAssets

router = APIRouter(prefix="/api/v1/video", tags=["video"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.post("/submit")
async def submit_video_form(
    mobile_number: str = Form(...),
    gender: str = Form(...),
    relationship_status: str = Form(...),
    attribute_love: str = Form(...),
    vibe: str = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
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

    valid_relationship_status = {"Married", "Situationship", "Nanaship", "Crushing", "Long-Distance", "Dating"}
    if relationship_status not in valid_relationship_status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid relationship_status. Must be one of: {', '.join(valid_relationship_status)}"
        )

    valid_vibes = {"rap", "rock", "pop"}
    if vibe not in valid_vibes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vibe. Must be one of: {', '.join(valid_vibes)}"
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

    if user and user.video_count >= 3:
        raise HTTPException(
            status_code=403,
            detail="You have already generated the maximum of three videos"
        )

    if not user:
        user = User(
            id=str(uuid4()),
            phone_hash=phone_hash,
            phone_encrypted=encrypt_phone(mobile_number),
            video_count=0,
        )
        db.add(user)
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
        # Check if user already has a pending job (not verified yet)
        existing_job = db.query(VideoJob).filter(
            VideoJob.user_id == user.id,
            VideoJob.status == "queued"
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

    # User is verified - check if they already have a pending job
    pending_job = db.query(VideoJob).filter(
        VideoJob.user_id == user.id,
        VideoJob.status != "sent"
    ).first()

    if pending_job:
        # Job already exists and counted, just return it
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
