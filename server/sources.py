"""Catalogue of the open data behind the map, served to the client's data panel.

Each entry says who publishes the data, what it is, how often the publisher
updates it ("updates"), how often TrainRadar fetches it ("checks") and what
TrainRadar uses it for, so the app can teach what is openly available.
Live numbers (counts, last update, errors) are added by app.py.
"""

from __future__ import annotations

RENFE = "Renfe (data.renfe.com)"
CC_BY = {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}

USED = [
    {
        "id": "vehicles",
        "name": "Cercanías / Rodalies vehicle positions",
        "publisher": RENFE,
        "format": "GTFS Realtime (JSON and Protocol Buffers)",
        "updates": "About every 20 seconds",
        "checks": "Every 20 seconds",
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/ubicacion-vehiculos",
        "feed": "https://gtfsrt.renfe.com/vehicle_positions.json",
        "use": "Where each commuter train is, and the stop it is at or heading to.",
    },
    {
        "id": "trips",
        "name": "Cercanías / Rodalies trip updates",
        "publisher": RENFE,
        "format": "GTFS Realtime",
        "updates": "About every 20 seconds",
        "checks": "Every 20 seconds",
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-viaje-cercanias",
        "feed": "https://gtfsrt.renfe.com/trip_updates.json",
        "use": "Delay of each commuter train, shown as the ring around its dot.",
    },
    {
        "id": "vehicles_ld",
        "name": "High-speed, long and medium distance vehicle positions",
        "publisher": RENFE,
        "format": "GTFS Realtime",
        "updates": "About every 20 seconds",
        "checks": "Every 20 seconds",
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/posicion-vehiculos-av-ld-md",
        "feed": "https://gtfsrt.renfe.com/vehicle_positions_LD.json",
        "use": "Where each AVE, Avlo, Alvia, Avant, Intercity and regional train is.",
        "note": "Its header timestamp runs an hour behind, so TrainRadar times it from the server's Last-Modified header.",
    },
    {
        "id": "trips_ld",
        "name": "High-speed, long and medium distance trip updates",
        "publisher": RENFE,
        "format": "GTFS Realtime",
        "updates": "About every 20 seconds",
        "checks": "Every 20 seconds",
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-viaje-alta-velocidad-larga-media-distancia",
        "feed": "https://gtfsrt.renfe.com/trip_updates_LD.json",
        "use": "Delay of each long-distance and regional train.",
    },
    {
        "id": "alerts",
        "name": "Service alerts",
        "publisher": RENFE,
        "format": "GTFS Realtime",
        "updates": "When Renfe publishes or withdraws a notice",
        "checks": "Every 2 minutes",
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/incidencias-avisos",
        "feed": "https://gtfsrt.renfe.com/alerts.json",
        "use": "The Alerts list. Today it only covers Cercanías and Rodalies lines.",
    },
    {
        "id": "gtfs_cercanias",
        "name": "Cercanías / Rodalies timetables",
        "publisher": RENFE,
        "format": "GTFS (static)",
        "updates": "Daily",
        "checks": "Daily: downloaded again when over 24 hours old, reloaded after 03:00",
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-cercanias",
        "feed": "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip",
        "use": "Stations, lines, line colours and routes on the map, and the timetables behind trip and departure lists.",
    },
    {
        "id": "gtfs_ld",
        "name": "High-speed, long and medium distance timetables",
        "publisher": RENFE,
        "format": "GTFS (static)",
        "updates": "Daily",
        "checks": "Daily: downloaded again when over 24 hours old, reloaded after 03:00",
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-de-alta-velocidad-larga-distancia-y-media-distancia",
        "feed": "https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip",
        "use": "Product names (AVE, Alvia, MD…), stations and timetables for long-distance trains. It has no route shapes.",
    },
    {
        "id": "network",
        "name": "Rail network (INSPIRE transport networks)",
        "publisher": "Instituto Geográfico Nacional (IGN)",
        "format": "OGC API Features (GeoJSON)",
        "updates": "When IGN publishes a new version",
        "checks": "Monthly: checked every 6 hours, downloaded again when over 30 days old",
        "licence": CC_BY,
        "page": "https://api-features.idee.es/collections/railwaylink",
        "feed": "https://api-features.idee.es/collections/railwaylink/items",
        "use": "The track network drawn under the trains. IGN gives each link's gauge, not its speed: standard gauge (1,435 mm) is Spain's high-speed network, Iberian gauge (1,668 mm) the conventional one, metre gauge the FEVE and regional lines.",
        "note": "Gauge is a close but imperfect stand-in for speed: a few fast lines are Iberian gauge (parts of the Atlantic Axis, Madrid–Extremadura) and show as conventional. About 40% of links have no gauge at all, mostly sidings and yards; turn on Other track to see them.",
    },
    {
        "id": "basemap",
        "name": "Basemap",
        "publisher": "OpenFreeMap, with OpenStreetMap data",
        "format": "Vector tiles",
        "updates": "Weekly",
        "checks": "Your browser loads the map tiles from OpenFreeMap directly",
        "licence": {"name": "ODbL (data)", "url": "https://www.openstreetmap.org/copyright"},
        "page": "https://openfreemap.org",
        "use": "Land, sea, roads and place names.",
    },
]

# Open datasets TrainRadar doesn't draw (yet), listed so people know they exist.
MORE = [
    {"name": "All Renfe stations, with addresses and services", "publisher": RENFE,
     "page": "https://data.renfe.com/dataset/estaciones-listado-completo"},
    {"name": "Passengers per hour band at Cercanías stations", "publisher": RENFE,
     "page": "https://data.renfe.com/dataset/volumen-de-viajeros-por-franja-horaria-estaciones-de-cercanias"},
    {"name": "Fleet: Renfe's train models and their specifications", "publisher": RENFE,
     "page": "https://data.renfe.com/dataset/fichas-nuestros-trenes"},
    {"name": "Punctuality commitment and compensation for delays", "publisher": RENFE,
     "page": "https://data.renfe.com/dataset/compromiso-puntualidad"},
    {"name": "FEVE (metre gauge) stations", "publisher": RENFE,
     "page": "https://data.renfe.com/dataset/listado-estaciones-feve"},
    {"name": "Adif rail infrastructure (WFS/WMS)", "publisher": "Adif",
     "page": "https://datos.gob.es/es/catalogo/e0dat0002-red-de-transporte-ferroviario-de-adif1"},
    {"name": "National Access Point for multimodal transport (other operators' GTFS)", "publisher": "Ministerio de Transportes",
     "page": "https://nap.transportes.gob.es"},
]
