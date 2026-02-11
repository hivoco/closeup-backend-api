"""
Check which numbers exist in the database and which don't.
Uses phone_hash to look up numbers.
"""

from app.core.database import SessionLocal
from app.core.security import hash_phone
from app.models.user import User

# Add your 10-digit numbers here
NUMBERS = [
    "8725461129",
    "9876543210",
    "9123456789",
    "7890123456",
    "8001234567",
]


def run():
    db = SessionLocal()
    try:
        found = []
        not_found = []

        for number in NUMBERS:
            phone_hash = hash_phone(number)
            user = db.query(User).filter(User.phone_hash == phone_hash).first()
            if user:
                found.append(number)
                print(f"  ✅ {number} — FOUND (user_id: {user.id[:8]}..., video_count: {user.video_count})")
            else:
                not_found.append(number)
                print(f"  ❌ {number} — NOT FOUND")

        print(f"\nSummary: {len(found)} found, {len(not_found)} not found out of {len(NUMBERS)} numbers.")

    finally:
        db.close()


if __name__ == "__main__":
    run()
