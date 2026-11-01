"use strict";

const TRAIN_OLD_S = 300; // a vehicle report older than this is drawn faded
const ANIM_MS = 1500;
const THEME_KEY = "trainradar-theme";
const SERVICE_NAMES = {
  "high-speed": "High speed",
  "long-distance": "Long distance",
  regional: "Regional / medium distance",
  cercanias: "Cercanías / Rodalies",
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Madrid" });
const hhmm = (epoch) => timeFmt.format(new Date(epoch * 1000));
const fmtInt = new Intl.NumberFormat("en-GB");

function delayClass(d) {
  if (d == null) return "none";
  if (d <= 60) return "positive";
  if (d <= 300) return "caution";
  return "risk";
}
function delayText(d) {
  if (d == null) return "No live data";
  if (d <= 60) return "On time";
  return `+${Math.round(d / 60)} min`;
}
function ago(epoch) {
  if (!epoch) return "never";
  const s = Math.max(0, Math.round(Date.now() / 1000 - epoch));
  if (s < 90) return `${s} s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

const state = {
  snapshot: null,
  shown: new Map(), // id -> [lon, lat] currently drawn
  shapes: null,
  stopsGeo: null,
  network: null,
  stops: [],        // [{id, name, lon, lat}]
  nucleos: [],
  lines: new Map(), // nucleo -> Set(line)
  filter: { service: "", nucleo: "", line: "" },
  selected: null,   // {type: "train"|"stop"|"alerts"|"data", id}
  alerts: [],
};

// ---------------------------------------------------------------- theme

function theme() {
  return document.documentElement.dataset.theme
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

// MapLibre paint properties need literal colors, so read Brokkr's tokens from the cascade.
function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function palette() {
  return {
    positive: token("--npc-color-status-positive-mark"),
    caution: token("--npc-color-status-caution-mark"),
    risk: token("--npc-color-status-risk-mark"),
    none: token("--npc-color-status-neutral-mark"),
    text: token("--npc-color-text-default"),
    subtle: token("--npc-color-text-subtle"),
    page: token("--npc-color-surface-page"),
    raised: token("--npc-color-surface-raised"),
    land: token("--app-map-land"),
    water: token("--app-map-water"),
    service: {
      "high-speed": token("--app-service-high-speed"),
      "long-distance": token("--app-service-long-distance"),
      regional: token("--app-service-regional"),
    },
    track: {
      "high-speed": token("--app-track-high-speed"),
      conventional: token("--app-track-conventional"),
      metre: token("--app-track-metre"),
      other: token("--app-track-other"),
    },
  };
}
const serviceColor = (service) => palette().service[service] || token("--npc-color-text-subtle");

// Finding 4: Brokkr has no basemap; OpenFreeMap's neutral styles are the closest match.
const basemap = () => `https://tiles.openfreemap.org/styles/${theme() === "dark" ? "dark" : "positron"}`;

function syncThemeButton() {
  const next = theme() === "dark" ? "light" : "dark";
  const btn = $("theme-btn");
  btn.setAttribute("aria-label", `Switch to ${next} mode`);
  btn.title = `Switch to ${next} mode`;
  btn.querySelector("use").setAttribute("href", `icons/sprite.svg#npc-icon-${next}`);
}

function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem(THEME_KEY, t); } catch {}
  syncThemeButton();
  map.setStyle(basemap(), { diff: false });
}

$("theme-btn").addEventListener("click", () => setTheme(theme() === "dark" ? "light" : "dark"));
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (document.documentElement.dataset.theme) return; // an explicit choice wins
  syncThemeButton();
  map.setStyle(basemap(), { diff: false });
});
syncThemeButton();

// ---------------------------------------------------------------- map setup

