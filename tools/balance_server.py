#!/usr/bin/env python3
# tools/balance_server.py -- LAN endpoint for the AI Passport balance page.
# Rolling-window GLM usage from ALL hermes databases. A background thread
# samples deltas every 60s regardless of device polling, so the 5h/7d
# windows stay continuous even when the badge is offline.
import glob
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HERMES_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")
PORT = 8765
COEFFS = {"glm-5.3": (6.9, 1.7, 24.0)}
DEFAULT_COEFF = (6.9, 1.7, 24.0)
HIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".balance_history.json")
SAMPLE_PERIOD = 60


def points(model, inp, cached, outp):
    ci, cc, co = COEFFS.get((model or "").lower(), DEFAULT_COEFF)
    return (inp * ci + cached * cc + outp * co) / 10000.0


def db_paths():
    paths = []
    main = os.path.join(HERMES_DIR, "state.db")
    if os.path.exists(main):
        paths.append(main)
    paths += sorted(glob.glob(os.path.join(HERMES_DIR, "profiles", "*", "state.db")))
    return paths


def db_rows():
    rows = []
    for p in db_paths():
        tag = os.path.basename(os.path.dirname(p)) or "main"
        try:
            con = sqlite3.connect("file:" + p + "?mode=ro", uri=True, timeout=3)
            try:
                cur = con.cursor()
                for sid, model, inp, outp, cached, calls in cur.execute(
                    "select session_id, model, sum(input_tokens), sum(output_tokens),"
                    " sum(cache_read_tokens), sum(api_call_count)"
                    " from session_model_usage group by session_id, model"
                ):
                    rows.append((tag + "|" + str(sid) + "|" + str(model), model,
                                 inp or 0, outp or 0, cached or 0, calls or 0))
            finally:
                con.close()
        except Exception:
            pass
    return rows


def load_hist():
    try:
        with open(HIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"samples": [], "last": {}}


def save_hist(h):
    tmp = HIST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(h, f)
    os.replace(tmp, HIST_PATH)


HIST_LOCK = threading.Lock()


def sample_once():
    with HIST_LOCK:
        h = load_hist()
        now = time.time()
        cur = {}
        for key, model, inp, outp, cached, calls in db_rows():
            cur[key] = [inp, outp, cached, calls]
        last = h.get("last", {})
        delta_pts = 0.0
        delta_calls = 0
        for k, v in cur.items():
            pv = last.get(k)
            if pv is None:
                continue
            d = [max(0, v[i] - pv[i]) for i in range(4)]
            delta_calls += d[3]
            delta_pts += points(k.rsplit("|", 1)[-1], d[0], d[2], d[1])
        if last:
            h["samples"].append([now, round(delta_pts, 2), delta_calls])
            cutoff = now - 8 * 86400
            h["samples"] = [s for s in h["samples"] if s[0] >= cutoff]
        h["last"] = cur
        h["updated"] = int(now)
        save_hist(h)


def sampler_loop():
    while True:
        try:
            sample_once()
        except Exception:
            pass
        time.sleep(SAMPLE_PERIOD)


def window_stats(sec):
    with HIST_LOCK:
        h = load_hist()
        now = time.time()
        pts = sum(s[1] for s in h["samples"] if s[0] >= now - sec)
        calls = sum(s[2] for s in h["samples"] if s[0] >= now - sec)
        started = h["samples"][0][0] if h["samples"] else now
    return round(pts, 1), calls, int(started)


def take_sample():
    p5, c5, started = window_stats(5 * 3600)
    pw, cw, _ = window_stats(7 * 86400)
    return {
        "updated": int(time.time()),
        "now_local": time.strftime("%H:%M"),
        "window_5h": {"points": p5, "calls": c5},
        "week": {"points": pw, "calls": cw},
        "history_started": started,
        "note": "delta est. from local agent dbs",
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] != "/balance":
            self.send_response(404); self.end_headers(); return
        try:
            body = json.dumps(take_sample()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(500); self.end_headers()
            self.wfile.write(str(e).encode())
    def log_message(self, *a):
        pass


if __name__ == "__main__":
    sample_once()
    threading.Thread(target=sampler_loop, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
