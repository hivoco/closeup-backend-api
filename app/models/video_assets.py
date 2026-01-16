from sqlalchemy import Column, BigInteger, Text, DateTime
from app.core.database import Base
from app.core.timezone import get_ist_now

class VideoAssets(Base):
    __tablename__ = "video_assets"

    job_id = Column(BigInteger, primary_key=True)
    raw_selfie_url = Column(Text)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)
    updated_at = Column(DateTime, default=get_ist_now, onupdate=get_ist_now, nullable=False)
