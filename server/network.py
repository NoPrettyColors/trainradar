"""Spain's rail network from IGN's INSPIRE transport networks (OGC API Features).

IGN publishes every railway link with its gauge but no speed class. In Spain
the gauge tells the networks apart: the high-speed lines are standard gauge
(1,435 mm), the conventional network is Iberian gauge (1,668 mm) and FEVE and
regional lines are metre gauge. Links are downloaded page by page, simplified
and cached as gzipped GeoJSON, refreshed monthly in the background.
"""

from __future__ import annotations

import gzip
import json
import logging
import threading
import time
import urllib.request
from pathlib import Path

from . import errors

log = logging.getLogger(__name__)

API = "https://api-features.idee.es/collections/railwaylink/items"
PAGE = 1000
MAX_AGE_S = 30 * 24 * 3600
TOLERANCE = 0.0002  # degrees, about 20 m: invisible at the zooms the layer is drawn
UA = "trainradar/0.1 (+https://trainradar.noprettycolors.com)"

# INSPIRE gauge category, or the gauge in mm when the category is missing -> network class.
# Links with neither (about half of them, mostly sidings and yard tracks) are "other".
CATEGORIES = {"standard": "high-speed", "broad": "conventional", "narrow": "metre"}
GAUGES = {1435: "high-speed", 1668: "conventional", 1000: "metre"}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError("unreachable")


def _simplify(pts: list[list[float]], tol: float) -> list[list[float]]:
    """Douglas-Peucker, iterative so long lines can't hit the recursion limit."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
        far, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > far:
                far, idx = d, i
        if far > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def _classify(props: dict) -> str:
    return CATEGORIES.get(props.get("nominalgaugecategory")) or GAUGES.get(props.get("nominalgauge"), "other")


def download() -> dict:
    features, offset, total, t0 = [], 0, None, time.time()
    while total is None or offset < total:
        page = _get(f"{API}?f=json&limit={PAGE}&offset={offset}")
        total = page.get("numberMatched") or 0
        for f in page.get("features", []):
            g = f.get("geometry") or {}
            if g.get("type") != "LineString":
                continue
            coords = _simplify([[round(x, 5), round(y, 5)] for x, y, *_ in g["coordinates"]], TOLERANCE)
            p = f.get("properties") or {}
            features.append({
                "type": "Feature",
                "properties": {"net": _classify(p), "tracks": p.get("numberoftracks"),
                               "electrified": p.get("electrified") == "true"},
                "geometry": {"type": "LineString", "coordinates": coords},
            })
        offset += PAGE
        if not page.get("features"):
            break
    log.info("Rail network downloaded in %.0fs: %d links", time.time() - t0, len(features))
    return {"type": "FeatureCollection", "features": features}


class Network:
    """Serves the cached network; downloads it in the background when missing or old."""

    def __init__(self, data_dir: Path):
        self.path = data_dir / "network.geojson.gz"
        self.gz: bytes | None = None
        self.stats: dict = {}
        self.error: str | None = None
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        self.gz = self.path.read_bytes()
        counts: dict[str, int] = {}
        for f in json.loads(gzip.decompress(self.gz))["features"]:
            counts[f["properties"]["net"]] = counts.get(f["properties"]["net"], 0) + 1
        self.stats = {"links": sum(counts.values()), "by_network": counts,
                      "updated_at": int(self.path.stat().st_mtime)}

    def _refresh(self) -> None:
        try:
            data = download()
            tmp = self.path.with_suffix(".part")
            tmp.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode()))
            tmp.replace(self.path)
            self._load()
            self.error = None
        except Exception as e:
            self.error = errors.label(e)
            log.exception("Rail network download failed")

    def start(self) -> None:
        def loop():
            while True:
                if not self.path.exists() or time.time() - self.path.stat().st_mtime > MAX_AGE_S:
                    self._refresh()
                time.sleep(6 * 3600)
        threading.Thread(target=loop, name="network", daemon=True).start()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    n = Network(Path(sys.argv[1] if len(sys.argv) > 1 else "data"))
    n._refresh()
    print(n.stats, len(n.gz or b""), "bytes gzipped", n.error)
