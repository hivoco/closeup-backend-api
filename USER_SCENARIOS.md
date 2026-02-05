# Close-Up Video Submission - User Scenarios

## Overview
This document describes all possible user scenarios in the Close-Up video submission system, including how the system handles new users, unverified users, verified users, and various video processing states.

---

## Scenario 1: New User - First Time Submission

### User Status
- Mobile number: Never used before
- Verification status: Not verified
- Video count: 0

### Flow
1. User fills the form with:
   - Mobile number
   - Gender
   - Attribute love
   - Relationship status
   - Vibe
   - Takes a selfie (validated by AI)

2. User submits the form

3. **Backend Response:**
   ```json
   {
     "status": "otp_sent",
     "message": "OTP sent successfully",
     "job_id": 123,
     "mobile_number": "9876543210"
   }
   ```

4. **Frontend Action:**
   - Shows OTP verification screen
   - User enters 6-digit OTP

5. User verifies OTP

6. **Backend Response:**
   ```json
   {
     "status": "verified",
     "message": "Verification successful",
     "job_id": 123
   }
   ```

7. **Result:**
   - User record created in database
   - UserVerification record created (is_verified = true)
   - VideoJob created with status = "queued"
   - VideoAssets created with selfie S3 URL
   - User redirected to video processing page

---

## Scenario 2: Old User Without Verification (OTP Not Verified Yet)

### User Status
- Mobile number: Exists in database
- Verification status: `is_verified = false`
- Video count: 0
- Previous OTP: Not verified or expired

### Flow
1. User fills and submits the form

2. **Backend Response:**
   ```json
   {
     "status": "otp_sent",
     "message": "OTP sent successfully",
     "job_id": 124,
     "mobile_number": "9876543210"
   }
   ```

3. **Frontend Action:**
   - Shows OTP verification screen
   - User must verify OTP to proceed

4. User verifies OTP

5. **Result:**
   - UserVerification updated (is_verified = true, verified_at = current IST time)
   - VideoJob created with status = "queued"
   - VideoAssets created with selfie S3 URL
   - User redirected to video processing page

---

## Scenario 3: Verified User - First Video Submission

### User Status
- Mobile number: Exists and verified
- Verification status: `is_verified = true`
- Video count: 0 (or all previous videos completed)
- No pending videos

### Flow
1. User fills and submits the form

2. **Backend Response:**
   ```json
   {
     "status": "video_created",
     "message": "Video job created successfully",
     "job_id": 125,
     "mobile_number": "9876543210"
   }
   ```

3. **Frontend Action:**
   - ✅ Shows success toast: "Video submitted successfully!"
   - ❌ NO OTP verification needed (user already verified)
   - Redirects to video processing/tracking page

4. **Result:**
   - VideoJob created with status = "queued"
   - VideoAssets created with selfie S3 URL
   - Video enters processing pipeline

---

## Scenario 4: Verified User - Video Already Being Processed

### User Status
- Mobile number: Exists and verified
- Verification status: `is_verified = true`
- Video count: 1
- Existing video status: "queued", "photo_processing", "photo_done", "lipsync_processing", "lipsync_done", "stitching"

### Flow
1. User fills and submits the form

2. **Backend Response:**
   ```json
   {
     "status": "pending",
     "message": "You already have a video being processed. Please wait until it's complete.",
     "job_id": 125,
     "mobile_number": "9876543210"
   }
   ```

3. **Frontend Action:**
   - ⚠️ Shows warning toast (yellow): "Your previous video is still being processed. Please wait..."
   - Shows existing job_id and status
   - Form remains visible but submission blocked

4. **Result:**
   - NO new video job created
   - User must wait for current video to complete
   - User can track existing video status

---

## Scenario 5: Verified User - Previous Video Completed, New Submission

### User Status
- Mobile number: Exists and verified
- Verification status: `is_verified = true`
- Video count: 1 or more
- Previous video status: "uploaded" or "sent"

### Flow
1. User fills and submits the form

2. **Backend Response:**
   ```json
   {
     "status": "video_created",
     "message": "Video job created successfully",
     "job_id": 126,
     "mobile_number": "9876543210"
   }
   ```

3. **Frontend Action:**
   - ✅ Shows success toast: "Video submitted successfully!"
   - NO OTP verification needed
   - Redirects to video processing page

4. **Result:**
   - New VideoJob created with status = "queued"
   - video_count incremented
   - New video enters processing pipeline

---

## Scenario 6: Verified User - Previous Video Failed, New Submission

### User Status
- Mobile number: Exists and verified
- Verification status: `is_verified = true`
- Video count: 1
- Previous video status: "failed"

### Flow
1. User fills and submits the form

2. **Backend Response:**
   ```json
   {
     "status": "video_created",
     "message": "Video job created successfully",
     "job_id": 127,
     "mobile_number": "9876543210"
   }
   ```

