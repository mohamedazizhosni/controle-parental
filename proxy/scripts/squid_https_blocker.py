#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
import urllib.parse
import threading

CONFIG_FILE = "/app/ia_config/blocked_categories.json"
BACKEND_URL = "http://backend:8000"

KEYWORDS = {
    "adult":    ["porn", "sex", "xxx", "adult", "nude", "hentai", "escort", "onlyfans"],
    "violence": ["kill", "murder", "blood", "gore", "bomb", "terror"],
    "gambling": ["casino", "poker", "bet", "slot", "roulette", "jackpot"],
    "social":   ["facebook", "twitter", "instagram", "tiktok", "snapchat", "youtube", "whatsapp"],
    "games":    ["game", "minecraft", "fortnite", "roblox", "arcade"]
}

def load_blocked_categories():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f).get("blocked_categories", [])
        except:
            pass
    return []

def should_block(domain, blocked_cats):
    if not blocked_cats:
        return False
    dl = domain.lower()
    for cat in blocked_cats:
        for word in KEYWORDS.get(cat, []):
            if word in dl:
                return True
    return False

def send_history(client_ip, domain, blocked):
    """Envoi asynchrone de l'historique HTTPS au backend."""
    try:
        url = f"https://{domain}"
        data = json.dumps({"ip": client_ip, "url": url, "blocked": blocked}).encode()
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
        # Avec %DST %SRC, Squid envoie : "domain client_ip"
        parts = line.strip().split()
        if not parts:
            continue

        domain = parts[0]
        client_ip = parts[1] if len(parts) > 1 else "0.0.0.0"

        blocked_cats = load_blocked_categories()
        blocked = should_block(domain, blocked_cats)

        # Envoyer l'historique HTTPS
        send_history(client_ip, domain, blocked)

        if blocked:
            # OK = l'ACL correspond → http_access deny s'applique → BLOQUÉ
            sys.stdout.write("OK\n")
        else:
            # ERR = l'ACL ne correspond pas → autorisé
            sys.stdout.write("ERR\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
