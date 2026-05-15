from pydantic import BaseModel
from typing import Optional

class FCMTokenRegister(BaseModel):
    fcm_token: str
    device_platform: Optional[str] = "android"
