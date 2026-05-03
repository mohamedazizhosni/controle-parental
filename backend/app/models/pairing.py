from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class PairingCode(BaseModel):
    code: str
    profile_id: str
    parent_email: str
    device_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    used: bool = False
