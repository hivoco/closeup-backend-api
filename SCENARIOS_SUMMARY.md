# Close-Up Video Submission - Scenarios Summary

## Quick Reference Guide

### What Happens When User Submits?

```
User Submits Form
       ↓
Check: Does mobile number exist in database?
       ↓
    ┌──────┴──────┐
   YES            NO
    ↓              ↓
Check Verified   Create New User
    ↓              ↓
 ┌──────┴──────┐  Send OTP
YES            NO   ↓
 ↓              ↓  Show OTP Screen
Check Pending  Send OTP
Video           ↓
 ↓           Show OTP Screen
┌────┴────┐
YES      NO
 ↓        ↓
BLOCK   CREATE
Pending  Video
Warning   Job
```

---

## All Scenarios - Quick Summary

### 1️⃣ NEW USER (Never Used App Before)

**User Details:**
- Mobile: 9876543210 (NOT in database)
- Verified: ❌ No
- Previous Videos: 0

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔧 Backend creates new User record
5. 📩 Backend sends OTP via SMS/WhatsApp
6. 📱 Frontend shows OTP verification screen
7. ✅ User enters 6-digit OTP
8. ✅ OTP verified successfully
9. 🎬 Video job created (status: "queued")
10. ✅ User redirected to video processing page

**API Response:**
```json
{
  "status": "otp_sent",
  "message": "OTP sent successfully",
  "job_id": 123,
  "mobile_number": "9876543210"
}
```

**Result:**
- User created ✅
- OTP sent ✅
- Video job created AFTER OTP verification ✅
- User is now verified for future submissions ✅

---

### 2️⃣ OLD USER - NOT VERIFIED (Has Account But Never Verified OTP)

**User Details:**
- Mobile: 9876543210 (EXISTS in database)
- Verified: ❌ No (`is_verified = false`)
- Previous Videos: 0

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔍 Backend finds existing user
5. 🔍 Backend checks: `is_verified = false`
6. 📩 Backend sends NEW OTP
7. 📱 Frontend shows OTP verification screen
8. ✅ User enters 6-digit OTP
9. ✅ OTP verified → `is_verified = true`
10. 🎬 Video job created (status: "queued")
11. ✅ User redirected to video processing page

**API Response:**
```json
{
  "status": "otp_sent",
  "message": "OTP sent successfully",
  "job_id": 124,
  "mobile_number": "9876543210"
}
```

**Result:**
- User already exists ✅
- New OTP sent ✅
- User gets verified after entering OTP ✅
- Video job created AFTER OTP verification ✅
- User won't need OTP again ✅

---

### 3️⃣ OLD USER - VERIFIED - NO PENDING VIDEO (First Video or All Previous Complete)

**User Details:**
- Mobile: 9876543210 (EXISTS in database)
- Verified: ✅ Yes (`is_verified = true`)
- Previous Videos: 0 OR all videos have status "uploaded"/"sent"/"failed"

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔍 Backend finds existing user
5. 🔍 Backend checks: `is_verified = true` ✅
6. 🔍 Backend checks: No pending videos ✅
7. 🎬 Video job created immediately (status: "queued")
8. ✅ Success toast shown
9. ✅ User redirected to video processing page

**API Response:**
```json
{
  "status": "video_created",
  "message": "Video job created successfully",
  "job_id": 125,
  "mobile_number": "9876543210"
}
```

**Result:**
- ❌ NO OTP required (already verified!)
- Video job created immediately ✅
- User can track video progress ✅

---

### 4️⃣ OLD USER - VERIFIED - VIDEO BEING PROCESSED (Can't Submit New One)

**User Details:**
- Mobile: 9876543210 (EXISTS in database)
- Verified: ✅ Yes (`is_verified = true`)
- Previous Videos: 1 video with status = "queued" or "photo_processing" or "lipsync_processing" etc.

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔍 Backend finds existing user
5. 🔍 Backend checks: `is_verified = true` ✅
6. 🔍 Backend checks: Pending video found! ⚠️
7. 🚫 Backend BLOCKS new submission
8. ⚠️ Frontend shows WARNING toast
9. 📊 Shows existing job ID and status

