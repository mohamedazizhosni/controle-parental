from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from bson import ObjectId

class NavigationEntry(BaseModel):
    child_id: str
    url: str
    title: Optional[str] = None
    category: str = "unknown"
    blocked: bool = False
    timestamp: datetime = datetime.utcnow()

class Alert(BaseModel):
    child_id: str
    message: str
    alert_type: str  # "blocked_site", "time_limit_exceeded", "disable_request", etc.
    read: bool = False
    timestamp: datetime = datetime.utcnow()