const map = new maplibregl.Map({
  container: "map",
  style: basemap(),
  center: [-3.7, 40.2],
  zoom: 5.2,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-left");
// MapLibre only tracks window resizes; the container can also change size on its own (header wrap, hidden pane).
new ResizeObserver(() => map.resize()).observe($("map"));

const staticData = Promise.all(
  ["/api/shapes", "/api/stops", "/api/nucleos"].map((u) => fetch(u).then((r) => r.json()))
).then(([shapes, stops, nucleos]) => {
  state.shapes = shapes;
  state.stopsGeo = stops;
  state.nucleos = nucleos;
  for (const f of shapes.features) {
    const { nucleo, line } = f.properties;
    if (!state.lines.has(nucleo)) state.lines.set(nucleo, new Set());
    if (line) state.lines.get(nucleo).add(line);
  }
  state.stops = stops.features.map((f) => ({ id: f.properties.id, name: f.properties.name, lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] }));
  fillNucleoSelect();
  readHash({ duration: 0 }); // jump, don't animate: the layout may still be settling
});

// The server downloads the rail network in the background on first start, so retry until it's there.
async function loadNetwork() {
  try {
    const r = await fetch("/api/network");
    if (r.ok) {
      state.network = await r.json();
      if (map.isStyleLoaded() || map.getSource("shapes")) addNetworkLayers();
      return;
    }
  } catch {}
  setTimeout(loadNetwork, 60000);
}
loadNetwork();

// "style.load" fires on first load and again after every setStyle (theme switch), which drops our layers.
map.on("style.load", async () => {
  tuneBasemap();
  await staticData;
  addLayers();
  addNetworkLayers();
  applyFilter();
  applyVisibility();
  drawTrains();
  if (state.selected?.type === "train") map.setFilter("train-selected", ["==", ["get", "trip_id"], state.selected.id]);
});

// OpenFreeMap's dark style draws land and sea in nearly the same black. Use Brokkr surfaces so the coast reads.
function tuneBasemap() {
  if (theme() !== "dark") return;
  const c = palette();
  const style = map.getStyle();
  for (const l of style.layers) {
    if (l.type === "background") map.setPaintProperty(l.id, "background-color", c.land);
    else if (l.id === "water" && l.type === "fill") map.setPaintProperty(l.id, "fill-color", c.water);
    else if (l.id === "waterway" && l.type === "line") map.setPaintProperty(l.id, "line-color", c.water);
    // Its roads are near-black, made for a black background: on the lighter land they'd outshout the rail lines.
    else if (l["source-layer"] === "transportation" && l.type === "line") map.setPaintProperty(l.id, "line-opacity", 0.35);
  }
}

function addLayers() {
  const c = palette();
  map.addSource("shapes", { type: "geojson", data: state.shapes });
  map.addLayer({
    id: "shapes", type: "line", source: "shapes",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": ["get", "color"],
      "line-width": ["interpolate", ["linear"], ["zoom"], 5, 1.2, 10, 2.5, 14, 4],
      "line-opacity": 0.75,
    },
  });

  // Stations served by high-speed, long-distance or regional trains show from a regional view;
  // Cercanías-only stations appear once zoomed in further.
  const ld = ["!=", ["get", "kind"], "cercanias"];
  map.addSource("stops", { type: "geojson", data: state.stopsGeo });
  map.addLayer({
    id: "stops", type: "circle", source: "stops", minzoom: 6.5,
    filter: ["any", ld, [">=", ["zoom"], 9.5]],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 6.5, ["case", ld, 1.5, 0], 10, ["case", ld, 4, 2.5], 14, ["case", ld, 6, 5]],
      "circle-color": c.raised,
      "circle-stroke-color": c.text,
      "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 5, 0.8, 10, 1.2],
    },
  });
  map.addLayer({
    id: "stop-labels", type: "symbol", source: "stops", minzoom: 7,
    filter: ["any", ["all", ld, [">=", ["zoom"], 8.5]], [">=", ["zoom"], 12]],
    layout: {
      "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11,
      "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true,
      "symbol-sort-key": ["case", ld, 0, 1],
    },
    paint: { "text-color": c.subtle, "text-halo-color": c.page, "text-halo-width": 1.2 },
  });

  const fill = ["match", ["get", "service"],
    "high-speed", c.service["high-speed"], "long-distance", c.service["long-distance"], "regional", c.service.regional,
    ["get", "color"]];
  const isLd = ["!=", ["get", "service"], "cercanias"];
  map.addSource("trains", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "train-selected", type: "circle", source: "trains", filter: ["==", ["get", "id"], ""],
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 9, 10, 13, 14, 17], "circle-color": "transparent", "circle-stroke-color": c.text, "circle-stroke-width": 2 },
  });
  map.addLayer({
    id: "trains", type: "circle", source: "trains",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, ["case", isLd, 5, 4], 10, ["case", isLd, 8, 7], 14, ["case", isLd, 11, 10]],
      "circle-color": fill,
      "circle-stroke-color": ["match", ["get", "dclass"], "positive", c.positive, "caution", c.caution, "risk", c.risk, c.none],
      "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 5, 1.5, 10, 3],
      "circle-opacity": ["case", ["get", "old"], 0.4, 1],
      "circle-stroke-opacity": ["case", ["get", "old"], 0.4, 1],
    },
  });
  const label = (id, minzoom) => map.addLayer({
    id, type: "symbol", source: "trains", minzoom,
    layout: { "text-field": ["get", "line"], "text-font": ["Noto Sans Bold"], "text-size": 11, "text-offset": [1.2, 0], "text-anchor": "left", "text-allow-overlap": false },
    paint: { "text-color": c.text, "text-halo-color": c.page, "text-halo-width": 1.5 },
  });
  label("train-labels", 9);
  label("train-labels-ld", 6.5);
}

