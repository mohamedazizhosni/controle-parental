#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
import threading
import re

CONFIG_FILE = "/app/ia_config/blocked_categories.json"
BACKEND_URL = "http://backend:8000"

# Import des keywords et domaines enrichis
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
    # Enlever www.
    if dl.startswith("www."):
        dl = dl[4:]
    for w in WHITELIST_DOMAINS:
        if dl == w or dl.endswith("." + w):
            return True
    return False


def should_block(domain: str, blocked_cats: list) -> bool:
    if not blocked_cats:
        return False

    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]

    # Whitelist prioritaire
    if is_whitelisted(dl):
        return False

    # 1. Correspondance exacte ou sous-domaine dans BLOCKED_DOMAINS
    for cat in blocked_cats:
        for blocked_domain in BLOCKED_DOMAINS.get(cat, []):
            if dl == blocked_domain or dl.endswith("." + blocked_domain):
                return True

    # 2. Mots-clés dans le domaine
    for cat in blocked_cats:
        for word in KEYWORDS.get(cat, []):
            word_clean = word.lower()
            if word_clean in dl:
                return True

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

        domain = parts[0]
        client_ip = parts[1] if len(parts) > 1 else "0.0.0.0"

        blocked_cats = load_blocked_categories()
        blocked = should_block(domain, blocked_cats)

        send_history(client_ip, domain, blocked)

        # OK = ACL correspond → http_access deny bloque
        # ERR = ACL ne correspond pas → autorisé
        sys.stdout.write("OK\n" if blocked else "ERR\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
