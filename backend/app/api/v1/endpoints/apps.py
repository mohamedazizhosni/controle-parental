from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime
from bson import ObjectId
from ....db.mongodb import get_db
from ....models.app_usage import BlockedApp, BlockedAppInDB, InstalledApp
from .auth import get_current_user

router = APIRouter(prefix="/apps", tags=["Apps Android"])


# ─────────────────────────────────────────
# APPS BLOQUÉES
# ─────────────────────────────────────────

@router.get("/blocked/{child_id}")
async def get_blocked_apps(
    child_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Récupérer la liste des apps bloquées pour un enfant."""
    # Vérifier que l'enfant appartient au parent
    child = await db["children"].find_one({
        "_id": ObjectId(child_id),
        "parent_email": current_user["email"]
    })
    if not child:
        raise HTTPException(status_code=404, detail="Enfant non trouvé")

    cursor = db["blocked_apps"].find({
        "child_id": child_id,
        "parent_email": current_user["email"]
    })
    apps = []
    async for app in cursor:
        app["_id"] = str(app["_id"])
        apps.append(app)
    return apps


@router.post("/blocked/{child_id}")
async def block_app(
    child_id: str,
    app_data: BlockedApp,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Bloquer une application pour un enfant."""
    child = await db["children"].find_one({
        "_id": ObjectId(child_id),
        "parent_email": current_user["email"]
    })
    if not child:
        raise HTTPException(status_code=404, detail="Enfant non trouvé")

    # Éviter les doublons
    existing = await db["blocked_apps"].find_one({
        "child_id": child_id,
        "package_name": app_data.package_name
    })
    if existing:
        return {"status": "already_blocked", "package_name": app_data.package_name}

    doc = {
        "child_id": child_id,
        "parent_email": current_user["email"],
        "package_name": app_data.package_name,
        "app_name": app_data.app_name or app_data.package_name,
        "blocked_at": datetime.utcnow(),
    }
    await db["blocked_apps"].insert_one(doc)
    return {"status": "blocked", "package_name": app_data.package_name}


@router.delete("/blocked/{child_id}/{package_name}")
async def unblock_app(
    child_id: str,
    package_name: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Débloquer une application pour un enfant."""
    result = await db["blocked_apps"].delete_one({
        "child_id": child_id,
        "parent_email": current_user["email"],
        "package_name": package_name
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="App non trouvée dans la liste")
    return {"status": "unblocked", "package_name": package_name}


# ─────────────────────────────────────────
# APPS INSTALLÉES (rapportées par l'agent Android)
# ─────────────────────────────────────────

@router.post("/installed/{child_id}")
async def report_installed_apps(
    child_id: str,
    apps: List[InstalledApp],
    db=Depends(get_db)
):
    """L'agent Android envoie la liste des apps installées (pas d'auth JWT — utilise device_name)."""
    if not apps:
        return {"status": "ok", "count": 0}

    # Remplacer la liste complète
    await db["installed_apps"].delete_many({"child_id": child_id})
    docs = [
        {
            "child_id": child_id,
            "package_name": app.package_name,
            "app_name": app.app_name or app.package_name,
            "version": app.version,
            "install_time": app.install_time,
            "updated_at": datetime.utcnow(),
        }
        for app in apps
    ]
    await db["installed_apps"].insert_many(docs)
    return {"status": "ok", "count": len(docs)}


@router.get("/installed/{child_id}")
async def get_installed_apps(
    child_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Récupérer la liste des apps installées sur l'appareil de l'enfant."""
    child = await db["children"].find_one({
        "_id": ObjectId(child_id),
        "parent_email": current_user["email"]
    })
    if not child:
        raise HTTPException(status_code=404, detail="Enfant non trouvé")

    # Enrichir avec le statut bloqué
    blocked_cursor = db["blocked_apps"].find({"child_id": child_id})
    blocked_pkgs = set()
    async for b in blocked_cursor:
        blocked_pkgs.add(b["package_name"])

    cursor = db["installed_apps"].find({"child_id": child_id})
    apps = []
    async for app in cursor:
        app["_id"] = str(app["_id"])
        app["is_blocked"] = app["package_name"] in blocked_pkgs
        apps.append(app)

    # Trier : bloquées en premier, puis par nom
    apps.sort(key=lambda x: (not x["is_blocked"], x.get("app_name", "")))
    return apps


# ─────────────────────────────────────────
# ENDPOINT POUR L'AGENT ANDROID
# (récupérer la liste des apps à bloquer)
# ─────────────────────────────────────────

@router.get("/blocked_list/{child_id}")
async def get_blocked_apps_for_agent(
    child_id: str,
    db=Depends(get_db)
):
    """
    Endpoint public (sans JWT) pour l'agent Android.
    Retourne juste la liste des package_names à bloquer.
    """
    cursor = db["blocked_apps"].find({"child_id": child_id})
    packages = []
    async for app in cursor:
        packages.append(app["package_name"])
    return {"child_id": child_id, "blocked_packages": packages}
