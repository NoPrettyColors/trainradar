"use strict";

const COLORS = { ok: "#1f9d55", minor: "#e0a100", major: "#d43a2f", unknown: "#9a9a94" };
const TRAIN_OLD_S = 300; // a vehicle report older than this is drawn faded
const ANIM_MS = 1500;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Madrid" });
const hhmm = (epoch) => timeFmt.format(new Date(epoch * 1000));

function delayClass(d) {
  if (d == null) return "unknown";
  if (d <= 60) return "ok";
  if (d <= 300) return "minor";
  return "major";
}
function delayText(d) {
  if (d == null) return "No live data";
  if (d <= 60) return "On time";
  return `+${Math.round(d / 60)} min`;
}

const state = {
  snapshot: null,
  shown: new Map(), // id -> [lon, lat] currently drawn
  stops: [],        // [{id, name, lon, lat}]
  nucleos: [],
  lines: new Map(), // nucleo -> Set(line)
  filter: { nucleo: "", line: "" },
  selected: null,   // {type: "train"|"stop"|"alerts", id}
  alerts: [],
};

// ---------------------------------------------------------------- map setup

const dark = matchMedia("(prefers-color-scheme: dark)").matches;
const map = new maplibregl.Map({
  container: "map",
  style: `https://tiles.openfreemap.org/styles/${dark ? "dark" : "positron"}`,
  center: [-3.7, 40.2],
  zoom: 5.2,
  attributionControl: { compact: true },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-left");
// MapLibre only tracks window resizes; the container can also change size on its own (header wrap, hidden pane).
new ResizeObserver(() => map.resize()).observe(document.getElementById("map"));

const delayColorExpr = ["match", ["get", "dclass"], "ok", COLORS.ok, "minor", COLORS.minor, "major", COLORS.major, COLORS.unknown];

map.on("load", async () => {
  const [shapes, stops, nucleos] = await Promise.all(
    ["/api/shapes", "/api/stops", "/api/nucleos"].map((u) => fetch(u).then((r) => r.json()))
  );

  state.nucleos = nucleos;
  for (const f of shapes.features) {
    const { nucleo, line } = f.properties;
    if (!state.lines.has(nucleo)) state.lines.set(nucleo, new Set());
    if (line) state.lines.get(nucleo).add(line);
  }
  state.stops = stops.features.map((f) => ({ id: f.properties.id, name: f.properties.name, lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] }));
  fillNucleoSelect();

  map.addSource("shapes", { type: "geojson", data: shapes });
  map.addLayer({
    id: "shapes", type: "line", source: "shapes",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": ["get", "color"],
      "line-width": ["interpolate", ["linear"], ["zoom"], 5, 1.2, 10, 2.5, 14, 4],
      "line-opacity": 0.75,
    },
  });

  map.addSource("stops", { type: "geojson", data: stops });
  map.addLayer({
    id: "stops", type: "circle", source: "stops", minzoom: 9.5,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2.5, 14, 5],
      "circle-color": dark ? "#1f1f1d" : "#ffffff",
      "circle-stroke-color": dark ? "#ecebe6" : "#1c1c1a",
      "circle-stroke-width": 1.2,
    },
  });
  map.addLayer({
    id: "stop-labels", type: "symbol", source: "stops", minzoom: 12,
    layout: { "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11, "text-offset": [0, 1.1], "text-anchor": "top", "text-optional": true },
    paint: { "text-color": dark ? "#cfcec8" : "#3a3a36", "text-halo-color": dark ? "#141413" : "#ffffff", "text-halo-width": 1.2 },
  });

  map.addSource("trains", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: "train-selected", type: "circle", source: "trains", filter: ["==", ["get", "id"], ""],
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 9, 10, 13, 14, 17], "circle-color": "transparent", "circle-stroke-color": dark ? "#ffffff" : "#1c1c1a", "circle-stroke-width": 2 },
  });
  map.addLayer({
    id: "trains", type: "circle", source: "trains",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 4, 10, 7, 14, 10],
      "circle-color": ["get", "color"],
      "circle-stroke-color": delayColorExpr,
      "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 5, 1.5, 10, 3],
      "circle-opacity": ["case", ["get", "old"], 0.4, 1],
      "circle-stroke-opacity": ["case", ["get", "old"], 0.4, 1],
    },
  });
  map.addLayer({
    id: "train-labels", type: "symbol", source: "trains", minzoom: 9,
    layout: { "text-field": ["get", "line"], "text-font": ["Noto Sans Bold"], "text-size": 11, "text-offset": [1.2, 0], "text-anchor": "left", "text-allow-overlap": false },
    paint: { "text-color": dark ? "#ecebe6" : "#1c1c1a", "text-halo-color": dark ? "#141413" : "#ffffff", "text-halo-width": 1.5 },
  });

  map.on("click", "trains", (e) => select({ type: "train", id: e.features[0].properties.trip_id }));
  map.on("click", "stops", (e) => {
    if (map.queryRenderedFeatures(e.point, { layers: ["trains"] }).length) return;
    select({ type: "stop", id: e.features[0].properties.id });
  });
  for (const l of ["trains", "stops"]) {
    map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
  }

  readHash();
  if (state.snapshot) animateTo(state.snapshot.trains);
});

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

