from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime, timedelta
from pydantic import BaseModel
from bson import ObjectId
from typing import Dict, List
from ....db.mongodb import get_db
from .auth import get_current_user

router = APIRouter(prefix="/history", tags=["History"])


class HistoryLog(BaseModel):
    ip: str
    url: str
    blocked: bool = False


@router.post("/log")
async def log_history(log: HistoryLog, request: Request):
    """Appelé par le proxy Squid ou l'agent Android pour enregistrer une navigation."""
    db = get_db()

    source_ip = log.ip
    if not source_ip or source_ip in ["0.0.0.0", "127.0.0.1"]:
        source_ip = request.client.host
        if "x-forwarded-for" in request.headers:
            source_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            source_ip = request.headers["x-real-ip"]

    device = None
    child_id = None

    mapping = await db.ip_mapping.find_one({"ip": source_ip})
    if mapping:
        device_name = mapping["device_name"]
        device = await db.devices.find_one({"device_name": device_name})

    if not device:
        recent_devices = await db.devices.find(
            {"active_child_id": {"$exists": True, "$ne": None}}
        ).to_list(length=10)
        if recent_devices:
            device = recent_devices[0]
            device_name = device.get("device_name", "unknown")
            await db.ip_mapping.update_one(
                {"device_name": device_name},
                {"$set": {"ip": source_ip, "updated_at": datetime.utcnow()}},
                upsert=True
            )

    if not device:
        entry = {
            "child_id": None,
            "url": log.url,
            "protocol": "HTTPS" if log.url.startswith("https://") else "HTTP",
            "title": "",
            "category": "unknown",
            "blocked": log.blocked,
            "timestamp": datetime.utcnow(),
            "source_ip": source_ip,
            "device_name": None,
            "error": "no device mapping found"
        }
        await db.history.insert_one(entry)
        return {"message": "no device found", "ip": source_ip}

    child_id = device.get("active_child_id")
    if not child_id:
        entry = {
            "child_id": None,
            "url": log.url,
            "protocol": "HTTPS" if log.url.startswith("https://") else "HTTP",
            "title": "",
            "category": "unknown",
            "blocked": log.blocked,
            "timestamp": datetime.utcnow(),
            "source_ip": source_ip,
            "device_name": device.get("device_name"),
            "error": "no active child"
        }
        await db.history.insert_one(entry)
        return {"message": "no active child", "device": device.get("device_name")}

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

    protocol = "HTTPS" if log.url.startswith("https://") else "HTTP"
    now = datetime.utcnow()

    entry = {
        "child_id": child_id,
        "url": log.url,
        "protocol": protocol,
        "title": "",
        "category": category,
        "blocked": log.blocked,
        "timestamp": now,
        "source_ip": source_ip,
        "device_name": device.get("device_name"),
    }
    await db.history.insert_one(entry)

    if log.blocked:
        child_doc = None
        if child_id and ObjectId.is_valid(child_id):
            child_doc = await db.children.find_one({"_id": ObjectId(child_id)})
        child_name = child_doc.get("name", "Enfant") if child_doc else "Enfant"

        alert = {
            "child_id": child_id,
            "child_name": child_name,
            "message": f"Site bloqué ({category}) : {log.url}",
            "url": log.url,
            "category": category,
            "alert_type": "blocked_site",
            "device_name": device.get("device_name"),
            "read": False,
            "timestamp": now,
        }
        await db.alerts.insert_one(alert)

        parent_email = device.get("parent_email")
        if parent_email:
            try:
                from .notifications import manager, _send_fcm_push

                ws_message = {
                    "type": "blocked_site",
                    "child_name": child_name,
                    "url": log.url,
                    "category": category,
                    "device_name": device.get("device_name"),
                    "timestamp": now.isoformat(),
                }
                await manager.send_personal_message(ws_message, parent_email)

                # Déduplication FCM : ne pas renvoyer si la même URL a déjà
                # généré une notification pour cet enfant dans les 5 dernières minutes.
                five_minutes_ago = now - timedelta(minutes=5)
                recent_alert = await db.alerts.find_one({
                    "child_id": child_id,
                    "url": log.url,
                    "alert_type": "blocked_site",
                    "timestamp": {"$gte": five_minutes_ago},
                    # Exclure l'alerte qu'on vient d'insérer (elle est la plus récente)
                    "_id": {"$ne": alert.get("_id")},
                })

                if recent_alert is None:
                    # Pas de doublon récent : envoyer la notification FCM
                    if not manager.is_connected(parent_email):
                        await _send_fcm_push(
                            db,
                            parent_email,
                            title=f"⚠️ Site bloqué – {child_name}",
                            body=f"Tentative d'accès à {log.url} ({category})",
                            data={
                                "type": "blocked_site",
                                "child_id": child_id,
                                "child_name": child_name,
                                "url": log.url,
                                "category": category,
                                "route": "/alerts",
                            },
                        )
                # Si recent_alert existe : doublon dans les 5 min → pas de FCM
            except Exception:
                pass

    return {"message": "ok", "child_id": child_id, "device_name": device.get("device_name")}


@router.get("/all")
async def get_all_children_history(
    current_user=Depends(get_current_user),
    limit: int = 50
):
    """Récupère l'historique de tous les enfants du parent connecté."""
    db = get_db()

    children = await db.children.find(
        {"parent_email": current_user["email"]}
    ).to_list(length=None)

    if not children:
        return {}

    result = {}
    for child in children:
        child_id = str(child["_id"])
        child_name = child.get("name", "Enfant")

        entries = await db.history.find(
            {"child_id": child_id}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

        formatted_entries = []
        for e in entries:
            e["_id"] = str(e["_id"])
            if "timestamp" in e and hasattr(e["timestamp"], "isoformat"):
                e["timestamp"] = e["timestamp"].isoformat()
            formatted_entries.append(e)

        result[child_id] = {
            "child_name": child_name,
            "child_id": child_id,
            "history": formatted_entries,
            "total_entries": len(formatted_entries)
        }

    return result


@router.get("/{child_id}")
async def get_history(child_id: str):
    """Appelé par l'application parent pour afficher l'historique d'un enfant."""
    db = get_db()
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child id")

    entries = await db.history.find(
        {"child_id": child_id}
    ).sort("timestamp", -1).limit(200).to_list(length=200)

    for e in entries:
        e["_id"] = str(e["_id"])
        if "timestamp" in e and hasattr(e["timestamp"], "isoformat"):
            e["timestamp"] = e["timestamp"].isoformat()

    return entries
