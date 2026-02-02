from fastapi import APIRouter, File, UploadFile, HTTPException
from typing import Optional, Literal
import httpx
import base64
import io
from uuid import uuid4
from PIL import Image
from pydantic import BaseModel
from app.core.config import settings
from app.core.redis import GroqKeyManager, PhotoValidationQueue

router = APIRouter(prefix="/api/v1/photo-validation", tags=["photo-validation"])

# Image resize settings for faster processing
MAX_IMAGE_SIZE = 512  # Max width/height in pixels
JPEG_QUALITY = 85     # JPEG compression quality

GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are an EXTREMELY STRICT image moderation system for a close-up romantic video product.
Analyze the image and classify it into ONE category ONLY.

REJECT_RELIGIOUS – ANY religious elements:
- Religious symbols (cross, crescent, om, etc.)
- Religious clothing (hijab, niqab, skullcap, robes)
- EXCEPTION: Turbans/pagris, tilak, bindi, and rosary are ALLOWED and should NOT be rejected
- Places of worship, religious text, idols, prayer gestures

REJECT_NSFW – ANY inappropriate content:
- Nudity, partial nudity, cleavage emphasis
- Sexual or seductive poses
- Bedroom/intimate scenes, lingerie, towel-only

REJECT_ANGLE_LOW – Camera is held too LOW (below face level):
- Face is angled downward / chin is tucked
- Camera is looking UP at the person from below
- Nostrils or underside of chin are prominently visible
- Person appears to be looking down at the camera

REJECT_ANGLE_HIGH – Camera is held too HIGH (above face level):
- Face is angled upward / chin is raised
- Camera is looking DOWN at the person from above
- Top of head or forehead is overly prominent
- Person appears to be looking up at the camera

REJECT_HAZY – Photo is hazy, foggy, or unclear:
- Image looks hazy, foggy, or has a misty appearance
- Blurry or out-of-focus photo where facial features are not sharp
- Dirty or smudged camera lens causing unclear image
- Low light, dark, or overexposed photo where face details are lost
- Steam, smoke, or any visual obstruction causing haziness

REJECT_INVALID – Image unsuitable for face video generation:
- HANDS OR FINGERS touching, covering, or near the face (even partially)
- Any object obscuring the face (phone, food, drink, pen, etc.)
- Face not 100% clearly visible and unobstructed
- Photo of a photo, screenshot, or image on a screen
- AI-generated, cartoon, anime, illustration, filtered face
- Multiple people or faces
- Side profile, tilted head, looking away (must be front-facing)
- Face too far, too close, cropped, or not centered
- Sunglasses, masks, helmets, hats covering face
- Hair covering significant part of face (eyes, nose, or mouth)
- Child or minor
- Celebrity or public figure
- Unusual expressions (tongue out, eyes closed, making faces)

APPROVED – ONLY if ALL conditions are met:
- ONE real adult human face, clearly visible
- Face is 100% unobstructed (NO hands, fingers, objects, hair blocking)
- Front-facing, looking directly at camera, eyes open
- Camera is at face level (straight on, not from above or below)
- Clear, well-lit, sharp image quality
- Natural expression (neutral or slight smile)
- No religious, NSFW, or invalid elements

CRITICAL RULES:
- Be EXTREMELY strict. When in doubt, REJECT.
- If ANY part of face is covered by hands/fingers → REJECT_INVALID
- If face is not perfectly clear and visible → REJECT_INVALID
- If camera angle is from below face level → REJECT_ANGLE_LOW
- If camera angle is from above face level → REJECT_ANGLE_HIGH
- If image is hazy, blurry, foggy, or unclear → REJECT_HAZY
- Return ONLY one word:

REJECT_RELIGIOUS
REJECT_NSFW
REJECT_ANGLE_LOW
REJECT_ANGLE_HIGH
REJECT_HAZY
REJECT_INVALID
APPROVED"""

ImageLabel = Literal["REJECT_RELIGIOUS", "REJECT_NSFW", "REJECT_ANGLE_LOW", "REJECT_ANGLE_HIGH", "REJECT_HAZY", "REJECT_INVALID", "APPROVED"]


class Usage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ValidationResponse(BaseModel):
    valid: bool
    reason: Optional[str] = None
    message: Optional[str] = None
    label: Optional[ImageLabel] = None
    usage: Optional[Usage] = None


def get_reason_for_label(label: ImageLabel) -> str:
    reasons = {
        "REJECT_RELIGIOUS": "Photo does not meet requirements. Please upload a clear, front-facing selfie with only your face visible.",
        "REJECT_NSFW": "Inappropriate or NSFW content detected. Please upload an appropriate photo.",
        "REJECT_ANGLE_LOW": "Your camera is too low. Please hold your phone at face level and take a straight photo.",
        "REJECT_ANGLE_HIGH": "Your camera is too high. Please hold your phone at face level and take a straight photo.",
        "REJECT_HAZY": "Your photo is not clear. Please clean your camera lens and take the photo in good lighting.",
        "REJECT_INVALID": "Photo does not meet requirements. Please upload a clear, front-facing selfie with only your face visible.",
        "APPROVED": "Photo validated successfully!"
    }
    return reasons.get(label, "Image validation failed. Please try again.")


def resize_image(file_bytes: bytes, max_size: int = MAX_IMAGE_SIZE) -> tuple[bytes, str]:
    """
    Resize image to max dimensions while maintaining aspect ratio.
    Converts to JPEG for smaller size.

    Returns:
        (resized_bytes, mime_type)
    """
    try:
        img = Image.open(io.BytesIO(file_bytes))

        # Convert RGBA to RGB (JPEG doesn't support transparency)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Get original dimensions
        orig_width, orig_height = img.size

        # Only resize if image is larger than max_size
        if orig_width > max_size or orig_height > max_size:
            # Calculate new dimensions maintaining aspect ratio
            if orig_width > orig_height:
                new_width = max_size
                new_height = int(orig_height * (max_size / orig_width))
            else:
                new_height = max_size
                new_width = int(orig_width * (max_size / orig_height))

            # Resize using high-quality LANCZOS filter
            img = img.resize((new_width, new_height), Image.LANCZOS)
            print(f"🔄 Resized: {orig_width}x{orig_height} → {new_width}x{new_height}")
        else:
            print(f"📐 Image size OK: {orig_width}x{orig_height}")

        # Convert to JPEG bytes
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=JPEG_QUALITY, optimize=True)
        output.seek(0)

        return output.read(), 'image/jpeg'
    except Exception as e:
        print(f"⚠️ Resize failed, using original: {e}")
        return file_bytes, 'image/jpeg'


def to_data_url(file_bytes: bytes, mime_type: str) -> str:
    base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
    return f"data:{mime_type};base64,{base64_encoded}"


@router.post("/check_photo", response_model=ValidationResponse)
async def check_photo(photo: UploadFile = File(...)):
    """
    Validates a photo using Groq AI to check if it meets requirements.

    Features:
    - Multiple API keys with automatic load balancing (3x capacity)
    - Automatic failover when one key hits rate limit
    - Queue system for burst traffic handling

    Returns:
        - valid: Boolean indicating if photo is acceptable
        - reason/message: Description of validation result
        - label: Classification label (APPROVED, REJECT_RELIGIOUS, REJECT_NSFW, REJECT_INVALID)
        - usage: Token usage statistics
    """

    # Get available API key (round-robin with failover)
    key_result = GroqKeyManager.get_available_key()

    if not key_result:
        # All keys exhausted - return rate limit response
        retry_after = GroqKeyManager.get_retry_after()
        remaining = GroqKeyManager.get_total_remaining()
        print(f"⚠️ All Groq API keys at limit. Retry after {retry_after}s (remaining: {remaining})")
        raise HTTPException(
            status_code=429,
            detail=f"Service is busy. Please try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )

    api_key, key_index = key_result

    print(f"📸 Received photo: {photo.filename}, Content-Type: {photo.content_type}")

    # Validate file type
    if not photo.content_type or not photo.content_type.startswith('image/'):
        print(f"❌ Invalid file type: {photo.content_type}")
        raise HTTPException(
            status_code=400,
            detail="File must be an image"
        )

    # Read file
    file_bytes = await photo.read()
    file_size = len(file_bytes)
    print(f"📦 File size: {file_size} bytes ({file_size / 1024:.2f} KB)")

    # Validate file size (max 10MB)
    if file_size > 10 * 1024 * 1024:
        print(f"❌ File too large: {file_size / (1024*1024):.2f} MB")
        raise HTTPException(
            status_code=400,
            detail="Image size must be less than 10MB"
        )

    # Resize image for faster processing (fewer tokens = faster response)
    resized_bytes, mime_type = resize_image(file_bytes)
    resized_size = len(resized_bytes)
    print(f"📦 After resize: {resized_size} bytes ({resized_size / 1024:.2f} KB) - Saved {((file_size - resized_size) / file_size * 100):.1f}%")

    # Create data URL for Groq API
    data_url = to_data_url(resized_bytes, mime_type)

    # Call Groq API with selected key
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Classify this image."},
                                {"type": "image_url", "image_url": {"url": data_url}}
                            ]
                        }
                    ],
                    "temperature": 0.0,
                    "max_tokens": 5
                }
            )

            if response.status_code != 200:
                error_data = response.json()
                print(f"❌ Groq API Error: {error_data}")
                raise HTTPException(
                    status_code=500,
                    detail="Image validation service unavailable. Please try again."
                )

            data = response.json()
            label = data["choices"][0]["message"]["content"].strip().upper().replace(".", "")

            print(f"🤖 Groq AI Classification: {label}")

            # Get usage stats
            usage_data = data.get("usage", {})
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens"),
                completion_tokens=usage_data.get("completion_tokens"),
                total_tokens=usage_data.get("total_tokens")
            )

            print(f"💰 Token usage: {usage_data.get('total_tokens', 0)} tokens")

            # Check if approved
            if label == "APPROVED":
                print("✅ Photo APPROVED")
                return ValidationResponse(
                    valid=True,
                    message=get_reason_for_label(label),
                    label=label,
                    usage=usage
                )

            # Rejected
            print(f"❌ Photo REJECTED: {label}")
            return ValidationResponse(
                valid=False,
                reason=get_reason_for_label(label),
                message=get_reason_for_label(label),
                label=label,
                usage=usage
            )

    except httpx.TimeoutException:
        print("❌ Groq API Timeout")
        raise HTTPException(
            status_code=504,
            detail="Image validation timed out. Please try again."
        )
    except httpx.HTTPError as e:
        print(f"❌ HTTP Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Image validation failed. Please try again."
        )
    except Exception as e:
        print(f"❌ Validation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Image validation failed. Please try again."
        )


class QueueResponse(BaseModel):
    """Response for queued validation requests"""
    status: str
    validation_id: Optional[str] = None
    position: Optional[int] = None
    message: str


class StatusResponse(BaseModel):
    """Response for validation status check"""
    status: str  # "queued", "processing", "completed", "not_found"
    position: Optional[int] = None
    result: Optional[ValidationResponse] = None
    message: str


class CapacityResponse(BaseModel):
    """Response for capacity info"""
    total_keys: int
    remaining_requests: int
    queue_size: int
    retry_after: int


@router.post("/queue_photo", response_model=QueueResponse)
async def queue_photo(photo: UploadFile = File(...)):
    """
    Queue a photo for validation when service is at capacity.

    This endpoint:
    1. First tries to validate immediately if capacity is available
    2. If all API keys are exhausted, queues the request
    3. Returns a validation_id to check status later

    Use /status/{validation_id} to check result.
    """
    # First, try to get an available key
    key_result = GroqKeyManager.get_available_key()

    if key_result:
        # Capacity available - redirect to immediate validation
        # Reset file position since we read it for checking
        await photo.seek(0)
        return QueueResponse(
            status="processing",
            message="Capacity available. Use /check_photo for immediate validation."
        )

    # All keys exhausted - queue the request
    print(f"📸 Queueing photo: {photo.filename}")

    # Validate file type
    if not photo.content_type or not photo.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Read and resize
    file_bytes = await photo.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image size must be less than 10MB")

    resized_bytes, mime_type = resize_image(file_bytes)
    data_url = to_data_url(resized_bytes, mime_type)

    # Generate validation ID and queue
    validation_id = str(uuid4())
    success = PhotoValidationQueue.enqueue(validation_id, data_url)

    if not success:
        raise HTTPException(
            status_code=503,
            detail="Queue is full. Please try again later."
        )

    queue_size = PhotoValidationQueue.get_queue_size()

    return QueueResponse(
        status="queued",
        validation_id=validation_id,
        position=queue_size,
        message=f"Request queued at position {queue_size}. Check status with /status/{validation_id}"
    )


@router.get("/status/{validation_id}", response_model=StatusResponse)
async def get_validation_status(validation_id: str):
    """
    Check the status of a queued photo validation.

    Returns:
        - status: "queued", "processing", "completed", or "not_found"
        - position: Queue position if still queued
        - result: Validation result if completed
    """
    status_data = PhotoValidationQueue.get_status(validation_id)

    if not status_data:
        return StatusResponse(
            status="not_found",
            message="Validation request not found or expired."
        )

    if status_data["status"] == "completed":
        result_data = status_data.get("result", {})
        return StatusResponse(
            status="completed",
            result=ValidationResponse(
                valid=result_data.get("valid", False),
                reason=result_data.get("reason"),
                message=result_data.get("message"),
                label=result_data.get("label")
            ),
            message="Validation completed."
        )

    if status_data["status"] == "processing":
        return StatusResponse(
            status="processing",
            message="Your photo is being validated."
        )

    # Still queued
    position = status_data.get("position", 0)
    return StatusResponse(
        status="queued",
        position=position,
        message=f"Your request is at position {position} in the queue."
    )


@router.get("/capacity", response_model=CapacityResponse)
async def get_capacity():
    """
    Get current API capacity information.

    Returns:
        - total_keys: Number of configured API keys
        - remaining_requests: Total remaining requests across all keys
        - queue_size: Current queue size
        - retry_after: Seconds until capacity becomes available
    """
    total_keys = len(settings.groq_api_keys_list)
    remaining = GroqKeyManager.get_total_remaining()
    queue_size = PhotoValidationQueue.get_queue_size()
    retry_after = GroqKeyManager.get_retry_after() if remaining == 0 else 0

    return CapacityResponse(
        total_keys=total_keys,
        remaining_requests=remaining,
        queue_size=queue_size,
        retry_after=retry_after
    )