function applyFilter({ fly = false } = {}) {
  const { nucleo, line } = state.filter;
  const f = ["all"];
  if (nucleo) f.push(["==", ["get", "nucleo"], nucleo]);
  if (line) f.push(["==", ["get", "line"], line]);
  for (const id of ["shapes", "trains", "train-labels"]) if (map.getLayer(id)) map.setFilter(id, f.length > 1 ? f : null);
  $("nucleo").value = nucleo;
  fillLineSelect();
  if (fly) {
    const n = state.nucleos.find((x) => x.name === nucleo);
    if (n) map.fitBounds([[n.bbox[0], n.bbox[1]], [n.bbox[2], n.bbox[3]]], { padding: 40, duration: 800 });
    else map.flyTo({ center: [-3.7, 40.2], zoom: 5.2 });
  }
  const params = new URLSearchParams();
  if (nucleo) params.set("n", nucleo);
  if (line) params.set("l", line);
  history.replaceState(null, "", params.toString() ? `#${params}` : location.pathname);
  updateSearchList();
  updateFreshness();
  updateAlertCount();
  if (state.selected?.type === "alerts") renderAlerts();
}

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.filter.nucleo = p.get("n") || "";
  state.filter.line = p.get("l") || "";
  applyFilter({ fly: !!state.filter.nucleo });
}

addEventListener("hashchange", readHash);
$("nucleo").addEventListener("change", (e) => { state.filter = { nucleo: e.target.value, line: "" }; applyFilter({ fly: true }); });
$("line").addEventListener("change", (e) => { state.filter.line = e.target.value; applyFilter(); });

function visibleTrains() {
  const { nucleo, line } = state.filter;
  return (state.snapshot?.trains || []).filter((t) => (!nucleo || t.nucleo === nucleo) && (!line || t.line === line));
}

// ---------------------------------------------------------------- live data

function connect() {
  const es = new EventSource("/api/stream");
  es.addEventListener("trains", (e) => onSnapshot(JSON.parse(e.data)));
  es.onerror = () => { $("fresh").textContent = "Reconnecting…"; $("fresh").classList.add("stale"); };
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
      id: t.id, trip_id: t.trip_id, line: t.line, color: t.color, nucleo: t.nucleo,
      dclass: delayClass(t.delay), old: nowS - t.ts > TRAIN_OLD_S,
    },
    geometry: { type: "Point", coordinates: [lon, lat] },
  };
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
    map.getSource("trains").setData({ type: "FeatureCollection", features });
    if (k < 1) animFrame = requestAnimationFrame(step);
  };
  animFrame = requestAnimationFrame(step);
}

function updateFreshness() {
  const s = state.snapshot;
  const el = $("fresh");
  if (!s || !s.feed_ts) return;
  const age = Math.max(0, Math.round(Date.now() / 1000 - s.feed_ts));
  const n = visibleTrains().length;
  const ago = age < 90 ? `${age}s` : `${Math.round(age / 60)} min`;
  el.textContent = `${n} trains · updated ${ago} ago`;
  el.classList.toggle("stale", age > s.stale_after_s);
}
setInterval(updateFreshness, 1000);

// ---------------------------------------------------------------- search

function updateSearchList() {
  const dl = $("search-list");
  const opts = [];
  for (const t of visibleTrains()) opts.push(`${t.line} ${t.train} → ${t.destination}`);
  const { nucleo } = state.filter;
  const names = new Set();
  for (const s of state.stops) {
    if (nucleo) {
      const n = state.nucleos.find((x) => x.name === nucleo);
      if (n && (s.lon < n.bbox[0] || s.lon > n.bbox[2] || s.lat < n.bbox[1] || s.lat > n.bbox[3])) continue;
    }
    names.add(s.name);
  }
  opts.push(...[...names].sort());
  dl.innerHTML = opts.map((o) => `<option value="${esc(o)}">`).join("");
}

$("search").addEventListener("change", (e) => {
  const v = e.target.value.trim();
  if (!v) return;
  const num = v.match(/^\S+\s+(\d+)\s+→/)?.[1] || (/^\d+$/.test(v) ? v : null);
  const train = num && state.snapshot?.trains.find((t) => t.train === num);
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

function select(sel) {
  state.selected = sel;
  $("alerts-btn").setAttribute("aria-expanded", String(sel.type === "alerts"));
  $("panel").hidden = false;
  $("panel-body").innerHTML = `<p class="empty">Loading…</p>`;
  refreshPanel({ fly: true });
}

function closePanel() {
  state.selected = null;
  $("panel").hidden = true;
  $("alerts-btn").setAttribute("aria-expanded", "false");
  map.setFilter("train-selected", ["==", ["get", "id"], ""]);
}
$("panel-close").addEventListener("click", closePanel);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel(); });

