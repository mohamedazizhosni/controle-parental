"""
Endpoint pour signaler les tentatives de contournement du contrôle parental.
POST /api/v1/alerts/report  → appelé par l'agent Android ou Windows
GET  /api/v1/alerts/all     → liste les alertes (appel interne)
"""

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel
from datetime import datetime
from bson import ObjectId
from ....db.mongodb import get_db

router = APIRouter(prefix="/alerts", tags=["Alerts"])

INTERNAL_SECRET = "squid-internal-secret-2024"


class AlertReport(BaseModel):
    device_name: str
    alert_type: str   # "vpn_disabled" | "vpn_disable_attempt" | "proxy_disabled" | "proxy_disable_attempt"
    message: str
    url: str = ""


@router.post("/report")
async def report_alert(payload: AlertReport):
    """
    Appelé par l'agent Android ou Windows quand l'enfant tente de désactiver
    le VPN ou le proxy. Aucune authentification requise (réseau local uniquement).
    """
    db = get_db()

    device = await db.devices.find_one({"device_name": payload.device_name})
    if not device:
        return {"error": "device not found"}

    child_id = device.get("active_child_id")
    parent_email = device.get("parent_email")

    child_name = "Enfant"
    if child_id and ObjectId.is_valid(child_id):
        child_doc = await db.children.find_one({"_id": ObjectId(child_id)})
        if child_doc:
            child_name = child_doc.get("name", "Enfant")

    now = datetime.utcnow()

    # Sauvegarder l'alerte en base
    alert = {
        "child_id": child_id,
        "child_name": child_name,
        "message": payload.message,
        "url": payload.url,
        "category": "security",
        "alert_type": payload.alert_type,
        "device_name": payload.device_name,
        "read": False,
        "timestamp": now,
    }
    await db.alerts.insert_one(alert)

    if not parent_email:
        return {"status": "saved_no_parent"}

    try:
        from .notifications import manager, _send_fcm_push

        # Choisir le titre selon le type d'alerte
        if "vpn" in payload.alert_type:
            icon = "🛡️"
            subject = "VPN désactivé" if payload.alert_type == "vpn_disabled" else "Tentative désactivation VPN"
        else:
            icon = "⚠️"
            subject = "Proxy désactivé" if payload.alert_type == "proxy_disabled" else "Tentative désactivation proxy"

        # Message WebSocket — contient 'message' pour que notification_service.dart le détecte
        ws_message = {
            "type": payload.alert_type,
            "title": f"{icon} {subject} — {child_name}",
            "message": payload.message,
            "child_name": child_name,
            "device_name": payload.device_name,
            "timestamp": now.isoformat(),
        }
        await manager.send_personal_message(ws_message, parent_email)

        # FCM push si le parent n'est pas connecté via WebSocket
        if not manager.is_connected(parent_email):
            await _send_fcm_push(
                db,
                parent_email,
                title=f"{icon} {subject} — {child_name}",
                body=payload.message,
                data={
                    "type": payload.alert_type,
                    "child_id": str(child_id) if child_id else "",
                    "child_name": child_name,
                    "device_name": payload.device_name,
                    "route": "/alerts",
                },
            )
    except Exception as e:
        import logging
        logging.getLogger("alerts").warning(f"Erreur envoi notification alerte: {e}")

    return {"status": "reported", "child_name": child_name}


@router.get("/all")
async def get_all_alerts_for_parent(
    parent_email: str,
    x_internal_secret: str = Header(default=""),
    limit: int = 50,
):
    """Récupère toutes les alertes pour un parent (appel interne backend)."""
    if x_internal_secret != INTERNAL_SECRET:
        return {"error": "forbidden"}
    db = get_db()
    children = await db.children.find({"parent_email": parent_email}).to_list(length=None)
    child_ids = [str(c["_id"]) for c in children]
    result = await db.alerts.find(
        {"child_id": {"$in": child_ids}}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    for a in result:
        a["_id"] = str(a["_id"])
        if "timestamp" in a and hasattr(a["timestamp"], "isoformat"):
            a["timestamp"] = a["timestamp"].isoformat()
    return result
