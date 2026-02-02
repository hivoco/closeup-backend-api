"""
Duplicate users & jobs from Feb 1 2026 (status=sent) into Feb 2 2026.

For each source job with status "sent" on 2026-02-01:
  - Creates a NEW user (new UUID, same phone_encrypted, same fields)
  - Creates a NEW video_job (same fields, new id, date=Feb 2, random time)
  - Creates NEW video_assets (copied from original)

Usage:
    python duplicate.py

Run from the closeup_backend directory.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import random
import hashlib
from datetime import datetime
from uuid import uuid4
from sqlalchemy import text
from app.core.database import engine
from app.core.config import settings

SOURCE_DATE = "2026-02-01"
TARGET_DATE = datetime(2026, 2, 2)
LIMIT = 20  # Exactly 20 new users/jobs


def _unique_phone_hash(original_phone_hash: str, index: int) -> str:
    """Generate a unique phone_hash for duplicated users.
    Uses the original hash + index to create a new unique hash,
    so it won't collide with the original or other duplicates.
    """
    return hashlib.sha256(
        f"{original_phone_hash}_dup_{index}{settings.PHONE_HASH_SALT}".encode()
    ).hexdigest()


def _random_time() -> datetime:
    """Random time on Feb 2, 2026 between 08:00 and 22:00."""
    hour = random.randint(8, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return TARGET_DATE.replace(hour=hour, minute=minute, second=second)


def run():
    with engine.connect() as conn:
        # Step 1: Find all "sent" jobs from Feb 1, 2026
        source_jobs = conn.execute(
            text(
                "SELECT vj.*, u.phone_encrypted, u.phone_hash, "
                "u.video_count, u.terms_accepted "
                "FROM video_jobs vj "
                "JOIN users u ON vj.user_id = u.id "
                "WHERE DATE(vj.created_at) = :source_date "
                "AND vj.status = 'sent' "
                "ORDER BY vj.id"
            ),
            {"source_date": SOURCE_DATE},
        ).fetchall()

        if not source_jobs:
            print(f"No jobs with status 'sent' found on {SOURCE_DATE}. Aborting.")
            return

        print(f"Found {len(source_jobs)} sent job(s) on {SOURCE_DATE}:")
        for job in source_jobs:
            print(f"  Job ID: {job.id}, User: {job.user_id}, Status: {job.status}")

        # Step 2: Get next available job ID
        max_id_row = conn.execute(text("SELECT MAX(id) as max_id FROM video_jobs")).fetchone()
        next_job_id = (max_id_row.max_id or 0) + 1
        print(f"\nStarting new job IDs from {next_job_id}")

        created_count = 0

        for i in range(LIMIT):
            # Cycle through source jobs if fewer than LIMIT
            src = source_jobs[i % len(source_jobs)]
            job_time = _random_time()
            new_user_id = str(uuid4())
            new_phone_hash = _unique_phone_hash(src.phone_hash, next_job_id + i)

            # Step 3: Create new user (same fields, new id, same phone_encrypted)
            conn.execute(
                text(
                    "INSERT INTO users "
                    "(id, phone_encrypted, phone_hash, video_count, terms_accepted, "
                    "created_at, updated_at) "
                    "VALUES (:id, :phone_encrypted, :phone_hash, :video_count, "
                    ":terms_accepted, :created_at, :updated_at)"
                ),
                {
                    "id": new_user_id,
                    "phone_encrypted": src.phone_encrypted,
                    "phone_hash": new_phone_hash,
                    "video_count": src.video_count,
                    "terms_accepted": src.terms_accepted,
                    "created_at": job_time,
                    "updated_at": job_time,
                },
            )

            # Step 4: Create user_verification (verified)
            conn.execute(
                text(
                    "INSERT INTO user_verification "
                    "(user_id, is_verified, verified_at, verification_method, "
                    "created_at, updated_at) "
                    "VALUES (:user_id, :is_verified, :verified_at, "
                    ":verification_method, :created_at, :updated_at)"
                ),
                {
                    "user_id": new_user_id,
                    "is_verified": True,
                    "verified_at": job_time,
                    "verification_method": "otp",
                    "created_at": job_time,
                    "updated_at": job_time,
                },
            )

            # Step 5: Create new video_job (same fields, new id, new user, new date)
            new_job_id = next_job_id + i
            conn.execute(
                text(
                    "INSERT INTO video_jobs "
                    "(id, user_id, gender, attribute_love, relationship_status, vibe, "
                    "status, retry_count, locked_by, locked_at, failed_stage, "
                    "last_error_code, created_at, updated_at) "
                    "VALUES (:id, :user_id, :gender, :attribute_love, :relationship_status, "
                    ":vibe, :status, :retry_count, :locked_by, :locked_at, :failed_stage, "
                    ":last_error_code, :created_at, :updated_at)"
                ),
                {
                    "id": new_job_id,
                    "user_id": new_user_id,
                    "gender": src.gender,
                    "attribute_love": src.attribute_love,
                    "relationship_status": src.relationship_status,
                    "vibe": src.vibe,
                    "status": src.status,
                    "retry_count": src.retry_count,
                    "locked_by": src.locked_by,
                    "locked_at": src.locked_at,
                    "failed_stage": src.failed_stage,
                    "last_error_code": src.last_error_code,
                    "created_at": job_time,
                    "updated_at": job_time,
                },
            )

            # Step 6: Duplicate video_assets
            assets = conn.execute(
                text("SELECT * FROM video_assets WHERE job_id = :job_id"),
                {"job_id": src.id},
            ).fetchone()

            if assets:
                conn.execute(
                    text(
                        "INSERT INTO video_assets "
                        "(job_id, raw_selfie_url, normalized_image_url, "
                        "lipsync_seg2_url, lipsync_seg4_url, final_video_url, "
                        "error, created_at, updated_at) "
                        "VALUES (:job_id, :raw_selfie_url, :normalized_image_url, "
                        ":lipsync_seg2_url, :lipsync_seg4_url, :final_video_url, "
                        ":error, :created_at, :updated_at)"
                    ),
                    {
                        "job_id": new_job_id,
                        "raw_selfie_url": assets.raw_selfie_url,
                        "normalized_image_url": assets.normalized_image_url,
                        "lipsync_seg2_url": assets.lipsync_seg2_url,
                        "lipsync_seg4_url": assets.lipsync_seg4_url,
                        "final_video_url": assets.final_video_url,
                        "error": assets.error,
                        "created_at": job_time,
                        "updated_at": job_time,
                    },
                )

            created_count += 1
            print(
                f"[{created_count}] Job #{new_job_id} at {job_time.strftime('%H:%M:%S')} "
                f"| User: {new_user_id[:8]}... "
                f"| Copied from job #{src.id}"
            )

        conn.commit()
        print(f"\nDone! {created_count} new entries created:")
        print(f"  - {created_count} users (each with unique ID, same mobile number)")
        print(f"  - {created_count} user_verifications (all verified)")
        print(f"  - {created_count} video_jobs (IDs {next_job_id}-{next_job_id + created_count - 1})")
        print(f"  - video_assets copied for each job")
        print(f"  - All dated 2026-02-02 with random times")


if __name__ == "__main__":
    run()
