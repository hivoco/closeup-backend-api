from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str
    PHONE_HASH_SALT: str
    FERNET_KEY: str
    OTP_EXPIRY_MINUTES: int = 5

    AWS_REGION: str
    AWS_S3_BUCKET: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str

    GROQ_API_KEY: str

    # Redis Configuration
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0

    class Config:
        env_file = ".env"

settings = Settings()