// Drawn bottom to top. Widths are [zoom 5, zoom 10, zoom 14].
const NETWORK_LAYERS = {
  "net-other": { net: "other", toggle: "show-other", width: [0.5, 1, 1.5], opacity: 0.6 },
  "net-conventional": { net: "conventional", toggle: "show-conventional", width: [0.9, 1.8, 2.5], opacity: 0.8 },
  "net-metre": { net: "metre", toggle: "show-metre", width: [0.9, 1.8, 2.5], opacity: 0.8, dash: [2, 1.5] },
  "net-hs": { net: "high-speed", toggle: "show-hs", width: [1.6, 3, 4], opacity: 0.9 },
};

function addNetworkLayers() {
  if (!state.network || !map.getSource("shapes") || map.getSource("network")) return;
  const c = palette();
  map.addSource("network", { type: "geojson", data: state.network });
  for (const [id, l] of Object.entries(NETWORK_LAYERS)) {
    map.addLayer({
      id, type: "line", source: "network",
      filter: ["==", ["get", "net"], l.net],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": c.track[l.net],
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, l.width[0], 10, l.width[1], 14, l.width[2]],
        "line-opacity": l.opacity,
        ...(l.dash ? { "line-dasharray": l.dash } : {}),
      },
    }, "shapes"); // under the Cercanías lines, stations and trains
  }
  applyVisibility();
}

function applyVisibility() {
  const vis = (on) => (on ? "visible" : "none");
  for (const [id, { toggle }] of Object.entries(NETWORK_LAYERS)) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis($(toggle).checked));
  }
  for (const id of ["stops", "stop-labels"]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis($("show-stations").checked));
  }
}
for (const id of ["show-hs", "show-conventional", "show-metre", "show-other", "show-stations"]) $(id).addEventListener("change", applyVisibility);
// The legend and MapLibre's attribution cover too much of a phone screen to start open.
if (matchMedia("(max-width: 600px)").matches) {
  $("legend").open = false;
  const fold = () => document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
  map.once("load", () => setTimeout(fold, 0));
}

