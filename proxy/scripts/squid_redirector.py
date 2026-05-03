#!/usr/bin/env python3
import sys
import json
import urllib.request
import threading

IA_URL = "http://ia:8001/predict"
BACKEND_URL = "http://backend:8000"
TIMEOUT = 3

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

def main():
    for line in sys.stdin:
        parts = line.strip().split()
        if not parts:
            sys.stdout.write("\n")
            sys.stdout.flush()
            continue

        url = parts[0]
        client_ip = parts[1] if len(parts) > 1 else "0.0.0.0"

        # Ignorer les requêtes non-HTTP
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
                result = json.loads(resp.read().decode())
                blocked = result.get("blocked", False)
            send_history(client_ip, url, blocked)
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
