#!/usr/bin/env python3
import sys
import json
import urllib.request
import threading

IA_URL          = "http://ia:8001/predict"
BACKEND_URL     = "http://backend:8000"
TIMEOUT         = 3
INTERNAL_SECRET = "squid-internal-secret-2024"


def send_history(client_ip, url, blocked):
    try:
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


def push_to_backend_blocklist(domain: str, category: str, confidence: float):
    """
    Pousse un domaine HTTP bloqué par l'IA vers la blacklist dynamique backend.
    Android synchronisera automatiquement cette liste.
    """
    try:
        dl = domain.lower().strip().lstrip("www.")
        data = json.dumps({
            "domain": dl,
            "category": category,
            "source": "squid_http_redirector",
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
        threading.Thread(
            target=lambda: urllib.request.urlopen(req, timeout=2),
            daemon=True
        ).start()
    except:
        pass


def extract_domain(url: str) -> str:
    """Extrait le domaine d'une URL HTTP."""
    try:
        without_scheme = url.replace("http://", "").replace("https://", "")
        return without_scheme.split("/")[0].split(":")[0]
    except:
        return url


def main():
    for line in sys.stdin:
        parts = line.strip().split()
        if not parts:
            sys.stdout.write("\n")
            sys.stdout.flush()
            continue

        url = parts[0]
        client_ip = parts[1] if len(parts) > 1 else "0.0.0.0"

        if not url.startswith("http://"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            continue

        try:
            req = urllib.request.Request(
                IA_URL,
                data=json.dumps({"url": url, "fetch_content": False}).encode(),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                result     = json.loads(resp.read().decode())
                blocked    = result.get("blocked", False)
                category   = result.get("category", "safe")
                confidence = result.get("confidence", 0.0)

            send_history(client_ip, url, blocked)

            # Si l'IA a bloqué ce domaine HTTP → pousser dans la blacklist backend
            # Android le bloquera automatiquement (même domaine en HTTP et HTTPS)
            if blocked and confidence >= 0.60:
                domain = extract_domain(url)
                push_to_backend_blocklist(domain, category, confidence)

            if blocked:
                sys.stdout.write("http://blocked.parental-control.local/\n")
            else:
                sys.stdout.write("\n")
        except:
            send_history(client_ip, url, False)
            sys.stdout.write("\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
