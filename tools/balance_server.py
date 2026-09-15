#!/usr/bin/env python3
# tools/balance_server.py -- LAN endpoint for the AI Passport balance page.
# Serves rolling-window GLM usage computed from the hermes agent database
# (read-only) using a local delta-history file: each request snapshots the
# per-(session,model) aggregates and records the increase since the previous
# sample, so rolling 5h/7d numbers stay exact despite database aggregation.
import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

DB_PATH = r"C:\Users\f3794\AppData\Local\hermes\profiles\work-project-agen\state.db"
HIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".balance_history.json")
PORT = 8765
COEFFS = {"glm-5.3": (6.9, 1.7, 24.0)}
DEFAULT_COEFF = (6.9, 1.7, 24.0)


def points(model, inp, cached, outp):
    ci, cc, co = COEFFS.get((model or "").lower(), DEFAULT_COEFF)
    return (inp * ci + cached * cc + outp * co) / 10000.0


def db_rows():
    con = sqlite3.connect("file:" + DB_PATH + "?mode=ro", uri=True, timeout=3)
    try:
        cur = con.cursor()
        return cur.execute(
            "select session_id, model, sum(input_tokens), sum(output_tokens),"
            " sum(cache_read_tokens), sum(api_call_count)"
            " from session_model_usage group by session_id, model"
        ).fetchall()
    finally:
        con.close()


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


def take_sample():
    h = load_hist()
    now = time.time()
    rows = db_rows()
    cur = {}
    for sid, model, inp, outp, cached, calls in rows:
        cur[str(sid) + "|" + str(model)] = [inp or 0, outp or 0, cached or 0, calls or 0]
    last = h.get("last", {})
    delta_pts = 0.0
    delta_calls = 0
    for k, v in cur.items():
        pv = last.get(k)
        if pv is None:
            continue  # brand-new row: unknown split, start tracking from next sample
        d = [max(0, v[i] - pv[i]) for i in range(4)]
        delta_calls += d[3]
        delta_pts += points(k.split("|")[-1], d[0], d[2], d[1])
    if last:
        h["samples"].append([now, round(delta_pts, 2), delta_calls])
        cutoff = now - 8 * 86400
        h["samples"] = [s for s in h["samples"] if s[0] >= cutoff]
    h["last"] = cur
    h["updated"] = int(now)
    save_hist(h)

    def window(sec):
        pts = sum(s[1] for s in h["samples"] if s[0] >= now - sec)
        calls = sum(s[2] for s in h["samples"] if s[0] >= now - sec)
        return round(pts, 1), calls

    p5, c5 = window(5 * 3600)
    pw, cw = window(7 * 86400)
    hist_start = h["samples"][0][0] if h["samples"] else now
    return {
        "updated": int(now),
        "window_5h": {"points": p5, "calls": c5},
        "week": {"points": pw, "calls": cw},
        "history_started": int(hist_start),
        "note": "delta-based local estimate from hermes db",
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
    take_sample()  # prime history
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
