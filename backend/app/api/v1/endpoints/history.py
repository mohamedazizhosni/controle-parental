from fastapi import APIRouter, HTTPException
from datetime import datetime
from pydantic import BaseModel
from bson import ObjectId
from ....db.mongodb import get_db

router = APIRouter(prefix="/history", tags=["History"])


class HistoryLog(BaseModel):
    ip: str
    url: str
    blocked: bool = False


@router.post("/log")
async def log_history(log: HistoryLog):
    """Appelé par le proxy Squid pour enregistrer une navigation (HTTP et HTTPS)."""
    db = get_db()

    # Trouver l'appareil associé à cette IP
    mapping = await db.ip_mapping.find_one({"ip": log.ip})
    if not mapping:
        return {"message": "unknown IP"}

    device_name = mapping["device_name"]
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        return {"message": "device not found"}

    child_id = device.get("active_child_id")
    if not child_id:
        return {"message": "no active child"}

    # Déterminer la catégorie depuis l'URL
    category = "unknown"
    url_lower = log.url.lower()
    keywords_map = {
        "adult":    ["porn", "sex", "xxx", "adult", "nude", "hentai"],
        "violence": ["kill", "murder", "blood", "gore", "terror"],
        "gambling": ["casino", "poker", "bet", "slot", "roulette"],
        "social":   ["facebook", "twitter", "instagram", "tiktok", "youtube", "whatsapp"],
        "games":    ["game", "minecraft", "fortnite", "roblox"],
    }
    for cat, words in keywords_map.items():
        if any(w in url_lower for w in words):
            category = cat
            break

    # Protocole HTTP ou HTTPS
    protocol = "HTTPS" if log.url.startswith("https://") else "HTTP"

    entry = {
        "child_id": child_id,
        "url": log.url,
        "protocol": protocol,
        "title": "",
        "category": category,
        "blocked": log.blocked,
        "timestamp": datetime.utcnow()
    }
    await db.history.insert_one(entry)
    return {"message": "ok"}


@router.get("/{child_id}")
async def get_history(child_id: str):
    """Appelé par l'application parent pour afficher l'historique d'un enfant."""
    db = get_db()
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child id")

    # child_id est stocké comme string dans la base de données
    entries = await db.history.find(
        {"child_id": child_id}
    ).sort("timestamp", -1).limit(200).to_list(length=200)

    for e in entries:
        e["_id"] = str(e["_id"])
        if "timestamp" in e:
            e["timestamp"] = e["timestamp"].isoformat()

    return entries
