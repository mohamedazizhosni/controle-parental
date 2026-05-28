"""
Endpoint pour signaler les tentatives de contournement du contrôle parental.
POST /api/v1/alerts/report  → appelé par l'agent Android ou Windows
GET  /api/v1/alerts         → liste les alertes pour le parent connecté
PUT  /api/v1/alerts/{id}/read → marquer comme lue
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
    alert_type: str   # "vpn_disabled" | "proxy_disabled" | "blocked_site"
    message: str
    url: str = ""


@router.post("/report")
async def report_alert(
    payload: AlertReport,
    x_internal_secret: str = Header(default=""),
    request: Request = None,
):
    """
    Appelé par l'agent Android ou Windows quand l'enfant tente de désactiver
    le VPN ou le proxy. Aucune authentification requise (réseau local uniquement).
    """
    db = get_db()

    device = await db.devices.find_one({"device_name": payload.device_name})
    if not device:
        return {"error": "device not found", "device_name": payload.device_name}

    # Chercher active_child_id OU child_id (les deux noms sont utilisés selon le contexte)
    child_id = device.get("active_child_id") or device.get("child_id")
    parent_email = device.get("parent_email")

    child_name = "Enfant"
    if child_id and ObjectId.is_valid(str(child_id)):
        child_doc = await db.children.find_one({"_id": ObjectId(child_id)})
        if child_doc:
            child_name = child_doc.get("name", "Enfant")

    now = datetime.utcnow()

    # Sauvegarder l'alerte en base
    alert = {
        "child_id": str(child_id) if child_id else None,
        "child_name": child_name,
        "message": payload.message,
        "url": payload.url,
        "category": "security",
        "alert_type": payload.alert_type,
        "device_name": payload.device_name,
        "parent_email": parent_email,
        "read": False,
        "timestamp": now,
    }
    await db.alerts.insert_one(alert)

    if not parent_email:
        return {"status": "saved_no_parent"}

    try:
        from .notifications import manager, _send_fcm_push

        # Choisir l'icône selon le type
        if "vpn" in payload.alert_type:
            icon = "🛡️"
        elif "proxy" in payload.alert_type:
            icon = "⚠️"
        else:
            icon = "🚨"

        title = f"{icon} Alerte sécurité — {child_name}"
        ws_message = {
            "type": payload.alert_type,
            "title": title,
            "message": payload.message,
            "child_name": child_name,
            "device_name": payload.device_name,
            "timestamp": now.isoformat(),
        }

        # Envoyer via WebSocket si connecté (notification instantanée)
        if manager.is_connected(parent_email):
            await manager.send_personal_message(ws_message, parent_email)

        # Envoyer FCM TOUJOURS (app en arrière-plan, écran éteint, app fermée)
        await _send_fcm_push(
            db,
            parent_email,
            title=title,
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
        return {"status": "saved_notify_error", "error": str(e)}

    return {"status": "reported", "child_name": child_name, "parent_email": parent_email}


@router.get("")
async def get_alerts(current_user=None, limit: int = 50):
    """Liste toutes les alertes (non lues en premier)."""
    return {"info": "Use /notifications/history for authenticated access"}


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
    alerts = await db.alerts.find(
        {"parent_email": parent_email}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    for a in alerts:
        a["_id"] = str(a["_id"])
        if "timestamp" in a and hasattr(a["timestamp"], "isoformat"):
            a["timestamp"] = a["timestamp"].isoformat()
    return alerts
