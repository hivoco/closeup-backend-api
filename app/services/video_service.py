from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import hash_phone, encrypt_phone
from uuid import uuid4

def handle_video_submit(db: Session, payload):
    phone_hash = hash_phone(payload.phone_number)

    user = db.query(User).filter_by(phone_hash=phone_hash).first()

    if user and user.video_count >= 3:
        raise ValueError("VIDEO_LIMIT")

    if not user:
        user = User(
            id=str(uuid4()),
            phone_hash=phone_hash,
            phone_encrypted=encrypt_phone(payload.phone_number)
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
