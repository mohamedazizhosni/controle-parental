from fastapi import APIRouter, Depends, HTTPException
from app.db.mongodb import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.app_usage import AppUsageReport
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/app_usage", tags=["App Usage Android"])

@router.post("/report")
async def report_app_usage(report: AppUsageReport):
    db = get_db()
    # Chercher le device par active_child_id (après select_child)
    # OU par child_id (défini lors du pairing initial)
    device = await db.devices.find_one({
        "$or": [
            {"active_child_id": report.child_id},
            {"child_id": report.child_id},
        ]
    })
    if not device:
        raise HTTPException(404, "Device not found")
    for app in report.apps:
        await db.app_usage.update_one(
            {
                "child_id": report.child_id,
                "package_name": app.package_name,
                "date": app.date,
            },
            {"$set": {
                "app_name": app.app_name,
                "usage_seconds": app.usage_seconds,
                "device_name": report.device_name,
                "updated_at": datetime.utcnow(),
            }},
            upsert=True,
        )
    return {"message": f"{len(report.apps)} usage records saved"}

@router.get("/daily/{child_id}")
async def get_daily_usage(child_id: str, current_user=Depends(get_current_user)):
    db = get_db()
    child = await db.children.find_one({
        "_id": ObjectId(child_id),
        "parent_email": current_user["email"]
    })
    if not child:
        raise HTTPException(404, "Child not found")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cursor = db.app_usage.find({"child_id": child_id, "date": today}, {"_id": 0})
    records = await cursor.to_list(length=200)
    return {"date": today, "usage": records}

@router.get("/history/{child_id}")
async def get_app_usage_history(
    child_id: str,
    date: str = None,
    current_user=Depends(get_current_user)
):
    db = get_db()
    child = await db.children.find_one({
        "_id": ObjectId(child_id),
        "parent_email": current_user["email"]
    })
    if not child:
        raise HTTPException(404, "Child not found")
    query = {"child_id": child_id}
    if date:
        query["date"] = date
    cursor = db.app_usage.find(query, {"_id": 0})
    records = await cursor.to_list(length=500)
    return {"usage": records}
