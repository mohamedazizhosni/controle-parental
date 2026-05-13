#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
import threading
import re

CONFIG_FILE = "/app/ia_config/blocked_categories.json"
BACKEND_URL = "http://backend:8000"
IA_URL      = "http://ia:8001/predict"

sys.path.insert(0, '/usr/local/bin')
try:
    from keywords import KEYWORDS, BLOCKED_DOMAINS, WHITELIST_DOMAINS
except ImportError:
    KEYWORDS = {}
    BLOCKED_DOMAINS = {}
    WHITELIST_DOMAINS = []


def load_blocked_categories():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f).get("blocked_categories", [])
        except:
            pass
    return []


def is_whitelisted(domain: str) -> bool:
    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]
    for w in WHITELIST_DOMAINS:
        if dl == w or dl.endswith("." + w):
            return True
    return False


def keyword_check(domain: str, blocked_cats: list) -> bool:
    """Étape 1 : vérification rapide par mots-clés (instantané)."""
    if not blocked_cats:
        return False

    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]

    if is_whitelisted(dl):
        return False

    # Correspondance domaine exact
    for cat in blocked_cats:
        for blocked_domain in BLOCKED_DOMAINS.get(cat, []):
            if dl == blocked_domain or dl.endswith("." + blocked_domain):
                return True

    # Mots-clés dans le domaine
    for cat in blocked_cats:
        for word in KEYWORDS.get(cat, []):
            if word.lower() in dl:
                return True

    return False


def ia_check(domain: str) -> bool:
    """
    Étape 2 : appel à l'IA (TF-IDF + NB) avec l'URL HTTPS complète.
    L'IA va fetch le contenu de la page et classifier.
    """
    try:
        url = f"https://{domain}"
        data = json.dumps({
            "url": url,
            "fetch_content": True   # ← L'IA fetch le contenu HTTPS
        }).encode()
        req = urllib.request.Request(
            IA_URL,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            result = json.loads(resp.read().decode())
            return result.get("blocked", False)
    except Exception:
        return False


def send_history(client_ip: str, domain: str, blocked: bool):
    try:
        url = f"https://{domain}"
        data = json.dumps({
            "ip": client_ip,
            "url": url,
            "blocked": blocked
        }).encode()
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/v1/history/log",
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        threading.Thread(
            target=lambda: urllib.request.urlopen(req, timeout=2),
            daemon=True
        ).start()
    except:
        pass


def main():
    for line in sys.stdin:
        parts = line.strip().split()
        if not parts:
            continue

        domain    = parts[0]
        client_ip = parts[1] if len(parts) > 1 else "0.0.0.0"

        blocked_cats = load_blocked_categories()

        # ── Étape 1 : mots-clés (instantané) ─────────────────────────────────
        blocked = keyword_check(domain, blocked_cats)

        # ── Étape 2 : IA TF-IDF + NB si pas encore bloqué ───────────────────
        if not blocked and blocked_cats:
            blocked = ia_check(domain)

        # Logger en arrière-plan
        send_history(client_ip, domain, blocked)

        sys.stdout.write("OK\n" if blocked else "ERR\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
