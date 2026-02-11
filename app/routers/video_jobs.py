import logging
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import decrypt_phone, hash_phone
from app.core.timezone import get_ist_now
from app.core.config import settings
from app.core.admin_auth import get_current_admin
from app.core.otp import send_failed_message
from app.core.redis import FeatureFlags
from app.models.video_job import VideoJob
from app.models.video_assets import VideoAssets
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/video-jobs",
    tags=["video-jobs"],
    dependencies=[Depends(get_current_admin)],
)


class VideoJobResponse(BaseModel):
    id: int
    user_id: str
    mobile_number: Optional[str] = None
    gender: Optional[str] = None
    attribute_love: Optional[str] = None
    relationship_status: Optional[str] = None
    vibe: Optional[str] = None
    status: Optional[str] = None
    retry_count: Optional[int] = None
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    failed_stage: Optional[str] = None
    last_error_code: Optional[str] = None
    photo_validated: Optional[bool] = None
    terms_accepted: Optional[bool] = None
    marketing_opt_in: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class VideoJobDetailResponse(VideoJobResponse):
    """Extended response with photo, video assets and user details"""
    raw_selfie_url: Optional[str] = None
    normalized_image_url: Optional[str] = None
    lipsync_seg2_url: Optional[str] = None
    lipsync_seg4_url: Optional[str] = None
    final_video_url: Optional[str] = None
    video_count: Optional[int] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class PaginatedVideoJobsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[VideoJobResponse]
    filters_applied: dict
    message: str


@router.get("/list", response_model=PaginatedVideoJobsResponse)
def list_video_jobs(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (starts from 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Number of items per page (max 100)"),
    status: Optional[str] = Query(None, description="Filter by status: queued, photo_processing, photo_done, lipsync_processing, lipsync_done, stitching, uploaded, sent, failed"),
    failed_stage: Optional[str] = Query(None, description="Filter by failed stage: photo, lipsync, stitch, delivery"),
    start_date: Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    mobile_number: Optional[str] = Query(None, description="Filter by mobile number (10-digit)"),
    job_id: Optional[int] = Query(None, description="Filter by job ID"),
):
    """
    Get paginated list of video jobs with filters.

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 20, max: 100)
    - **status**: Filter by job status
    - **failed_stage**: Filter by failed stage (only applicable when status=failed)
    - **start_date**: Filter jobs from this date
    - **end_date**: Filter jobs until this date
    - **user_id**: Filter by specific user
    - **mobile_number**: Filter by mobile number
    - **job_id**: Filter by job ID

    Returns latest updated jobs first.
    """

    # Build base query
    query = db.query(VideoJob)

    # Apply filters
    filters = []

    if status:
        filters.append(VideoJob.status == status)

    if failed_stage:
        filters.append(VideoJob.failed_stage == failed_stage)

    # If mobile_number provided, find user by phone hash and filter by user_id
    if mobile_number:
        phone_hash = hash_phone(mobile_number)
        user_by_phone = db.query(User).filter(User.phone_hash == phone_hash).first()
        if user_by_phone:
            filters.append(VideoJob.user_id == user_by_phone.id)
        else:
            # No user found with this number — return empty result
            return PaginatedVideoJobsResponse(
                total=0, page=page, page_size=page_size, total_pages=0,
                items=[], filters_applied={"mobile_number": mobile_number},
                message=f"No user found with mobile number {mobile_number}."
            )

    if job_id:
        filters.append(VideoJob.id == job_id)

    if user_id:
        filters.append(VideoJob.user_id == user_id)

    # Date range filters
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        filters.append(VideoJob.updated_at >= start_datetime)

    if end_date:
        # Include the entire end_date day
        end_datetime = datetime.combine(end_date, datetime.max.time())
        filters.append(VideoJob.updated_at <= end_datetime)

    # Apply all filters
    if filters:
        query = query.filter(and_(*filters))

    # Get total count
    total = query.count()

    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size  # Ceiling division
    offset = (page - 1) * page_size

    # Order by latest created first and apply pagination
    jobs = query.order_by(desc(VideoJob.id)).offset(offset).limit(page_size).all()

    # Build response items with mobile numbers
    items = []
    for job in jobs:
        # Get user and decrypt phone
        user = db.query(User).filter(User.id == job.user_id).first()
        mobile_number = None
        if user and user.phone_encrypted:
            try:
                mobile_number = decrypt_phone(user.phone_encrypted)
            except Exception as e:
                print(f"⚠️ Failed to decrypt phone for user {user.id}: {str(e)}")
                mobile_number = "***ENCRYPTED***"

        # Create response dict with all job fields plus mobile_number
        job_dict = {
            "id": job.id,
            "user_id": job.user_id,
            "mobile_number": mobile_number,
            "gender": job.gender,
            "attribute_love": job.attribute_love,
            "relationship_status": job.relationship_status,
            "vibe": job.vibe,
            "status": job.status,
            "retry_count": job.retry_count,
            "locked_by": job.locked_by,
            "locked_at": job.locked_at,
            "failed_stage": job.failed_stage,
            "last_error_code": job.last_error_code,
            "photo_validated": job.photo_validated,
            "terms_accepted": user.terms_accepted if user else None,
            "marketing_opt_in": user.marketing_opt_in if user else None,
            "created_at": job.created_at,
            "updated_at": job.updated_at
        }
        items.append(VideoJobResponse(**job_dict))

    # Build filters applied dictionary
    filters_applied = {}
    filter_parts = []

    if status:
        filters_applied["status"] = status
        filter_parts.append(f"status='{status}'")

    if failed_stage:
        filters_applied["failed_stage"] = failed_stage
        filter_parts.append(f"failed_stage='{failed_stage}'")

    if mobile_number:
        filters_applied["mobile_number"] = mobile_number
        filter_parts.append(f"mobile_number='{mobile_number}'")

    if job_id:
        filters_applied["job_id"] = job_id
        filter_parts.append(f"job_id={job_id}")

    if user_id:
        filters_applied["user_id"] = user_id
        filter_parts.append(f"user_id='{user_id}'")

    if start_date:
        filters_applied["start_date"] = start_date.isoformat()
        filter_parts.append(f"from {start_date.isoformat()}")

    if end_date:
        filters_applied["end_date"] = end_date.isoformat()
        filter_parts.append(f"to {end_date.isoformat()}")

    # Generate descriptive message
    if filter_parts:
        filter_desc = " with filters: " + ", ".join(filter_parts)
        message = f"Found {total} video job(s){filter_desc}. Showing page {page} of {total_pages}."
    else:
        message = f"Found {total} video job(s). Showing page {page} of {total_pages}."

    return PaginatedVideoJobsResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
        filters_applied=filters_applied,
        message=message
    )


