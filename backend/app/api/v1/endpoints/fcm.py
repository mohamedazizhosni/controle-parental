from fastapi import APIRouter, Depends
from app.db.mongodb import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.fcm import FCMTokenRegister

router = APIRouter(prefix="/fcm", tags=["FCM"])

@router.post("/register")
async def register_fcm_token(
    data: FCMTokenRegister,
    current_user=Depends(get_current_user)
):
    db = get_db()
    await db.fcm_tokens.update_one(
        {"parent_email": current_user["email"]},
        {"$set": {
            "parent_email": current_user["email"],
            "token": data.fcm_token,
            "platform": data.device_platform,
        }},
        upsert=True,
    )
    return {"message": "FCM token registered"}

@router.delete("/unregister")
async def unregister_fcm_token(current_user=Depends(get_current_user)):
    db = get_db()
    await db.fcm_tokens.delete_one({"parent_email": current_user["email"]})
    return {"message": "FCM token removed"}
