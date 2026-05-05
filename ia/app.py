import json
import os
import re
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
from cachetools import TTLCache
import hashlib
from urllib.parse import urlparse

app = FastAPI(title="IA Parental Control")

# Cache LRU : 1000 URLs pendant 1 heure
url_cache = TTLCache(maxsize=1000, ttl=3600)

# Dictionnaire des mots-clés par catégorie
KEYWORDS = {
    "adult": ["porn", "sex", "xxx", "adult", "nude", "hentai", "escort", "onlyfans", "xvideos", "pornhub"],
    "violence": ["kill", "murder", "blood", "gore", "fight", "bomb", "terror", "death", "execute", "weapon"],
    "gambling": ["casino", "poker", "bet", "slot", "roulette", "jackpot", "paris sportifs", "betting"],
    "social": ["facebook", "twitter", "instagram", "tiktok", "snapchat", "youtube", "whatsapp", "telegram"],
    "games": ["game", "play", "fun", "arcade", "minecraft", "fortnite", "roblox", "steam", "gaming"]
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

def extract_domain(url: str) -> str:
    """Extrait le domaine d'une URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        # Enlever www. si présent
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain.lower()
    except:
        return url.lower()

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
    cached: bool = False

@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    # Générer une clé de cache unique
    cache_key = hashlib.md5(f"{req.url}:{req.fetch_content}".encode()).hexdigest()
    
    # Vérifier le cache d'abord
    if cache_key in url_cache:
        cached_result = url_cache[cache_key].copy()
        cached_result["cached"] = True
        return PredictResponse(**cached_result)
    
    blocked_cats = load_blocked_categories()
    if not blocked_cats:
        # Aucune catégorie à bloquer
        result = {"category": "safe", "confidence": 1.0, "blocked": False, "content_analyzed": False}
        url_cache[cache_key] = result
        return PredictResponse(**result)

    # Extraire le domaine
    domain = extract_domain(req.url)
    
    # Analyse 1 : Vérifier le domaine seul (rapide)
    for cat in blocked_cats:
        if cat not in KEYWORDS:
            continue
        for word in KEYWORDS[cat]:
            if word in domain or word in req.url.lower():
                result = {"category": cat, "confidence": 0.95, "blocked": True, "content_analyzed": False}
                url_cache[cache_key] = result
                return PredictResponse(**result)
    
    # Analyse 2 : Analyser le contenu de la page (si HTTP ou fetch_content=True)
    content_analyzed = False
    text = ""
    
    if req.fetch_content:
        # Pour HTTPS, analyser le contenu peut ne pas être possible selon la config proxy
        # Mais on tente quand même si demandé
        if req.url.startswith("http://") or req.url.startswith("https://"):
            text = fetch_text_from_url(req.url)
            content_analyzed = bool(text)
    
    if text:
        # Combiner URL + contenu pour analyse
        combined = (req.url + " " + domain + " " + text).lower()
        
        # Vérifier uniquement les catégories bloquées dans le contenu
        for cat in blocked_cats:
            if cat not in KEYWORDS:
                continue
            matches = sum(1 for word in KEYWORDS[cat] if word in combined)
            if matches >= 2:  # Au moins 2 mots-clés trouvés = confiance haute
                result = {"category": cat, "confidence": 0.9, "blocked": True, "content_analyzed": True}
                url_cache[cache_key] = result
                return PredictResponse(**result)
            elif matches == 1:  # 1 seul mot-clé = confiance moyenne
                result = {"category": cat, "confidence": 0.6, "blocked": True, "content_analyzed": True}
                url_cache[cache_key] = result
                return PredictResponse(**result)
    
    # Aucune catégorie bloquée détectée
    result = {"category": "safe", "confidence": 0.5, "blocked": False, "content_analyzed": content_analyzed}
    url_cache[cache_key] = result
    return PredictResponse(**result)

@app.get("/health")
async def health():
    return {"status": "ok", "cache_size": len(url_cache)}

@app.get("/cache/stats")
async def cache_stats():
    """Statistiques du cache pour monitoring."""
    return {
        "cache_size": len(url_cache),
        "cache_max": url_cache.maxsize,
        "cache_ttl": url_cache.ttl
    }

@app.post("/cache/clear")
async def clear_cache():
    """Vider le cache manuellement."""
    url_cache.clear()
    return {"message": "Cache cleared", "cache_size": 0}
