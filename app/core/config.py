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

    # Groq API Keys (comma-separated for multiple keys)
    # Example: "key1,key2,key3" for 3x capacity
    GROQ_API_KEYS: str  # Primary + additional keys, comma-separated

    # Redis Configuration
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0

    class Config:
        env_file = ".env"

    @property
    def groq_api_keys_list(self) -> list[str]:
        """Parse comma-separated Groq API keys into list"""
        return [key.strip() for key in self.GROQ_API_KEYS.split(",") if key.strip()]

settings = Settings()