// Layer events are bound to layer ids, so they survive setStyle.
map.on("click", "trains", (e) => select({ type: "train", id: e.features[0].properties.trip_id }));
map.on("click", "stops", (e) => {
  if (map.queryRenderedFeatures(e.point, { layers: ["trains"] }).length) return;
  select({ type: "stop", id: e.features[0].properties.id });
});
for (const l of ["trains", "stops"]) {
  map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
}

// Live data doesn't wait for the basemap: "load" only fires once tiles have rendered.
connect();
loadAlerts();
setInterval(loadAlerts, 120000);

// ---------------------------------------------------------------- filters

function fillNucleoSelect() {
  const sel = $("nucleo");
  for (const n of state.nucleos) sel.add(new Option(n.name, n.name));
}

function fillLineSelect() {
  const sel = $("line");
  sel.length = 1;
  const n = state.filter.nucleo;
  if (!n) { sel.disabled = true; return; }
  sel.disabled = false;
  const lines = [...(state.lines.get(n) || [])].sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
  for (const l of lines) sel.add(new Option(l, l));
  sel.value = state.filter.line;
}

// The service filter applies to every train. A núcleo (and line) narrows Cercanías trains only,
// so long-distance trains through that city stay on the map unless a single line is picked.
function trainFilter() {
  const { service, nucleo, line } = state.filter;
  const f = ["all"];
  if (service) f.push(["==", ["get", "service"], service]);
  if (line) f.push(["==", ["get", "nucleo"], nucleo], ["==", ["get", "line"], line]);
  else if (nucleo) f.push(["any", ["!=", ["get", "service"], "cercanias"], ["==", ["get", "nucleo"], nucleo]]);
  return f;
}
function trainMatches(t) {
  const { service, nucleo, line } = state.filter;
  if (service && t.service !== service) return false;
  if (line) return t.nucleo === nucleo && t.line === line;
  return !nucleo || t.service !== "cercanias" || t.nucleo === nucleo;
}

function applyFilter({ fly = false, duration = 800 } = {}) {
  const { service, nucleo, line } = state.filter;
  const tf = trainFilter();
  const isLd = ["!=", ["get", "service"], "cercanias"];
  if (map.getLayer("trains")) {
    map.setFilter("trains", tf.length > 1 ? tf : null);
    map.setFilter("train-labels", ["all", ["==", ["get", "service"], "cercanias"], ...tf.slice(1)]);
    map.setFilter("train-labels-ld", ["all", isLd, ...tf.slice(1)]);
  }
  if (map.getLayer("shapes")) {
    const sf = ["all"];
    if (service && service !== "cercanias") sf.push(["==", 1, 0]);
    if (nucleo) sf.push(["==", ["get", "nucleo"], nucleo]);
    if (line) sf.push(["==", ["get", "line"], line]);
    map.setFilter("shapes", sf.length > 1 ? sf : null);
  }
  $("service").value = service;
  $("nucleo").value = nucleo;
  fillLineSelect();
  if (fly) {
    const n = state.nucleos.find((x) => x.name === nucleo);
    if (n) map.fitBounds([[n.bbox[0], n.bbox[1]], [n.bbox[2], n.bbox[3]]], { padding: 40, duration });
    else map.flyTo({ center: [-3.7, 40.2], zoom: 5.2, duration });
  }
  const params = new URLSearchParams();
  if (service) params.set("s", service);
  if (nucleo) params.set("n", nucleo);
  if (line) params.set("l", line);
  history.replaceState(null, "", params.toString() ? `#${params}` : location.pathname);
  updateSearchList();
  updateFreshness();
  updateAlertCount();
  if (state.selected?.type === "alerts") renderAlerts();
}

function readHash({ duration = 800 } = {}) {
  const p = new URLSearchParams(location.hash.slice(1));
  state.filter.service = SERVICE_NAMES[p.get("s")] ? p.get("s") : "";
  state.filter.nucleo = p.get("n") || "";
  state.filter.line = p.get("l") || "";
  applyFilter({ fly: !!state.filter.nucleo, duration });
}

