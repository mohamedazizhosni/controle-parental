import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key-change-me")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost,http://192.168.100.94")

settings = Settings()
