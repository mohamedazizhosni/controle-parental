from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
from bson import ObjectId
import os
import json
from ....db.mongodb import get_db

router = APIRouter(prefix="/devices", tags=["Devices"])

CONFIG_FILE = "/app/ia_config/blocked_categories.json"

def write_categories(categories: list):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"blocked_categories": categories}, f)

async def auto_register_device_ip(device_name: str, request: Request):
    """Enregistre automatiquement l'IP de l'appareil lors de chaque requête"""
    try:
        db = get_db()
        # Récupérer l'IP réelle du client
        client_ip = request.client.host
        
        # Si derrière un proxy, utiliser X-Forwarded-For
        if "x-forwarded-for" in request.headers:
            client_ip = request.headers["x-forwarded-for"].split(",")[0].strip()
        elif "x-real-ip" in request.headers:
            client_ip = request.headers["x-real-ip"]
        
        # Enregistrer le mapping IP → appareil
        await db.ip_mapping.update_one(
            {"device_name": device_name},
            {"$set": {"ip": client_ip, "updated_at": datetime.utcnow()}},
            upsert=True
        )
    except Exception as e:
        # Ne pas bloquer la requête si l'enregistrement échoue
        print(f"Erreur lors de l'enregistrement de l'IP: {e}")


@router.post("/{device_name}/verify_parent_pin")
async def verify_parent_pin(device_name: str, parent_pin: str, request: Request):
    # Enregistrer automatiquement l'IP
    await auto_register_device_ip(device_name, request)
    
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Device not found")
    parent_email = device.get("parent_email")
    children = await db.children.find({"parent_email": parent_email}).to_list(length=1)
    if not children:
        raise HTTPException(404, "No children found for parent")
    child = children[0]
    stored_pin = child.get("parent_pin")
    if stored_pin is None or stored_pin == "":
        return {"valid": False, "message": "No parent PIN set"}
    if parent_pin == stored_pin:
        return {"valid": True}
    else:
        return {"valid": False, "message": "PIN incorrect"}


@router.post("/{device_name}/select_child")
async def select_child(device_name: str, child_id: str, request: Request):
    # Enregistrer automatiquement l'IP
    await auto_register_device_ip(device_name, request)
    
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Device not found")
    parent_email = device.get("parent_email")
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child id")
    child = await db.children.find_one({"_id": ObjectId(child_id), "parent_email": parent_email})
    if not child:
        raise HTTPException(403, "Child not allowed")
    await db.devices.update_one(
        {"_id": device["_id"]},
        {"$set": {"active_child_id": child_id}}
    )
    blocked_cats = child.get("blocked_categories", [])
    write_categories(blocked_cats)
    return {"valid": True, "message": f"Active child set to {child['name']}, categories updated"}


@router.get("/{device_name}/children")
async def get_children_for_device(device_name: str, request: Request):
    # Enregistrer automatiquement l'IP
    await auto_register_device_ip(device_name, request)
    
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Device not found")
    parent_email = device.get("parent_email")
    device_mode = device.get("device_mode", "shared")
    children = await db.children.find({
        "parent_email": parent_email,
        "device_mode": device_mode
    }).to_list(length=100)
    for c in children:
        c["_id"] = str(c["_id"])
    return children


@router.get("/{device_name}/active_child_profile")
async def get_active_child_profile(device_name: str, request: Request):
    # Enregistrer automatiquement l'IP
    await auto_register_device_ip(device_name, request)
    
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Device not found")
    child_id = device.get("active_child_id")
    if not child_id:
        return {"active": False, "profile": None}
    if not ObjectId.is_valid(child_id):
        return {"active": False, "profile": None}
    child = await db.children.find_one({"_id": ObjectId(child_id)})
    if not child:
        return {"active": False, "profile": None}
    child["_id"] = str(child["_id"])
    return {"active": True, "profile": child}


@router.post("/{device_name}/verify_child_pin")
async def verify_child_pin(device_name: str, child_id: str, child_pin: str, request: Request):
    # Enregistrer automatiquement l'IP
    await auto_register_device_ip(device_name, request)
    
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Device not found")
    parent_email = device.get("parent_email")
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child id")
    try:
        obj_id = ObjectId(child_id)
    except:
        raise HTTPException(400, "Invalid child id format")
    child = await db.children.find_one({"_id": obj_id, "parent_email": parent_email})
    if not child:
        raise HTTPException(404, "Child not found")
    stored_pin = child.get("child_pin")
    if stored_pin is None or stored_pin == "":
        await db.devices.update_one(
            {"_id": device["_id"]},
            {"$set": {"active_child_id": child_id}}
        )
        blocked_cats = child.get("blocked_categories", [])
        write_categories(blocked_cats)
        return {"valid": True, "child_id": child_id, "name": child["name"]}
    if child_pin == stored_pin:
        await db.devices.update_one(
            {"_id": device["_id"]},
            {"$set": {"active_child_id": child_id}}
        )
        blocked_cats = child.get("blocked_categories", [])
        write_categories(blocked_cats)
        return {"valid": True, "child_id": child_id, "name": child["name"]}
    else:
        return {"valid": False, "message": "PIN enfant incorrect"}


@router.post("/register_ip")
async def register_ip(device_name: str, ip: str):
    db = get_db()
    await db.ip_mapping.update_one(
        {"device_name": device_name},
        {"$set": {"ip": ip, "updated_at": datetime.utcnow()}},
        upsert=True
    )
    return {"message": "IP registered"}


@router.get("/ip_to_child/{ip}")
async def ip_to_child(ip: str):
    db = get_db()
    mapping = await db.ip_mapping.find_one({"ip": ip})
    if not mapping:
        return {"child_id": None}
    device_name = mapping["device_name"]
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        return {"child_id": None}
    child_id = device.get("active_child_id")
    return {"child_id": child_id}
