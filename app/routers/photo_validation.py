from fastapi import APIRouter, File, UploadFile, HTTPException
from typing import Optional, Literal
import httpx
import base64
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter(prefix="/api/v1/photo-validation", tags=["photo-validation"])

GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are a VERY STRICT image moderation and validation system for a close-up romantic video product.
Your task is to analyze a single uploaded image and classify it into ONE of the following categories ONLY:

REJECT_RELIGIOUS – if the image contains ANY religious elements, including but not limited to:
- Religious symbols (cross, crescent, star of David, om, tilak, bindi, rosary, etc.)
- Religious clothing or headwear (hijab, niqab, turban, skullcap, priest/nun robes)
- Places of worship (temple, church, mosque, shrine)
- Religious text, idols, ceremonies, prayer gestures

REJECT_NSFW – if the image contains ANY sexual, suggestive, or inappropriate content, including:
- Nudity, partial nudity, cleavage emphasis
- Sexual or seductive poses
- Bedroom or bed scenes implying intimacy
- Lingerie, see-through clothing, towel-only images

REJECT_INVALID – if the image is unsuitable for close-up face video generation, including:
- Photo of a photo, framed photo, or image displayed on a phone or screen
- AI-generated, cartoon, anime, illustration, heavily edited or filtered face
- Multiple people or more than one visible face
- Face not centered, not facing the camera, side profile, tilted, looking away
- Face too far, cropped, partially visible, or not a clear close-up
- Sunglasses, masks, helmets, hands covering face
- Child or minor
- Celebrity, public figure, or stock photo
- Non-human, mannequin, doll, statue, or object
- Extremely blurry, dark, overexposed, or low-quality images

APPROVED – ONLY if ALL conditions are met:
- Exactly one real adult human face
- Front-facing, looking directly at the camera
- Clear, well-lit, close-up selfie
- Neutral background preferred
- No religious, NSFW, artificial, or invalid elements

IMPORTANT RULES:
- Be extremely conservative.
- If you are unsure, DO NOT approve.
- Default to rejection.
- Do NOT explain your reasoning.
- Return ONLY one word from the following list:

REJECT_RELIGIOUS
REJECT_NSFW
REJECT_INVALID
APPROVED"""

ImageLabel = Literal["REJECT_RELIGIOUS", "REJECT_NSFW", "REJECT_INVALID", "APPROVED"]


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
        "REJECT_RELIGIOUS": "Religious symbols or imagery detected. Please upload a simple personal photo without religious elements.",
        "REJECT_NSFW": "Inappropriate or NSFW content detected. Please upload an appropriate photo.",
        "REJECT_INVALID": "Photo does not meet requirements. Please upload a clear, front-facing selfie with only your face visible.",
        "APPROVED": "Photo validated successfully!"
    }
    return reasons.get(label, "Image validation failed. Please try again.")


def to_data_url(file_bytes: bytes, mime_type: str) -> str:
    base64_encoded = base64.b64encode(file_bytes).decode('utf-8')
    return f"data:{mime_type};base64,{base64_encoded}"


@router.post("/check_photo", response_model=ValidationResponse)
async def check_photo(photo: UploadFile = File(...)):
    """
    Validates a photo using Groq AI to check if it meets requirements.

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

    # Create data URL for Groq API
    data_url = to_data_url(file_bytes, photo.content_type)

    # Call Groq API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
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