@router.get("/{job_id}", response_model=VideoJobDetailResponse)
def get_video_job(
    job_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific video job by ID with full details including photo URL.
    """
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Video job with ID {job_id} not found"
        )

    # Get user and decrypt phone
    user = db.query(User).filter(User.id == job.user_id).first()
    mobile_number = None
    terms_accepted = None
    marketing_opt_in = None
    video_count = None
    if user:
        terms_accepted = user.terms_accepted
        marketing_opt_in = user.marketing_opt_in
        video_count = user.video_count
        if user.phone_encrypted:
            try:
                mobile_number = decrypt_phone(user.phone_encrypted)
            except Exception as e:
                print(f"⚠️ Failed to decrypt phone for user {user.id}: {str(e)}")
                mobile_number = "***ENCRYPTED***"

    # Get all asset URLs from video_assets
    assets = db.query(VideoAssets).filter(VideoAssets.job_id == job_id).first()

    job_dict = {
        "id": job.id,
        "user_id": job.user_id,
        "mobile_number": mobile_number,
        "gender": job.gender,
        "attribute_love": job.attribute_love,
        "relationship_status": job.relationship_status,
        "vibe": job.vibe,
        "status": job.status,
        "retry_count": job.retry_count,
        "locked_by": job.locked_by,
        "locked_at": job.locked_at,
        "failed_stage": job.failed_stage,
        "last_error_code": job.last_error_code,
        "photo_validated": job.photo_validated,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "raw_selfie_url": assets.raw_selfie_url if assets else None,
        "normalized_image_url": assets.normalized_image_url if assets else None,
        "lipsync_seg2_url": assets.lipsync_seg2_url if assets else None,
        "lipsync_seg4_url": assets.lipsync_seg4_url if assets else None,
        "final_video_url": assets.final_video_url if assets else None,
        "terms_accepted": terms_accepted,
        "marketing_opt_in": marketing_opt_in,
        "video_count": video_count,
    }

    return VideoJobDetailResponse(**job_dict)


@router.get("/stats/summary")
def get_job_stats(
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None, description="Stats from date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Stats to date (YYYY-MM-DD)"),
):
    """
    Get statistics summary of video jobs.

    Returns counts grouped by status and failed stages.
    """

    # Build base query
    query = db.query(VideoJob)

    # Apply date filters if provided
    filters = []
    if start_date:
        start_datetime = datetime.combine(start_date, datetime.min.time())
        filters.append(VideoJob.updated_at >= start_datetime)

    if end_date:
        end_datetime = datetime.combine(end_date, datetime.max.time())
        filters.append(VideoJob.updated_at <= end_datetime)

    if filters:
        query = query.filter(and_(*filters))

    # Get all jobs
    all_jobs = query.all()

    # Count by status
    status_counts = {}
    for job in all_jobs:
        status = job.status or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    # Count by failed stage (only for failed jobs)
    failed_stage_counts = {}
    failed_jobs = [job for job in all_jobs if job.status == "failed"]
    for job in failed_jobs:
        stage = job.failed_stage or "unknown"
        failed_stage_counts[stage] = failed_stage_counts.get(stage, 0) + 1

    return {
        "total_jobs": len(all_jobs),
        "status_breakdown": status_counts,
        "failed_jobs_count": len(failed_jobs),
        "failed_stage_breakdown": failed_stage_counts,
        "date_range": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }
    }


@router.patch("/{job_id}/status")
def update_job_status(
    job_id: int,
    status: str = Query(..., description="New status"),
    failed_stage: Optional[str] = Query(None, description="Failed stage (required if status=failed)"),
    error_code: Optional[str] = Query(None, description="Error code for failed jobs"),
    db: Session = Depends(get_db)
):
    """
    Update the status of a video job.

    - **status**: New status value
    - **failed_stage**: Required when status is 'failed'
    - **error_code**: Optional error code for debugging
    """

    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Video job with ID {job_id} not found"
        )

    # Validate status
    valid_statuses = ['wait', 'unverified_photo', 'client', 'queued', 'photo_processing', 'photo_done', 'lipsync_processing',
                      'lipsync_done', 'stitching', 'uploaded', 'sent', 'failed']

    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    # If status is failed, require failed_stage
    if status == 'failed' and not failed_stage:
        raise HTTPException(
            status_code=400,
            detail="failed_stage is required when status is 'failed'"
        )

    # Update job
    job.status = status

    if failed_stage:
        valid_stages = ['photo', 'lipsync', 'stitch', 'delivery']
        if failed_stage not in valid_stages:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid failed_stage. Must be one of: {', '.join(valid_stages)}"
            )
        job.failed_stage = failed_stage

    if error_code:
        job.last_error_code = error_code

    job.updated_at = get_ist_now()

    db.commit()
    db.refresh(job)

    return {
        "success": True,
        "message": f"Job {job_id} status updated to {status}",
        "job": VideoJobResponse.from_orm(job)
    }


@router.patch("/update-job")
def update_job_by_job_id(
    job_id: int = Query(..., description="Job ID"),
    status: str = Query(..., description="New status"),
    db: Session = Depends(get_db)
):
    """
    Update video job status by job_id.

    - **job_id**: Job ID (required)
    - **status**: New status (required)

    Rules:
    - When status is updated, retry_count increments by 1
    - failed_stage and last_error_code are set to null
    - status is validated against allowed values
    """

    print(f"📝 Updating job {job_id} to status: {status}")

    # Find job by job_id
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Video job with ID {job_id} not found"
        )

    # Validate status
    valid_statuses = ['wait', 'unverified_photo', 'client', 'queued', 'photo_processing', 'photo_done', 'lipsync_processing',
                      'lipsync_done', 'stitching', 'uploaded', 'sent', 'failed']

    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    # Update job
    old_status = job.status
    job.status = status

    # Increment retry_count by 1
    job.retry_count = (job.retry_count or 0) + 1

    # Set failed_stage and last_error_code to null
    job.failed_stage = None
    job.last_error_code = None

    # Update timestamp
    job.updated_at = get_ist_now()

    print(f"✅ Job {job_id} updated: {old_status} → {status}, retry_count: {job.retry_count}")

    # Commit changes
    db.commit()
    db.refresh(job)

    # Get user and decrypt phone for response
    user = db.query(User).filter(User.id == job.user_id).first()
    mobile_number = None
    if user and user.phone_encrypted:
        try:
            mobile_number = decrypt_phone(user.phone_encrypted)
        except Exception as e:
            print(f"⚠️ Failed to decrypt phone for user {user.id}: {str(e)}")
            mobile_number = "***ENCRYPTED***"

    # Send failed message via WhatsApp when status is changed to "failed"
    if status == "failed" and mobile_number and mobile_number != "***ENCRYPTED***":
        try:
            send_failed_message(mobile_number)
            print(f"📩 Failed message sent to {mobile_number} for job {job_id}")
        except Exception as e:
            print(f"⚠️ Failed to send failed message for job {job_id}: {str(e)}")

    # Create response
    job_dict = {
        "id": job.id,
        "user_id": job.user_id,
        "mobile_number": mobile_number,
        "gender": job.gender,
        "attribute_love": job.attribute_love,
        "relationship_status": job.relationship_status,
        "vibe": job.vibe,
        "status": job.status,
        "retry_count": job.retry_count,
        "locked_by": job.locked_by,
        "locked_at": job.locked_at,
        "failed_stage": job.failed_stage,
        "last_error_code": job.last_error_code,
        "created_at": job.created_at,
        "updated_at": job.updated_at
    }

    return {
        "success": True,
        "message": f"Job {job_id} status updated to '{status}' successfully (retry_count: {job.retry_count})",
        "job": VideoJobResponse(**job_dict)
    }


class UpdateJobFieldsRequest(BaseModel):
    gender: Optional[str] = None
    relationship_status: Optional[str] = None
    attribute_love: Optional[str] = None
    vibe: Optional[str] = None


@router.patch("/{job_id}/fields")
def update_job_fields(
    job_id: int,
    body: UpdateJobFieldsRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin)
):
    """
    Update video job fields (gender, relationship_status, attribute_love, vibe).

    - **job_id**: Job ID (required)
    - **gender**: New gender value (optional)
    - **relationship_status**: New relationship status (optional)
    - **attribute_love**: New attribute love value (optional)
    - **vibe**: New vibe value (optional)
    """
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Video job with ID {job_id} not found"
        )

    # Validate and update fields
    valid_genders = {'male', 'female', 'other', 'unspecified'}
    valid_relationships = {'Married', 'Situationship', 'Nanoship', 'Crushing', 'Long-Distance', 'Dating'}
    valid_attributes = {'Smile', 'Eyes', 'Hair', 'Face', 'Vibe', 'Sense of Humor', 'Heart'}
    valid_vibes = {'romantic', 'rock', 'rap'}

    updated_fields = []

    if body.gender is not None:
        if body.gender not in valid_genders:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid gender. Must be one of: {', '.join(valid_genders)}"
            )
        job.gender = body.gender
        updated_fields.append("gender")

    if body.relationship_status is not None:
        if body.relationship_status not in valid_relationships:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid relationship_status. Must be one of: {', '.join(valid_relationships)}"
            )
        job.relationship_status = body.relationship_status
        updated_fields.append("relationship_status")

    if body.attribute_love is not None:
        if body.attribute_love not in valid_attributes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid attribute_love. Must be one of: {', '.join(valid_attributes)}"
            )
        job.attribute_love = body.attribute_love
        updated_fields.append("attribute_love")

    if body.vibe is not None:
        if body.vibe not in valid_vibes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid vibe. Must be one of: {', '.join(valid_vibes)}"
            )
        job.vibe = body.vibe
        updated_fields.append("vibe")

    if not updated_fields:
        raise HTTPException(
            status_code=400,
            detail="No fields provided to update"
        )

    job.updated_at = get_ist_now()
    db.commit()
    db.refresh(job)

    # Get user phone for response
    user = db.query(User).filter(User.id == job.user_id).first()
    mobile_number = None
    if user and user.phone_encrypted:
        try:
            mobile_number = decrypt_phone(user.phone_encrypted)
        except Exception:
            mobile_number = "***ENCRYPTED***"

    job_dict = {
        "id": job.id,
        "user_id": job.user_id,
        "mobile_number": mobile_number,
        "gender": job.gender,
        "attribute_love": job.attribute_love,
        "relationship_status": job.relationship_status,
        "vibe": job.vibe,
        "status": job.status,
        "retry_count": job.retry_count,
        "locked_by": job.locked_by,
        "locked_at": job.locked_at,
        "failed_stage": job.failed_stage,
        "last_error_code": job.last_error_code,
        "created_at": job.created_at,
        "updated_at": job.updated_at
    }

    return {
        "success": True,
        "message": f"Job {job_id} updated: {', '.join(updated_fields)}",
        "job": VideoJobResponse(**job_dict)
    }


class UpdateVideoUrlRequest(BaseModel):
    final_video_url: str


@router.patch("/{job_id}/video-url")
def update_video_url(
    job_id: int,
    body: UpdateVideoUrlRequest,
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin)
):
    """Update the final_video_url for a video job."""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Video job with ID {job_id} not found")

    assets = db.query(VideoAssets).filter(VideoAssets.job_id == job_id).first()
    if not assets:
        assets = VideoAssets(job_id=job_id, final_video_url=body.final_video_url)
        db.add(assets)
    else:
        assets.final_video_url = body.final_video_url

    job.updated_at = get_ist_now()
    db.commit()

    return {
        "success": True,
        "message": f"Final video URL updated for job {job_id}",
        "final_video_url": body.final_video_url,
    }


@router.post("/{job_id}/send-video")
def send_video_whatsapp(
    job_id: int,
    db: Session = Depends(get_db),
):
    """
    Send the final video to the user via WhatsApp.

    Fetches the final_video_url from video_assets and the user's phone number,
    then sends it using the video_16 WhatsApp template.
    """
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Video job {job_id} not found")

    assets = db.query(VideoAssets).filter(VideoAssets.job_id == job_id).first()
    if not assets or not assets.final_video_url:
        raise HTTPException(status_code=400, detail="Final video is not available yet for this job")

    user = db.query(User).filter(User.id == job.user_id).first()
    if not user or not user.phone_encrypted:
        raise HTTPException(status_code=400, detail="User phone number not found")

    try:
        mobile_number = decrypt_phone(user.phone_encrypted)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt user phone number")

    # Format phone with 91 prefix
    phone = mobile_number.strip().replace("+", "").replace(" ", "").replace("-", "")
    if not phone.startswith("91"):
        phone = "91" + phone

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": "video_16",
            "language": {"code": "en"},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "video",
                            "video": {
                                "link": assets.final_video_url
                            }
                        }
                    ]
                }
            ]
        }
    }

    try:
        response = httpx.post(
            settings.WHATSAPP_API_URL,
            json=payload,
            headers={
                "X-API-KEY": settings.WHATSAPP_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )
        logger.info("WhatsApp send video response [%s]: %s", response.status_code, response.text)

        if response.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"WhatsApp API error: {response.text}"
            )

        # Update job status to sent
        job.status = "sent"
        job.updated_at = get_ist_now()
        db.commit()

        return {
            "success": True,
            "message": f"Video sent to {phone} via WhatsApp. Job status updated to 'sent'.",
            "job_id": job_id,
        }

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="WhatsApp API timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Send video error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to send video: {str(e)}")


class ReportCounts(BaseModel):
    total: int
    total_users: int
    returning_users: int
    gender: dict
    status: dict
    relationship_status: dict
    attribute_love: dict
    vibe: dict


class ReportsResponse(BaseModel):
    start_date: Optional[str]
    end_date: Optional[str]
    counts: ReportCounts


@router.get("/reports/stats", response_model=ReportsResponse)
def get_reports(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin)
):
    """
    Get reports/statistics for video jobs within a date range.

    - **start_date**: Start date filter (optional)
    - **end_date**: End date filter (optional, defaults to today)

    Returns counts for:
    - Total entries
    - Gender-wise breakdown
    - Status-wise breakdown
    - Relationship status breakdown
    - Attribute love breakdown
    - Vibe breakdown
    """
    from sqlalchemy import func, case

    # Build date filter
    filters = []
    if start_date:
        filters.append(VideoJob.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        filters.append(VideoJob.created_at <= datetime.combine(end_date, datetime.max.time()))

    # Base query with filters
    base_query = db.query(VideoJob)
    if filters:
        base_query = base_query.filter(and_(*filters))

    # Total count
    total = base_query.count()

    # Total users = all distinct users in date range
    total_users = db.query(func.count(func.distinct(VideoJob.user_id)))
    if filters:
        total_users = total_users.filter(and_(*filters))
    total_users = total_users.scalar() or 0

    # Returning users = users with 2+ total video jobs (across all time)
    jobs_per_user = db.query(
        VideoJob.user_id,
        func.count(VideoJob.id).label('total_jobs')
    ).group_by(VideoJob.user_id).subquery()

    user_ids_in_range = db.query(func.distinct(VideoJob.user_id))
    if filters:
        user_ids_in_range = user_ids_in_range.filter(and_(*filters))
    user_ids_in_range = user_ids_in_range.subquery()

    returning_users = db.query(func.count(jobs_per_user.c.user_id)).filter(
        jobs_per_user.c.user_id.in_(user_ids_in_range),
        jobs_per_user.c.total_jobs > 1
    ).scalar() or 0

    # Gender counts
    gender_counts = db.query(
        VideoJob.gender,
        func.count(VideoJob.id).label('count')
    )
    if filters:
        gender_counts = gender_counts.filter(and_(*filters))
    gender_counts = gender_counts.group_by(VideoJob.gender).all()
    gender_dict = {g or "unspecified": c for g, c in gender_counts}

    # Status counts
    status_counts = db.query(
        VideoJob.status,
        func.count(VideoJob.id).label('count')
    )
    if filters:
        status_counts = status_counts.filter(and_(*filters))
    status_counts = status_counts.group_by(VideoJob.status).all()
    status_dict = {s or "unknown": c for s, c in status_counts}

    # Relationship status counts
    relationship_counts = db.query(
        VideoJob.relationship_status,
        func.count(VideoJob.id).label('count')
    )
    if filters:
        relationship_counts = relationship_counts.filter(and_(*filters))
    relationship_counts = relationship_counts.group_by(VideoJob.relationship_status).all()
    relationship_dict = {r or "unknown": c for r, c in relationship_counts}

    # Attribute love counts
    attribute_counts = db.query(
        VideoJob.attribute_love,
        func.count(VideoJob.id).label('count')
    )
    if filters:
        attribute_counts = attribute_counts.filter(and_(*filters))
    attribute_counts = attribute_counts.group_by(VideoJob.attribute_love).all()
    attribute_dict = {a or "unknown": c for a, c in attribute_counts}

    # Vibe counts
    vibe_counts = db.query(
        VideoJob.vibe,
        func.count(VideoJob.id).label('count')
    )
    if filters:
        vibe_counts = vibe_counts.filter(and_(*filters))
    vibe_counts = vibe_counts.group_by(VideoJob.vibe).all()
    vibe_dict = {v or "unknown": c for v, c in vibe_counts}

    return ReportsResponse(
        start_date=str(start_date) if start_date else None,
        end_date=str(end_date) if end_date else None,
        counts=ReportCounts(
            total=total,
            total_users=total_users,
            returning_users=returning_users,
            gender=gender_dict,
            status=status_dict,
            relationship_status=relationship_dict,
            attribute_love=attribute_dict,
            vibe=vibe_dict
        )
    )


class TrendDataPoint(BaseModel):
    label: str
    total_entries: int
    total_users: int
    returning_users: int


class TrendResponse(BaseModel):
    mode: str  # "day" or "week"
    data: List[TrendDataPoint]


@router.get("/reports/trend", response_model=TrendResponse)
def get_reports_trend(
    mode: str = Query("day", description="Trend mode: 'day' or 'week'"),
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin)
):
    """
    Get day-wise or week-wise trend data for total entries, total users, returning users.
    """
    from sqlalchemy import func
    from datetime import timedelta

    # Default date range
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=29)  # Last 30 days

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    if mode == "week":
        # Week-wise: group by YEARWEEK
        # Get all jobs in range grouped by week
        entries_by_week = db.query(
            func.yearweek(VideoJob.created_at, 1).label('yw'),
            func.min(func.date(VideoJob.created_at)).label('week_start'),
            func.count(VideoJob.id).label('total_entries'),
            func.count(func.distinct(VideoJob.user_id)).label('total_users')
        ).filter(
            VideoJob.created_at >= start_dt,
            VideoJob.created_at <= end_dt
        ).group_by('yw').order_by('yw').all()

        # Get returning users per week (users with 2+ jobs overall who appear in that week)
        jobs_per_user = db.query(
            VideoJob.user_id,
            func.count(VideoJob.id).label('total_jobs')
        ).group_by(VideoJob.user_id).subquery()

        returning_by_week = db.query(
            func.yearweek(VideoJob.created_at, 1).label('yw'),
            func.count(func.distinct(VideoJob.user_id)).label('returning_count')
        ).join(
            jobs_per_user, jobs_per_user.c.user_id == VideoJob.user_id
        ).filter(
            VideoJob.created_at >= start_dt,
            VideoJob.created_at <= end_dt,
            jobs_per_user.c.total_jobs > 1
        ).group_by('yw').all()

        returning_map = {str(r.yw): r.returning_count for r in returning_by_week}

        data = []
        for row in entries_by_week:
            yw_key = str(row.yw)
            data.append(TrendDataPoint(
                label=f"Week of {row.week_start.strftime('%d %b')}",
                total_entries=row.total_entries,
                total_users=row.total_users,
                returning_users=returning_map.get(yw_key, 0)
            ))
    else:
        # Day-wise
        entries_by_day = db.query(
            func.date(VideoJob.created_at).label('day'),
            func.count(VideoJob.id).label('total_entries'),
            func.count(func.distinct(VideoJob.user_id)).label('total_users')
        ).filter(
            VideoJob.created_at >= start_dt,
            VideoJob.created_at <= end_dt
        ).group_by('day').order_by('day').all()

        # Get returning users per day
        jobs_per_user = db.query(
            VideoJob.user_id,
            func.count(VideoJob.id).label('total_jobs')
        ).group_by(VideoJob.user_id).subquery()

        returning_by_day = db.query(
            func.date(VideoJob.created_at).label('day'),
            func.count(func.distinct(VideoJob.user_id)).label('returning_count')
        ).join(
            jobs_per_user, jobs_per_user.c.user_id == VideoJob.user_id
        ).filter(
            VideoJob.created_at >= start_dt,
            VideoJob.created_at <= end_dt,
            jobs_per_user.c.total_jobs > 1
        ).group_by('day').all()

        returning_map = {str(r.day): r.returning_count for r in returning_by_day}

        data = []
        for row in entries_by_day:
            day_key = str(row.day)
            data.append(TrendDataPoint(
                label=row.day.strftime('%d %b'),
                total_entries=row.total_entries,
                total_users=row.total_users,
                returning_users=returning_map.get(day_key, 0)
            ))

    return TrendResponse(mode=mode, data=data)


@router.get("/reports/csv")
def download_reports_csv(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _: str = Depends(get_current_admin)
):
    """
    Download reports as CSV file.

    - **start_date**: Start date filter (optional)
    - **end_date**: End date filter (optional, defaults to today)
    """
    from fastapi.responses import StreamingResponse
    from sqlalchemy import func
    import io
    import csv

    # Build date filter
    filters = []
    if start_date:
        filters.append(VideoJob.created_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        filters.append(VideoJob.created_at <= datetime.combine(end_date, datetime.max.time()))

    # Base query with filters
    base_query = db.query(VideoJob)
    if filters:
        base_query = base_query.filter(and_(*filters))

    # Total count
    total = base_query.count()

    # Total users = all distinct users in date range
    total_users = db.query(func.count(func.distinct(VideoJob.user_id)))
    if filters:
        total_users = total_users.filter(and_(*filters))
    total_users = total_users.scalar() or 0

    # Returning users = users with 2+ total video jobs (across all time)
    jobs_per_user = db.query(
        VideoJob.user_id,
        func.count(VideoJob.id).label('total_jobs')
    ).group_by(VideoJob.user_id).subquery()

    user_ids_in_range = db.query(func.distinct(VideoJob.user_id))
    if filters:
        user_ids_in_range = user_ids_in_range.filter(and_(*filters))
    user_ids_in_range = user_ids_in_range.subquery()

    returning_users = db.query(func.count(jobs_per_user.c.user_id)).filter(
        jobs_per_user.c.user_id.in_(user_ids_in_range),
        jobs_per_user.c.total_jobs > 1
    ).scalar() or 0

    # Gender counts
    gender_counts = db.query(VideoJob.gender, func.count(VideoJob.id).label('count'))
    if filters:
        gender_counts = gender_counts.filter(and_(*filters))
    gender_counts = gender_counts.group_by(VideoJob.gender).all()

    # Status counts
    status_counts = db.query(VideoJob.status, func.count(VideoJob.id).label('count'))
    if filters:
        status_counts = status_counts.filter(and_(*filters))
    status_counts = status_counts.group_by(VideoJob.status).all()

    # Relationship status counts
    relationship_counts = db.query(VideoJob.relationship_status, func.count(VideoJob.id).label('count'))
    if filters:
        relationship_counts = relationship_counts.filter(and_(*filters))
    relationship_counts = relationship_counts.group_by(VideoJob.relationship_status).all()

    # Attribute love counts
    attribute_counts = db.query(VideoJob.attribute_love, func.count(VideoJob.id).label('count'))
    if filters:
        attribute_counts = attribute_counts.filter(and_(*filters))
    attribute_counts = attribute_counts.group_by(VideoJob.attribute_love).all()

    # Vibe counts
    vibe_counts = db.query(VideoJob.vibe, func.count(VideoJob.id).label('count'))
    if filters:
        vibe_counts = vibe_counts.filter(and_(*filters))
    vibe_counts = vibe_counts.group_by(VideoJob.vibe).all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(["Category", "Type", "Count"])

    # Write total
    writer.writerow(["Total", "entries", total])
    writer.writerow(["Users", "total_users", total_users])
    writer.writerow(["Users", "returning_users", returning_users])

    # Write gender breakdown
    for gender, count in gender_counts:
        writer.writerow(["Gender", gender or "unspecified", count])

    # Write status breakdown
    for status, count in status_counts:
        writer.writerow(["Status", status or "unknown", count])

    # Write relationship breakdown
    for rel, count in relationship_counts:
        writer.writerow(["Relationship", rel or "unknown", count])

    # Write attribute love breakdown
    for attr, count in attribute_counts:
        writer.writerow(["Attribute Love", attr or "unknown", count])

    # Write vibe breakdown
    for vibe, count in vibe_counts:
        writer.writerow(["Vibe", vibe or "unknown", count])

    # Prepare response
    output.seek(0)
    date_suffix = ""
    if start_date and end_date:
        date_suffix = f"_{start_date}_to_{end_date}"
    elif start_date:
        date_suffix = f"_from_{start_date}"
    elif end_date:
        date_suffix = f"_until_{end_date}"

    filename = f"video_jobs_report{date_suffix}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── Photo Validation Toggle ──────────────────────────────────────────

class PhotoValidationToggle(BaseModel):
    enabled: bool


@router.get("/settings/photo-validation")
def get_photo_validation_setting(
    _: str = Depends(get_current_admin)
):
    """Get current photo validation toggle status (admin only)."""
    enabled = FeatureFlags.is_enabled("photo_validation", default=True)
    auto_off = FeatureFlags.is_auto_off("photo_validation")
    return {
        "enabled": enabled,
        "auto_off": auto_off,
    }


@router.patch("/settings/photo-validation")
def set_photo_validation_setting(
    body: PhotoValidationToggle,
    _: str = Depends(get_current_admin)
):
    """Toggle photo validation ON/OFF (admin only)."""
    success = FeatureFlags.set_flag("photo_validation", body.enabled)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update setting")
    # set_flag with enabled=True already clears auto_off marker
    status = "enabled" if body.enabled else "disabled"
    return {"enabled": body.enabled, "message": f"Photo validation {status}"}
