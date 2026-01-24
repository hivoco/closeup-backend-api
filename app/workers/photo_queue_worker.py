"""
Photo Validation Queue Worker

Processes queued photo validation requests when API capacity is available.

Run as a separate process:
    python -m app.workers.photo_queue_worker

Or run multiple workers for parallel processing:
    python -m app.workers.photo_queue_worker &
    python -m app.workers.photo_queue_worker &
"""

import asyncio
import httpx
from app.core.redis import GroqKeyManager, PhotoValidationQueue
from app.core.config import settings

GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are an EXTREMELY STRICT image moderation system for a close-up romantic video product.
Analyze the image and classify it into ONE category ONLY.

REJECT_RELIGIOUS – ANY religious elements:
- Religious symbols (cross, crescent, om, tilak, bindi, rosary, etc.)
- Religious clothing (hijab, niqab, turban, skullcap, robes)
- Places of worship, religious text, idols, prayer gestures

REJECT_NSFW – ANY inappropriate content:
- Nudity, partial nudity, cleavage emphasis
- Sexual or seductive poses
- Bedroom/intimate scenes, lingerie, towel-only

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
- Blurry, dark, overexposed, or low-quality image
- Unusual expressions (tongue out, eyes closed, making faces)

APPROVED – ONLY if ALL conditions are met:
- ONE real adult human face, clearly visible
- Face is 100% unobstructed (NO hands, fingers, objects, hair blocking)
- Front-facing, looking directly at camera, eyes open
- Clear, well-lit, sharp image quality
- Natural expression (neutral or slight smile)
- No religious, NSFW, or invalid elements

CRITICAL RULES:
- Be EXTREMELY strict. When in doubt, REJECT.
- If ANY part of face is covered by hands/fingers → REJECT_INVALID
- If face is not perfectly clear and visible → REJECT_INVALID
- Return ONLY one word:

REJECT_RELIGIOUS
REJECT_NSFW
REJECT_INVALID
APPROVED"""


def get_reason_for_label(label: str) -> str:
    reasons = {
        "REJECT_RELIGIOUS": "Religious symbols or imagery detected. Please upload a simple personal photo without religious elements.",
        "REJECT_NSFW": "Inappropriate or NSFW content detected. Please upload an appropriate photo.",
        "REJECT_INVALID": "Photo does not meet requirements. Please upload a clear, front-facing selfie with only your face visible.",
        "APPROVED": "Photo validated successfully!"
    }
    return reasons.get(label, "Image validation failed. Please try again.")


async def process_single_item(item: dict) -> bool:
    """Process a single queued validation request"""
    validation_id = item["validation_id"]
    image_data = item["image_data"]

    print(f"🔄 Processing validation {validation_id}")

    # Update status to processing
    PhotoValidationQueue.set_status(validation_id, "processing")

    # Get available API key
    key_result = GroqKeyManager.get_available_key()
    if not key_result:
        # No capacity - put back in queue (at front)
        print(f"⏸️ No capacity, re-queuing {validation_id}")
        PhotoValidationQueue.set_status(validation_id, "queued", position=1)
        return False

    api_key, key_index = key_result

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
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Classify this image."},
                                {"type": "image_url", "image_url": {"url": image_data}}
                            ]
                        }
                    ],
                    "temperature": 0.0,
                    "max_tokens": 5
                }
            )

            if response.status_code != 200:
                error_data = response.json()
                print(f"❌ Groq API Error for {validation_id}: {error_data}")
                PhotoValidationQueue.set_result(validation_id, {
                    "valid": False,
                    "reason": "Validation service error",
                    "message": "Image validation failed. Please try again.",
                    "label": None
                })
                return True

            data = response.json()
            label = data["choices"][0]["message"]["content"].strip().upper().replace(".", "")

            print(f"✅ Completed {validation_id}: {label}")

            is_valid = label == "APPROVED"
            PhotoValidationQueue.set_result(validation_id, {
                "valid": is_valid,
                "reason": None if is_valid else get_reason_for_label(label),
                "message": get_reason_for_label(label),
                "label": label
            })
            return True

    except Exception as e:
        print(f"❌ Error processing {validation_id}: {e}")
        PhotoValidationQueue.set_result(validation_id, {
            "valid": False,
            "reason": "Validation error",
            "message": "Image validation failed. Please try again.",
            "label": None
        })
        return True


async def worker_loop():
    """Main worker loop - continuously process queue"""
    print("🚀 Photo validation worker started")
    print(f"📊 Total API keys: {len(settings.groq_api_keys_list)}")

    while True:
        try:
            # Check if we have capacity
            remaining = GroqKeyManager.get_total_remaining()

            if remaining == 0:
                # No capacity, wait
                retry_after = GroqKeyManager.get_retry_after()
                print(f"⏳ No capacity, waiting {retry_after}s...")
                await asyncio.sleep(retry_after)
                continue

            # Get next item from queue
            item = PhotoValidationQueue.dequeue()

            if not item:
                # Queue empty, wait before checking again
                await asyncio.sleep(1)
                continue

            # Process the item
            await process_single_item(item)

            # Small delay between processing
            await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            print("\n🛑 Worker stopped")
            break
        except Exception as e:
            print(f"❌ Worker error: {e}")
            await asyncio.sleep(5)


def run_worker():
    """Entry point for running the worker"""
    asyncio.run(worker_loop())


if __name__ == "__main__":
    run_worker()
