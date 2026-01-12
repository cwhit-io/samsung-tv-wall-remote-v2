import sys
import os
# ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient
import app.main as main

client = TestClient(main.app)

ip = "10.10.97.123"

endpoints = [
    ("GET", f"/api/debug/ping?ip={ip}"),
    ("GET", f"/api/debug/port?ip={ip}&port=8001"),
    ("GET", f"/api/debug/port?ip={ip}&port=8002"),
    ("GET", f"/api/debug/ssdp?ip={ip}&timeout=1"),
    ("POST", f"/api/debug/wake-and-wait", {"ip": ip, "port": 9, "wait_seconds": 1}),
]

for method, url, *maybe_body in endpoints:
    try:
        if method == "GET":
            r = client.get(url)
        else:
            r = client.post(url, json=maybe_body[0])
        print(url, "->", r.status_code, r.text[:400])
    except Exception as e:
        print(url, "-> Exception:", e)
