# TrainRadar

Live map of Renfe trains across Spain, from AVE high-speed services to Cercanías and Rodalies, drawn over the national rail network and built only on open data. It also explains each data source, so people can see what is openly available. The interface is in Catalan, Spanish and English (Spanish by default; `?lang=ca`, `es` or `en` picks one, and a visitor's choice is remembered). It runs at **https://trainradar.noprettycolors.com**.

It's a personal side project. Its interface also serves as a real-world test of the [Brokkr](https://brokkr.noprettycolors.com) design system, and the gaps it finds go back into Brokkr.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin/python elsewhere
.venv/Scripts/python -m server.app --port 8000
```

Open http://127.0.0.1:8000. The first start downloads both static GTFS feeds (~17 MB) into `data/`, or into `$TRAINRADAR_DATA` if that's set; they are refreshed when older than 24 h and reloaded after the service day changes. The rail network (~1 MB gzipped, about 5 minutes to fetch from IGN) downloads in the background on first start and is refreshed monthly; the map adds it when it's ready.

## Data sources

All of it is open data under CC BY 4.0 unless noted. The app's **Open data** panel lists the same sources with live figures.

| Source | URL | Used for |
|---|---|---|
| Renfe GTFS‑RT, Cercanías vehicle positions | `https://gtfsrt.renfe.com/vehicle_positions.json` | Commuter train positions and current or next stop (polled every 20 s) |
| Renfe GTFS‑RT, Cercanías trip updates | `https://gtfsrt.renfe.com/trip_updates.json` | Commuter train delays |
| Renfe GTFS‑RT, AV/LD/MD vehicle positions | `https://gtfsrt.renfe.com/vehicle_positions_LD.json` | High-speed, long-distance and regional train positions |
| Renfe GTFS‑RT, AV/LD/MD trip updates | `https://gtfsrt.renfe.com/trip_updates_LD.json` | Their delays |
| Renfe GTFS‑RT alerts | `https://gtfsrt.renfe.com/alerts.json` | Service alerts, Cercanías only (polled every 2 min) |
| Renfe static GTFS, Cercanías | `https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip` | Stations, lines and colours, shapes, timetables |
| Renfe static GTFS, AV/LD/MD | `https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip` | Products (AVE, Alvia, MD…), stations, timetables |
| IGN INSPIRE rail links (OGC API Features) | `https://api-features.idee.es/collections/railwaylink` | The track network, classed by gauge |

The basemap is OpenFreeMap (OpenStreetMap data, ODbL). The núcleo is the first two digits of a Cercanías `route_id` (see `NUCLEOS` in `server/static_gtfs.py`). Long-distance products are grouped into high speed, long distance and regional in `LD_SERVICES`. The catalogue shown in the app lives in `server/sources.py`.

## Architecture

```
server/static_gtfs.py   download + index both static GTFS feeds (only today's/yesterday's trips are kept)
server/realtime.py      poller thread → normalised train snapshot from both GTFS-RT families
server/network.py       IGN rail network: paged download, simplification, monthly refresh
server/sources.py       catalogue of open data sources for the Open data panel
server/app.py           stdlib HTTP server: JSON API + SSE + static files
server/errors.py        fixed public labels for upstream errors
web/                    MapLibre GL client in the Brokkr 1.1.0 app shell (no build step)
```

All clients share a single upstream poll, so traffic to Renfe stays the same however many viewers there are.

### API

| Endpoint | Returns |
|---|---|
| `GET /api/trains` | Current snapshot: `{version, feed_ts, trains:[…]}` |
| `GET /api/stream` | Server‑Sent Events, sending a `trains` event per new snapshot; 503 with `Retry-After` when the stream limit is reached |
| `GET /api/trip/{trip_id}` | Line, delay and stop list with scheduled and expected times |
| `GET /api/stop/{stop_id}` | Next departures (90 min) with delays, all services |
| `GET /api/alerts?nucleo=` | Active alerts |
| `GET /api/shapes`, `/api/stops`, `/api/nucleos` | Cercanías line shapes, all stations, núcleo bounding boxes |
| `GET /api/network` | Rail network GeoJSON (`net`: high-speed, conventional, metre, other); 503 while downloading |
| `GET /api/sources` | Data catalogue with live figures per source |
| `GET /api/status` | Feed health and trains per service |

Feed errors in `/api/sources` and `/api/status` are short labels (`timeout`, `HTTP 503`, `connection failed`, `bad data`); the full error is in the app log. Methods other than `GET` and `HEAD` get `405`.

Each open stream holds a server thread, so the app caps them: 500 in total and 50 per client address (`CF-Connecting-IP` behind Cloudflare). Change the caps with `--max-streams` and `--max-streams-per-ip`, or `$TRAINRADAR_MAX_STREAMS` and `$TRAINRADAR_MAX_STREAMS_PER_IP`. A refused browser tries again after 30 to 60 seconds.

## Deployment

The maintainer deploys `main` to production. Contributors never need access to the server.

## Known limits

- Renfe trains only. Other operators (Ouigo, Iryo, FGC, Euskotren…) aren't shown yet; open feeds for some of them are listed on the National Access Point.
- The rail network is classed by gauge, IGN's only relevant attribute: a few fast Iberian-gauge lines show as conventional, and about 40% of links have no gauge.
- The long-distance GTFS has no route shapes, so those trains have no line drawn of their own; they sit on the IGN network.
- Expected times apply the trip's current delay to all remaining stops, which is a simple estimate.
- A few Renfe shapes have gaps that draw as straight segments.
- Alerts have no end date in the feed, so some old notices stay "active".

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) for the process. Keep the server dependency-free beyond `tzdata`, take UI values from Brokkr tokens, and never commit server addresses, keys, certificates or tokens.

## License

[MIT](LICENSE). Bundled and runtime third-party components are listed in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). TrainRadar is not affiliated with Renfe.
