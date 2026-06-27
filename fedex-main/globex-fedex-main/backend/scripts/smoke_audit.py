"""Smoke audit — écrit NDJSON dans debug-0c9d66.log (racine workspace)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000")
LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "debug-0c9d66.log",
)
SESSION = "0c9d66"


def log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    entry = {
        "sessionId": SESSION,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": "smoke-audit",
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def call(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype:
                return resp.status, json.loads(raw.decode() or "null")
            return resp.status, {"bytes": len(raw), "content_type": ctype}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw[:200]


def main() -> int:
    failures = 0

    st, root = call("GET", "/")
    log("H0", "smoke:root", "health", {"status": st, "body": root})
    if st != 200:
        failures += 1

    st, faq = call("GET", "/support/faq?lang=fr")
    faq_items = faq.get("items") if isinstance(faq, dict) else None
    log("H2", "smoke:faq", "faq fr", {"status": st, "count": len(faq_items) if isinstance(faq_items, list) else 0})
    if st != 200 or not isinstance(faq_items, list) or len(faq_items) == 0:
        failures += 1

    st, gcfg = call("GET", "/auth/google/config")
    log("H3", "smoke:google", "google config", {"status": st, "enabled": gcfg.get("enabled") if isinstance(gcfg, dict) else None})
    if st != 200:
        failures += 1

    st, export_anon = call("GET", "/export/tracking-history.xlsx?limit=5")
    log("H1", "smoke:export_anon", "export without auth", {"status": st})
    if st != 401:
        failures += 1

    st, login = call("POST", "/auth/login", {"email": "admin@globex.ma", "password": "Admin@Globex2024"})
    token = login.get("access_token") if isinstance(login, dict) else None
    log("H5", "smoke:login", "admin login", {"status": st, "has_token": bool(token)})
    if st != 200 or not token:
        failures += 1
        print("smoke_audit: cannot continue without admin token", file=sys.stderr)
        return 1

    st, me = call("GET", "/auth/me", token=token)
    log("H5", "smoke:me", "auth me", {"status": st, "role": me.get("role") if isinstance(me, dict) else None})

    st, dash = call("GET", "/admin/dashboard", token=token)
    log("H5", "smoke:dashboard", "admin dashboard", {"status": st, "keys": list(dash.keys())[:8] if isinstance(dash, dict) else None})

    st, notifs = call("GET", "/admin/notifications?limit=5", token=token)
    notif_items = notifs.get("items") if isinstance(notifs, dict) else None
    log("H5", "smoke:notifs", "admin notifications", {"status": st, "count": len(notif_items) if isinstance(notif_items, list) else 0})

    st, export_auth = call("GET", "/export/tracking-history.xlsx?limit=5&lang=fr", token=token)
    log("H1", "smoke:export_auth", "export with auth", {"status": st, "detail": export_auth if st != 200 else "xlsx_ok"})
    if st != 200:
        failures += 1

    st, track = call("GET", "/tracking/123456789012/status", token=token)
    log("H4", "smoke:tracking", "tracking status", {"status": st})
    if st not in (200, 404, 422):
        failures += 1

    st, pod = call("GET", "/tracking/123456789012/proof-of-delivery", token=token)
    log("H4", "smoke:pod", "proof of delivery", {"status": st, "type": type(pod).__name__})

    log("H0", "smoke:summary", "done", {"failures": failures})
    print(f"smoke_audit: failures={failures} log={LOG_PATH}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
