import secrets
import string
import logging
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from ....db.mongodb import get_db
from ....core.security import get_password_hash, verify_password
from .auth import get_current_user

logger = logging.getLogger("master_code")
router = APIRouter(prefix="/master-code", tags=["Master Code"])


def _generate_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def _try_send_email(email: str, code: str):
    try:
        import smtplib, os
        from email.mime.text import MIMEText
        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        from_addr = os.getenv("SMTP_FROM", smtp_user)
        if not smtp_host or not smtp_user:
            logger.info("[MasterCode] SMTP non configuré, email ignoré.")
            return False
        msg = MIMEText(
            f"Votre code maître de contrôle parental est : {code}\n\n"
            f"Conservez ce code. Il est nécessaire pour désinstaller l'agent "
            f"sur les appareils de vos enfants.\n"
        )
        msg["Subject"] = "Contrôle Parental — Code maître"
        msg["From"] = from_addr
        msg["To"] = email
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(from_addr, [email], msg.as_string())
        logger.info(f"[MasterCode] Email envoyé à {email}")
        return True
    except Exception as e:
        logger.warning(f"[MasterCode] Email impossible : {e}")
        return False


@router.post("/generate")
async def generate_master_code(current_user=Depends(get_current_user)):
    """Génère un nouveau code maître — retourne le code en clair UNE SEULE FOIS."""
    db = get_db()
    code = _generate_code(8)
    hashed = get_password_hash(code)
    await db.users.update_one(
        {"email": current_user["email"]},
        {"$set": {
            "master_code_hash": hashed,
            "master_code_generated_at": datetime.utcnow()
        }}
    )
    email_sent = await _try_send_email(current_user["email"], code)
    logger.info(f"[MasterCode] Code généré pour {current_user['email']}")
    return {
        "code": code,
        "email_sent": email_sent,
        "message": "Code maître généré. Notez-le maintenant, il ne sera plus affiché."
    }


@router.get("/status")
async def get_master_code_status(current_user=Depends(get_current_user)):
    """Indique si un code maître existe (sans révéler le code)."""
    db = get_db()
    user = await db.users.find_one({"email": current_user["email"]})
    has_code = bool(user and user.get("master_code_hash"))
    generated_at = None
    if has_code and user.get("master_code_generated_at"):
        generated_at = user["master_code_generated_at"].isoformat()
    return {"has_master_code": has_code, "generated_at": generated_at}


@router.post("/verify")
async def verify_master_code(payload: dict, current_user=Depends(get_current_user)):
    """Vérifie le code maître avec authentification JWT parent."""
    code = payload.get("code", "").strip().upper()
    if not code:
        raise HTTPException(400, "Code requis")
    db = get_db()
    user = await db.users.find_one({"email": current_user["email"]})
    if not user or not user.get("master_code_hash"):
        raise HTTPException(404, "Aucun code maître configuré")
    if not verify_password(code, user["master_code_hash"]):
        raise HTTPException(401, "Code maître incorrect")
    return {"valid": True}


@router.post("/verify-by-device")
async def verify_master_code_by_device(payload: dict):
    """
    Vérifie le code depuis l'agent (sans JWT parent).
    L'agent envoie : device_name + code.
    """
    from bson import ObjectId
    device_name = payload.get("device_name", "").strip()
    code = payload.get("code", "").strip().upper()
    if not device_name or not code:
        raise HTTPException(400, "device_name et code requis")
    db = get_db()
    device = await db.devices.find_one({"device_name": device_name})
    if not device:
        raise HTTPException(404, "Appareil inconnu")
    child_id = device.get("child_id")
    if not child_id or not ObjectId.is_valid(child_id):
        raise HTTPException(404, "Enfant introuvable pour cet appareil")
    child = await db.children.find_one({"_id": ObjectId(child_id)})
    if not child:
        raise HTTPException(404, "Enfant introuvable")
    user = await db.users.find_one({"email": child["parent_email"]})
    if not user or not user.get("master_code_hash"):
        raise HTTPException(404, "Aucun code maître configuré pour ce parent")
    if not verify_password(code, user["master_code_hash"]):
        raise HTTPException(401, "Code maître incorrect")
    return {"valid": True}
