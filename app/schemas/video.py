from pydantic import BaseModel
from typing import Literal

class VideoSubmit(BaseModel):
    phone_number: str
    gender: Literal["male", "female", "other", "unspecified"]
    attribute_love: str
    relationship_status: str
    vibe: str
