from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ChildProfile(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    parent_email: str
    name: str
    age: int
    blocked_categories: List[str] = []
    daily_time_limit_minutes: Optional[int] = None
    allowed_time_slots: List[dict] = []
    parent_pin: Optional[str] = None
    child_pin: Optional[str] = None          # 👈 nouveau
    device_mode: Optional[str] = "shared"
    device_type: Optional[str] = "pc"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True

class ChildProfileCreate(BaseModel):
    name: str
    age: int
    blocked_categories: List[str] = []
    daily_time_limit_minutes: Optional[int] = None
    allowed_time_slots: List[dict] = []
    parent_pin: Optional[str] = None
    child_pin: Optional[str] = None
    device_mode: Optional[str] = "shared"
    device_type: Optional[str] = "pc"

class ChildProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    blocked_categories: Optional[List[str]] = None
    daily_time_limit_minutes: Optional[int] = None
    allowed_time_slots: Optional[List[dict]] = None
    parent_pin: Optional[str] = None
    child_pin: Optional[str] = None
    device_mode: Optional[str] = None
    device_type: Optional[str] = None
