#!/usr/bin/env python3
import sys
import json
import os
import urllib.request

CONFIG_FILE  = "/app/ia_config/blocked_categories.json"
BACKEND_URL  = "http://backend:8000"
IA_URL       = "http://ia:8001"
# Clé secrète partagée avec le backend pour l'endpoint interne (sans JWT)
INTERNAL_SECRET = "squid-internal-secret-2024"

sys.path.insert(0, '/usr/local/bin')
try:
    from keywords import KEYWORDS, BLOCKED_DOMAINS, WHITELIST_DOMAINS
except ImportError:
    KEYWORDS          = {}
    BLOCKED_DOMAINS   = {}
    WHITELIST_DOMAINS = []


def log(msg: str):
    print(f"[helper] {msg}", file=sys.stderr, flush=True)


def load_blocked_categories():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f).get("blocked_categories", [])
        except Exception as e:
            log(f"load_blocked_categories error: {e}")
    return []


def is_whitelisted(domain: str) -> bool:
    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]
    for w in WHITELIST_DOMAINS:
        if dl == w or dl.endswith("." + w):
            return True
    return False


def should_block_instant(domain: str, blocked_cats: list):
    if not blocked_cats:
        return False, "safe"

    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]

    if is_whitelisted(dl):
        return False, "safe"

    for cat in blocked_cats:
        for bd in BLOCKED_DOMAINS.get(cat, []):
            if dl == bd or dl.endswith("." + bd):
                log(f"BLOCK instant domain={domain} cat={cat} matched={bd}")
                return True, cat

    for cat in blocked_cats:
        for word in KEYWORDS.get(cat, []):
            if word.lower() in dl:
                log(f"BLOCK instant domain={domain} cat={cat} keyword={word}")
                return True, cat

    return False, "safe"


def ask_ia(domain: str):
    try:
        url     = f"https://{domain}"
        payload = json.dumps({"url": url, "fetch_content": True}).encode()
        req     = urllib.request.Request(
            f"{IA_URL}/predict",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data    = json.loads(resp.read())
            blocked = data.get("blocked", False)
            cat     = data.get("category", "safe")
            conf    = data.get("confidence", 0)
            log(f"IA domain={domain} blocked={blocked} cat={cat} conf={conf}")
            return blocked, cat, conf
    except Exception as e:
        log(f"ask_ia error domain={domain}: {e}")
        return False, "safe", 0.0


def push_to_backend_blocklist(domain: str, category: str, confidence: float, source: str = "squid_tfidf"):
    """
    Pousse un domaine découvert par Squid/TF-IDF vers la blacklist dynamique du backend.
    Android lira automatiquement cette liste via /api/v1/blocklist/domains/{child_id}/agent.
    Utilise l'endpoint interne (sans JWT) sécurisé par clé secrète.
    """
    try:
        dl = domain.lower().strip()
        if dl.startswith("www."):
            dl = dl[4:]
        data = json.dumps({
            "domain": dl,
            "category": category,
            "source": source,
            "confidence": confidence,
        }).encode()
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/v1/blocklist/dynamic/add_internal",
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Internal-Secret": INTERNAL_SECRET,
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
        log(f"push_to_backend_blocklist OK domain={dl} cat={category}")
    except Exception as e:
        log(f"push_to_backend_blocklist error domain={domain}: {e}")


def send_history(client_ip: str, domain: str, blocked: bool):
    try:
        data = json.dumps({
            "ip": client_ip,
            "url": f"https://{domain}",
            "blocked": blocked,
        }).encode()
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/v1/history/log",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def main():
    log("squid_https_blocker started")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            sys.stdout.write("ERR\n")
            sys.stdout.flush()
            continue

        parts     = line.split()
        domain    = parts[0]
        client_ip = parts[1] if len(parts) > 1 else "0.0.0.0"

        try:
            blocked_cats = load_blocked_categories()

            blocked, category = should_block_instant(domain, blocked_cats)
            ia_confidence = 0.0

            if not blocked and blocked_cats:
                blocked, category, ia_confidence = ask_ia(domain)
                # Si TF-IDF a découvert un nouveau domaine malveillant →
                # le pousser dans la blacklist dynamique backend
                # → Android le bloquera automatiquement à la prochaine sync
                if blocked and ia_confidence >= 0.60:
                    push_to_backend_blocklist(domain, category, ia_confidence, source="squid_tfidf")

            send_history(client_ip, domain, blocked)

            answer = "OK" if blocked else "ERR"
            log(f"domain={domain} → {answer}")
            sys.stdout.write(f"{answer}\n")
            sys.stdout.flush()

        except Exception as e:
            log(f"CRITICAL error domain={domain}: {e}")
            sys.stdout.write("ERR\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
