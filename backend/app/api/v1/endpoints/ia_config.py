from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
import json
import os
from ....db.mongodb import get_db
from .auth import get_current_user

router = APIRouter(prefix="/ia", tags=["IA"])

CONFIG_FILE = "/app/ia_config/blocked_categories.json"

def write_categories(categories: list):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump({"blocked_categories": categories}, f)

@router.post("/update_categories")
async def update_global_categories(current_user = Depends(get_current_user)):
    """Récupère toutes les catégories bloquées pour tous les enfants du parent
       et les écrit dans le fichier partagé."""
    db = get_db()
    children = await db.children.find({"parent_email": current_user["email"]}).to_list(None)
    all_categories = set()
    for child in children:
        for cat in child.get("blocked_categories", []):
            all_categories.add(cat)
    write_categories(list(all_categories))
    return {"message": "Categories updated", "categories": list(all_categories)}
