from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Set
import json
import asyncio
import logging
from datetime import datetime
from bson import ObjectId
from ....db.mongodb import get_db
from .auth import get_current_user

logger = logging.getLogger("notifications")

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# Gestionnaire de connexions WebSocket
class ConnectionManager:
    def __init__(self):
        # parent_email -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, parent_email: str):
        await websocket.accept()
        if parent_email not in self.active_connections:
            self.active_connections[parent_email] = set()
        self.active_connections[parent_email].add(websocket)
        logger.info(f"Parent {parent_email} connecté via WebSocket")

    def disconnect(self, websocket: WebSocket, parent_email: str):
        if parent_email in self.active_connections:
            self.active_connections[parent_email].discard(websocket)
            if not self.active_connections[parent_email]:
                del self.active_connections[parent_email]
        logger.info(f"Parent {parent_email} déconnecté")

    async def send_personal_message(self, message: dict, parent_email: str):
        """Envoyer un message à un parent spécifique."""
        if parent_email in self.active_connections:
            dead_connections = set()
            for connection in self.active_connections[parent_email]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Erreur envoi à {parent_email}: {e}")
                    dead_connections.add(connection)
            for dead in dead_connections:
                self.active_connections[parent_email].discard(dead)

    async def broadcast_to_parent(self, parent_email: str, notification: dict):
        """Envoyer une notification à toutes les connexions d'un parent."""
        message = {
            "type": "notification",
            "timestamp": datetime.utcnow().isoformat(),
            "data": notification
        }
        await self.send_personal_message(message, parent_email)

    def is_connected(self, parent_email: str) -> bool:
        return (
            parent_email in self.active_connections
            and len(self.active_connections[parent_email]) > 0
        )

manager = ConnectionManager()


# Correction : fonction helper pour envoyer un push FCM via firebase_admin
# Utilisée en fallback quand le parent n'est pas connecté via WebSocket
async def _send_fcm_push(db, parent_email: str, title: str, body: str, data: dict = None):
    """Envoyer un push FCM si le token est enregistré."""
    try:
        import firebase_admin
        from firebase_admin import messaging as fb_messaging

        record = await db.fcm_tokens.find_one({"parent_email": parent_email})
        if not record or not record.get("token"):
            return

        message = fb_messaging.Message(
            notification=fb_messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=record["token"],
            android=fb_messaging.AndroidConfig(
                priority="high",
                notification=fb_messaging.AndroidNotification(
                    channel_id="parental_control_channel",
                    priority="high",
                ),
            ),
        )
        fb_messaging.send(message)
        logger.info(f"FCM push envoyé à {parent_email}")
    except Exception as e:
        logger.warning(f"FCM push échoué pour {parent_email}: {e}")


@router.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """
    WebSocket endpoint pour notifications temps réel.
    Les parents se connectent avec leur JWT token.
    """
    try:
        from ....core.security import decode_access_token
        payload = decode_access_token(token)

        if not payload:
            await websocket.close(code=1008, reason="Invalid token")
            return

        parent_email = payload.get("sub")
        if not parent_email:
            await websocket.close(code=1008, reason="Invalid token payload")
            return

        await manager.connect(websocket, parent_email)

        await websocket.send_json({
            "type": "connected",
            "message": "Connecté au service de notifications",
            "parent_email": parent_email,
            "timestamp": datetime.utcnow().isoformat()
        })

        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"Erreur WebSocket pour {parent_email}: {e}")
                break

    except Exception as e:
        logger.error(f"Erreur connexion WebSocket: {e}")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except:
            pass
    finally:
        if 'parent_email' in locals():
            manager.disconnect(websocket, parent_email)


@router.post("/send")
async def send_notification(
    child_id: str,
    notification_type: str,
    message: str,
    data: dict = None
):
    """API pour envoyer des notifications (appelé par d'autres services)."""
    db = get_db()

    if not ObjectId.is_valid(child_id):
        return {"error": "Invalid child_id"}

    child = await db.children.find_one({"_id": ObjectId(child_id)})
    if not child:
        return {"error": "Child not found"}

    parent_email = child.get("parent_email")

    notification = {
        "id": str(ObjectId()),
        "child_id": child_id,
        "child_name": child.get("name"),
        "type": notification_type,
        "message": message,
        "data": data or {},
        "timestamp": datetime.utcnow().isoformat(),
        "read": False
    }

    await db.notifications.insert_one(notification)

    # Envoyer via WebSocket si le parent est connecté
    await manager.broadcast_to_parent(parent_email, notification)

    # Correction : envoyer un push FCM si le parent n'est PAS connecté via WebSocket
    # Avant : si le parent avait l'app fermée, aucune notification n'arrivait
    if not manager.is_connected(parent_email):
        await _send_fcm_push(
            db,
            parent_email,
            title=f"Alerte - {child.get('name', '')}",
            body=message,
            data={"type": notification_type, "child_id": child_id, "route": "/alerts"},
        )

    return {
        "status": "sent",
        "parent_email": parent_email,
        "ws_connected": manager.is_connected(parent_email)
    }


@router.get("/history")
async def get_notification_history(
    current_user=Depends(get_current_user),
    limit: int = 50,
    unread_only: bool = False
):
    """Récupérer l'historique des notifications."""
    db = get_db()

    children = await db.children.find(
        {"parent_email": current_user["email"]}
    ).to_list(length=None)

    child_ids = [str(c["_id"]) for c in children]

    query = {"child_id": {"$in": child_ids}}
    if unread_only:
        query["read"] = False

    notifications = await db.notifications.find(query)\
        .sort("timestamp", -1)\
        .limit(limit)\
        .to_list(length=limit)

    for notif in notifications:
        notif["_id"] = str(notif["_id"])

    return notifications


@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user=Depends(get_current_user)
):
    """Marquer une notification comme lue."""
    db = get_db()

    if not ObjectId.is_valid(notification_id):
        return {"error": "Invalid notification_id"}

    result = await db.notifications.update_one(
        {"_id": ObjectId(notification_id)},
        {"$set": {"read": True}}
    )

    if result.modified_count == 0:
        return {"error": "Notification not found"}

    return {"status": "ok"}


# Fonction helper pour envoyer des notifications depuis d'autres endpoints
async def send_notification_to_parent(
    db,
    child_id: str,
    notification_type: str,
    message: str,
    data: dict = None
):
    """Fonction utilitaire pour envoyer des notifications depuis le code."""
    child = await db.children.find_one({"_id": ObjectId(child_id)})
    if not child:
        return

    parent_email = child.get("parent_email")

    notification = {
        "id": str(ObjectId()),
        "child_id": child_id,
        "child_name": child.get("name"),
        "type": notification_type,
        "message": message,
        "data": data or {},
        "timestamp": datetime.utcnow().isoformat(),
        "read": False
    }

    await db.notifications.insert_one(notification)
    await manager.broadcast_to_parent(parent_email, notification)

    # Correction : fallback FCM si WebSocket absent
    if not manager.is_connected(parent_email):
        await _send_fcm_push(
            db,
            parent_email,
            title=f"Alerte - {child.get('name', '')}",
            body=message,
            data={"type": notification_type, "child_id": child_id, "route": "/alerts"},
        )