let panelReq = 0;
async function refreshPanel({ fly = false } = {}) {
  const sel = state.selected;
  if (!sel) return;
  const req = ++panelReq;
  if (sel.type === "alerts") return renderAlerts();
  const url = sel.type === "train" ? `/api/trip/${encodeURIComponent(sel.id)}` : `/api/stop/${encodeURIComponent(sel.id)}`;
  const r = await fetch(url);
  if (req !== panelReq) return;
  if (!r.ok) { $("panel-body").innerHTML = `<p class="empty">No longer available.</p>`; return; }
  const d = await r.json();
  if (sel.type === "train") renderTrip(d, fly); else renderStop(d, fly);
}

function badge(line, color, text) {
  return `<span class="badge" style="background:${esc(color)};color:${esc(text)}">${esc(line)}</span>`;
}

function renderTrip(d, fly) {
  const t = d.train;
  map.setFilter("train-selected", ["==", ["get", "trip_id"], d.trip_id]);
  if (fly && t) map.flyTo({ center: [t.lon, t.lat], zoom: Math.max(map.getZoom(), 11), duration: 800 });
  const dest = d.stops.at(-1)?.name || "";
  const status = t ? ({ STOPPED_AT: "Stopped at", INCOMING_AT: "Arriving at", IN_TRANSIT_TO: "Heading to" }[t.status] || "Near") + ` ${esc(t.stop_name)}` : "Not reporting a position";
  const rows = d.stops.map((s) => {
    const cls = [s.passed && "passed", s.current && "current"].filter(Boolean).join(" ");
    const late = s.expected && s.expected - s.scheduled > 60;
    const time = late ? `<s>${hhmm(s.scheduled)}</s>${hhmm(s.expected)}` : hhmm(s.scheduled);
    return `<li class="${cls}"><span class="pin"></span><a data-stop="${esc(s.id)}">${esc(s.name)}</a><span class="t">${time}</span></li>`;
  }).join("");
  $("panel-body").innerHTML = `
    <h2>${badge(d.line, d.color, d.text_color)}to ${esc(dest)}</h2>
    <p class="meta">
      Train ${esc(t?.train || "—")} · ${esc(d.nucleo)}${t?.platform ? ` · Platform ${esc(t.platform)}` : ""}<br>
      ${status} · <span class="delay ${delayClass(d.delay)}">${delayText(d.delay)}</span>
    </p>
    <ul class="stops">${rows}</ul>`;
  for (const a of $("panel-body").querySelectorAll("[data-stop]")) a.addEventListener("click", () => select({ type: "stop", id: a.dataset.stop }));
}

function renderStop(d, fly) {
  map.setFilter("train-selected", ["==", ["get", "id"], ""]);
  if (fly) map.flyTo({ center: [d.stop.lon, d.stop.lat], zoom: Math.max(map.getZoom(), 12), duration: 800 });
  const rows = d.departures.map((r) => {
    const late = r.delay != null && r.delay > 60;
    const time = late ? `<s>${hhmm(r.scheduled)}</s>${hhmm(r.expected)}` : hhmm(r.scheduled);
    return `<tr>
      <td>${badge(r.line, r.color, r.text_color)}</td>
      <td><a data-trip="${esc(r.trip_id)}" class="${r.live ? "live" : ""}">${esc(r.destination)}</a></td>
      <td class="t">${time}${r.delay != null ? `<br><span class="delay ${delayClass(r.delay)}">${delayText(r.delay)}</span>` : ""}</td>
    </tr>`;
  }).join("");
  $("panel-body").innerHTML = `
    <h2>${esc(d.stop.name)}</h2>
    <p class="meta">Next departures · ● = live position</p>
    ${rows ? `<table class="board">${rows}</table>` : `<p class="empty">No departures in the next 90 minutes.</p>`}`;
  for (const a of $("panel-body").querySelectorAll("[data-trip]")) a.addEventListener("click", () => select({ type: "train", id: a.dataset.trip }));
}

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
    <p class="meta">${nucleo ? esc(nucleo) : "All networks"} · ${list.length} active</p>
    ${list.map((a) => `<div class="alert"><div class="lines">${esc(a.nucleos.join(", "))}${a.lines.length ? " · " + esc(a.lines.join(", ")) : ""}</div>${esc(a.text)}</div>`).join("") || `<p class="empty">No active alerts.</p>`}`;
}

$("alerts-btn").addEventListener("click", () => {
  if (state.selected?.type === "alerts") closePanel(); else select({ type: "alerts" });
});
