#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
from urllib.parse import urlparse

CONFIG_FILE     = "/app/ia_config/blocked_categories.json"
BACKEND_URL     = "http://backend:8000"
IA_URL          = "http://ia:8001"
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


def extract_domain_from_url(url: str) -> str:
    """
    Extrait le domaine depuis :
      - URL complète  : https://roblox.com/path  → roblox.com
      - host:port     : roblox.com:443            → roblox.com  ← CORRIGÉ
    Squid envoie %URI sous forme "host:443" pour les requêtes CONNECT (HTTPS).
    urlparse("roblox.com:443") interprète "roblox.com" comme scheme et "443"
    comme path → retournait "443" au lieu de "roblox.com".
    """
    try:
        url = url.strip()

        # ── Cas CONNECT Squid : "host:port" sans scheme ───────────────────────
        if not url.startswith("http://") and not url.startswith("https://"):
            host_part = url.split("/")[0]       # retire le path éventuel
            domain    = host_part.split(":")[0] # retire le port
            if domain.startswith("www."):
                domain = domain[4:]
            return domain.lower().strip()

        # ── URL complète avec scheme ──────────────────────────────────────────
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        domain = domain.split(":")[0]           # retire le port éventuel
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower().strip()

    except Exception:
        return url.split(":")[0].split("/")[0].lower().strip()


def is_whitelisted(domain: str) -> bool:
    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]
    for w in WHITELIST_DOMAINS:
        if dl == w or dl.endswith("." + w):
            return True
    return False


def should_block_instant(domain: str, blocked_cats: list):
    """
    Blocage instantané par domaine et mots-clés dans l'URL.
    Rapide, sans appel réseau.
    """
    if not blocked_cats:
        return False, "safe"

    dl = domain.lower().strip()
    if dl.startswith("www."):
        dl = dl[4:]

    if is_whitelisted(dl):
        return False, "safe"

    # Correspondance exacte de domaine dans BLOCKED_DOMAINS
    for cat in blocked_cats:
        for bd in BLOCKED_DOMAINS.get(cat, []):
            if dl == bd or dl.endswith("." + bd):
                log(f"BLOCK instant domain={domain} cat={cat} matched={bd}")
                return True, cat

    # Mots-clés dans le domaine
    for cat in blocked_cats:
        for word in KEYWORDS.get(cat, []):
            if word.lower() in dl:
                log(f"BLOCK instant domain={domain} cat={cat} keyword={word}")
                return True, cat

    return False, "safe"


def ask_ia(full_url: str):
    """
    Envoie l'URL COMPLÈTE à l'IA pour analyse du contenu
    de la PAGE SPÉCIFIQUE visitée (plus seulement la page d'accueil).
    """
    try:
        payload = json.dumps({
            "url": full_url,
            "fetch_content": True,
        }).encode()
        req = urllib.request.Request(
            f"{IA_URL}/predict",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data       = json.loads(resp.read())
            blocked    = data.get("blocked", False)
            cat        = data.get("category", "safe")
            conf       = data.get("confidence", 0)
            analyzed   = data.get("content_analyzed", False)
            log(f"IA url={full_url} blocked={blocked} cat={cat} conf={conf} content_analyzed={analyzed}")
            return blocked, cat, conf
    except Exception as e:
        log(f"ask_ia error url={full_url}: {e}")
        return False, "safe", 0.0


def push_to_backend_blocklist(domain: str, category: str, confidence: float, source: str = "squid_tfidf"):
    """
    Pousse un domaine découvert vers la blacklist dynamique backend.
    Android synchronisera automatiquement cette liste.
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


def send_history(client_ip: str, url: str, blocked: bool):
    """Enregistre l'URL complète visitée dans l'historique backend."""
    try:
        data = json.dumps({
            "ip": client_ip,
            "url": url,
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
    log("squid_https_blocker started — mode analyse page spécifique (%URI)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            sys.stdout.write("ERR\n")
            sys.stdout.flush()
            continue

        parts     = line.split()
        full_url  = parts[0]   # %URI → URL complète OU host:port (CONNECT HTTPS)
        client_ip = parts[1] if len(parts) > 1 else "0.0.0.0"

        # Extraire le domaine — gère maintenant host:port ET https://...
        domain = extract_domain_from_url(full_url)

        try:
            blocked_cats = load_blocked_categories()

            # Étape 1 : blocage instantané par domaine (sans appel réseau → rapide)
            blocked, category = should_block_instant(domain, blocked_cats)
            ia_confidence = 0.0

            if not blocked and blocked_cats:
                # Pour l'IA : reconstruire une URL valide si c'était un host:port
                ia_url = full_url
                if not full_url.startswith("http://") and not full_url.startswith("https://"):
                    ia_url = f"https://{domain}"

                # Étape 2 : analyse IA du contenu de la PAGE SPÉCIFIQUE visitée
                blocked, category, ia_confidence = ask_ia(ia_url)

                # Si l'IA a confirmé → pousser le domaine dans la blacklist dynamique
                if blocked and ia_confidence >= 0.60:
                    push_to_backend_blocklist(
                        domain, category, ia_confidence, source="squid_tfidf"
                    )

            # Enregistrer dans l'historique (URL reconstruite si nécessaire)
            history_url = full_url
            if not full_url.startswith("http://") and not full_url.startswith("https://"):
                history_url = f"https://{domain}"
            send_history(client_ip, history_url, blocked)

            # OK = bloquer, ERR = autoriser (convention Squid external_acl)
            answer = "OK" if blocked else "ERR"
            log(f"url={full_url} domain={domain} → {answer} cat={category}")
            sys.stdout.write(f"{answer}\n")
            sys.stdout.flush()

        except Exception as e:
            log(f"CRITICAL error url={full_url}: {e}")
            sys.stdout.write("ERR\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
