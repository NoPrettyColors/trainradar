"""Catalogue of the open data behind the map, served to the client's data panel.

Each entry says who publishes the data, what it is, how often the publisher
updates it ("updates"), how often TrainRadar fetches it ("checks") and what
TrainRadar uses it for, so the app can teach what is openly available.
Text fields are given in every language the app speaks; `localise` picks one.
Live numbers (counts, last update, errors) are added by app.py.
"""

from __future__ import annotations

LANGS = ("en", "es", "ca")


def L(en: str, es: str, ca: str) -> dict:
    return {"en": en, "es": es, "ca": ca}


def localise(value, lang: str):
    """Resolve every L(...) in a catalogue entry to one language."""
    if isinstance(value, dict) and set(value) == set(LANGS):
        return value.get(lang) or value["en"]
    if isinstance(value, dict):
        return {k: localise(v, lang) for k, v in value.items()}
    if isinstance(value, list):
        return [localise(v, lang) for v in value]
    return value


RENFE = "Renfe (data.renfe.com)"
CC_BY = {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}
GTFS_RT = "GTFS Realtime"
GTFS_STATIC = L("GTFS (static)", "GTFS (estático)", "GTFS (estàtic)")
EVERY_20S = L("About every 20 seconds", "Cada 20 segundos aprox.", "Cada 20 segons aprox.")
FETCH_20S = L("Every 20 seconds", "Cada 20 segundos", "Cada 20 segons")
DAILY = L("Daily", "A diario", "Cada dia")
FETCH_DAILY = L(
    "Daily: downloaded again when over 24 hours old, reloaded after 03:00",
    "A diario: se descarga de nuevo si tiene más de 24 horas y se recarga después de las 03:00",
    "Cada dia: es torna a descarregar si té més de 24 hores i es recarrega després de les 03:00",
)

