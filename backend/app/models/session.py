from pydantic import BaseModel
from datetime import datetime

class Session(BaseModel):
    device_name: str
    child_id: str
    date: datetime   # ← maintenant datetime (minuit UTC)
    total_seconds: int = 0
    last_ping: datetime = datetime.utcnow()