addEventListener("hashchange", () => readHash());
$("service").addEventListener("change", (e) => {
  state.filter.service = e.target.value;
  if (e.target.value && e.target.value !== "cercanias") state.filter.line = "";
  applyFilter();
});
$("nucleo").addEventListener("change", (e) => { state.filter = { ...state.filter, nucleo: e.target.value, line: "" }; applyFilter({ fly: true }); });
$("line").addEventListener("change", (e) => { state.filter.line = e.target.value; applyFilter(); });

const visibleTrains = () => (state.snapshot?.trains || []).filter(trainMatches);

// ---------------------------------------------------------------- live data

let online = true;
function connect() {
  const es = new EventSource("/api/stream");
  es.addEventListener("trains", (e) => { online = true; onSnapshot(JSON.parse(e.data)); });
  es.onerror = () => { online = false; updateFreshness(); };
}

function onSnapshot(snap) {
  state.snapshot = snap;
  if (map.getSource("trains")) animateTo(snap.trains);
  updateFreshness();
  updateSearchList();
  if (state.selected && state.selected.type !== "alerts") refreshPanel();
}

function featureFor(t, lon, lat, nowS) {
  return {
    type: "Feature",
    properties: {
      id: t.id, trip_id: t.trip_id, line: t.line, color: t.color, nucleo: t.nucleo, service: t.service,
      dclass: delayClass(t.delay), old: nowS - t.ts > TRAIN_OLD_S,
    },
    geometry: { type: "Point", coordinates: [lon, lat] },
  };
}

// Redraw at the last drawn positions, e.g. after a theme switch rebuilt the layers.
function drawTrains() {
  const trains = state.snapshot?.trains || [];
  const nowS = Date.now() / 1000;
  const features = trains.map((t) => {
    const [x, y] = state.shown.get(t.id) || [t.lon, t.lat];
    return featureFor(t, x, y, nowS);
  });
  map.getSource("trains")?.setData({ type: "FeatureCollection", features });
}

let animFrame = 0;
function animateTo(trains) {
  cancelAnimationFrame(animFrame);
  const from = new Map(state.shown);
  const start = performance.now();
  const nowS = Date.now() / 1000;
  const step = (now) => {
    const k = Math.min(1, (now - start) / ANIM_MS);
    const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    const features = [];
    state.shown = new Map();
    for (const t of trains) {
      const [fx, fy] = from.get(t.id) || [t.lon, t.lat];
      const x = fx + (t.lon - fx) * e, y = fy + (t.lat - fy) * e;
      state.shown.set(t.id, [x, y]);
      features.push(featureFor(t, x, y, nowS));
    }
    map.getSource("trains")?.setData({ type: "FeatureCollection", features });
    if (k < 1) animFrame = requestAnimationFrame(step);
  };
  animFrame = requestAnimationFrame(step);
}

// Brokkr status bar: the sync time at the end, and "Offline" after it when the connection drops.
function updateFreshness() {
  const s = state.snapshot;
  const el = $("fresh");
  if (!s || !s.feed_ts) {
    el.textContent = online ? "Connecting…" : "Offline";
    return;
  }
  const age = Math.max(0, Math.round(Date.now() / 1000 - s.feed_ts));
  const stale = age > s.stale_after_s;
  const parts = [`${fmtInt.format(visibleTrains().length)} trains`, `Synced ${hhmm(s.feed_ts)}`];
  if (!online) parts.push("Offline");
  else if (stale) parts.push("Renfe feed delayed");
  el.textContent = parts.join(" | ");
  el.classList.toggle("stale", !online || stale);
}
setInterval(updateFreshness, 1000);

// ---------------------------------------------------------------- search

