from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from bson import ObjectId
from datetime import datetime, date
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
    """Retourne un datetime à 00:00:00 UTC pour la date actuelle."""
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

async def update_ia_config(token: str):
    """Appelle l'endpoint IA pour rafraîchir la liste des catégories bloquées."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://backend:8000/api/v1/ia/update_categories",
                headers={"Authorization": f"Bearer {token}"},
                timeout=2.0
            )
    except Exception:
        # Ignorer les erreurs (ne pas casser la création/modification)
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
    result = await db.children.insert_one(new_profile)
    created = await db.children.find_one({"_id": result.inserted_id})
    # Mettre à jour la configuration IA
    await update_ia_config(current_user["token"])
    return ChildProfile(**profile_helper(created))

@router.get("/", response_model=List[ChildProfile])
async def list_child_profiles(current_user = Depends(get_current_user)):
    db = get_db()
    profiles = []
    async for doc in db.children.find({"parent_email": current_user["email"]}):
        profiles.append(ChildProfile(**profile_helper(doc)))
    return profiles

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
    if update_dict:
        await db.children.update_one({"_id": ObjectId(profile_id)}, {"$set": update_dict})
        # Si la limite de temps a changé, supprimer les sessions du jour pour cet enfant
        if "daily_time_limit_minutes" in update_dict:
            today = get_today_midnight()
            await db.sessions.delete_many({
                "child_id": profile_id,
                "date": today
            })
    updated = await db.children.find_one({"_id": ObjectId(profile_id)})
    # Mettre à jour la configuration IA
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
    # Mettre à jour la configuration IA
    await update_ia_config(current_user["token"])

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
    query = {"child_id": {"$in": child_ids}}
    if unread_only:
        query["read"] = False
    cursor = db.alerts.find(query).sort("timestamp", -1)
    alerts = await cursor.to_list(length=100)
    for a in alerts:
        a["_id"] = str(a["_id"])
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
