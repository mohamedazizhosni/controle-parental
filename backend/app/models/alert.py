from pydantic import BaseModel
from datetime import datetime

class Alert(BaseModel):
    parent_email: str
    profile_name: str
    device_name: str
    url: str
    category: str
    timestamp: datetime = datetime.utcnow()
    read: bool = False
