from pydantic import BaseModel
from typing import Optional, List

class AppEntry(BaseModel):
    package_name: str
    app_name: str
    usage_seconds: int
    date: str

class AppUsageReport(BaseModel):
    device_name: str
    child_id: str
    apps: List[AppEntry]

class BlockedApp(BaseModel):
    package_name: str
    app_name: Optional[str] = ""

class BlockedAppInDB(BaseModel):
    package_name: str
    app_name: Optional[str] = ""
    blocked: bool = True

class BlockedAppUpdate(BaseModel):
    package_name: str
    app_name: Optional[str] = ""
    blocked: bool

class InstalledApp(BaseModel):
    package_name: str
    app_name: str
