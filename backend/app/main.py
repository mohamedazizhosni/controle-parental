import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.v1.endpoints import (
    auth, children, pairing, session,
    ia_config, devices, history, notifications,
    stats, fcm, apps, app_usage, blocklist, alerts, master_code
)
from .db.mongodb import connect_to_mongo, close_mongo_connection
from .core.config import settings

logger = logging.getLogger("main")

app = FastAPI(title="Parental Control API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:*",
        "http://127.0.0.1",
        "http://127.0.0.1:*",
        "http://192.168.1.*",
        "http://192.168.100.*",
        settings.ALLOWED_ORIGINS,
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "x-internal-secret"],
)


def _init_firebase():
    service_account_path = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT",
        "/app/firebase-service-account.json",
    )
    if not os.path.exists(service_account_path):
        logger.warning(
            f"[FCM] Fichier service account introuvable : {service_account_path}. "
            "Les push FCM seront désactivés."
        )
        return
    try:
        import firebase_admin
        from firebase_admin import credentials
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            logger.info("[FCM] firebase_admin initialisé avec succès.")
        else:
            logger.info("[FCM] firebase_admin déjà initialisé.")
    except Exception as e:
        logger.error(f"[FCM] Erreur initialisation firebase_admin : {e}")


@app.on_event("startup")
async def startup():
    await connect_to_mongo()
    _init_firebase()


@app.on_event("shutdown")
async def shutdown():
    await close_mongo_connection()


app.include_router(auth.router,          prefix="/api/v1")
app.include_router(children.router,      prefix="/api/v1")
app.include_router(pairing.router,       prefix="/api/v1")
app.include_router(session.router,       prefix="/api/v1")
app.include_router(ia_config.router,     prefix="/api/v1")
app.include_router(devices.router,       prefix="/api/v1")
app.include_router(history.router,       prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(stats.router,         prefix="/api/v1")
app.include_router(fcm.router,           prefix="/api/v1")
app.include_router(apps.router,          prefix="/api/v1")
app.include_router(app_usage.router,     prefix="/api/v1")
app.include_router(blocklist.router,     prefix="/api/v1")
app.include_router(alerts.router,        prefix="/api/v1")
app.include_router(master_code.router,   prefix="/api/v1")   # ← NOUVEAU


@app.get("/")
async def root():
    return {"message": "Parental Control API is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/v1/health")
async def api_health():
    return {"status": "ok", "api_version": "v1"}