function updateSearchList() {
  const dl = $("search-list");
  const opts = [];
  for (const t of visibleTrains()) opts.push(`${t.line} ${t.train} → ${t.destination}`);
  const { nucleo } = state.filter;
  const n = nucleo && state.nucleos.find((x) => x.name === nucleo);
  const names = new Set();
  for (const s of state.stops) {
    if (n && (s.lon < n.bbox[0] || s.lon > n.bbox[2] || s.lat < n.bbox[1] || s.lat > n.bbox[3])) continue;
    names.add(s.name);
  }
  opts.push(...[...names].sort());
  dl.innerHTML = opts.map((o) => `<option value="${esc(o)}">`).join("");
}

$("search").addEventListener("change", (e) => {
  const v = e.target.value.trim();
  if (!v) return;
  const num = v.match(/^.+?\s+(\d+)\s+→/)?.[1] || (/^\d+$/.test(v) ? v : null);
  const train = num && state.snapshot?.trains.find((t) => t.train === num || t.train === num.padStart(5, "0"));
  if (train) {
    select({ type: "train", id: train.trip_id });
  } else {
    const stop = state.stops.find((s) => s.name.toLowerCase() === v.toLowerCase())
      || state.stops.find((s) => s.name.toLowerCase().includes(v.toLowerCase()));
    if (stop) select({ type: "stop", id: stop.id });
  }
  e.target.value = "";
  e.target.blur();
});

// ---------------------------------------------------------------- panel

const PANEL_BUTTONS = { alerts: "alerts-btn", data: "data-btn" };

function select(sel) {
  state.selected = sel;
  for (const [type, id] of Object.entries(PANEL_BUTTONS)) $(id).setAttribute("aria-expanded", String(sel.type === type));
  $("panel").hidden = false;
  $("panel-body").innerHTML = `<p class="empty">Loading…</p>`;
  refreshPanel({ fly: true });
}

function closePanel() {
  state.selected = null;
  $("panel").hidden = true;
  for (const id of Object.values(PANEL_BUTTONS)) $(id).setAttribute("aria-expanded", "false");
  if (map.getLayer("train-selected")) map.setFilter("train-selected", ["==", ["get", "id"], ""]);
}
$("panel-close").addEventListener("click", closePanel);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel(); });

let panelReq = 0;
async function refreshPanel({ fly = false } = {}) {
  const sel = state.selected;
  if (!sel) return;
  const req = ++panelReq;
  if (sel.type === "alerts") return renderAlerts();
  if (sel.type === "data") return renderData(req);
  const url = sel.type === "train" ? `/api/trip/${encodeURIComponent(sel.id)}` : `/api/stop/${encodeURIComponent(sel.id)}`;
  const r = await fetch(url);
  if (req !== panelReq) return;
  if (!r.ok) { $("panel-body").innerHTML = `<p class="empty">No longer available.</p>`; return; }
  const d = await r.json();
  if (sel.type === "train") renderTrip(d, fly); else renderStop(d, fly);
}

// Cercanías lines carry Renfe's own colours; other services use the app's service colours.
function badge(line, color, text, service) {
  const bg = service && service !== "cercanias" ? serviceColor(service) : color;
  const fg = service && service !== "cercanias" ? token("--app-service-on-fill") : text;
  return `<span class="badge" style="background:${esc(bg)};color:${esc(fg)}">${esc(line)}</span>`;
}