**API Response:**
```json
{
  "status": "pending",
  "message": "You already have a video being processed. Please wait until it's complete.",
  "job_id": 125,
  "mobile_number": "9876543210"
}
```

**Result:**
- ❌ NO new video job created
- ⚠️ User must wait for current video to complete
- 📊 User can track existing video progress
- ✅ Prevents duplicate video submissions

---

### 5️⃣ OLD USER - 2ND VIDEO AFTER 1ST COMPLETED

**User Details:**
- Mobile: 9876543210 (EXISTS in database)
- Verified: ✅ Yes (`is_verified = true`)
- Previous Videos: 1 video with status = "sent" (delivered to WhatsApp)
- Video Count: 1

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔍 Backend finds existing user
5. 🔍 Backend checks: `is_verified = true` ✅
6. 🔍 Backend checks: Previous video = "sent" (complete) ✅
7. 🎬 New video job created (job_id: 126, status: "queued")
8. 🔢 video_count incremented: 1 → 2
9. ✅ Success toast shown
10. ✅ User redirected to video processing page

**API Response:**
```json
{
  "status": "video_created",
  "message": "Video job created successfully",
  "job_id": 126,
  "mobile_number": "9876543210"
}
```

**Result:**
- ❌ NO OTP required
- 🎬 New video job created ✅
- 🔢 video_count = 2
- 📊 Both videos stored in database (1st: "sent", 2nd: "queued")

---

### 6️⃣ OLD USER - PREVIOUS VIDEO FAILED

**User Details:**
- Mobile: 9876543210 (EXISTS in database)
- Verified: ✅ Yes (`is_verified = true`)
- Previous Videos: 1 video with status = "failed"
- Failed Stage: "lipsync" (example)

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔍 Backend finds existing user
5. 🔍 Backend checks: `is_verified = true` ✅
6. 🔍 Backend checks: Previous video = "failed" (not blocking) ✅
7. 🎬 New video job created (job_id: 127, status: "queued")
8. ✅ Success toast shown
9. ✅ User redirected to video processing page

**API Response:**
```json
{
  "status": "video_created",
  "message": "Video job created successfully",
  "job_id": 127,
  "mobile_number": "9876543210"
}
```

**Result:**
- ❌ NO OTP required
- 🎬 New video job created ✅
- 📊 Failed video remains in database (for debugging)
- ✅ User can retry with new submission

---

### 7️⃣ USER TRIES 2ND VIDEO WHILE 1ST IS QUEUED

**User Details:**
- Mobile: 9876543210 (EXISTS in database)
- Verified: ✅ Yes (`is_verified = true`)
- Previous Videos: 1 video (job_id: 125, status: "queued")

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔍 Backend finds existing user
5. 🔍 Backend checks: `is_verified = true` ✅
6. 🔍 Backend checks: Video job #125 is "queued" ⚠️
7. 🚫 Backend BLOCKS new submission
8. ⚠️ Frontend shows WARNING toast
9. 📊 Shows job #125 status

**API Response:**
```json
{
  "status": "pending",
  "message": "You already have a video being processed. Please wait until it's complete.",
  "job_id": 125,
  "mobile_number": "9876543210"
}
```

**Result:**
- ❌ NO new video job created
- ⚠️ User must wait for job #125
- 📊 Can track job #125 progress
- ✅ Prevents system overload

---

### 8️⃣ USER SUBMITS 2ND VIDEO AFTER 1ST SENT TO WHATSAPP

**User Details:**
- Mobile: 9876543210 (EXISTS in database)
- Verified: ✅ Yes (`is_verified = true`)
- Previous Videos: 1 video (job_id: 125, status: "sent")
- Video Count: 1

