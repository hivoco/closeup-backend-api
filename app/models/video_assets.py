from sqlalchemy import Column, BigInteger, Text, DateTime
from app.core.database import Base
from app.core.timezone import get_ist_now

class VideoAssets(Base):
    __tablename__ = "video_assets"

    job_id = Column(BigInteger, primary_key=True)
    raw_selfie_url = Column(Text)
    normalized_image_url = Column(Text)
    lipsync_seg2_url = Column(Text)
    lipsync_seg4_url = Column(Text)
    final_video_url = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)
    updated_at = Column(DateTime, default=get_ist_now, onupdate=get_ist_now, nullable=False)
