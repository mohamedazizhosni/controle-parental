import json
import os
import re
import sys
import requests
import joblib
import numpy as np
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
MODEL_PATH  = "/app/model.pkl"

# ── Chargement du modèle NLP ──────────────────────────────────────────────────
_nlp_model = None

def get_nlp_model():
    global _nlp_model
    if _nlp_model is None and os.path.exists(MODEL_PATH):
        try:
            _nlp_model = joblib.load(MODEL_PATH)
            print("Modèle NLP chargé.")
        except Exception as e:
            print(f"Erreur chargement modèle: {e}")
    return _nlp_model

# ── Import des keywords ───────────────────────────────────────────────────────
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


def extract_url_text(url: str) -> str:
    """Extrait tous les tokens lisibles d'une URL (domaine + chemin + paramètres)."""
    try:
        parsed = urlparse(url)
        parts = [
            parsed.netloc or '',
            parsed.path or '',
            parsed.query or '',
            parsed.fragment or '',
        ]
        combined = ' '.join(parts)
        # Séparer les mots collés : adult-content → adult content
        combined = re.sub(r'[-_/\.%+]', ' ', combined)
        # Séparer camelCase : adultContent → adult Content
        combined = re.sub(r'([a-z])([A-Z])', r'\1 \2', combined)
        return combined.lower()
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


def fetch_page_content(url: str, timeout: int = 4) -> str:
    """
    Fetch le contenu HTML d'une URL (HTTP ou HTTPS).
    Retourne titre + meta description + début du texte visible.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ParentalControlBot/2.0)",
            "Accept-Language": "fr,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = requests.get(url, timeout=timeout, headers=headers,
                            verify=False, allow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extraire titre
        title = soup.title.string if soup.title else ""

        # Extraire meta description et keywords
        meta_desc = ""
        meta_kw   = ""
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or "").lower()
            if name in ("description", "og:description"):
                meta_desc = meta.get("content", "")
            elif name == "keywords":
                meta_kw = meta.get("content", "")

        # Extraire texte visible (limité)
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = soup.get_text(separator=" ", strip=True)
        body_text = re.sub(r'\s+', ' ', body_text)[:3000]

        combined = f"{title} {meta_desc} {meta_kw} {body_text}"
        return combined.lower()
    except Exception:
        return ""


def nlp_classify(text: str, blocked_cats: List[str]):
    """
    Classifie un texte avec TF-IDF + Naive Bayes.
    Retourne (categorie, confidence) ou (None, 0) si modèle absent.
    """
    model = get_nlp_model()
    if model is None or not text.strip():
        return None, 0.0

    try:
        proba = model.predict_proba([text])[0]
        classes = model.classes_
        # Filtrer uniquement les catégories bloquées
        best_cat   = None
        best_proba = 0.0
        for i, cls in enumerate(classes):
            if cls in blocked_cats and proba[i] > best_proba:
                best_proba = proba[i]
                best_cat   = cls
        return best_cat, float(best_proba)
    except Exception as e:
        print(f"Erreur NLP: {e}")
        return None, 0.0


# ── Modèles Pydantic ──────────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    url: str
    fetch_content: bool = True


class PredictResponse(BaseModel):
    category: str
    confidence: float
    blocked: bool
    method: str = "keywords"   # keywords | nlp_url | nlp_content
    content_analyzed: bool = False
    cached: bool = False


# ── Endpoint principal ────────────────────────────────────────────────────────

@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    cache_key = hashlib.md5(f"{req.url}:{req.fetch_content}".encode()).hexdigest()

    if cache_key in url_cache:
        cached_result = url_cache[cache_key].copy()
        cached_result["cached"] = True
        return PredictResponse(**cached_result)

    blocked_cats = load_blocked_categories()
    if not blocked_cats:
        result = {"category": "safe", "confidence": 1.0, "blocked": False,
                  "method": "keywords", "content_analyzed": False}
        url_cache[cache_key] = result
        return PredictResponse(**result)

    domain    = extract_domain(req.url)
    url_lower = req.url.lower()

    # ── Étape 0 : Whitelist prioritaire ──────────────────────────────────────
    if is_whitelisted(domain):
        result = {"category": "safe", "confidence": 1.0, "blocked": False,
                  "method": "keywords", "content_analyzed": False}
        url_cache[cache_key] = result
        return PredictResponse(**result)

    # ── Étape 1a : Domaine exact dans liste noire ─────────────────────────────
    for cat in blocked_cats:
        for blocked_domain in BLOCKED_DOMAINS.get(cat, []):
            if domain == blocked_domain or domain.endswith("." + blocked_domain):
                result = {"category": cat, "confidence": 1.0, "blocked": True,
                          "method": "keywords", "content_analyzed": False}
                url_cache[cache_key] = result
                return PredictResponse(**result)

    # ── Étape 1b : Mots-clés dans domaine/URL ────────────────────────────────
    for cat in blocked_cats:
        for word in KEYWORDS.get(cat, []):
            if word in domain or word in url_lower:
                result = {"category": cat, "confidence": 0.95, "blocked": True,
                          "method": "keywords", "content_analyzed": False}
                url_cache[cache_key] = result
                return PredictResponse(**result)

    # ── Étape 2 : NLP sur l'URL seule (tokens extraits) ──────────────────────
    url_text = extract_url_text(req.url)
    nlp_cat, nlp_conf = nlp_classify(url_text, blocked_cats)
    if nlp_cat and nlp_conf >= 0.70:
        result = {"category": nlp_cat, "confidence": nlp_conf, "blocked": True,
                  "method": "nlp_url", "content_analyzed": False}
        url_cache[cache_key] = result
        return PredictResponse(**result)

    # ── Étape 3 : Fetch contenu + NLP (HTTP et HTTPS) ────────────────────────
    if not req.fetch_content:
        result = {"category": "safe", "confidence": 0.5, "blocked": False,
                  "method": "keywords", "content_analyzed": False}
        url_cache[cache_key] = result
        return PredictResponse(**result)

    page_text = fetch_page_content(req.url)
    if page_text:
        # Combiner URL + contenu pour meilleure précision
        combined_text = url_text + " " + page_text

        # NLP sur contenu complet
        nlp_cat, nlp_conf = nlp_classify(combined_text, blocked_cats)
        if nlp_cat and nlp_conf >= 0.60:
            result = {"category": nlp_cat, "confidence": nlp_conf, "blocked": True,
                      "method": "nlp_content", "content_analyzed": True}
            url_cache[cache_key] = result
            return PredictResponse(**result)

        # Fallback : comptage de mots-clés dans le contenu
        for cat in blocked_cats:
            matches = sum(1 for word in KEYWORDS.get(cat, []) if word in combined_text)
            if matches >= 3:
                result = {"category": cat, "confidence": 0.85, "blocked": True,
                          "method": "keywords", "content_analyzed": True}
                url_cache[cache_key] = result
                return PredictResponse(**result)

    result = {"category": "safe", "confidence": 0.5, "blocked": False,
              "method": "keywords", "content_analyzed": bool(page_text)}
    url_cache[cache_key] = result
    return PredictResponse(**result)


# ── Endpoints utilitaires ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Charger le modèle au démarrage du serveur."""
    get_nlp_model()


