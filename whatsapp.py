"""
WhatsApp Video Sender

Sends the final video to a user via WhatsApp by calling the CloseUp API.

Usage:
    python whatsapp.py <job_id>

Example:
    python whatsapp.py 42
"""

import sys
import httpx

API_KEY = "31de2247e558b4e48139c8e9d594c64bdb069be61467006cb6220f7e6e744506"
BASE_URL = "https://api.closeuplovetunes.in"


def send_video(job_id: int) -> None:
    print(f"[INFO] Sending video for job #{job_id}...")

    response = httpx.post(
        f"{BASE_URL}/api/v1/video-jobs/{job_id}/send-video",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=15.0,
    )

    data = response.json()

    if response.status_code == 200:
        print(f"[SUCCESS] {data.get('message')}")
    else:
        print(f"[ERROR] {response.status_code} - {data.get('detail', data)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python whatsapp.py <job_id>")
        print("Example: python whatsapp.py 42")
        sys.exit(1)

    try:
        job_id = int(sys.argv[1])
    except ValueError:
        print("[ERROR] job_id must be a number")
        sys.exit(1)

    send_video(job_id)
