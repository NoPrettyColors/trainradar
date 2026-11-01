"""Poll Renfe's Cercanías GTFS-Realtime JSON feeds and keep a live snapshot."""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

from .static_gtfs import StaticGTFS

log = logging.getLogger(__name__)

FEEDS = {
    "vehicles": "https://gtfsrt.renfe.com/vehicle_positions.json",
    "trips": "https://gtfsrt.renfe.com/trip_updates.json",
    "alerts": "https://gtfsrt.renfe.com/alerts.json",
}
POLL_S = 20
ALERTS_POLL_S = 120
STALE_S = 180


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "trainradar/0.1 (+https://trainradar.noprettycolors.com)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


class LiveState:
    def __init__(self, static_provider):
        self._static = static_provider  # callable -> StaticGTFS (may be reloaded daily)
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.version = 0
        self.trains: list[dict] = []
        self.delays: dict[str, int] = {}  # trip_id -> delay seconds
        self.alerts: list[dict] = []
        self.feed_ts = 0  # vehicle feed header timestamp
        self.fetched_at = 0.0
        self.last_error: str | None = None
        self._snapshot_json = b"[]"

    # ---- polling -----------------------------------------------------------

    def start(self) -> None:
        threading.Thread(target=self._loop, name="rt-poller", daemon=True).start()

    def _loop(self) -> None:
        last_alerts = 0.0
        while True:
            try:
                self.poll()
                if time.time() - last_alerts > ALERTS_POLL_S:
                    self.poll_alerts()
                    last_alerts = time.time()
                self.last_error = None
            except Exception as e:  # keep polling through upstream hiccups
                self.last_error = f"{type(e).__name__}: {e}"
                log.warning("Realtime poll failed: %s", self.last_error)
            time.sleep(POLL_S)

    def poll(self) -> None:
        vp = _fetch(FEEDS["vehicles"])
        tu = _fetch(FEEDS["trips"])
        g: StaticGTFS = self._static()

        delays: dict[str, int] = {}
        for ent in tu.get("entity", []):
            t = ent.get("tripUpdate") or {}
            tid = (t.get("trip") or {}).get("tripId")
            if not tid:
                continue
            d = t.get("delay")
            if d is None:
                stus = t.get("stopTimeUpdate") or []
                if stus:
                    d = (stus[0].get("arrival") or stus[0].get("departure") or {}).get("delay")
            if d is not None:
                delays[tid] = int(d)

        trains = []
        for ent in vp.get("entity", []):
            v = ent.get("vehicle") or {}
            pos = v.get("position") or {}
            if "latitude" not in pos:
                continue
            tid = (v.get("trip") or {}).get("tripId", "")
            veh = v.get("vehicle") or {}
            label = veh.get("label", "")
            trip = g.trips.get(tid)
            route = g.routes.get(trip["route_id"]) if trip else None
            line = route["short"] if route else label.split("-")[0]
            stop = g.stops.get(v.get("stopId", ""))
            stops = g.stop_times.get(tid) or []
            dest = g.stops.get(stops[-1][0]) if stops else None
            trains.append({
                "id": ent.get("id"),
                "train": veh.get("id", ""),
                "trip_id": tid,
                "lat": pos["latitude"],
                "lon": pos["longitude"],
                "line": line,
                "color": route["color"] if route else "#888888",
                "text_color": route["text"] if route else "#FFFFFF",
                "nucleo": route["nucleo"] if route else g.nucleo_of(tid),
                "status": v.get("currentStatus", ""),
                "stop_id": v.get("stopId", ""),
                "stop_name": stop["name"] if stop else "",
                "destination": dest["name"] if dest else "",
                "platform": label.split("PLATF.(")[1].rstrip(")") if "PLATF.(" in label else None,
                "delay": delays.get(tid),
                "ts": int(v.get("timestamp") or 0),
            })

        with self.cond:
            self.trains = trains
            self.delays = delays
            self.feed_ts = int((vp.get("header") or {}).get("timestamp") or 0)
            self.fetched_at = time.time()
            self.version += 1
            self._snapshot_json = json.dumps(self.snapshot_unlocked(), ensure_ascii=False).encode()
            self.cond.notify_all()
        log.info("Realtime: %d trains, %d delays (v%d)", len(trains), len(delays), self.version)

    def poll_alerts(self) -> None:
        data = _fetch(FEEDS["alerts"])
        g: StaticGTFS = self._static()
        now = time.time()
        alerts = []
        for ent in data.get("entity", []):
            a = ent.get("alert") or {}
            periods = a.get("activePeriod") or [{}]
            if not any(int(p.get("start", 0)) <= now <= int(p.get("end") or 1e12) for p in periods):
                continue
            text = " ".join(t.get("text", "") for t in (a.get("descriptionText") or {}).get("translation", [])[:1])
            route_ids = [e["routeId"] for e in a.get("informedEntity", []) if e.get("routeId")]
            lines = sorted({g.routes[r]["short"] for r in route_ids if r in g.routes})
            nucleos = sorted({g.nucleo_of(r) for r in route_ids})
            alerts.append({"id": ent.get("id"), "text": text.strip(), "lines": lines, "nucleos": nucleos})
        with self.lock:
            self.alerts = alerts

    # ---- reads -------------------------------------------------------------

    def snapshot_unlocked(self) -> dict:
        # Staleness is judged by the client from feed_ts, since this JSON is cached between polls.
        return {
            "version": self.version,
            "feed_ts": self.feed_ts,
            "fetched_at": int(self.fetched_at),
            "stale_after_s": STALE_S,
            "trains": self.trains,
        }

    def status(self) -> dict:
        with self.lock:
            return {
                "version": self.version,
                "feed_ts": self.feed_ts,
                "fetched_at": int(self.fetched_at),
                "trains": len(self.trains),
                "alerts": len(self.alerts),
                "error": self.last_error,
            }

    def snapshot_json(self) -> bytes:
        with self.lock:
            return self._snapshot_json

    def wait_for(self, version: int, timeout: float) -> int:
        with self.cond:
            self.cond.wait_for(lambda: self.version != version, timeout=timeout)
            return self.version
