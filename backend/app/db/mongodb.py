from motor.motor_asyncio import AsyncIOMotorClient
from ..core.config import settings

client = None
db = None

async def connect_to_mongo():
    global client, db
    client = AsyncIOMotorClient(settings.MONGO_URL)
    db = client.parental_db

async def close_mongo_connection():
    global client
    if client:
        client.close()

def get_db():
    return db
