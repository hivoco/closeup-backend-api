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
    terms_accepted: Optional[bool] = None
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
    video_count = None
    if user:
        terms_accepted = user.terms_accepted
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
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "raw_selfie_url": assets.raw_selfie_url if assets else None,
        "normalized_image_url": assets.normalized_image_url if assets else None,
        "lipsync_seg2_url": assets.lipsync_seg2_url if assets else None,
        "lipsync_seg4_url": assets.lipsync_seg4_url if assets else None,
        "final_video_url": assets.final_video_url if assets else None,
        "terms_accepted": terms_accepted,
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
    valid_statuses = ['wait', 'queued', 'photo_processing', 'photo_done', 'lipsync_processing',
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
    valid_statuses = ['wait', 'queued', 'photo_processing', 'photo_done', 'lipsync_processing',
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