USED = [
    {
        "id": "vehicles",
        "name": L("Cercanías / Rodalies vehicle positions",
                  "Posiciones de los trenes de Cercanías / Rodalies",
                  "Posicions dels trens de Rodalies / Cercanías"),
        "publisher": RENFE,
        "format": L("GTFS Realtime (JSON and Protocol Buffers)",
                    "GTFS Realtime (JSON y Protocol Buffers)",
                    "GTFS Realtime (JSON i Protocol Buffers)"),
        "updates": EVERY_20S,
        "checks": FETCH_20S,
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/ubicacion-vehiculos",
        "feed": "https://gtfsrt.renfe.com/vehicle_positions.json",
        "use": L("Where each commuter train is, and the stop it is at or heading to.",
                 "Dónde está cada tren de cercanías y en qué parada está o hacia cuál va.",
                 "On és cada tren de rodalies i a quina parada és o cap a quina va."),
    },
    {
        "id": "trips",
        "name": L("Cercanías / Rodalies trip updates",
                  "Actualizaciones de viaje de Cercanías / Rodalies",
                  "Actualitzacions de viatge de Rodalies / Cercanías"),
        "publisher": RENFE,
        "format": GTFS_RT,
        "updates": EVERY_20S,
        "checks": FETCH_20S,
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-viaje-cercanias",
        "feed": "https://gtfsrt.renfe.com/trip_updates.json",
        "use": L("Delay of each commuter train, shown as the ring around its dot.",
                 "El retraso de cada tren de cercanías, que se ve en el anillo alrededor de su punto.",
                 "El retard de cada tren de rodalies, que es veu a l'anell al voltant del seu punt."),
    },
    {
        "id": "vehicles_ld",
        "name": L("High-speed, long and medium distance vehicle positions",
                  "Posiciones de alta velocidad, larga y media distancia",
                  "Posicions d'alta velocitat, llarga i mitjana distància"),
        "publisher": RENFE,
        "format": GTFS_RT,
        "updates": EVERY_20S,
        "checks": FETCH_20S,
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/posicion-vehiculos-av-ld-md",
        "feed": "https://gtfsrt.renfe.com/vehicle_positions_LD.json",
        "use": L("Where each AVE, Avlo, Alvia, Avant, Intercity and regional train is.",
                 "Dónde está cada AVE, Avlo, Alvia, Avant, Intercity y regional.",
                 "On és cada AVE, Avlo, Alvia, Avant, Intercity i regional."),
        "note": L("Its header timestamp runs an hour behind, so TrainRadar times it from the server's Last-Modified header.",
                  "Su marca de tiempo va una hora por detrás, así que TrainRadar usa la cabecera Last-Modified del servidor.",
                  "La seva marca de temps va una hora endarrerida, així que TrainRadar fa servir la capçalera Last-Modified del servidor."),
    },
    {
        "id": "trips_ld",
        "name": L("High-speed, long and medium distance trip updates",
                  "Actualizaciones de viaje de alta velocidad, larga y media distancia",
                  "Actualitzacions de viatge d'alta velocitat, llarga i mitjana distància"),
        "publisher": RENFE,
        "format": GTFS_RT,
        "updates": EVERY_20S,
        "checks": FETCH_20S,
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-viaje-alta-velocidad-larga-media-distancia",
        "feed": "https://gtfsrt.renfe.com/trip_updates_LD.json",
        "use": L("Delay of each long-distance and regional train.",
                 "El retraso de cada tren de larga distancia y regional.",
                 "El retard de cada tren de llarga distància i regional."),
    },
    {
        "id": "alerts",
        "name": L("Service alerts", "Avisos de servicio", "Avisos de servei"),
        "publisher": RENFE,
        "format": GTFS_RT,
        "updates": L("When Renfe publishes or withdraws a notice",
                     "Cuando Renfe publica o retira un aviso",
                     "Quan Renfe publica o retira un avís"),
        "checks": L("Every 2 minutes", "Cada 2 minutos", "Cada 2 minuts"),
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/incidencias-avisos",
        "feed": "https://gtfsrt.renfe.com/alerts.json",
        "use": L("The Alerts list. Today it only covers Cercanías and Rodalies lines, in Spanish only.",
                 "La lista de avisos. Por ahora solo cubre líneas de Cercanías y Rodalies, y solo en castellano.",
                 "La llista d'avisos. Ara només cobreix línies de Rodalies i Cercanías, i només en castellà."),
    },
    {
        "id": "gtfs_cercanias",
        "name": L("Cercanías / Rodalies timetables", "Horarios de Cercanías / Rodalies", "Horaris de Rodalies / Cercanías"),
        "publisher": RENFE,
        "format": GTFS_STATIC,
        "updates": DAILY,
        "checks": FETCH_DAILY,
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-cercanias",
        "feed": "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip",
        "use": L("Stations, lines, line colours and routes on the map, and the timetables behind trip and departure lists.",
                 "Estaciones, líneas, colores de línea y recorridos del mapa, y los horarios de los viajes y las salidas.",
                 "Estacions, línies, colors de línia i recorreguts del mapa, i els horaris dels viatges i les sortides."),
    },
    {
        "id": "gtfs_ld",
        "name": L("High-speed, long and medium distance timetables",
                  "Horarios de alta velocidad, larga y media distancia",
                  "Horaris d'alta velocitat, llarga i mitjana distància"),
        "publisher": RENFE,
        "format": GTFS_STATIC,
        "updates": DAILY,
        "checks": FETCH_DAILY,
        "licence": CC_BY,
        "page": "https://data.renfe.com/dataset/horarios-de-alta-velocidad-larga-distancia-y-media-distancia",
        "feed": "https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip",
        "use": L("Product names (AVE, Alvia, MD…), stations and timetables for long-distance trains. It has no route shapes.",
                 "Productos (AVE, Alvia, MD…), estaciones y horarios de los trenes de larga distancia. No incluye recorridos.",
                 "Productes (AVE, Alvia, MD…), estacions i horaris dels trens de llarga distància. No inclou recorreguts."),
    },
    {
        "id": "network",
        "name": L("Rail network (INSPIRE transport networks)",
                  "Red ferroviaria (redes de transporte INSPIRE)",
                  "Xarxa ferroviària (xarxes de transport INSPIRE)"),
        "publisher": "Instituto Geográfico Nacional (IGN)",
        "format": "OGC API Features (GeoJSON)",
        "updates": L("When IGN publishes a new version",
                     "Cuando el IGN publica una nueva versión",
                     "Quan l'IGN publica una nova versió"),
        "checks": L("Monthly: checked every 6 hours, downloaded again when over 30 days old",
                    "Mensual: se comprueba cada 6 horas y se descarga de nuevo si tiene más de 30 días",
                    "Mensual: es comprova cada 6 hores i es torna a descarregar si té més de 30 dies"),
        "licence": CC_BY,
        "page": "https://api-features.idee.es/collections/railwaylink",
        "feed": "https://api-features.idee.es/collections/railwaylink/items",
        "use": L("The track network drawn under the trains. IGN gives each link's gauge, not its speed: standard gauge (1,435 mm) is Spain's high-speed network, Iberian gauge (1,668 mm) the conventional one, metre gauge the FEVE and regional lines.",
                 "La red de vías bajo los trenes. El IGN da el ancho de cada tramo, no su velocidad: el ancho estándar (1.435 mm) es la red de alta velocidad de España, el ancho ibérico (1.668 mm) la convencional y el ancho métrico las líneas de FEVE y regionales.",
                 "La xarxa de vies sota els trens. L'IGN dona l'ample de cada tram, no la velocitat: l'ample estàndard (1.435 mm) és la xarxa d'alta velocitat d'Espanya, l'ample ibèric (1.668 mm) la convencional i l'ample mètric les línies de FEVE i regionals."),
        "note": L("Gauge is a close but imperfect stand-in for speed: a few fast lines are Iberian gauge (parts of the Atlantic Axis, Madrid–Extremadura) and show as conventional. About 40% of links have no gauge at all, mostly sidings and yards; turn on Other track to see them.",
                  "El ancho es una aproximación buena pero imperfecta de la velocidad: algunas líneas rápidas son de ancho ibérico (partes del Eje Atlántico, Madrid–Extremadura) y aparecen como convencionales. Alrededor del 40 % de los tramos no tiene ancho, sobre todo apartaderos y playas de vías; activa «Otras vías» para verlos.",
                  "L'ample és una aproximació bona però imperfecta de la velocitat: algunes línies ràpides són d'ample ibèric (parts de l'Eix Atlàntic, Madrid–Extremadura) i surten com a convencionals. Al voltant del 40 % dels trams no té ample, sobretot apartadors i platges de vies; activa «Altres vies» per veure'ls."),
    },
    {
        "id": "basemap",
        "name": L("Basemap", "Mapa base", "Mapa base"),
        "publisher": L("OpenFreeMap, with OpenStreetMap data",
                       "OpenFreeMap, con datos de OpenStreetMap",
                       "OpenFreeMap, amb dades d'OpenStreetMap"),
        "format": L("Vector tiles", "Teselas vectoriales", "Tessel·les vectorials"),
        "updates": L("Weekly", "Semanal", "Setmanal"),
        "checks": L("Your browser loads the map tiles from OpenFreeMap directly",
                    "Tu navegador carga las teselas directamente de OpenFreeMap",
                    "El teu navegador carrega les tessel·les directament d'OpenFreeMap"),
        "licence": {"name": L("ODbL (data)", "ODbL (datos)", "ODbL (dades)"), "url": "https://www.openstreetmap.org/copyright"},
        "page": "https://openfreemap.org",
        "use": L("Land, sea, roads and place names.", "Tierra, mar, carreteras y topónimos.", "Terra, mar, carreteres i topònims."),
    },
]

