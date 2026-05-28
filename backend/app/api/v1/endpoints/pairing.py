import random
import string
import os
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
        raise HTTPException(400, "Invalid profile id")
    profile = await db.children.find_one(
        {"_id": ObjectId(profile_id), "parent_email": current_user["email"]}
    )
    if not profile:
        raise HTTPException(404, "Profile not found")
    for _ in range(5):
        code = generate_code()
        existing = await db.pairing_codes.find_one({"code": code, "used": False})
        if not existing:
            break
    else:
        raise HTTPException(500, "Could not generate unique code")
    pairing = {
        "code": code,
        "profile_id": profile_id,
        "parent_email": current_user["email"],
        "device_type": "android",
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
        "used": False,
    }
    await db.pairing_codes.insert_one(pairing)
    return {"code": code, "expires_in_minutes": 10}


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

    # Stocker child_id ET active_child_id pour compatibilité avec alerts.py
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
    """Bloque un appareil à distance (internet coupé sur l'agent)."""
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
    """Débloque un appareil à distance (réactive le mode enfant sur l'agent)."""
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