3. **Frontend Action:**
   - ✅ Shows success toast: "Video submitted successfully!"
   - NO OTP verification needed
   - Redirects to video processing page

4. **Result:**
   - New VideoJob created with status = "queued"
   - Failed video remains in database (status = "failed")
   - New video enters processing pipeline

---

## Scenario 7: Verified User - 2nd Video Submission While 1st is Queued

### User Status
- Mobile number: Exists and verified
- Verification status: `is_verified = true`
- Video count: 1
- 1st Video status: "queued" (not yet sent to WhatsApp)

### Flow
1. User tries to submit 2nd video

2. **Backend Check:**
   - Queries for existing video jobs with status NOT IN ("uploaded", "sent", "failed")
   - Finds job #125 with status = "queued"

3. **Backend Response:**
   ```json
   {
     "status": "pending",
     "message": "You already have a video being processed. Please wait until it's complete.",
     "job_id": 125,
     "mobile_number": "9876543210"
   }
   ```

4. **Frontend Action:**
   - ⚠️ Shows warning toast: "Your previous video is still being processed..."
   - Prevents new submission
   - Shows link to track existing job #125

5. **Result:**
   - NO new video created
   - User must wait for job #125 to complete or fail

---

## Scenario 8: Verified User - 2nd Video After 1st Sent to WhatsApp

### User Status
- Mobile number: Exists and verified
- Verification status: `is_verified = true`
- Video count: 1
- 1st Video status: "sent" (successfully delivered to WhatsApp)

### Flow
1. User submits 2nd video

2. **Backend Check:**
   - Queries for existing video jobs with status NOT IN ("uploaded", "sent", "failed")
   - Finds NO pending jobs (1st video is "sent")

3. **Backend Response:**
   ```json
   {
     "status": "video_created",
     "message": "Video job created successfully",
     "job_id": 128,
     "mobile_number": "9876543210"
   }
   ```

4. **Frontend Action:**
   - ✅ Shows success toast: "Video submitted successfully!"
   - Redirects to video processing page

5. **Result:**
   - New VideoJob #128 created with status = "queued"
   - video_count incremented to 2
   - Both videos stored in database (1st = "sent", 2nd = "queued")

---

## Video Processing States

### Complete Video Lifecycle

1. **queued** → Initial state when job is created
2. **photo_processing** → User's selfie being processed
3. **photo_done** → Photo processing complete
4. **lipsync_processing** → Lip-sync video generation in progress
5. **lipsync_done** → Lip-sync complete
6. **stitching** → Combining video segments
7. **uploaded** → Video uploaded to final storage
8. **sent** → Video sent to user via WhatsApp ✅
9. **failed** → Processing failed at any stage ❌

---

## OTP Flow Details

### OTP Generation
- 6-digit random number
- Valid for 10 minutes (configurable via `OTP_EXPIRY_MINUTES`)
- Stored as hashed value in database
- Maximum 3 verification attempts

### OTP Verification
- User enters 6-digit code
- Backend validates:
  - OTP hash matches
  - OTP not expired
  - OTP not already used
  - Attempts < 3

### OTP Success
- `UserVerification.is_verified` set to `true`
- `verified_at` timestamp recorded (IST)
- User can submit videos without OTP from now on

---

## Photo Validation Rules (Groq AI)

### APPROVED ✅
- Exactly one real adult human face
- Front-facing, looking at camera
- Clear, well-lit, close-up selfie
- Neutral background
- No religious, NSFW, or invalid elements

### REJECT_RELIGIOUS ❌
- Religious symbols (cross, crescent, tilak, bindi, etc.)
- Religious clothing (hijab, turban, priest robes, etc.)
- Places of worship
- Religious ceremonies

### REJECT_NSFW ❌
- Nudity or partial nudity
- Sexual or suggestive poses
- Bedroom scenes
- Lingerie or revealing clothing

### REJECT_INVALID ❌
- Photo of a photo/screen
- AI-generated, cartoon, anime
- Multiple people/faces
- Face not centered or not facing camera
- Sunglasses, masks, face coverings
- Child or minor
- Celebrity or stock photo
- Blurry or low quality

---

## API Endpoints Summary

### 1. Submit Video
**POST** `/api/v1/video/submit`

**Request:**
```
FormData {
  mobile_number: "9876543210"
  gender: "male"
  attribute_love: "Smile"
  relationship_status: "Dating"
  vibe: "Romance"
  photo: File
}
```

**Responses:**
- `otp_sent` - New/unverified user
- `pending` - Video already being processed
- `video_created` - New video job created (verified user)

---

### 2. Verify OTP
**POST** `/api/v1/auth/verify-otp`

**Request:**
```json
{
  "mobile_number": "9876543210",
  "otp": "123456"
}
```

**Response:**
```json
{
  "status": "verified",
  "message": "Verification successful",
  "job_id": 123
}
```

---

### 3. Photo Validation
**POST** `/api/v1/photo-validation/check_photo`

**Request:**
```
FormData {
  photo: File (max 10MB)
}
```

