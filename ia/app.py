import json
import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
from cachetools import TTLCache
import hashlib
from urllib.parse import urlparse

app = FastAPI(title="IA Parental Control")

# Cache LRU : 5000 URLs pendant 2 heures
url_cache = TTLCache(maxsize=5000, ttl=7200)

CONFIG_FILE = "/app/ia_config/blocked_categories.json"

# Import des keywords enrichis
sys.path.insert(0, '/app')
try:
    from keywords import KEYWORDS, BLOCKED_DOMAINS, WHITELIST_DOMAINS
except ImportError:
    KEYWORDS = {
        "adult":    ["porn", "sex", "xxx", "adult", "nude", "hentai", "escort", "onlyfans"],
        "violence": ["kill", "murder", "blood", "gore", "bomb", "terror"],
        "gambling": ["casino", "poker", "bet", "slot", "roulette", "jackpot"],
        "social":   ["facebook", "twitter", "instagram", "tiktok", "snapchat", "youtube"],
        "games":    ["game", "minecraft", "fortnite", "roblox", "steam"],
    }
    BLOCKED_DOMAINS = {}
    WHITELIST_DOMAINS = []


def load_blocked_categories() -> List[str]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("blocked_categories", [])
        except:
            pass
    return []


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain.lower()
    except:
        return url.lower()


def is_whitelisted(domain: str) -> bool:
    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]
    for w in WHITELIST_DOMAINS:
        if dl == w or dl.endswith("." + w):
            return True
    return False


def fetch_text_from_url(url: str, timeout: int = 5) -> str:
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
    cache_key = hashlib.md5(f"{req.url}:{req.fetch_content}".encode()).hexdigest()

    if cache_key in url_cache:
        cached_result = url_cache[cache_key].copy()
        cached_result["cached"] = True
        return PredictResponse(**cached_result)

    blocked_cats = load_blocked_categories()
    if not blocked_cats:
        result = {"category": "safe", "confidence": 1.0, "blocked": False, "content_analyzed": False}
        url_cache[cache_key] = result
        return PredictResponse(**result)

    domain = extract_domain(req.url)

    # Whitelist prioritaire
    if is_whitelisted(domain):
        result = {"category": "safe", "confidence": 1.0, "blocked": False, "content_analyzed": False}
        url_cache[cache_key] = result
        return PredictResponse(**result)

    # Analyse 1 : correspondance exacte de domaine dans BLOCKED_DOMAINS
    for cat in blocked_cats:
        for blocked_domain in BLOCKED_DOMAINS.get(cat, []):
            if domain == blocked_domain or domain.endswith("." + blocked_domain):
                result = {"category": cat, "confidence": 1.0, "blocked": True, "content_analyzed": False}
                url_cache[cache_key] = result
                return PredictResponse(**result)

    # Analyse 2 : mots-clés dans le domaine / URL
    url_lower = req.url.lower()
    for cat in blocked_cats:
        for word in KEYWORDS.get(cat, []):
            if word in domain or word in url_lower:
                result = {"category": cat, "confidence": 0.95, "blocked": True, "content_analyzed": False}
                url_cache[cache_key] = result
                return PredictResponse(**result)

    # Analyse 3 : contenu de la page (HTTP seulement)
    text = ""
    content_analyzed = False
    if req.fetch_content and req.url.startswith("http://"):
        text = fetch_text_from_url(req.url)
        content_analyzed = bool(text)

    if text:
        combined = (req.url + " " + domain + " " + text).lower()
        for cat in blocked_cats:
            matches = sum(1 for word in KEYWORDS.get(cat, []) if word in combined)
            if matches >= 3:
                result = {"category": cat, "confidence": 0.95, "blocked": True, "content_analyzed": True}
                url_cache[cache_key] = result
                return PredictResponse(**result)
            elif matches == 2:
                result = {"category": cat, "confidence": 0.80, "blocked": True, "content_analyzed": True}
                url_cache[cache_key] = result
                return PredictResponse(**result)
            elif matches == 1:
                result = {"category": cat, "confidence": 0.55, "blocked": True, "content_analyzed": True}
                url_cache[cache_key] = result
                return PredictResponse(**result)

    result = {"category": "safe", "confidence": 0.5, "blocked": False, "content_analyzed": content_analyzed}
    url_cache[cache_key] = result
    return PredictResponse(**result)


@app.get("/health")
async def health():
    return {"status": "ok", "cache_size": len(url_cache)}


@app.get("/cache/stats")
async def cache_stats():
    return {
        "cache_size": len(url_cache),
        "max_size": url_cache.maxsize,
        "ttl_seconds": url_cache.ttl,
    }


@app.get("/keywords/stats")
async def keywords_stats():
    """Statistiques sur les mots-clés et domaines chargés."""
    return {
        "categories": list(KEYWORDS.keys()),
        "keywords_count": {cat: len(words) for cat, words in KEYWORDS.items()},
        "blocked_domains_count": {cat: len(domains) for cat, domains in BLOCKED_DOMAINS.items()},
        "whitelist_count": len(WHITELIST_DOMAINS),
        "total_keywords": sum(len(w) for w in KEYWORDS.values()),
        "total_blocked_domains": sum(len(d) for d in BLOCKED_DOMAINS.values()),
    }
