from sqlalchemy import Column, String, Enum, BigInteger, Integer, DateTime, Boolean
from app.core.database import Base
from app.core.timezone import get_ist_now

class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(String(36), nullable=False)

    gender = Column(Enum("male","female","other","unspecified"))
    attribute_love = Column(Enum(
        "Smile","Eyes","Hair","Face","Vibe",
        "Sense of Humor","Heart"
    ))
    relationship_status = Column(Enum(
        "Married","Situationship","Nanoship",
        "Crushing","Long-Distance","Dating"
    ))
    vibe = Column(Enum(
        "rap","rock","romantic"
    ))

    status = Column(Enum(
        "wait","unverified_photo","client","queued","photo_processing","photo_done",
        "lipsync_processing","lipsync_done",
        "stitching","uploaded","sent","failed"
    ), default="queued")

    retry_count = Column(Integer, default=0)
    locked_by = Column(String(64), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    failed_stage = Column(Enum("photo","lipsync","stitch","delivery"), nullable=True)
    last_error_code = Column(String(64), nullable=True)
    photo_validated = Column(Boolean, default=True, nullable=False, server_default="1")
    utm_source = Column(String(128), nullable=True)
    utm_medium = Column(String(128), nullable=True)
    utm_campaign = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)
    updated_at = Column(DateTime, default=get_ist_now, onupdate=get_ist_now, nullable=False)