**What Happens:**
1. ✅ User fills form + takes selfie
2. ✅ Photo validated by Groq AI
3. ✅ User submits form
4. 🔍 Backend finds existing user
5. 🔍 Backend checks: `is_verified = true` ✅
6. 🔍 Backend checks: Job #125 is "sent" (complete) ✅
7. 🎬 New video job created (job_id: 128, status: "queued")
8. 🔢 video_count incremented: 1 → 2
9. ✅ Success toast shown
10. ✅ User redirected to video processing page

**API Response:**
```json
{
  "status": "video_created",
  "message": "Video job created successfully",
  "job_id": 128,
  "mobile_number": "9876543210"
}
```

**Result:**
- ❌ NO OTP required
- 🎬 New video job #128 created ✅
- 🔢 video_count = 2
- 📊 Both videos in database (125: "sent", 128: "queued")
- ✅ User can create multiple videos over time

---

## Decision Tree Flowchart

```
┌─────────────────────────────────────┐
│     USER SUBMITS FORM + PHOTO       │
└─────────────┬───────────────────────┘
              ↓
┌─────────────────────────────────────┐
│   Does Mobile Number Exist?         │
└─────────────┬───────────────────────┘
              ↓
         ┌────┴────┐
        NO         YES
         ↓          ↓
    CREATE USER    ↓
         ↓          ↓
    SEND OTP   ┌───────────────────┐
         ↓     │  Is User Verified? │
    OTP SCREEN └────────┬──────────┘
         ↓              ↓
    VERIFY OTP    ┌────┴────┐
         ↓       NO        YES
    CREATE JOB    ↓          ↓
         ↓    SEND OTP  ┌──────────────────┐
         ↓        ↓     │ Has Pending Video?│
         ↓   OTP SCREEN └────┬─────────────┘
         ↓        ↓          ↓
         ↓   VERIFY OTP ┌────┴────┐
         ↓        ↓    YES       NO
         ↓   CREATE JOB ↓          ↓
         ↓        ↓   BLOCK    CREATE JOB
         ↓        ↓   (pending)    ↓
         └────────┴───────┬────────┘
                          ↓
                   ┌────────────┐
                   │   DONE ✅   │
                   └────────────┘
```

---

## Summary Comparison Table

| # | Scenario | User Exists? | Verified? | Pending Video? | Response | OTP? | Job Created? |
|---|----------|--------------|-----------|----------------|----------|------|--------------|
| 1 | New User | ❌ No | ❌ No | ❌ No | `otp_sent` | ✅ Yes | After OTP ✅ |
| 2 | Old Unverified | ✅ Yes | ❌ No | ❌ No | `otp_sent` | ✅ Yes | After OTP ✅ |
| 3 | Verified - No Pending | ✅ Yes | ✅ Yes | ❌ No | `video_created` | ❌ No | Immediate ✅ |
| 4 | Verified - Processing | ✅ Yes | ✅ Yes | ✅ Yes | `pending` | ❌ No | ❌ Blocked |
| 5 | 2nd Video - 1st Done | ✅ Yes | ✅ Yes | ❌ No | `video_created` | ❌ No | Immediate ✅ |
| 6 | Previous Failed | ✅ Yes | ✅ Yes | ❌ No | `video_created` | ❌ No | Immediate ✅ |
| 7 | 2nd While 1st Queued | ✅ Yes | ✅ Yes | ✅ Yes | `pending` | ❌ No | ❌ Blocked |
| 8 | 2nd After 1st Sent | ✅ Yes | ✅ Yes | ❌ No | `video_created` | ❌ No | Immediate ✅ |

---

## Key Business Rules

### ✅ When Video Job is Created:
- New user after OTP verification
- Verified user with NO pending videos
- Verified user whose previous video is "uploaded", "sent", or "failed"

### ❌ When Video Job is Blocked:
- Verified user with pending video (status: queued, photo_processing, lipsync_processing, stitching)

### 🔐 When OTP is Required:
- New users (first time)
- Old users who never verified OTP (`is_verified = false`)

### ⚡ When OTP is NOT Required:
- Verified users (`is_verified = true`)
- OTP verification is ONE-TIME only

---

## Video Status Lifecycle

