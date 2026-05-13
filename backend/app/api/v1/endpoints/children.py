from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
import httpx
from ....db.mongodb import get_db
from ....models.child_profile import ChildProfile, ChildProfileCreate, ChildProfileUpdate
from ....models.history import NavigationEntry, Alert
from .auth import get_current_user

router = APIRouter(prefix="/children", tags=["Children"])


def profile_helper(profile) -> dict:
    profile["_id"] = str(profile["_id"])
    return profile


def get_today_midnight() -> datetime:
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def _slot_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _slots_overlap(slots_a: list, slots_b: list) -> bool:
    for a in slots_a:
        a_start = _slot_to_minutes(a["start"])
        a_end = _slot_to_minutes(a["end"])
        for b in slots_b:
            b_start = _slot_to_minutes(b["start"])
            b_end = _slot_to_minutes(b["end"])
            if a_start < b_end and a_end > b_start:
                return True
    return False


async def _check_slot_conflicts(db, shared_device_id: str, exclude_child_id: Optional[str],
                                new_slots: list, parent_email: str):
    if not shared_device_id or not new_slots:
        return
    query = {
        "parent_email": parent_email,
        "device_mode": "dedicated",
        "shared_device_id": shared_device_id,
    }
    if exclude_child_id:
        query["_id"] = {"$ne": ObjectId(exclude_child_id)}
    async for sibling in db.children.find(query):
        sibling_slots = sibling.get("allowed_time_slots", [])
        if _slots_overlap(new_slots, sibling_slots):
            raise HTTPException(
                status_code=409,
                detail=f"Conflit de plage horaire avec le profil '{sibling['name']}' "
                       f"dans le même groupe d'appareils."
            )


async def update_ia_config(token: str):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://backend:8000/api/v1/ia/update_categories",
                headers={"Authorization": f"Bearer {token}"},
                timeout=2.0
            )
    except Exception:
        pass


# ---------- Gestion des profils ----------

@router.post("/", response_model=ChildProfile, status_code=status.HTTP_201_CREATED)
async def create_child_profile(
    profile: ChildProfileCreate,
    current_user = Depends(get_current_user)
):
    db = get_db()
    new_profile = profile.dict(exclude_unset=True)
    new_profile["parent_email"] = current_user["email"]

    if new_profile.get("device_mode") == "shared":
        new_profile["allowed_time_slots"] = []
        new_profile.pop("shared_device_id", None)
    elif new_profile.get("device_mode") == "dedicated":
        new_profile["daily_time_limit_minutes"] = None
        await _check_slot_conflicts(
            db,
            new_profile.get("shared_device_id"),
            None,
            new_profile.get("allowed_time_slots", []),
            current_user["email"]
        )

    result = await db.children.insert_one(new_profile)
    created = await db.children.find_one({"_id": result.inserted_id})
    await update_ia_config(current_user["token"])
    return ChildProfile(**profile_helper(created))


@router.get("/", response_model=List[ChildProfile])
async def list_child_profiles(current_user = Depends(get_current_user)):
    db = get_db()
    profiles = []
    async for doc in db.children.find({"parent_email": current_user["email"]}):
        profiles.append(ChildProfile(**profile_helper(doc)))
    return profiles


# ---------- Routes fixes — AVANT les routes paramétrées /{id} ----------

@router.get("/shared_groups")
async def list_shared_groups(current_user = Depends(get_current_user)):
    db = get_db()
    pipeline = [
        {"$match": {"parent_email": current_user["email"], "device_mode": "dedicated",
                    "shared_device_id": {"$ne": None}}},
        {"$group": {"_id": "$shared_device_id", "count": {"$sum": 1}}},
        {"$project": {"shared_device_id": "$_id", "count": 1, "_id": 0}}
    ]
    result = await db.children.aggregate(pipeline).to_list(None)
    return result


@router.get("/group/{shared_device_id}")
async def get_group_profiles(shared_device_id: str, current_user = Depends(get_current_user)):
    db = get_db()
    profiles = []
    async for doc in db.children.find({
        "parent_email": current_user["email"],
        "device_mode": "dedicated",
        "shared_device_id": shared_device_id
    }):
        profiles.append(profile_helper(doc))
    return profiles


# ---------- Historique ----------

@router.post("/history", status_code=status.HTTP_201_CREATED)
async def add_history(entry: NavigationEntry):
    db = get_db()
    await db.history.insert_one(entry.dict())
    return {"message": "ok"}