function renderTrip(d, fly) {
  const t = d.train;
  if (map.getLayer("train-selected")) map.setFilter("train-selected", ["==", ["get", "trip_id"], d.trip_id]);
  if (fly && t) map.flyTo({ center: [t.lon, t.lat], zoom: Math.max(map.getZoom(), d.service === "cercanias" ? 11 : 8), duration: 800 });
  const dest = d.stops.at(-1)?.name || "";
  const status = t ? ({ STOPPED_AT: "Stopped at", INCOMING_AT: "Arriving at", IN_TRANSIT_TO: "Heading to" }[t.status] || "Near") + ` ${esc(t.stop_name)}` : "Not reporting a position";
  const rows = d.stops.map((s) => {
    const cls = [s.passed && "passed", s.current && "current"].filter(Boolean).join(" ");
    const late = s.expected && s.expected - s.scheduled > 60;
    const time = late ? `<s>${hhmm(s.scheduled)}</s>${hhmm(s.expected)}` : hhmm(s.scheduled);
    return `<li class="${cls}"><span class="pin"></span><a data-stop="${esc(s.id)}">${esc(s.name)}</a><span class="t">${time}</span></li>`;
  }).join("");
  const where = d.service === "cercanias" ? d.nucleo : SERVICE_NAMES[d.service] || "";
  $("panel-body").innerHTML = `
    <h2>${badge(d.line, d.color, d.text_color, d.service)}to ${esc(dest)}</h2>
    <p class="meta">
      Train ${esc(t?.train || "—")} · ${esc(where)}${t?.platform ? ` · Platform ${esc(t.platform)}` : ""}<br>
      ${status} · <span class="delay ${delayClass(d.delay)}">${delayText(d.delay)}</span>
    </p>
    <p class="section">Stops</p>
    <ul class="stops">${rows}</ul>`;
  for (const a of $("panel-body").querySelectorAll("[data-stop]")) a.addEventListener("click", () => select({ type: "stop", id: a.dataset.stop }));
}

function renderStop(d, fly) {
  if (map.getLayer("train-selected")) map.setFilter("train-selected", ["==", ["get", "id"], ""]);
  if (fly) map.flyTo({ center: [d.stop.lon, d.stop.lat], zoom: Math.max(map.getZoom(), 12), duration: 800 });
  const rows = d.departures.map((r) => {
    const late = r.delay != null && r.delay > 60;
    const time = late ? `<s>${hhmm(r.scheduled)}</s>${hhmm(r.expected)}` : hhmm(r.scheduled);
    return `<tr>
      <td>${badge(r.line, r.color, r.text_color, r.service)}</td>
      <td><a data-trip="${esc(r.trip_id)}" class="${r.live ? "live" : ""}">${esc(r.destination)}</a></td>
      <td class="t">${time}${r.delay != null ? `<br><span class="delay ${delayClass(r.delay)}">${delayText(r.delay)}</span>` : ""}</td>
    </tr>`;
  }).join("");
  $("panel-body").innerHTML = `
    <h2>${esc(d.stop.name)}</h2>
    <p class="meta">● = live position</p>
    <p class="section">Next departures</p>
    ${rows ? `<table class="board">${rows}</table>` : `<p class="empty">No departures in the next 90 minutes.</p>`}`;
  for (const a of $("panel-body").querySelectorAll("[data-trip]")) a.addEventListener("click", () => select({ type: "train", id: a.dataset.trip }));
}

// ---------------------------------------------------------------- open data

function liveLine(src) {
  const l = src.live || {};
  if (l.error) return `<span class="delay risk">Not responding: ${esc(l.error)}</span>`;
  const bits = [];
  if (l.entities != null) bits.push(`${fmtInt.format(l.entities)} ${src.id === "alerts" ? "notices" : "records"} in the feed`);
  if (l.active != null) bits.push(`${fmtInt.format(l.active)} active now`);
  if (l.stations != null) bits.push(`${fmtInt.format(l.stations)} stations served`, `${fmtInt.format(l.routes)} routes`, `${fmtInt.format(l.trips_today)} trips today`);
  if (l.links != null) bits.push(`${fmtInt.format(l.links)} track links`);
  if (l.updated_at) bits.push(`${src.id.startsWith("gtfs_") ? "loaded" : "updated"} ${ago(l.updated_at)}`);
  if (src.id === "network" && !l.links) bits.push("downloading on first start…");
  return bits.length ? esc(bits.join(" · ")) : "";
}