```
queued
  ↓
photo_processing
  ↓
photo_done
  ↓
lipsync_processing
  ↓
lipsync_done
  ↓
stitching
  ↓
uploaded
  ↓
sent ✅ (Delivered to WhatsApp)

OR

failed ❌ (Any stage can fail)
```

### Pending States (Block New Submissions):
- `queued`
- `photo_processing`
- `photo_done`
- `lipsync_processing`
- `lipsync_done`
- `stitching`

### Complete States (Allow New Submissions):
- `uploaded`
- `sent`
- `failed`

---

## User Verification Status

### is_verified = false
- User exists but never verified OTP
- **Action:** Send OTP on every submission
- **Job Creation:** After OTP verification

### is_verified = true
- User verified OTP at least once
- **Action:** NO OTP required anymore
- **Job Creation:** Immediate (if no pending video)

---

## Frontend Toast Notifications

### ✅ Success (Green)
- "Photo validated successfully! ✓"
- "OTP verified successfully! 🎉"
- "Video submitted successfully!"

### ❌ Error (Red)
- "Photo validation failed. Please retake."
- "Invalid OTP. Please try again."
- "Failed to submit video."

### ⚠️ Warning (Yellow)
- "Your previous video is still being processed. Please wait..."
- Shown when user has pending video

### ℹ️ Info (Blue)
- "New OTP sent successfully!"
- "Validating photo..."

---

## Photo Validation (Groq AI)

### ✅ APPROVED
- One adult face, front-facing
- Clear, well-lit selfie
- No religious/NSFW/invalid elements

### ❌ REJECT_RELIGIOUS
- Religious symbols (tilak, bindi, cross, etc.)
- Religious clothing (hijab, turban, etc.)

### ❌ REJECT_NSFW
- Nudity, suggestive content
- Bedroom scenes, revealing clothing

### ❌ REJECT_INVALID
- Multiple faces, side profile
- Sunglasses, masks
- AI-generated, cartoon
- Blurry, low quality
- Child/minor

**File Size Limit:** 10MB

---

## Quick Lookup: "What Happens If..."

### Old user comes who is NOT verified?
→ **Scenario 2**: Send OTP → User verifies → Video created

### Old user comes who IS verified with NO pending video?
→ **Scenario 3**: Video created immediately (NO OTP)

### Old user comes who IS verified with video being processed?
→ **Scenario 4**: BLOCKED with warning (wait for current video)

### Old user comes after previous video was sent?
→ **Scenario 5 or 8**: New video created immediately (NO OTP)

### Old user comes after previous video failed?
→ **Scenario 6**: New video created immediately (NO OTP)

### User tries to submit 2nd video while 1st is still queued?
→ **Scenario 7**: BLOCKED with warning (one video at a time)

---

## Database Tables

### users
- Stores encrypted phone numbers
- `is_verified` managed in `user_verification` table

### user_verification
- `is_verified` (boolean)
- `verified_at` (datetime)
- `verification_method` ("otp")

### user_otp
- OTP hash (not plain text)
- `expires_at` (10 minutes from creation)
- `is_used` (prevents reuse)
- Max 3 attempts

### video_jobs
- Job status tracking
- `retry_count` for failed jobs
- `failed_stage` and `last_error_code` for debugging

### video_assets
- Stores S3 URLs (selfie, processed video)

**All timestamps use IST (Indian Standard Time, UTC+5:30)**

---

## API Endpoints

### POST /api/v1/video/submit
Submit form + photo → Returns `otp_sent`, `pending`, or `video_created`

### POST /api/v1/auth/verify-otp
Verify 6-digit OTP → Returns `verified` status

### POST /api/v1/photo-validation/check_photo
Validate photo with Groq AI → Returns `valid`/`invalid` with label

### GET /api/v1/video-jobs/list
List all video jobs (Admin) → Supports filtering

### PATCH /api/v1/video-jobs/update-job
Update job status (Admin) → Increments retry_count, clears errors

---

**Last Updated:** January 8, 2026
**Version:** 1.0