@router.get("/history/{child_id}")
async def get_history(child_id: str, current_user = Depends(get_current_user), limit: int = 100):
    db = get_db()
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child id")
    profile = await db.children.find_one({"_id": ObjectId(child_id), "parent_email": current_user["email"]})
    if not profile:
        raise HTTPException(404, "Child not found")
    cursor = db.history.find({"child_id": child_id}).sort("timestamp", -1).limit(limit)
    entries = await cursor.to_list(length=limit)
    for e in entries:
        e["_id"] = str(e["_id"])
        if "timestamp" in e and hasattr(e["timestamp"], "isoformat"):
            e["timestamp"] = e["timestamp"].isoformat()
    return entries


# ---------- Alertes ----------

@router.post("/alert", status_code=status.HTTP_201_CREATED)
async def send_alert(alert: Alert):
    db = get_db()
    await db.alerts.insert_one(alert.dict())
    return {"message": "alert received"}


@router.get("/alerts")
async def get_alerts(current_user = Depends(get_current_user), unread_only: bool = False):
    db = get_db()
    children = await db.children.find({"parent_email": current_user["email"]}).to_list(None)
    child_ids = [str(c["_id"]) for c in children]
    child_name_map = {str(c["_id"]): c.get("name", "Enfant") for c in children}

    query = {"child_id": {"$in": child_ids}}
    if unread_only:
        query["read"] = False
    cursor = db.alerts.find(query).sort("timestamp", -1)
    alerts = await cursor.to_list(length=200)
    for a in alerts:
        a["_id"] = str(a["_id"])
        if "timestamp" in a and hasattr(a["timestamp"], "isoformat"):
            a["timestamp"] = a["timestamp"].isoformat()
        if not a.get("child_name") and a.get("child_id"):
            a["child_name"] = child_name_map.get(a["child_id"], "Enfant")
    return alerts


@router.put("/alert/{alert_id}/read")
async def mark_alert_read(alert_id: str, current_user = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(alert_id):
        raise HTTPException(400, "Invalid alert id")
    result = await db.alerts.update_one({"_id": ObjectId(alert_id)}, {"$set": {"read": True}})
    if result.modified_count == 0:
        raise HTTPException(404, "Alert not found")
    return {"message": "marked read"}


# ---------- Routes paramétrées /{profile_id} — TOUJOURS EN DERNIER ----------

@router.get("/{profile_id}", response_model=ChildProfile)
async def get_child_profile(profile_id: str, current_user = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(profile_id):
        raise HTTPException(status_code=400, detail="Invalid profile id")
    profile = await db.children.find_one({"_id": ObjectId(profile_id), "parent_email": current_user["email"]})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ChildProfile(**profile_helper(profile))


@router.put("/{profile_id}", response_model=ChildProfile)
async def update_child_profile(
    profile_id: str,
    update_data: ChildProfileUpdate,
    current_user = Depends(get_current_user)
):
    db = get_db()
    if not ObjectId.is_valid(profile_id):
        raise HTTPException(status_code=400, detail="Invalid profile id")
    existing = await db.children.find_one({"_id": ObjectId(profile_id), "parent_email": current_user["email"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_dict = {k: v for k, v in update_data.dict(exclude_unset=True).items() if v is not None}

    effective_mode = update_dict.get("device_mode", existing.get("device_mode", "shared"))

    if effective_mode == "shared":
        update_dict["allowed_time_slots"] = []
        update_dict.pop("shared_device_id", None)
    elif effective_mode == "dedicated":
        update_dict["daily_time_limit_minutes"] = None
        new_slots = update_dict.get("allowed_time_slots", existing.get("allowed_time_slots", []))
        shared_id = update_dict.get("shared_device_id", existing.get("shared_device_id"))
        await _check_slot_conflicts(db, shared_id, profile_id, new_slots, current_user["email"])

    if update_dict:
        await db.children.update_one({"_id": ObjectId(profile_id)}, {"$set": update_dict})
        if "daily_time_limit_minutes" in update_dict:
            today = get_today_midnight()
            await db.sessions.delete_many({"child_id": profile_id, "date": today})

    updated = await db.children.find_one({"_id": ObjectId(profile_id)})
    await update_ia_config(current_user["token"])
    return ChildProfile(**profile_helper(updated))


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_child_profile(profile_id: str, current_user = Depends(get_current_user)):
    db = get_db()
    if not ObjectId.is_valid(profile_id):
        raise HTTPException(status_code=400, detail="Invalid profile id")
    result = await db.children.delete_one({"_id": ObjectId(profile_id), "parent_email": current_user["email"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    await update_ia_config(current_user["token"])
