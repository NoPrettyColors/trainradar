"""Poll Renfe's GTFS-Realtime JSON feeds and keep a live snapshot.

Two families of feeds are merged: Cercanías/Rodalies, and high-speed,
long-distance and medium-distance (AV/LD/MD).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from email.utils import parsedate_to_datetime

from . import errors
from .static_gtfs import StaticGTFS

log = logging.getLogger(__name__)

FEEDS = {
    "vehicles": "https://gtfsrt.renfe.com/vehicle_positions.json",
    "trips": "https://gtfsrt.renfe.com/trip_updates.json",
    "vehicles_ld": "https://gtfsrt.renfe.com/vehicle_positions_LD.json",
    "trips_ld": "https://gtfsrt.renfe.com/trip_updates_LD.json",
    "alerts": "https://gtfsrt.renfe.com/alerts.json",
}
POLL_S = 20
ALERTS_POLL_S = 120
STALE_S = 180
MAX_FEED_BYTES = 20 << 20  # each feed is about 120 KB


def _fetch(url: str) -> tuple[dict, int]:
    """Return the feed and when the server last changed it.

    The AV/LD/MD vehicle feed's header timestamp runs an hour behind, so the
    HTTP Last-Modified header is the more reliable freshness signal.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "trainradar/0.1 (+https://trainradar.noprettycolors.com)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(errors.read_capped(r, MAX_FEED_BYTES))
        lm = r.headers.get("Last-Modified")
    try:
        modified = int(parsedate_to_datetime(lm).timestamp()) if lm else 0
    except (TypeError, ValueError):
        modified = 0
    return data, modified or int((data.get("header") or {}).get("timestamp") or 0)


def _delays(feed: dict) -> dict[str, int]:
    delays: dict[str, int] = {}
    for ent in feed.get("entity", []):
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
    return delays


class LiveState:
    def __init__(self, static_provider):
        self._static = static_provider  # .feeds -> {"cercanias": StaticGTFS, "ld": StaticGTFS}, reloaded daily
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.version = 0
        self.trains: list[dict] = []
        self.delays: dict[str, int] = {}  # trip_id -> delay seconds
        self.alerts: list[dict] = []
        self.feed_ts = 0  # newest vehicle feed update
        self.fetched_at = 0.0
        self.last_error: str | None = None
        self.feed_status: dict[str, dict] = {k: {"url": u} for k, u in FEEDS.items()}
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
                self.last_error = errors.label(e)
                log.warning("Realtime poll failed: %s: %s", type(e).__name__, e)
            time.sleep(POLL_S)

    def _get(self, name: str) -> tuple[dict, int] | None:
        """Fetch one feed, recording its health; a failing feed doesn't block the others."""
        st = self.feed_status[name]
        try:
            data, modified = _fetch(FEEDS[name])
        except Exception as e:
            st["error"] = errors.label(e)
            log.warning("Feed %s failed: %s: %s", name, type(e).__name__, e)
            return None
        st.update(error=None, fetched_at=int(time.time()), updated_at=modified, entities=len(data.get("entity", [])))
        return data, modified

    def poll(self) -> None:
        feeds = self._static.feeds
        delays: dict[str, int] = {}
        trains: list[dict] = []
        newest = 0
        for vname, tname, g in (("vehicles", "trips", feeds["cercanias"]), ("vehicles_ld", "trips_ld", feeds["ld"])):
            tu = self._get(tname)
            if tu:
                delays |= _delays(tu[0])
            vp = self._get(vname)
            if not vp:
                # Keep the last known trains of this family rather than dropping them.
                trains += [t for t in self.trains if (t["service"] == "cercanias") == (g.kind == "cercanias")]
                continue
            newest = max(newest, vp[1])
            trains += self._trains(vp[0], vp[1], g, delays)
        if not newest:
            raise RuntimeError("no vehicle feed could be read")

        with self.cond:
            self.trains = trains
            self.delays = delays
            self.feed_ts = newest
            self.fetched_at = time.time()
            self.version += 1
            self._snapshot_json = json.dumps(self.snapshot_unlocked(), ensure_ascii=False).encode()
            self.cond.notify_all()
        log.info("Realtime: %d trains, %d delays (v%d)", len(trains), len(delays), self.version)

    @staticmethod
    def _trains(vp: dict, feed_time: int, g: StaticGTFS, delays: dict[str, int]) -> list[dict]:
        out = []
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
            out.append({
                "id": ent.get("id"),
                "train": veh.get("id", ""),
                "trip_id": tid,
                "lat": pos["latitude"],
                "lon": pos["longitude"],
                "line": line,
                "service": route["service"] if route else ("cercanias" if g.kind == "cercanias" else "regional"),
                "color": route["color"] if route else ("#888888" if g.kind == "cercanias" else ""),
                "text_color": route["text"] if route else "",
                "nucleo": route["nucleo"] if route else g.nucleo_of(tid),
                "status": v.get("currentStatus", ""),
                "stop_id": v.get("stopId", ""),
                "stop_name": stop["name"] if stop else "",
                "destination": dest["name"] if dest else "",
                "platform": label.split("PLATF.(")[1].rstrip(")") if "PLATF.(" in label else None,
                "delay": delays.get(tid),
                # AV/LD/MD vehicles carry no timestamp of their own.
                "ts": int(v.get("timestamp") or feed_time),
            })
        return out

    def poll_alerts(self) -> None:
        got = self._get("alerts")
        if not got:
            return
        data = got[0]
        g: StaticGTFS = self._static.feeds["cercanias"]
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
            by_service: dict[str, int] = {}
            for t in self.trains:
                by_service[t["service"]] = by_service.get(t["service"], 0) + 1
            return {
                "version": self.version,
                "feed_ts": self.feed_ts,
                "fetched_at": int(self.fetched_at),
                "trains": len(self.trains),
                "by_service": by_service,
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