# Open datasets TrainRadar doesn't draw (yet), listed so people know they exist.
MORE = [
    {"name": L("All Renfe stations, with addresses and services",
               "Todas las estaciones de Renfe, con dirección y servicios",
               "Totes les estacions de Renfe, amb adreça i serveis"),
     "publisher": RENFE, "page": "https://data.renfe.com/dataset/estaciones-listado-completo"},
    {"name": L("Passengers per hour band at Cercanías stations",
               "Viajeros por franja horaria en estaciones de Cercanías",
               "Viatgers per franja horària a les estacions de Rodalies"),
     "publisher": RENFE, "page": "https://data.renfe.com/dataset/volumen-de-viajeros-por-franja-horaria-estaciones-de-cercanias"},
    {"name": L("Fleet: Renfe's train models and their specifications",
               "Flota: modelos de tren de Renfe y sus características",
               "Flota: models de tren de Renfe i les seves característiques"),
     "publisher": RENFE, "page": "https://data.renfe.com/dataset/fichas-nuestros-trenes"},
    {"name": L("Punctuality commitment and compensation for delays",
               "Compromiso de puntualidad e indemnizaciones por retraso",
               "Compromís de puntualitat i indemnitzacions per retard"),
     "publisher": RENFE, "page": "https://data.renfe.com/dataset/compromiso-puntualidad"},
    {"name": L("FEVE (metre gauge) stations", "Estaciones de FEVE (ancho métrico)", "Estacions de FEVE (ample mètric)"),
     "publisher": RENFE, "page": "https://data.renfe.com/dataset/listado-estaciones-feve"},
    {"name": L("Adif rail infrastructure (WFS/WMS)",
               "Infraestructura ferroviaria de Adif (WFS/WMS)",
               "Infraestructura ferroviària d'Adif (WFS/WMS)"),
     "publisher": "Adif", "page": "https://datos.gob.es/es/catalogo/e0dat0002-red-de-transporte-ferroviario-de-adif1"},
    {"name": L("National Access Point for multimodal transport (other operators' GTFS)",
               "Punto de Acceso Nacional de transporte multimodal (GTFS de otros operadores)",
               "Punt d'Accés Nacional de transport multimodal (GTFS d'altres operadors)"),
     "publisher": "Ministerio de Transportes", "page": "https://nap.transportes.gob.es"},
]