@app.get("/health")
async def health():
    model = get_nlp_model()
    return {
        "status": "ok",
        "cache_size": len(url_cache),
        "nlp_model_loaded": model is not None,
    }


@app.get("/cache/stats")
async def cache_stats():
    return {
        "cache_size": len(url_cache),
        "max_size": url_cache.maxsize,
        "ttl_seconds": url_cache.ttl,
    }


@app.get("/keywords/stats")
async def keywords_stats():
    model = get_nlp_model()
    return {
        "categories": list(KEYWORDS.keys()),
        "keywords_count": {cat: len(words) for cat, words in KEYWORDS.items()},
        "blocked_domains_count": {cat: len(domains) for cat, domains in BLOCKED_DOMAINS.items()},
        "whitelist_count": len(WHITELIST_DOMAINS),
        "total_keywords": sum(len(w) for w in KEYWORDS.values()),
        "total_blocked_domains": sum(len(d) for d in BLOCKED_DOMAINS.values()),
        "nlp_model_loaded": model is not None,
    }


@app.post("/retrain")
async def retrain():
    """Réentraîner le modèle à la demande."""
    global _nlp_model
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "/app/train_model.py"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            _nlp_model = None
            get_nlp_model()
            return {"status": "ok", "message": "Modèle réentraîné avec succès"}
        else:
            return {"status": "error", "message": result.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}
