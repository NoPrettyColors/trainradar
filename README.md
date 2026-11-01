# TrainRadar

Live map of every Renfe commuter train in Spain (all 15 *núcleos*, Rodalies de Catalunya included), built only on Renfe's official open data. It runs at **https://trainradar.noprettycolors.com**.

It's a personal side project. Its interface also serves as a real-world test of the [Brokkr](https://brokkr.noprettycolors.com) design system, with gaps logged in [docs/BROKKR-FINDINGS.md](docs/BROKKR-FINDINGS.md).

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin/python elsewhere
.venv/Scripts/python -m server.app --port 8000
```

Open http://127.0.0.1:8000. The first start downloads the static GTFS (~16 MB) into `data/`, or into `$TRAINRADAR_DATA` if that's set. It is refreshed when older than 24 h and reloaded after the service day changes.

## Data sources

| Feed | URL | Used for |
|---|---|---|
| GTFS‑RT vehicle positions | `https://gtfsrt.renfe.com/vehicle_positions.json` | Train positions and current or next stop (polled every 20 s) |
| GTFS‑RT trip updates | `https://gtfsrt.renfe.com/trip_updates.json` | Delay per trip |
| GTFS‑RT alerts | `https://gtfsrt.renfe.com/alerts.json` | Service alerts (polled every 2 min) |
| Static GTFS | `https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip` | Stops, lines and colours, shapes, timetables |

The basemap is OpenFreeMap (OpenStreetMap data). The núcleo is the first two digits of `route_id` (see `NUCLEOS` in `server/static_gtfs.py`).

## Architecture

```
server/static_gtfs.py   download + index static GTFS (only today's/yesterday's trips are kept)
server/realtime.py      poller thread → normalised train snapshot
server/app.py           stdlib HTTP server: JSON API + SSE + static files
web/                    MapLibre GL client on Brokkr 1.0.3 tokens (no build step)
```

All clients share a single upstream poll, so traffic to Renfe stays the same however many viewers there are.

### API

| Endpoint | Returns |
|---|---|
| `GET /api/trains` | Current snapshot: `{version, feed_ts, trains:[…]}` |
| `GET /api/stream` | Server‑Sent Events, sending a `trains` event per new snapshot |
| `GET /api/trip/{trip_id}` | Line, delay and stop list with scheduled and expected times |
| `GET /api/stop/{stop_id}` | Next departures (90 min) with delays |
| `GET /api/alerts?nucleo=` | Active alerts |
| `GET /api/shapes`, `/api/stops`, `/api/nucleos` | GeoJSON layers and network bounding boxes |
| `GET /api/status` | Feed health |

## Deployment

The maintainer deploys `main` to production. Contributors never need access to the server.

## Known limits

- Only Cercanías and Rodalies. Renfe has no open realtime feed for AVE, Larga Distancia or Media Distancia; its long-distance web viewer is undocumented and isn't used here.
- Expected times apply the trip's current delay to all remaining stops, which is a simple estimate.
- A few Renfe shapes have gaps that draw as straight segments.
- Alerts have no end date in the feed, so some old notices stay "active".

## Contributing

Issues and pull requests are welcome. Keep the server dependency-free beyond `tzdata`, take UI values from Brokkr tokens, and never commit server addresses, keys, certificates or tokens.

## License

[MIT](LICENSE). Bundled and runtime third-party components are listed in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). TrainRadar is not affiliated with Renfe.
