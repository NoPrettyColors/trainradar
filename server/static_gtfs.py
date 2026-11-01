"""Renfe static GTFS feeds: download, cache and index.

Two feeds share one loader: Cercanías/Rodalies, and high-speed, long-distance
and medium-distance (AV/LD/MD). Both are published daily as zips of
fixed-width-padded CSV files, so every field is stripped on read. Cercanías
stop_times.txt is ~290 MB; only rows for trips that run today (and yesterday's
after-midnight tail) are kept in memory.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

FEEDS = {
    "cercanias": ("https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip", "cercanias_gtfs.zip"),
    "ld": ("https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip", "ld_gtfs.zip"),
}
TZ = ZoneInfo("Europe/Madrid")
MAX_AGE_S = 24 * 3600

# The first two digits of a route_id identify the núcleo (regional network).
NUCLEOS = {
    "10": "Madrid",
    "20": "Asturias",
    "30": "Sevilla",
    "31": "Cádiz",
    "32": "Málaga",
    "40": "València",
    "41": "Murcia / Alicante",
    "45": "Cartagena",
    "46": "Ferrol",
    "47": "León",
    "51": "Rodalies de Catalunya",
    "60": "Bilbao",
    "61": "San Sebastián",
    "62": "Santander",
    "70": "Zaragoza",
}


# AV/LD/MD products (route_short_name) grouped into the services the map shows.
LD_SERVICES = {
    "high-speed": {"AVE", "AVE INT", "AVLO", "AVANT", "AVANT EXP", "EUROMED"},
    "long-distance": {"ALVIA", "INTERCITY", "TRENCELTA", "TRENHOTEL"},
}
SERVICE_NAMES = {
    "cercanias": "Cercanías / Rodalies",
    "high-speed": "High speed",
    "long-distance": "Long distance",
    "regional": "Regional / medium distance",
}


def ld_service(product: str) -> str:
    p = product.upper()
    return next((s for s, names in LD_SERVICES.items() if p in names), "regional")


def _rows(zf: zipfile.ZipFile, name: str):
    with zf.open(name) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        header = [h.strip() for h in next(reader)]
        for row in reader:
            yield dict(zip(header, (v.strip() for v in row)))


def hex_color(value: str | None, default: str) -> str:
    """'#RRGGBB' from a GTFS color field; anything else gets the default.

    The client writes route colors into inline styles, so only a plain hex color gets through.
    """
    return "#" + (value if value and re.fullmatch(r"[0-9A-Fa-f]{6}", value) else default)


def gtfs_seconds(hms: str) -> int:
    """GTFS times can exceed 24:00:00 for trips running past midnight."""
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


@dataclass
class StaticGTFS:
    kind: str = "cercanias"
    loaded_at: float = 0.0
    service_date: date | None = None
    stops: dict[str, dict] = field(default_factory=dict)
    routes: dict[str, dict] = field(default_factory=dict)
    trips: dict[str, dict] = field(default_factory=dict)
    # trip_id -> [(stop_id, arrival_s, departure_s)] for active trips only
    stop_times: dict[str, list[tuple[str, int, int]]] = field(default_factory=dict)
    # stop_id -> [(arrival_s, trip_id)] sorted, for station boards
    stop_index: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    # trip_id -> service date midnight (epoch seconds) the times are relative to
    trip_base: dict[str, int] = field(default_factory=dict)
    shapes_geojson: dict = field(default_factory=dict)
    stops_geojson: dict = field(default_factory=dict)

    def nucleo_of(self, route_id: str) -> str:
        if self.kind != "cercanias":
            return ""
        return NUCLEOS.get(route_id[:2], route_id[:2])


def _download(url: str, dest: Path) -> None:
    log.info("Downloading static GTFS from %s", url)
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "trainradar/0.1 (+https://trainradar.noprettycolors.com)"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)


def _active_services(zf: zipfile.ZipFile, day: date) -> set[str]:
    wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    ymd = day.strftime("%Y%m%d")
    active = {
        r["service_id"]
        for r in _rows(zf, "calendar.txt")
        if r["start_date"] <= ymd <= r["end_date"] and r[wd] == "1"
    }
    if "calendar_dates.txt" in zf.namelist():
        for r in _rows(zf, "calendar_dates.txt"):
            if r["date"] == ymd:
                (active.add if r["exception_type"] == "1" else active.discard)(r["service_id"])
    return active


def _midnight(day: date) -> int:
    # GTFS times count from "noon minus 12h", which equals local midnight except on DST days.
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=TZ)
    return int(noon.timestamp()) - 12 * 3600


def load(data_dir: Path, kind: str = "cercanias") -> StaticGTFS:
    data_dir.mkdir(parents=True, exist_ok=True)
    url, fname = FEEDS[kind]
    zpath = data_dir / fname
    if not zpath.exists() or time.time() - zpath.stat().st_mtime > MAX_AGE_S:
        try:
            _download(url, zpath)
        except Exception:
            if not zpath.exists():
                raise
            log.exception("GTFS download failed; using cached copy")

    t0 = time.time()
    g = StaticGTFS(kind=kind, loaded_at=time.time())
    today = datetime.now(TZ).date()
    yesterday = today - timedelta(days=1)
    g.service_date = today

    with zipfile.ZipFile(zpath) as zf:
        for r in _rows(zf, "stops.txt"):
            g.stops[r["stop_id"]] = {
                "id": r["stop_id"],
                "name": r["stop_name"],
                "lat": float(r["stop_lat"]),
                "lon": float(r["stop_lon"]),
            }
        for r in _rows(zf, "routes.txt"):
            route = {
                "id": r["route_id"],
                "short": r["route_short_name"],
                "long": " ".join(r["route_long_name"].split()),
                "color": hex_color(r.get("route_color"), "888888"),
                "text": hex_color(r.get("route_text_color"), "FFFFFF"),
                "nucleo": g.nucleo_of(r["route_id"]),
                "service": "cercanias" if kind == "cercanias" else ld_service(r["route_short_name"]),
            }
            if kind != "cercanias":
                # The AV/LD/MD feed gives every route the same off-white; the client colours by service.
                route["color"] = route["text"] = ""
            g.routes[r["route_id"]] = route

        svc_today = _active_services(zf, today)
        svc_yday = _active_services(zf, yesterday)
        base_today, base_yday = _midnight(today), _midnight(yesterday)

        shape_color: dict[str, tuple[str, str, str]] = {}
        for r in _rows(zf, "trips.txt"):
            route = g.routes.get(r["route_id"], {})
            if r.get("shape_id") and r["shape_id"] not in shape_color:
                shape_color[r["shape_id"]] = (route.get("color", "#888"), route.get("short", ""), route.get("nucleo", ""))
            sid = r["service_id"]
            if sid in svc_today:
                g.trip_base[r["trip_id"]] = base_today
            elif sid in svc_yday:
                g.trip_base[r["trip_id"]] = base_yday
            else:
                continue
            g.trips[r["trip_id"]] = {
                "id": r["trip_id"],
                "route_id": r["route_id"],
                "shape_id": r.get("shape_id", ""),
                "block_id": r.get("block_id", ""),
            }

        for r in _rows(zf, "stop_times.txt"):
            tid = r["trip_id"]
            if tid not in g.trips:
                continue
            g.stop_times.setdefault(tid, []).append(
                (int(r["stop_sequence"]), r["stop_id"], gtfs_seconds(r["arrival_time"]), gtfs_seconds(r["departure_time"]))
            )

        for tid, rows in g.stop_times.items():
            rows.sort()
            g.stop_times[tid] = [(s, a, d) for _, s, a, d in rows]
            base = g.trip_base[tid]
            for stop_id, arr, _ in g.stop_times[tid]:
                g.stop_index.setdefault(stop_id, []).append((base + arr, tid))
        for lst in g.stop_index.values():
            lst.sort()

        shapes: dict[str, list[tuple[int, float, float]]] = {}
        for r in (_rows(zf, "shapes.txt") if "shapes.txt" in zf.namelist() else ()):
            shapes.setdefault(r["shape_id"], []).append(
                (int(r["shape_pt_sequence"]), round(float(r["shape_pt_lon"]), 5), round(float(r["shape_pt_lat"]), 5))
            )
        features = []
        for sid, pts in shapes.items():
            pts.sort()
            color, short, nucleo = shape_color.get(sid, ("#888888", "", ""))
            features.append({
                "type": "Feature",
                "properties": {"shape_id": sid, "color": color, "line": short, "nucleo": nucleo},
                "geometry": {"type": "LineString", "coordinates": [[x, y] for _, x, y in pts]},
            })
        g.shapes_geojson = {"type": "FeatureCollection", "features": features}

    served = set(g.stop_index)
    g.stops_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": s["id"], "name": s["name"], "kind": kind},
                "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
            }
            for s in g.stops.values()
            if s["id"] in served
        ],
    }
    log.info(
        "Static GTFS (%s) loaded in %.1fs: %d stops, %d active trips, %d shapes",
        kind, time.time() - t0, len(g.stops), len(g.trips), len(g.shapes_geojson["features"]),
    )
    return g