**Response:**
```json
{
  "valid": true,
  "message": "Photo validated successfully!",
  "label": "APPROVED",
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 1,
    "total_tokens": 1235
  }
}
```

---

### 4. List Video Jobs (Admin)
**GET** `/api/v1/video-jobs/list`

**Query Parameters:**
- `status` (optional): Filter by status
- `from_date` (optional): Filter from date (YYYY-MM-DD)
- `to_date` (optional): Filter to date (YYYY-MM-DD)
- `limit` (default: 100): Number of records

**Response:**
```json
{
  "total": 150,
  "jobs": [
    {
      "id": 123,
      "user_id": "uuid",
      "mobile_number": "9876543210",
      "gender": "male",
      "status": "sent",
      "retry_count": 0,
      "created_at": "2026-01-08T14:30:00+05:30",
      "updated_at": "2026-01-08T15:45:00+05:30"
    }
  ]
}
```

---

### 5. Update Job Status (Admin)
**PATCH** `/api/v1/video-jobs/update-job`

**Query Parameters:**
- `job_id`: Job ID to update
- `status`: New status

**Behavior:**
- Updates job status
- Increments `retry_count` by 1
- Sets `failed_stage` to NULL
- Sets `last_error_code` to NULL
- Updates `updated_at` to current IST time

**Response:**
```json
{
  "message": "Job status updated successfully",
  "job_id": 123,
  "old_status": "failed",
  "new_status": "queued",
  "retry_count": 3
}
```

---

## Database Models (IST Timezone)

All datetime fields now use **IST (Indian Standard Time, UTC+5:30)**

### Auto-filled Fields
- `created_at` - Automatically set to current IST time on record creation
- `updated_at` - Automatically set to current IST time on record update

### Tables
1. **users** - User records with encrypted phone numbers
2. **user_verification** - OTP verification status
3. **user_otp** - OTP records with expiry times
4. **video_jobs** - Video processing jobs
5. **video_assets** - Video asset URLs (selfie, processed video, etc.)

---

## Frontend Toast Notifications

### Success (Green) ✅
- "Photo validated successfully! ✓"
- "OTP verified successfully! 🎉"
- "Video submitted successfully!"
- "Job status updated successfully!"

### Error (Red) ❌
- "Photo validation failed. Please retake."
- "Invalid OTP. Please try again."
- "Failed to submit video."

### Warning (Yellow) ⚠️
- "Your previous video is still being processed. Please wait..."

### Info (Blue) ℹ️
- "New OTP sent successfully!"
- "Validating photo..."

---

## Summary Table

| Scenario | User Status | Verification | Pending Video | Response Status | OTP Required | New Job Created |
|----------|-------------|--------------|---------------|-----------------|--------------|-----------------|
| 1. New User | Not Exists | No | No | `otp_sent` | ✅ Yes | ✅ Yes |
| 2. Unverified User | Exists | No | No | `otp_sent` | ✅ Yes | ✅ Yes |
| 3. Verified - 1st Video | Exists | Yes | No | `video_created` | ❌ No | ✅ Yes |
| 4. Verified - Video Processing | Exists | Yes | Yes | `pending` | ❌ No | ❌ No |
| 5. Verified - Previous Complete | Exists | Yes | No (completed) | `video_created` | ❌ No | ✅ Yes |
| 6. Verified - Previous Failed | Exists | Yes | No (failed) | `video_created` | ❌ No | ✅ Yes |
| 7. 2nd Video - 1st Queued | Exists | Yes | Yes (queued) | `pending` | ❌ No | ❌ No |
| 8. 2nd Video - 1st Sent | Exists | Yes | No (sent) | `video_created` | ❌ No | ✅ Yes |

---

## Key Business Rules

1. **One Video at a Time**: Users can only have one video in processing state at a time
2. **OTP Required Once**: After successful OTP verification, user never needs OTP again
3. **Photo Validation**: All photos must pass Groq AI validation before submission
4. **10MB Photo Limit**: Maximum photo size is 10MB
5. **OTP Expiry**: OTP valid for 10 minutes with max 3 attempts
6. **IST Timezone**: All timestamps stored and displayed in Indian Standard Time
7. **Retry Logic**: Admin can retry failed jobs, which increments retry_count and clears error fields
8. **Duplicate Prevention**: Phone number hashing prevents duplicate user records

---

## Technology Stack

### Backend
- FastAPI (Python)
- SQLAlchemy ORM
- MySQL Database
- AWS S3 (File Storage)
- Groq AI API (Photo Validation)
- Bcrypt (Password Hashing)
- Cryptography (Phone Encryption)

### Frontend
- Next.js 16 (App Router)
- React 19
- TypeScript
- Tailwind CSS 4
- React Toastify (Notifications)
- MediaDevices API (Camera)

---

## Contact & Support

For questions or issues, please contact the development team.

**Last Updated**: January 8, 2026
**Version**: 1.0
