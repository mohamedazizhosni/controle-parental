from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime
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
    """Appelé par le proxy Squid pour enregistrer une navigation (HTTP et HTTPS)."""
    db = get_db()

    # Récupérer l'IP source depuis la requête (plus fiable)
    source_ip = log.ip
    
    # Si l'IP est vide ou localhost, essayer d'autres sources
    if not source_ip or source_ip in ["0.0.0.0", "127.0.0.1"]:
        source_ip = request.client.host
        if "x-forwarded-for" in request.headers:
            source_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            source_ip = request.headers["x-real-ip"]

    # Méthode 1 : Trouver l'appareil via mapping IP
    mapping = await db.ip_mapping.find_one({"ip": source_ip})
    
    device = None
    child_id = None
    
    if mapping:
        device_name = mapping["device_name"]
        device = await db.devices.find_one({"device_name": device_name})
    
    # Méthode 2 : Si pas de mapping, chercher un appareil actif récemment
    if not device:
        # Chercher tous les appareils avec un enfant actif
        recent_devices = await db.devices.find(
            {"active_child_id": {"$exists": True, "$ne": None}}
        ).to_list(length=10)
        
        # Prendre le premier appareil actif (ou améliorer la logique selon vos besoins)
        if recent_devices:
            device = recent_devices[0]
            device_name = device.get("device_name", "unknown")
            
            # Enregistrer automatiquement ce mapping IP pour les prochaines fois
            await db.ip_mapping.update_one(
                {"device_name": device_name},
                {"$set": {"ip": source_ip, "updated_at": datetime.utcnow()}},
                upsert=True
            )
    
    if not device:
        return {"message": "no device found", "ip": source_ip}

    child_id = device.get("active_child_id")
    if not child_id:
        return {"message": "no active child", "device": device.get("device_name")}

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
        "timestamp": datetime.utcnow(),
        "source_ip": source_ip  # Ajouter l'IP source pour debug
    }
    await db.history.insert_one(entry)
    return {"message": "ok", "child_id": child_id}


@router.get("/all")
async def get_all_children_history(
    current_user = Depends(get_current_user),
    limit: int = 50
):
    """
    Récupère automatiquement l'historique de tous les enfants du parent connecté.
    Retourne un dictionnaire avec child_id comme clé et liste d'entrées comme valeur.
    """
    db = get_db()
    
    # Récupérer tous les enfants du parent
    children = await db.children.find(
        {"parent_email": current_user["email"]}
    ).to_list(length=None)
    
    if not children:
        return {}
    
    # Récupérer l'historique pour tous les enfants
    result = {}
    for child in children:
        child_id = str(child["_id"])
        child_name = child.get("name", "Enfant")
        
        # Récupérer l'historique de cet enfant
        entries = await db.history.find(
            {"child_id": child_id}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        # Formater les entrées
        formatted_entries = []
        for e in entries:
            e["_id"] = str(e["_id"])
            if "timestamp" in e:
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

    # child_id est stocké comme string dans la base de données
    entries = await db.history.find(
        {"child_id": child_id}
    ).sort("timestamp", -1).limit(200).to_list(length=200)

    for e in entries:
        e["_id"] = str(e["_id"])
        if "timestamp" in e:
            e["timestamp"] = e["timestamp"].isoformat()

    return entries
