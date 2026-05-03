#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error

IA_URL = "http://ia:8001/predict"
timeout = 3

def main():
    for line in sys.stdin:
        domain = line.strip()
        if not domain:
            continue
        url = f"http://{domain}"
        try:
            req = urllib.request.Request(
                IA_URL,
                data=json.dumps({"url": url, "fetch_content": False}).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode())
                if result.get("blocked", False):
                    sys.stdout.write("ERR\n")
                else:
                    sys.stdout.write("OK\n")
        except Exception:
            sys.stdout.write("OK\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
