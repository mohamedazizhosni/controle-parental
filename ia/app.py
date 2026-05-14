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
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
import joblib

app = FastAPI(title="IA Parental Control")

# Cache LRU : 5000 URLs pendant 2 heures
url_cache = TTLCache(maxsize=5000, ttl=7200)

CONFIG_FILE = "/app/ia_config/blocked_categories.json"
MODEL_FILE = "/app/ia_config/model.pkl"

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


# ── TF-IDF + Naive Bayes ───────────────────────────────────────────────────────

def build_training_data():
    texts, labels = [], []
    for cat, words in KEYWORDS.items():
        for i in range(0, len(words), 3):
            chunk = words[i:i+6]
            texts.append(" ".join(chunk) + " " + " ".join(chunk))
            labels.append(cat)
        for dom in BLOCKED_DOMAINS.get(cat, [])[:20]:
            texts.append(dom.replace(".", " ") + " " + " ".join(words[:5]))
            labels.append(cat)
    safe_words = [
        "weather forecast news today business education science technology",
        "cooking recipe food restaurant healthy nutrition",
        "travel tourism hotel flight airport",
        "sport football basketball athletics olympic",
        "music art culture history museum",
        "finance bank economy stock market investment",
        "health medical doctor hospital medicine",
        "education school university research study",
    ]
    for sw in safe_words:
        texts.append(sw)
        labels.append("safe")
    return texts, labels


def train_or_load_model() -> Pipeline:
    if os.path.exists(MODEL_FILE):
        try:
            return joblib.load(MODEL_FILE)
        except Exception:
            pass

    texts, labels = build_training_data()
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )),
        ("clf", MultinomialNB(alpha=0.5)),
    ])
    pipeline.fit(texts, labels)
    os.makedirs(os.path.dirname(MODEL_FILE), exist_ok=True)
    try:
        joblib.dump(pipeline, MODEL_FILE)
    except Exception:
        pass
    return pipeline


# Chargement du modèle au démarrage
tfidf_model: Pipeline = train_or_load_model()


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
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ParentalControlBot/2.0)",
            "Accept-Language": "fr,en;q=0.9",
        }
        resp = requests.get(url, timeout=timeout, headers=headers, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        parts = []
        if soup.title:
            parts.append(soup.title.get_text())
        for meta in soup.find_all("meta", attrs={"name": ["description", "keywords"]}):
            parts.append(meta.get("content", ""))
        parts.append(soup.get_text(separator=" ", strip=True))
        text = " ".join(parts)
        text = re.sub(r'\s+', ' ', text)
        return text.lower()[:8000]
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

    # Analyse 3 : fetch contenu HTTP ET HTTPS + TF-IDF + Naive Bayes
    text = ""
    content_analyzed = False
    if req.fetch_content and (req.url.startswith("http://") or req.url.startswith("https://")):
        text = fetch_text_from_url(req.url)
        content_analyzed = bool(text)

    if text:
        combined = (req.url + " " + domain + " " + text).lower()

        # 3a — Analyse TF-IDF + Naive Bayes
        proba = tfidf_model.predict_proba([combined])[0]
        classes = tfidf_model.classes_
        best_idx = int(np.argmax(proba))
        best_cat = classes[best_idx]
        best_conf = float(proba[best_idx])

        if best_cat in blocked_cats and best_conf >= 0.40:
            result = {
                "category": best_cat,
                "confidence": round(best_conf, 3),
                "blocked": True,
                "content_analyzed": True,
            }
            url_cache[cache_key] = result
            return PredictResponse(**result)

        # 3b — Fallback comptage de mots-clés si TF-IDF hésitant
        for cat in blocked_cats:
            matches = sum(1 for word in KEYWORDS.get(cat, []) if word in combined)
            if matches >= 2:
                result = {"category": cat, "confidence": 0.75, "blocked": True, "content_analyzed": True}
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
    return {
        "categories": list(KEYWORDS.keys()),
        "keywords_count": {cat: len(words) for cat, words in KEYWORDS.items()},
        "blocked_domains_count": {cat: len(domains) for cat, domains in BLOCKED_DOMAINS.items()},
        "whitelist_count": len(WHITELIST_DOMAINS),
        "total_keywords": sum(len(w) for w in KEYWORDS.values()),
        "total_blocked_domains": sum(len(d) for d in BLOCKED_DOMAINS.values()),
    }
