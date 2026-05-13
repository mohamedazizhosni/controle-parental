from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.v1.endpoints import auth, children, pairing, session, ia_config, devices, history, notifications, stats
from .db.mongodb import connect_to_mongo, close_mongo_connection
from .core.config import settings

app = FastAPI(title="Parental Control API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:*",
        "http://127.0.0.1",
        "http://127.0.0.1:*",
        "http://192.168.1.*",
        "http://192.168.220.*",
        settings.ALLOWED_ORIGINS,
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.on_event("startup")
async def startup():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown():
    await close_mongo_connection()

app.include_router(auth.router, prefix="/api/v1")
app.include_router(children.router, prefix="/api/v1")
app.include_router(pairing.router, prefix="/api/v1")
app.include_router(session.router, prefix="/api/v1")
app.include_router(ia_config.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Parental Control API is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/v1/health")
async def api_health():
    return {"status": "ok", "api_version": "v1"}