async function renderData(req) {
  let d;
  try { d = await fetch("/api/sources").then((r) => r.json()); } catch { d = null; }
  if (req !== panelReq || state.selected?.type !== "data") return;
  if (!d) { $("panel-body").innerHTML = `<p class="empty">Couldn't load the source list.</p>`; return; }
  const counts = Object.entries(SERVICE_NAMES)
    .map(([k, name]) => `<li><span class="badge" style="background:${esc(k === "cercanias" ? token("--npc-color-surface-raised") : serviceColor(k))};color:${esc(k === "cercanias" ? token("--npc-color-text-default") : token("--app-service-on-fill"))}">${fmtInt.format(d.trains[k] || 0)}</span>${esc(name)}</li>`)
    .join("");
  const cards = d.used.map((s) => `
    <article class="source">
      <h3>${esc(s.name)}</h3>
      <p class="source-meta">${esc(s.publisher)} · ${esc(s.format)} · ${esc(s.updates)} · <a href="${esc(s.licence.url)}" target="_blank" rel="noopener">${esc(s.licence.name)}</a></p>
      <p>${esc(s.use)}</p>
      ${s.note ? `<p class="source-note">${esc(s.note)}</p>` : ""}
      <p class="source-live">${liveLine(s)}</p>
      <p class="source-links"><a href="${esc(s.page)}" target="_blank" rel="noopener">About the dataset</a>${s.feed ? ` · <a href="${esc(s.feed)}" target="_blank" rel="noopener">Open the raw data</a>` : ""}</p>
    </article>`).join("");
  const more = d.more.map((m) => `<li><a href="${esc(m.page)}" target="_blank" rel="noopener">${esc(m.name)}</a> <span class="source-meta">${esc(m.publisher)}</span></li>`).join("");
  $("panel-body").innerHTML = `
    <h2>Open data</h2>
    <p class="meta">Everything on this map comes from open data published by public bodies in Spain. Here's each source, how often it changes and what TrainRadar does with it. Open any feed yourself: it's public.</p>
    <p class="section">Trains on the map now</p>
    <ul class="counts">${counts}</ul>
    <p class="section">Sources used</p>
    ${cards}
    <p class="section">More open rail data</p>
    <ul class="more">${more}</ul>
    <p class="meta">TrainRadar is open source: <a href="https://github.com/NoPrettyColors/trainradar" target="_blank" rel="noopener">github.com/NoPrettyColors/trainradar</a></p>`;
}

$("data-btn").addEventListener("click", () => {
  if (state.selected?.type === "data") closePanel(); else select({ type: "data" });
});

// ---------------------------------------------------------------- alerts

async function loadAlerts() {
  try {
    state.alerts = await fetch("/api/alerts").then((r) => r.json());
  } catch { return; }
  updateAlertCount();
  if (state.selected?.type === "alerts") renderAlerts();
}

function filteredAlerts() {
  const { nucleo } = state.filter;
  return state.alerts.filter((a) => !nucleo || a.nucleos.includes(nucleo));
}

function updateAlertCount() {
  $("alerts-count").textContent = filteredAlerts().length;
}

function renderAlerts() {
  const { nucleo } = state.filter;
  const list = filteredAlerts();
  $("panel-body").innerHTML = `
    <h2>Service alerts</h2>
    <p class="meta">${nucleo ? esc(nucleo) : "All Cercanías networks"} · ${list.length} active · Renfe's alerts feed covers Cercanías and Rodalies only</p>
    ${list.map((a) => `<div class="alert"><div class="lines">${esc(a.nucleos.join(", "))}${a.lines.length ? " · " + esc(a.lines.join(", ")) : ""}</div>${esc(a.text)}</div>`).join("") || `<p class="empty">No active alerts.</p>`}`;
}

$("alerts-btn").addEventListener("click", () => {
  if (state.selected?.type === "alerts") closePanel(); else select({ type: "alerts" });
});
