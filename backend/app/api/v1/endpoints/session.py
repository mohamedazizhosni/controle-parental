from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
from bson import ObjectId
from ....db.mongodb import get_db
from .auth import get_current_user

router = APIRouter(prefix="/session", tags=["Session"])

def get_today_midnight():
    """Retourne un datetime à 00:00:00 UTC pour la date actuelle."""
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

@router.post("/ping")
async def session_ping(device_name: str, elapsed_seconds: int):
    db = get_db()
    today = get_today_midnight()

    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    child_id = device.get("child_id")
    if not child_id:
        raise HTTPException(status_code=400, detail="No child linked")

    try:
        obj_id = ObjectId(child_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid child id")

    profile = await db.children.find_one({"_id": obj_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    limit_minutes = profile.get("daily_time_limit_minutes")
    if limit_minutes is None:
        return {"should_disconnect": False, "message": "No time limit"}

    session = await db.sessions.find_one({"device_name": device_name, "date": today})
    if not session:
        session = {
            "device_name": device_name,
            "child_id": child_id,
            "date": today,
            "total_seconds": 0,
            "last_ping": datetime.utcnow()
        }
        await db.sessions.insert_one(session)
    else:
        elapsed = min(elapsed_seconds, 300)
        new_total = session["total_seconds"] + elapsed
        await db.sessions.update_one(
            {"_id": session["_id"]},
            {"$set": {"total_seconds": new_total, "last_ping": datetime.utcnow()}}
        )
        session["total_seconds"] = new_total

    limit_seconds = limit_minutes * 60
    if session["total_seconds"] >= limit_seconds:
        await db.devices.update_one({"device_name": device_name}, {"$set": {"enabled": False}})
        await db.alerts.insert_one({
            "child_id": child_id,
            "message": f"Temps de connexion quotidien dépassé ({limit_minutes} minutes)",
            "alert_type": "time_limit_exceeded",
            "read": False,
            "timestamp": datetime.utcnow()
        })
        return {"should_disconnect": True, "message": "Daily time limit exceeded"}

    return {"should_disconnect": False,
            "message": f"{session['total_seconds']}/{limit_seconds} seconds used"}

@router.get("/stats/{device_name}")
async def get_session_stats(device_name: str, current_user = Depends(get_current_user)):
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Device not found")
    if device.get("parent_email") != current_user["email"]:
        raise HTTPException(403, "Not authorized")
    today = get_today_midnight()
    session = await db.sessions.find_one({"device_name": device_name, "date": today})
    total_seconds = session["total_seconds"] if session else 0
    return {
        "device_name": device_name,
        "date": today.date().isoformat(),
        "total_seconds": total_seconds,
        "total_minutes": round(total_seconds / 60, 1)
    }

@router.get("/agent_stats/{device_name}")
async def get_agent_session_stats(device_name: str):
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Device not found")
    today = get_today_midnight()
    session = await db.sessions.find_one({"device_name": device_name, "date": today})
    total_seconds = session["total_seconds"] if session else 0
    return {
        "device_name": device_name,
        "date": today.date().isoformat(),
        "total_seconds": total_seconds,
        "total_minutes": round(total_seconds / 60, 1)
    }
