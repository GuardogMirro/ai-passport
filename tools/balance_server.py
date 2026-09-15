#!/usr/bin/env python3
# tools/balance_server.py -- LAN endpoint for the AI Passport balance page.
#
# v2 (2026-09-15): official quota source. Backend design mirrors the user's
# own DSH balance card (@local/dsh-balance-monitor, host half):
#   - upstream: GET https://open.bigmodel.cn/api/monitor/usage/quota/limit
#     (Bearer ZHIPU_API_KEY) -- the same live-verified endpoint the sidebar
#     card uses. No local-db estimation, no reverse-engineered gateways.
#   - 5 min TTL cache, 15 s upstream timeout, never throws to the caller.
#   - key resolved from ~/.dsh/.credentials.yaml (ZHIPU_API_KEY), env
#     fallback; the key never appears in logs or responses.
#   - stale-serve: on upstream failure the last good payload is re-served
#     with "stale": true so the badge keeps showing numbers.
#
# Response (GET /balance[?refresh=1]):
#   { ok, updated, now_local, source, level, stale,
#     window_5h: {used, limit, pct, reset_ms, reset_local} | null,
#     week:      {used, limit, pct, reset_ms, reset_local} | null,
#     windows: [ {kind, unit, number, used, limit, pct, reset_ms, reset_local} ],
#     diag: {http, age_s} }
#
# reset_local formatting follows the card's semantics: hour windows "HH:MM",
# weekly (and >=48h) windows always "MM-dd HH:MM".
import json
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("BALANCE_PORT", "8765"))
UPSTREAM_URL = "https://open.bigmodel.cn/api/monitor/usage/quota/limit"
KEY_NAME = "ZHIPU_API_KEY"
TTL_S = 5 * 60
TIMEOUT_S = 15

_LOCK = threading.Lock()
_CACHE = None  # {"at": epoch, "payload": {...}} last good official payload


def resolve_key():
    """Key from ~/.dsh/.credentials.yaml, env fallback. Never logged."""
    path = os.path.join(os.path.expanduser("~"), ".dsh", ".credentials.yaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^([A-Z_]+):\s*(\S+)", line)
                if m and m.group(1) == KEY_NAME:
                    return m.group(2).strip("\"'")
    except Exception:
        pass
    env = os.environ.get(KEY_NAME)
    return env if env else None


def fmt_reset(ms, with_date):
    try:
        t = time.localtime(ms / 1000.0)
    except Exception:
        return ""
    hm = "%02d:%02d" % (t.tm_hour, t.tm_min)
    if with_date or (ms / 1000.0 - time.time()) >= 48 * 3600:
        return "%02d-%02d %s" % (t.tm_mon, t.tm_mday, hm)
    return hm


def fetch_upstream(key):
    """One official call. Returns (ok, http_status, limits_list, level)."""
    req = urllib.request.Request(
        UPSTREAM_URL, headers={"Authorization": "Bearer " + key,
                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            body = json.loads(r.read().decode("utf-8"))
            if body.get("success") is not True or not isinstance(
                    body.get("data", {}).get("limits"), list):
                return False, r.status, None, None
            limits = [L for L in body["data"]["limits"]
                      if L.get("type") == "CREDIT_LIMIT"]
            return True, r.status, limits, body["data"].get("level", "")
    except Exception:
        return False, 0, None, None


def window_obj(L):
    unit = L.get("unit")
    number = L.get("number", 0)
    reset_ms = L.get("nextResetTime")
    with_date = unit == 6  # weekly windows always carry the date
    return {
        "kind": ("5h" if unit == 3 else ("7d" if unit == 6 else "u%s" % unit)),
        "unit": unit,
        "number": number,
        "used": L.get("currentValue", 0),
        "limit": L.get("usage", 0),
        "pct": L.get("percentage", 0),
        "reset_ms": reset_ms,
        "reset_local": fmt_reset(reset_ms, with_date) if isinstance(reset_ms, (int, float)) else "",
    }


def build_payload(limits, level):
    w5 = None
    wk = None
    windows = []
    for L in limits:
        w = window_obj(L)
        windows.append(w)
        if w["unit"] == 3 and w5 is None:
            w5 = w
        elif w["unit"] == 6 and wk is None:
            wk = w
    return {
        "ok": True,
        "updated": int(time.time()),
        "now_local": time.strftime("%H:%M"),
        "source": "official",
        "level": level,
        "stale": False,
        "window_5h": w5,
        "week": wk,
        "windows": windows,
    }


def get_status(force):
    """Cache-first official status; stale-serve on failure."""
    global _CACHE
    key = resolve_key()
    if key is None:
        return {"ok": False, "error": KEY_NAME + " not configured",
                "updated": int(time.time()), "now_local": time.strftime("%H:%M")}
    with _LOCK:
        if (not force and _CACHE is not None
                and time.time() - _CACHE["at"] < TTL_S):
            p = dict(_CACHE["payload"])
            p["diag"] = {"http": 200, "age_s": int(time.time() - _CACHE["at"])}
            return p
    ok, status, limits, level = fetch_upstream(key)
    with _LOCK:
        if ok:
            payload = build_payload(limits, level)
            _CACHE = {"at": time.time(), "payload": payload}
            payload["diag"] = {"http": status, "age_s": 0}
            return payload
        if _CACHE is not None:
            p = dict(_CACHE["payload"])
            p["stale"] = True
            p["diag"] = {"http": status,
                         "age_s": int(time.time() - _CACHE["at"])}
            return p
        return {"ok": False, "error": "upstream HTTP %s" % status,
                "updated": int(time.time()), "now_local": time.strftime("%H:%M"),
                "diag": {"http": status, "age_s": None}}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path != "/balance":
            self.send_response(404)
            self.end_headers()
            return
        force = "refresh=1" in (query or "")
        try:
            body = json.dumps(get_status(force)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=get_status, args=(True,), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
