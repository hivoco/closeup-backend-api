from fastapi import APIRouter, File, UploadFile, HTTPException
from typing import Optional, Literal
import httpx
import base64
import io
import hmac
import hashlib
import time
from uuid import uuid4
from PIL import Image
from pydantic import BaseModel
from app.core.config import settings
from app.core.redis import GroqKeyManager, PhotoValidationQueue, FeatureFlags

VALIDATION_TOKEN_EXPIRY = 600  # 10 minutes


def generate_validation_token(photo_hash: str) -> str:
    """Generate an HMAC-signed token proving photo was validated."""
    timestamp = str(int(time.time()))
    payload = f"{photo_hash}:{timestamp}"
    signature = hmac.new(
        settings.JWT_SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    return token


def verify_validation_token(token: str) -> bool:
    """Verify the HMAC-signed validation token."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 3:
            return False
        photo_hash, timestamp, signature = parts
        # Check expiry
        if int(time.time()) - int(timestamp) > VALIDATION_TOKEN_EXPIRY:
            return False
        # Verify signature
        payload = f"{photo_hash}:{timestamp}"
        expected = hmac.new(
            settings.JWT_SECRET_KEY.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False

router = APIRouter(prefix="/api/v1/photo-validation", tags=["photo-validation"])

# Image resize settings for faster processing
MAX_IMAGE_SIZE = 512  # Max width/height in pixels
JPEG_QUALITY = 85     # JPEG compression quality

GROQ_PRIMARY_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_FALLBACK_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"

SYSTEM_PROMPT = """Classify image: REJECT_UNCLEAR (blurry/foggy/dark), REJECT_CELEBRITY (famous person), REJECT_OBSTRUCTED (fingers/hands/objects/mask/hair on face, multiple/no faces), REJECT_NSFW (nudity/sexual), REJECT_MINOR (child or person under 18), REJECT_SCREENSHOT (photo of a photo/poster/screen/printed image, not a live selfie), APPROVED (clear unobstructed live selfie of an adult non-celebrity). Reply ONE word only."""

ImageLabel = Literal["REJECT_UNCLEAR", "REJECT_CELEBRITY", "REJECT_OBSTRUCTED", "REJECT_NSFW", "REJECT_MINOR", "REJECT_SCREENSHOT", "APPROVED"]


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
    validation_token: Optional[str] = None


def get_reason_for_label(label: ImageLabel) -> str:
    reasons = {
        "REJECT_UNCLEAR": "Your photo is not clear. Please take a sharp photo in good lighting.",
        "REJECT_CELEBRITY": "This looks like a celebrity or public figure. Please upload your own photo!",
        "REJECT_OBSTRUCTED": "Your face is not fully visible. Please remove any obstructions and show your full face clearly.",
        "REJECT_NSFW": "Inappropriate content detected. Please upload an appropriate photo.",
        "REJECT_MINOR": "You must be 18 or older to use this service. Please upload an adult's photo.",
        "REJECT_SCREENSHOT": "Please take a live selfie instead of uploading a photo of a photo, poster, or screen.",
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

    # Build attempts: try scout model with all keys first, then maverick with all keys
    all_keys = settings.groq_api_keys_list
    attempts = []
    for key in all_keys:
        attempts.append((key, GROQ_PRIMARY_MODEL))
    for key in all_keys:
        attempts.append((key, GROQ_FALLBACK_MODEL))

    last_error = None

    for attempt_key, attempt_model in attempts:
        try:
            print(f"🔑 Trying model={attempt_model.split('/')[-1]} with key ...{attempt_key[-6:]}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {attempt_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": attempt_model,
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
                    print(f"❌ Groq API Error ({attempt_model.split('/')[-1]}): {error_data}")
                    last_error = str(error_data)
                    continue  # Try next attempt

                data = response.json()
                label = data["choices"][0]["message"]["content"].strip().upper().replace(".", "")

                print(f"🤖 Groq AI Classification ({attempt_model.split('/')[-1]}): {label}")

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
                    photo_hash = hashlib.sha256(resized_bytes).hexdigest()
                    token = generate_validation_token(photo_hash)
                    return ValidationResponse(
                        valid=True,
                        message=get_reason_for_label(label),
                        label=label,
                        usage=usage,
                        validation_token=token
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

        except (httpx.TimeoutException, httpx.HTTPError) as e:
            print(f"❌ Request failed ({attempt_model.split('/')[-1]}): {str(e)}")
            last_error = str(e)
            continue  # Try next attempt
        except Exception as e:
            print(f"❌ Unexpected error ({attempt_model.split('/')[-1]}): {str(e)}")
            last_error = str(e)
            continue  # Try next attempt

    # All attempts failed - auto-disable photo validation until admin re-enables
    print(f"❌ All attempts failed. Last error: {last_error}")
    print("⚠️ Auto-disabling photo validation due to Groq overload (admin must re-enable)")
    FeatureFlags.set_flag("photo_validation", False, auto=True)
    raise HTTPException(
        status_code=503,
        detail="Image validation service unavailable. Photo validation has been auto-disabled. Please try submitting without photo check."
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
