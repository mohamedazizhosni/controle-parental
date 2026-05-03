import json
import os
import re
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="IA Parental Control")

# Dictionnaire des mots-clés par catégorie
KEYWORDS = {
    "adult": ["porn", "sex", "xxx", "adult", "nude", "hentai", "escort", "onlyfans"],
    "violence": ["kill", "murder", "blood", "gore", "fight", "bomb", "terror", "death", "execute"],
    "gambling": ["casino", "poker", "bet", "slot", "roulette", "jackpot", "paris sportifs"],
    "social": ["facebook", "twitter", "instagram", "tiktok", "snapchat", "youtube", "whatsapp"],
    "games": ["game", "play", "fun", "arcade", "minecraft", "fortnite", "roblox"]
}

CONFIG_FILE = "/app/ia_config/blocked_categories.json"

def load_blocked_categories() -> List[str]:
    """Charge la liste des catégories bloquées depuis le fichier partagé."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("blocked_categories", [])
        except:
            pass
    return []

def fetch_text_from_url(url: str, timeout: int = 5) -> str:
    """Télécharge une page web et extrait le texte brut."""
    try:
        headers = {"User-Agent": "ParentalControlBot/1.0"}
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text)
        return text.lower()[:5000]
    except Exception:
        return ""

class PredictRequest(BaseModel):
    url: str
    fetch_content: bool = True

class PredictResponse(BaseModel):
    category: str
    confidence: float
    blocked: bool
    content_analyzed: bool = False

@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    blocked_cats = load_blocked_categories()
    if not blocked_cats:
        # Aucune catégorie à bloquer
        return PredictResponse(category="safe", confidence=1.0, blocked=False, content_analyzed=False)

    text = ""
    if req.fetch_content:
        text = fetch_text_from_url(req.url)
    combined = (req.url + " " + text).lower()

    # Vérifier uniquement les catégories bloquées
    for cat in blocked_cats:
        if cat not in KEYWORDS:
            continue
        for word in KEYWORDS[cat]:
            if word in combined:
                return PredictResponse(category=cat, confidence=0.9, blocked=True, content_analyzed=bool(text))
    return PredictResponse(category="safe", confidence=0.5, blocked=False, content_analyzed=bool(text))

@app.get("/health")
async def health():
    return {"status": "ok"}
