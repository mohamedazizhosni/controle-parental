#!/usr/bin/env python3
"""
Squid TF-IDF Helper — Windows Agent
====================================
Lit le access.log de Squid en temps réel, extrait les domaines,
classe leur contenu avec TF-IDF + mots-clés, et soumet les
domaines malveillants au backend partagé.

Usage:
  python squid_tfidf_helper.py --log C:/squid/var/log/squid/access.log
                                --backend http://192.168.100.94
                                --token <JWT_TOKEN>
"""

import re
import time
import argparse
import requests
import logging
from pathlib import Path
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("squid_tfidf")

# ─────────────────────────────────────────────────────────────────────────────
# Corpus de référence TF-IDF (mots représentatifs par catégorie)
# ─────────────────────────────────────────────────────────────────────────────
CORPUS = {
    "jeux": (
        "game games gaming play player online multiplayer fps rpg mmorpg "
        "arcade puzzle strategy shooter battle royale esports tournament "
        "steam playstation xbox nintendo roblox minecraft fortnite lol "
        "dota valorant overwatch casino slots poker bet wager gambling "
        "jeu jouer jeux gratuit joueur jeux en ligne"
    ),
    "adulte": (
        "porn sex adult xxx nude naked erotic escort strip cam live "
        "amateur mature lesbian gay fetish bdsm hentai anime nsfw "
        "hot girls video tube free porn watch"
    ),
    "violence": (
        "gore blood death kill murder weapon torture brutal fight war "
        "shooting stab gore video death video graphic violent content"
    ),
    "piratage": (
        "torrent download crack keygen serial warez pirate free download "
        "movies series iptv stream illegal copyright bypass vpn proxy"
    ),
    "paris sportifs": (
        "bet betting odds sports football basketball tennis match prediction "
        "bookmaker sportsbook wager stake pari sportif cote pronostic"
    ),
    "drogues": (
        "cannabis weed drug marijuana cocaine heroin pills psychedelic "
        "lsd mdma ecstasy amphetamine opium seed grow order buy drugs"
    ),
    "haine": (
        "hate racist racism nazi white supremacy extremist terrorist jihad "
        "antisemitic discrimination propaganda radicalize"
    ),
}

VECTORIZER = TfidfVectorizer(ngram_range=(1, 2))
CORPUS_TEXTS = list(CORPUS.values())
CORPUS_KEYS  = list(CORPUS.keys())
CORPUS_MATRIX = None


def build_corpus_matrix():
    global CORPUS_MATRIX
    CORPUS_MATRIX = VECTORIZER.fit_transform(CORPUS_TEXTS)


def classify_url(url: str) -> tuple[str | None, float]:
    """Retourne (catégorie, confiance) ou (None, 0) si inoffensif."""
    tokens = re.findall(r'[a-z]{3,}', url.lower())
    if not tokens:
        return None, 0.0
    text = " ".join(tokens)
    try:
        vec = VECTORIZER.transform([text])
        sims = cosine_similarity(vec, CORPUS_MATRIX)[0]
        idx = int(np.argmax(sims))
        score = float(sims[idx])
        if score > 0.08:
            return CORPUS_KEYS[idx], score
    except Exception:
        pass
    return None, 0.0


# Domaines déjà soumis (éviter les doublons en mémoire)
submitted: set[str] = set()


def extract_domain(url: str) -> str | None:
    m = re.search(r'https?://([^/:]+)', url)
    if m:
        d = m.group(1).lower()
        return re.sub(r'^www\.', '', d)
    return None


def submit_domain(domain: str, category: str, confidence: float, backend: str, token: str):
    if domain in submitted:
        return
    submitted.add(domain)
    try:
        r = requests.post(
            f"{backend}/api/v1/blocklist/dynamic/add",
            json={
                "domain": domain,
                "category": category,
                "source": "squid_tfidf",
                "confidence": round(confidence, 4),
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            log.info(f"[{data['status'].upper()}] {domain} → {category} ({confidence:.2f})")
        else:
            log.warning(f"Backend error {r.status_code} pour {domain}")
    except Exception as e:
        log.error(f"Erreur envoi {domain}: {e}")


def tail_log(log_path: Path, backend: str, token: str):
    """Lit access.log de Squid en continu (tail -f)."""
    log.info(f"Surveillance de {log_path} ...")
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, 2)  # aller à la fin
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            # Format Squid access.log :
            # timestamp elapsed client action/status bytes method url ...
            parts = line.split()
            if len(parts) < 7:
                continue
            url = parts[6]
            domain = extract_domain(url)
            if not domain:
                continue
            category, confidence = classify_url(url)
            if category and confidence > 0.10:
                submit_domain(domain, category, confidence, backend, token)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log",     required=True, help="Chemin vers access.log de Squid")
    parser.add_argument("--backend", required=True, help="URL du backend ex: http://192.168.100.94")
    parser.add_argument("--token",   required=True, help="JWT token parent")
    args = parser.parse_args()

    build_corpus_matrix()
    tail_log(Path(args.log), args.backend, args.token)


if __name__ == "__main__":
    main()
