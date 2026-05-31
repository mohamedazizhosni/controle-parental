import random
import string
import os
import secrets as _secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from bson import ObjectId
from ....db.mongodb import get_db
from ....models.pairing import PairingCode
from .auth import get_current_user
from ....core.security import create_access_token

router = APIRouter(prefix="/pairing", tags=["Pairing"])


def generate_code() -> str:
    return ''.join(random.choices(string.digits, k=6))


class VerifyPairingRequest(BaseModel):
    code: str
    device_type: str = "android"
    device_name: str = "android_agent"


@router.post("/generate/{profile_id}")
async def generate_pairing_code(
    profile_id: str,
    current_user=Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(profile_id):
        raise HTTPException(400, "Invalid profile_id")
    profile = await db.children.find_one(
        {"_id": ObjectId(profile_id), "parent_email": current_user["email"]}
    )
    if not profile:
        raise HTTPException(404, "Profile not found")

    code = generate_code()
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    pairing_doc = {
        "code": code,
        "profile_id": profile_id,
        "parent_email": current_user["email"],
        "used": False,
        "expires_at": expires_at,
        "created_at": datetime.utcnow(),
    }
    await db.pairing_codes.insert_one(pairing_doc)
    return {
        "code": code,
        "expires_at": expires_at.isoformat(),
        "profile_name": profile["name"],
    }


@router.post("/verify")
async def verify_pairing_code(request: VerifyPairingRequest):
    db = get_db()
    pairing = await db.pairing_codes.find_one({"code": request.code, "used": False})
    if not pairing:
        raise HTTPException(404, "Invalid or expired code")
    if pairing["expires_at"] < datetime.utcnow():
        raise HTTPException(400, "Code expired")

    device_name = request.device_name
    await db.pairing_codes.update_one(
        {"_id": pairing["_id"]},
        {"$set": {"used": True, "device_name": device_name, "device_type": request.device_type}},
    )
    profile = await db.children.find_one({"_id": ObjectId(pairing["profile_id"])})
    if not profile:
        raise HTTPException(404, "Associated profile not found")

    device_mode = profile.get("device_mode", "shared")
    child_id = str(profile["_id"])

    await db.devices.update_one(
        {"device_name": device_name},
        {"$set": {
            "parent_email": pairing["parent_email"],
            "child_id": child_id,
            "active_child_id": child_id,
            "enabled": True,
            "device_mode": device_mode,
            "device_type": request.device_type,
        }},
        upsert=True,
    )
    await db.sessions.delete_many({"device_name": device_name})

    access_token = create_access_token(data={"sub": pairing["parent_email"]})

    return {
        "token": access_token,
        "child_id": child_id,
        "child_name": profile["name"],
        "profile": {
            "id": child_id,
            "name": profile["name"],
            "age": profile["age"],
            "blocked_categories": profile.get("blocked_categories", []),
            "daily_time_limit_minutes": profile.get("daily_time_limit_minutes"),
            "allowed_time_slots": profile.get("allowed_time_slots", []),
            "device_mode": device_mode,
        },
        "proxy": {"host": "192.168.100.94", "port": 3128},
        "parent_pin": profile.get("parent_pin", "0000"),
        "message": "Pairing successful.",
    }


@router.get("/ca-certificate")
async def get_ca_certificate():
    cert_path = "/etc/squid/ssl/ca-certificate.crt"
    if not os.path.exists(cert_path):
        raise HTTPException(status_code=404, detail="CA certificate not found")
    return FileResponse(
        cert_path,
        media_type="application/x-x509-ca-cert",
        filename="parental-control-ca.crt",
    )


@router.post("/disable/{device_name}")
async def disable_device(device_name: str, current_user=Depends(get_current_user)):
    """Bloque un appareil à distance."""
    db = get_db()
    device = await db.devices.find_one(
        {"device_name": device_name, "parent_email": current_user["email"]}
    )
    if not device:
        raise HTTPException(404, "Device not found")
    await db.devices.update_one(
        {"_id": device["_id"]}, {"$set": {"enabled": False}}
    )
    return {"message": f"Device {device_name} disabled"}


@router.post("/enable/{device_name}")
async def enable_device(device_name: str, current_user=Depends(get_current_user)):
    """Débloque un appareil à distance."""
    db = get_db()
    device = await db.devices.find_one(
        {"device_name": device_name, "parent_email": current_user["email"]}
    )
    if not device:
        raise HTTPException(404, "Device not found")
    await db.devices.update_one(
        {"_id": device["_id"]}, {"$set": {"enabled": True}}
    )
    return {"message": f"Device {device_name} enabled"}


@router.get("/status")
async def device_status(device_name: str):
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        return {"enabled": None, "paired": False}
    return {"enabled": device.get("enabled", True), "paired": True}


# ─── Token d'installation automatique ────────────────────────────────────────

@router.post("/generate-install-token")
async def generate_install_token(payload: dict, current_user=Depends(get_current_user)):
    """
    Génère un token d'installation one-shot pour l'agent Windows ou Android.
    Payload: { "profile_id": "...", "server_ip": "192.168.x.x" }
    Valable 30 minutes, lié au profil enfant choisi.
    Le parent affiche ce token sous forme de QR code dans l'app parent.
    """
    profile_id = payload.get("profile_id", "").strip()
    server_ip  = payload.get("server_ip", "").strip()

    if not profile_id or not server_ip:
        raise HTTPException(400, "profile_id et server_ip requis")

    db = get_db()
    if not ObjectId.is_valid(profile_id):
        raise HTTPException(400, "profile_id invalide")

    profile = await db.children.find_one(
        {"_id": ObjectId(profile_id), "parent_email": current_user["email"]}
    )
    if not profile:
        raise HTTPException(404, "Profil enfant introuvable")

    token = _secrets.token_urlsafe(16)
    expires_at = datetime.utcnow() + timedelta(minutes=30)

    await db.install_tokens.insert_one({
        "token":        token,
        "profile_id":   profile_id,
        "parent_email": current_user["email"],
        "server_ip":    server_ip,
        "used":         False,
        "expires_at":   expires_at,
        "created_at":   datetime.utcnow(),
    })

    return {
        "token":        token,
        "expires_at":   expires_at.isoformat(),
        "server_ip":    server_ip,
        "profile_name": profile["name"],
        "qr_data": {
            "type":       "install_token",
            "token":      token,
            "server_ip":  server_ip,
        },
        "message": "Token valable 30 minutes."
    }


@router.post("/redeem-install-token")
async def redeem_install_token(payload: dict):
    """
    Échangé par l'agent au premier lancement pour récupérer sa config.
    Payload: { "token": "...", "device_name": "...", "device_type": "windows"|"android" }
    """
    token       = payload.get("token", "").strip()
    device_name = payload.get("device_name", "").strip()
    device_type = payload.get("device_type", "windows").strip()

    if not token or not device_name:
        raise HTTPException(400, "token et device_name requis")

    db = get_db()
    record = await db.install_tokens.find_one({"token": token, "used": False})
    if not record:
        raise HTTPException(404, "Token invalide ou déjà utilisé")
    if record["expires_at"] < datetime.utcnow():
        raise HTTPException(400, "Token expiré (30 minutes dépassées)")

    profile = await db.children.find_one({"_id": ObjectId(record["profile_id"])})
    if not profile:
        raise HTTPException(404, "Profil introuvable")

    # Marquer le token comme utilisé (one-shot)
    await db.install_tokens.update_one(
        {"_id": record["_id"]},
        {"$set": {
            "used":         True,
            "device_name":  device_name,
            "device_type":  device_type,
            "redeemed_at":  datetime.utcnow(),
        }}
    )

    child_id  = str(profile["_id"])
    server_ip = record["server_ip"]

    # Enregistrer l'appareil
    await db.devices.update_one(
        {"device_name": device_name},
        {"$set": {
            "parent_email":    record["parent_email"],
            "child_id":        child_id,
            "active_child_id": child_id,
            "enabled":         True,
            "device_mode":     profile.get("device_mode", "shared"),
            "device_type":     device_type,
        }},
        upsert=True,
    )
    await db.sessions.delete_many({"device_name": device_name})

    access_token = create_access_token(data={"sub": record["parent_email"]})

    return {
        "token":      access_token,
        "server_ip":  server_ip,
        "child_id":   child_id,
        "child_name": profile["name"],
        "proxy_port": 3128,
        "profile": {
            "id":                       child_id,
            "name":                     profile["name"],
            "age":                      profile["age"],
            "blocked_categories":       profile.get("blocked_categories", []),
            "daily_time_limit_minutes": profile.get("daily_time_limit_minutes"),
            "allowed_time_slots":       profile.get("allowed_time_slots", []),
            "device_mode":              profile.get("device_mode", "shared"),
        },
        "parent_pin": profile.get("parent_pin", ""),
    }
