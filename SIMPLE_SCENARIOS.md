# Close-Up Video Submission - Simple Scenarios

## Scenario 1: New User - First Time Submission

**User Status:**
- Mobile number does not exist in database
- Never used the app before

**What Happens:**
1. User fills the form and takes a selfie
2. Photo is validated by AI
3. Backend creates new user account
4. **We send OTP to user's mobile number**
5. User enters 6-digit OTP
6. OTP is verified successfully
7. **We accept the request and start video processing**
8. Video job created with status "queued"
9. User gets confirmation and can track video progress

---

## Scenario 2: Old User - Not Verified

**User Status:**
- Mobile number exists in database
- User registered before but never verified OTP
- `is_verified = false`

**What Happens:**
1. User fills the form and takes a selfie
2. Photo is validated by AI
3. Backend finds existing user account
4. Backend checks: User is not verified
5. **We send OTP to user's mobile number**
6. User enters 6-digit OTP
7. OTP is verified successfully
8. User verification status updated to `is_verified = true`
9. **We start working on video creation**
10. Video job created with status "queued"
11. User gets confirmation and can track video progress

**Note:** After this verification, user will never need OTP again.

---

## Scenario 3: Old User - Verified - With Pending Video

**User Status:**
- Mobile number exists in database
- User is verified (`is_verified = true`)
- Has one video already being processed
- Previous video status: "queued", "photo_processing", "lipsync_processing", or "stitching"

**What Happens:**
1. User fills the form and takes a selfie
2. Photo is validated by AI
3. Backend finds existing user account
4. Backend checks: User is verified ✓
5. Backend checks: User already has a pending video ⚠️
6. **We show message: "You already have one video being processed. As soon as it is completed, you will get a WhatsApp message. Only then you can request for a second video."**
7. Request is rejected - NO new video job created
8. User can see their existing video job ID and track its progress
9. User must wait until current video status becomes "sent" (delivered to WhatsApp)

**Note:** We only allow ONE video at a time to prevent system overload.

---

## Scenario 4: Old User - Verified - No Pending Video

**User Status:**
- Mobile number exists in database
- User is verified (`is_verified = true`)
- No pending videos OR previous video completed (status: "sent", "uploaded", or "failed")

**What Happens:**
1. User fills the form and takes a selfie
2. Photo is validated by AI
3. Backend finds existing user account
4. Backend checks: User is verified ✓
5. Backend checks: No pending videos ✓
6. **We accept the request immediately (NO OTP required)**
7. **We start processing the video**
8. Video job created with status "queued"
9. User gets confirmation and can track video progress
10. User's video count is incremented

**Note:** This is the fastest flow - no OTP needed, instant video creation!

---

## Summary Table

| Scenario | User Status | Verified? | Pending Video? | OTP Required? | Action |
|----------|-------------|-----------|----------------|---------------|---------|
| **1. New User** | Not exists | No | No | ✅ Yes | Send OTP → Verify → Start video processing |
| **2. Old Unverified** | Exists | No | No | ✅ Yes | Send OTP → Verify → Start video creation |
| **3. Verified + Pending** | Exists | Yes | Yes | ❌ No | **REJECT** with message about pending video |
| **4. Verified + No Pending** | Exists | Yes | No | ❌ No | **ACCEPT** and start processing immediately |

---

## Key Points

### When We Send OTP:
- New users (Scenario 1)
- Old users who never verified (Scenario 2)

### When We DON'T Send OTP:
- Users who already verified once (Scenarios 3 & 4)
- **OTP is ONE-TIME only** - after first verification, never required again

### When We Accept Request:
- All scenarios EXCEPT Scenario 3 (pending video)

### When We Reject Request:
- Only Scenario 3 - when verified user has a video being processed
- Message: "Wait for WhatsApp message about current video completion"

### Video Processing States:

**Pending (Blocks new submission):**
- queued
- photo_processing
- photo_done
- lipsync_processing
- lipsync_done
- stitching

**Complete (Allows new submission):**
- sent (delivered to WhatsApp) ✅
- uploaded ✅
- failed ❌

---

## User Journey Examples

### Example 1: Brand New User
```
Submit Form → Send OTP → User Enters OTP → Verify → Create Video Job → Processing Starts
```

### Example 2: Returning User (Previously Didn't Verify)
```
Submit Form → Send OTP → User Enters OTP → Verify → Mark as Verified → Create Video Job → Processing Starts
```

### Example 3: Verified User with Video Being Made
```
Submit Form → Check: Video Pending → Show Warning Message → STOP (No new job)
```

### Example 4: Verified User Ready for New Video
```
Submit Form → Check: No Pending Video → Create Video Job Immediately → Processing Starts
```

---

**Last Updated:** January 8, 2026
