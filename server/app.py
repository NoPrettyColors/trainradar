"""HTTP server: JSON API, Server-Sent Events stream and the static web client.

Standard library only (plus tzdata on Windows), so it runs on any Python 3.11+.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import mimetypes
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import sources, static_gtfs
from .network import Network
from .realtime import LiveState

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
# Deployments keep the GTFS cache outside the release directory so it survives updates.
DATA = Path(os.environ.get("TRAINRADAR_DATA", ROOT / "data"))

log = logging.getLogger("trainradar")


class Static:
    """Holds both static feeds and reloads them when the service day changes."""

    def __init__(self):
        self.feeds = {k: static_gtfs.load(DATA, k) for k in static_gtfs.FEEDS}
        self._cache: dict[str, bytes] = {}
        self._build_cache()

    def __call__(self) -> static_gtfs.StaticGTFS:
        return self.feeds["cercanias"]

    @property
    def service_date(self):
        return self().service_date

    def trip(self, trip_id: str):
        for g in self.feeds.values():
            if trip_id in g.trips:
                return g, g.trips[trip_id]
        return None, None

    def stop(self, stop_id: str) -> dict | None:
        # Both feeds use Adif station codes; the long-distance feed has the full station names.
        return self.feeds["ld"].stops.get(stop_id) or self.feeds["cercanias"].stops.get(stop_id)

    def _build_cache(self) -> None:
        g = self()
        bboxes: dict[str, list[float]] = {}
        for f in g.shapes_geojson["features"]:
            n = f["properties"]["nucleo"]
            b = bboxes.setdefault(n, [180, 90, -180, -90])
            for x, y in f["geometry"]["coordinates"]:
                b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)
        nucleos = [{"name": n, "bbox": bboxes[n]} for n in static_gtfs.NUCLEOS.values() if n in bboxes]
        # One point per station; "kind" says which services call there: cercanias, ld or both.
        stations: dict[str, dict] = {}
        for k, feed in self.feeds.items():
            for f in feed.stops_geojson["features"]:
                p = f["properties"]
                if p["id"] in stations:
                    stations[p["id"]]["properties"]["kind"] = "both"
                    if k == "ld":
                        stations[p["id"]]["properties"]["name"] = p["name"]
                else:
                    stations[p["id"]] = {**f, "properties": dict(p)}
        stops = {"type": "FeatureCollection", "features": list(stations.values())}
        self._cache = {
            "shapes": gzip.compress(json.dumps(g.shapes_geojson, separators=(",", ":")).encode()),
            "stops": gzip.compress(json.dumps(stops, ensure_ascii=False, separators=(",", ":")).encode()),
            "nucleos": gzip.compress(json.dumps(nucleos, ensure_ascii=False).encode()),
        }

    def cached(self, key: str) -> bytes:
        return self._cache[key]

    def start_daily_reload(self) -> None:
        def loop():
            while True:
                time.sleep(600)
                if datetime.now(static_gtfs.TZ).date() != self.service_date and datetime.now(static_gtfs.TZ).hour >= 3:
                    try:
                        new = Static.__new__(Static)
                        new.feeds = {k: static_gtfs.load(DATA, k) for k in static_gtfs.FEEDS}
                        new._build_cache()
                        self.feeds, self._cache = new.feeds, new._cache
                    except Exception:
                        log.exception("Static GTFS reload failed; keeping previous day")
        threading.Thread(target=loop, name="gtfs-reload", daemon=True).start()


STATIC: Static
LIVE: LiveState
NETWORK: Network


def trip_detail(trip_id: str) -> dict | None:
    g, trip = STATIC.trip(trip_id)
    if not trip:
        return None
    route = g.routes.get(trip["route_id"], {})
    base = g.trip_base[trip_id]
    with LIVE.lock:
        delay = LIVE.delays.get(trip_id)
        train = next((t for t in LIVE.trains if t["trip_id"] == trip_id), None)
    rows = g.stop_times.get(trip_id, [])
    current = next((i for i, (s, _, _) in enumerate(rows) if train and s == train["stop_id"]), None)
    stops = []
    for i, (sid, arr, dep) in enumerate(rows):
        s = STATIC.stop(sid) or {}
        passed = current is not None and i < current
        upcoming = not passed
        stops.append({
            "id": sid,
            "name": s.get("name", sid),
            "scheduled": base + arr,
            "expected": base + arr + delay if (delay is not None and upcoming) else None,
            "passed": passed,
            "current": i == current,
        })
    return {
        "trip_id": trip_id,
        "line": route.get("short", ""),
        "route_name": route.get("long", ""),
        "color": route.get("color", "#888"),
        "text_color": route.get("text", "#fff"),
        "nucleo": route.get("nucleo", ""),
        "service": route.get("service", ""),
        "delay": delay,
        "train": train,
        "stops": stops,
    }


def stop_board(stop_id: str, window_min: int = 90, limit: int = 25) -> dict | None:
    stop = STATIC.stop(stop_id)
    if not stop:
        return None
    now = int(time.time())
    with LIVE.lock:
        delays = dict(LIVE.delays)
        live_trips = {t["trip_id"] for t in LIVE.trains}
    out = []
    for g in STATIC.feeds.values():
        for sched, tid in g.stop_index.get(stop_id, []):
            if sched < now - 3600:
                continue
            if sched > now + window_min * 60:
                break
            d = delays.get(tid)
            expected = sched + (d or 0)
            if expected < now - 60:
                continue
            trip = g.trips[tid]
            route = g.routes.get(trip["route_id"], {})
            rows = g.stop_times.get(tid, [])
            if rows and rows[-1][0] == stop_id:
                continue  # terminating here: not a departure
            dest = (STATIC.stop(rows[-1][0]) or {}).get("name", "") if rows else ""
            out.append({
                "trip_id": tid,
                "line": route.get("short", ""),
                "service": route.get("service", ""),
                "color": route.get("color", "#888"),
                "text_color": route.get("text", "#fff"),
                "destination": dest,
                "scheduled": sched,
                "expected": expected if d is not None else None,
                "delay": d,
                "live": tid in live_trips,
            })
    out.sort(key=lambda r: r["expected"] or r["scheduled"])
    return {"stop": stop, "departures": out[:limit]}


class Handler(BaseHTTPRequestHandler):
    server_version = "TrainRadar/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.debug("%s - " + fmt, self.address_string(), *args)

    def _send(self, body: bytes, ctype: str = "application/json; charset=utf-8", status: int = 200,
              gz: bool = False, cache: str = "no-store") -> None:
        if gz and "gzip" not in (self.headers.get("Accept-Encoding") or ""):
            body, gz = gzip.decompress(body), False
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode(), status=status)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        q = parse_qs(url.query)
        try:
            if path == "/api/trains":
                return self._send(LIVE.snapshot_json())
            if path == "/api/stream":
                return self._stream()
            if path in ("/api/shapes", "/api/stops", "/api/nucleos"):
                return self._send(STATIC.cached(path.rsplit("/", 1)[1]), gz=True, cache="public, max-age=3600")
            if path == "/api/alerts":
                n = q.get("nucleo", [None])[0]
                with LIVE.lock:
                    alerts = [a for a in LIVE.alerts if not n or n in a["nucleos"]]
                return self._json(alerts)
            if path == "/api/status":
                return self._json(LIVE.status() | {"static_loaded_at": int(STATIC().loaded_at),
                                                   "service_date": str(STATIC.service_date),
                                                   "network": bool(NETWORK.gz)})
            if path == "/api/network":
                if not NETWORK.gz:
                    return self._json({"error": "rail network still downloading"}, 503)
                return self._send(NETWORK.gz, "application/geo+json", gz=True, cache="public, max-age=86400")
            if path == "/api/sources":
                return self._json(sources_report())
            if path.startswith("/api/trip/"):
                d = trip_detail(path[len("/api/trip/"):])
                return self._json(d) if d else self._json({"error": "trip not found"}, 404)
            if path.startswith("/api/stop/"):
                d = stop_board(path[len("/api/stop/"):])
                return self._json(d) if d else self._json({"error": "stop not found"}, 404)
            if path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            return self._static(path)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _static(self, path: str) -> None:
        f = (WEB / ("index.html" if path in ("", "/") else path.lstrip("/"))).resolve()
        if WEB not in f.parents or not f.is_file():
            return self._send(b"Not found", "text/plain", 404)
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(f.read_bytes(), ctype, cache="no-cache")

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")  # tell proxies not to buffer the stream
        self.end_headers()
        self.close_connection = True
        version = -1
        while True:
            new = LIVE.wait_for(version, timeout=25)
            if new == version:
                self.wfile.write(b": keepalive\n\n")
            else:
                version = new
                self.wfile.write(b"event: trains\ndata: " + LIVE.snapshot_json() + b"\n\n")
            self.wfile.flush()


def sources_report() -> dict:
    """The data catalogue plus live numbers for each source."""
    with LIVE.lock:
        feeds = {k: dict(v) for k, v in LIVE.feed_status.items()}
        by_service: dict[str, int] = {}
        for t in LIVE.trains:
            by_service[t["service"]] = by_service.get(t["service"], 0) + 1
        n_alerts = len(LIVE.alerts)
    used = []
    for src in sources.USED:
        live: dict = {}
        if src["id"] in feeds:
            f = feeds[src["id"]]
            live = {"updated_at": f.get("updated_at"), "entities": f.get("entities"), "error": f.get("error")}
            if src["id"] == "alerts":
                live["active"] = n_alerts
        elif src["id"].startswith("gtfs_"):
            g = STATIC.feeds["cercanias" if src["id"] == "gtfs_cercanias" else "ld"]
            live = {"updated_at": int(g.loaded_at), "stations": len(g.stop_index),
                    "routes": len(g.routes), "trips_today": len(g.trips)}
        elif src["id"] == "network":
            live = NETWORK.stats | {"error": NETWORK.error}
        used.append({**src, "live": live})
    return {"used": used, "more": sources.MORE, "trains": by_service, "services": static_gtfs.SERVICE_NAMES}


def main() -> None:
    global STATIC, LIVE, NETWORK
    ap = argparse.ArgumentParser(description="Live map of Renfe trains in Spain")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    STATIC = Static()
    STATIC.start_daily_reload()
    NETWORK = Network(DATA)
    NETWORK.start()
    LIVE = LiveState(STATIC)
    try:
        LIVE.poll()
        LIVE.poll_alerts()
    except Exception:
        log.exception("Initial realtime poll failed; will retry in background")
    LIVE.start()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    srv.daemon_threads = True
    log.info("Serving on http://%s:%d", args.host, args.port)
    srv.serve_forever()


if __name__ == "__main__":
    main()
