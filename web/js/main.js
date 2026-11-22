import { CONFIG, isMobile } from "./config.js";
import { loadDem, createTerrainProvider, createTerrainMaterial } from "./terrain.js";
import { CampusLayers, loadJSON } from "./layers.js";
import { CameraController, MODES } from "./camera.js";
import { toEpsg5186, fmtLonLat } from "./geo.js";

const Cesium = window.Cesium;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const setLoading = (t) => { $("#loadingText").textContent = t; };
const DATA = "data";
// Light mode (default) opens fast: no shadows or MSAA, coarser terrain tiles, no vegetation until it is
// switched on. "Full detail" in the toolbar stores the choice and reloads.
const LIGHT = (() => { try { return localStorage.getItem("detail") !== "full"; } catch { return true; } })();

async function main() {
  if (!window.Cesium) throw new Error("CesiumJS failed to load from the CDN.");
  // No Cesium ion assets are used. Terrain and features are served from this repository.
  Cesium.Ion.defaultAccessToken = "";

  setLoading("Loading FABDEM terrain grid…");
  const [dem, summary, details] = await Promise.all([loadDem(`${DATA}/terrain`), loadJSON(`${DATA}/summary.json`), loadJSON(`${DATA}/campus_details.json`)]);

  const viewer = new Cesium.Viewer("cesium", {
    terrainProvider: createTerrainProvider(dem),
    baseLayer: false,
    baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
    navigationHelpButton: false, animation: false, timeline: false, fullscreenButton: false,
    infoBox: false, selectionIndicator: false,
    shadows: !isMobile && !LIGHT,
    msaaSamples: isMobile || LIGHT ? 1 : 4,
    useBrowserRecommendedResolution: true,
    contextOptions: { webgl: { alpha: true } },
  });
  window.viewer = viewer; // handy for debugging / automated checks
  const scene = viewer.scene, globe = scene.globe;
  globe.depthTestAgainstTerrain = true;
  globe.baseColor = Cesium.Color.fromCssColorString("#5b6157");
  globe.maximumScreenSpaceError = isMobile ? 2.5 : LIGHT ? 2.0 : 1.4;
  globe.tileCacheSize = isMobile ? 120 : 400;
  globe.preloadSiblings = !isMobile;
  globe.enableLighting = false;
  globe.showGroundAtmosphere = true;
  globe.shadows = Cesium.ShadowMode.RECEIVE_ONLY;
  scene.fog.enabled = true;
  scene.fog.density = 1.2e-4;
  scene.highDynamicRange = false;

  // ---------------- crop to the university: terrain clipped to campus boundary + 30 m ----------------
  const cb = details.clip.bbox;
  const fbx = { west: cb[0], south: cb[1], east: cb[2], north: cb[3] };
  globe.cartographicLimitRectangle = Cesium.Rectangle.fromDegrees(cb[0] - 0.0005, cb[1] - 0.0005, cb[2] + 0.0005, cb[3] + 0.0005);
  globe.clippingPolygons = new Cesium.ClippingPolygonCollection({
    polygons: details.clip.rings.map((r) => new Cesium.ClippingPolygon({ positions: Cesium.Cartesian3.fromDegreesArray(r.slice(0, -1).flat()) })),
    inverse: true,
  });
  globe.showSkirts = false;
  scene.skyBox.show = false;
  scene.skyAtmosphere.show = false;
  scene.sun.show = false;
  scene.moon.show = false;
  scene.backgroundColor = Cesium.Color.TRANSPARENT; // CSS sky gradient shows around the cut terrain
  addDioramaSides(viewer, dem, details.clip.rings);
  scene.postProcessStages.fxaa.enabled = isMobile;
  if (viewer.shadowMap) {
    viewer.shadowMap.size = isMobile ? 1024 : 2048;
    viewer.shadowMap.softShadows = !isMobile;
    viewer.shadowMap.darkness = 0.45;
    viewer.shadowMap.maximumDistance = 2500;
  }
  viewer.clock.shouldAnimate = false;

  // ---------------- imagery ----------------
  const layersColl = viewer.imageryLayers;
  let imageryLayer = null;
  let vworldKey = CONFIG.vworldKey || safeGet("vworldKey") || "";
  function makeImagery(key) {
    const c = CONFIG.imagery[key];
    if (!c) return null;
    let url = c.url;
    if (key === "vworld") { if (!vworldKey) return null; url = url.replace("{key}", encodeURIComponent(vworldKey)); }
    return new Cesium.UrlTemplateImageryProvider({ url, maximumLevel: c.maximumLevel, credit: c.credit, tilingScheme: new Cesium.WebMercatorTilingScheme() });
  }
  function setImagery(key) {
    if (imageryLayer) { layersColl.remove(imageryLayer, true); imageryLayer = null; }
    const rendered = key === "none";
    globe.baseColor = Cesium.Color.fromCssColorString(rendered ? "#8d9b62" : "#5b6157");
    if (window.__layers?.forestPrimitive) window.__layers.forestPrimitive.show = rendered;
    if (window.__hill) window.__hill.alpha = rendered ? 0.62 : Number($("#hillshade").value);
    const prov = key === "none" ? null : makeImagery(key);
    if (prov) { imageryLayer = layersColl.addImageryProvider(prov, 0); }
    $("#btnImagery").classList.toggle("on", !!prov);
    $("#vworldRow").classList.toggle("hidden", key !== "vworld");
    state.imagery = key;
  }
  const state = { imagery: "none", lastImagery: "esri", viz: "realistic", terrainOnly: false };
  const sel = $("#imagerySel");
  for (const [k, c] of Object.entries(CONFIG.imagery)) sel.add(new Option(c.label, k));
  sel.add(new Option("Rendered model (no imagery)", "none"));
  sel.value = "none";
  setImagery("none");
  sel.onchange = () => { setImagery(sel.value); if (sel.value !== "none") state.lastImagery = sel.value; };
  $("#vworldApply").onclick = () => { vworldKey = $("#vworldKey").value.trim(); safeSet("vworldKey", vworldKey); setImagery("vworld"); };
  $("#vworldKey").value = vworldKey;

  // Slope and hillshade are calculated on the same local grades as the terrain mesh.
  const ov = dem.meta.overlays;
  const rect = Cesium.Rectangle.fromDegrees(...ov.rectangle_deg);
  const hillLayer = layersColl.addImageryProvider(await Cesium.SingleTileImageryProvider.fromUrl(`${DATA}/terrain/${ov.hillshade}`, { rectangle: rect, credit: "Hillshade from FABDEM V1-2 and estimated local grades" }));
  hillLayer.alpha = 0.62;
  window.__hill = hillLayer;
  // the 1.2 MB slope overlay is fetched only when the slope view is first chosen
  let slopeLayer = null, slopeLoading = null;
  const ensureSlope = () => slopeLoading ??= Cesium.SingleTileImageryProvider.fromUrl(`${DATA}/terrain/${ov.slope}`, { rectangle: rect, credit: "Slope from FABDEM V1-2 and estimated local grades" })
    .then((prov) => { slopeLayer = layersColl.addImageryProvider(prov); slopeLayer.alpha = 0.78; slopeLayer.show = state.viz === "slope"; layersColl.raiseToTop(hillLayer); });

  // elevation ramp + contours (GPU material on rendered terrain)
  const local = dem.statsInRect(fbx.west, fbx.south, fbx.east, fbx.north);
  const rampMin = Math.floor(local.min / 10) * 10, rampMax = Math.ceil(local.max / 10) * 10;
  const material = createTerrainMaterial({ minH: rampMin, maxH: rampMax, geoidN: dem.geoidN(CONFIG.campusCenter.lon, CONFIG.campusCenter.lat) });

  function applyViz(v) {
    state.viz = v;
    $("#vizSel").value = v;
    if (slopeLayer) slopeLayer.show = v === "slope";
    else if (v === "slope") ensureSlope();
    const u = material.uniforms;
    u.showRamp = (v === "elevation" || v === "elevcontours") ? 1 : 0;
    u.showContours = (v === "contours" || v === "elevcontours") ? 1 : 0;
    u.rampAlpha = v === "elevcontours" ? 0.7 : 0.82;
    u.spacing = Number($("#contourSel").value);
    globe.material = (u.showRamp || u.showContours) ? material : undefined;
    $("#btnElevation").classList.toggle("on", v !== "realistic");
    renderVizLegend(v);
  }
  function renderVizLegend(v) {
    const L = $("#vizLegend");
    if (v === "elevation" || v === "elevcontours") {
      L.innerHTML = `<div class="bar" style="background:linear-gradient(90deg,#1a5c33,#669e45 20%,#d9d675 40%,#db994d 60%,#9e5c38 80%,#f5f0eb)"></div>
        <div class="ticks"><span>${rampMin} m</span><span>${(rampMin + rampMax) / 2} m</span><span>${rampMax} m</span></div>
        <div>Orthometric height (EGM2008), feature area range</div>`;
    } else if (v === "slope") {
      L.innerHTML = `<div class="bar" style="background:linear-gradient(90deg,#1a9850 0%,#91cf60 11%,#d9ef8b 22%,#fee08b 33%,#fc8d59 44%,#d73027 67%,#78003c 100%)"></div>
        <div class="ticks"><span>0°</span><span>10°</span><span>20°</span><span>30°</span><span>45°</span></div><div>Slope from the 1″ DTM and estimated local grades (Horn method).</div>`;
    } else if (v === "contours") {
      L.innerHTML = `<div>Contours every ${$("#contourSel").value} m; every 5th line is thicker. They are computed per pixel on the rendered DTM surface (orthometric).</div>`;
    } else L.innerHTML = "";
  }
  $("#vizSel").onchange = (e) => applyViz(e.target.value);
  $("#contourSel").onchange = () => applyViz(state.viz);
  $("#hillshade").oninput = (e) => { hillLayer.alpha = Number(e.target.value); };
  $("#wireframe").onchange = (e) => {
    try { globe._surface.tileProvider._debug.wireframe = e.target.checked; } catch { /* private API */ }
  };

  // ---------------- sun / shadows ----------------
  function applySun() {
    const d = $("#sunDate").value || "2026-05-20";
    const t = Number($("#sunTime").value);
    const hh = Math.floor(t), mm = Math.round((t - hh) * 60);
    $("#sunTimeLabel").textContent = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
    const kst = new Date(`${d}T${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:00+09:00`);
    viewer.clock.currentTime = Cesium.JulianDate.fromDate(kst);
    scene.requestRender();
  }
  $("#sunDate").onchange = applySun; $("#sunTime").oninput = applySun;
  $("#shadows").checked = !isMobile && !LIGHT;
  $("#shadows").onchange = (e) => { viewer.shadows = e.target.checked; };
  applySun();

  // ---------------- features ----------------
  setLoading("Loading buildings, roads and landcover…");
  const layers = new CampusLayers(viewer, dem, { mobile: isMobile });
  const { buildings } = await layers.load(DATA, setLoading);
  window.__layers = layers;
  setImagery(state.imagery);

  // ---------------- camera ----------------
  const home = { ...CONFIG.home, ...CONFIG.campusCenter };
  const cam = new CameraController(viewer, dem, layers, home, (mode, hint) => {
    document.querySelectorAll("#modeSeg button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
    $("#hint").textContent = hint;
    $("#touchpad").classList.toggle("hidden", !(isTouch && ["walk", "fly", "follow"].includes(mode)));
    $("#touchpad").dataset.mode = mode;
  }, { bounds: fbx, walkStart: gateWalkStart(layers.details) });
  window.cam = cam;
  // on-screen movement pad (touch devices)
  document.querySelectorAll("#touchpad [data-key]").forEach((b) => {
    const k = b.dataset.key;
    b.addEventListener("pointerdown", (e) => { e.preventDefault(); cam.keys.add(k); b.setPointerCapture?.(e.pointerId); });
    for (const ev of ["pointerup", "pointercancel", "pointerleave"]) b.addEventListener(ev, () => cam.keys.delete(k));
  });
  $("#walkCampus").onclick = () => {
    if (cam.mode === "walk") cam.setMode("orbit");
    const c = viewer.camera.positionCartographic;
    viewer.camera.setView({ destination: Cesium.Cartesian3.fromRadians(c.longitude, c.latitude, c.height + 1000) });
    cam.setMode("walk");
  };
  const seg = $("#modeSeg");
  for (const [k, label] of Object.entries(MODES)) {
    const b = document.createElement("button");
    b.dataset.mode = k; b.textContent = label.replace("First-person walk", "Walk").replace("Terrain-following", "Follow").replace("Fly-through", "Fly");
    b.title = label;
    b.onclick = () => cam.setMode(k);
    seg.appendChild(b);
  }
  cam.setMode("orbit");
  const h = CONFIG.home;
  viewer.camera.flyToBoundingSphere(cam.homeSphere, { offset: new Cesium.HeadingPitchRange(Cesium.Math.toRadians(h.heading), Cesium.Math.toRadians(h.pitch), h.range), duration: 0 });
  // default view: the main gate seen from 45° off its axis and from higher up, so the artificial-turf
  // field behind it is in frame too ("Whole campus" in the toolbar still flies to the overview above)
  const g = layers.details?.gate;
  if (g && !location.hash) {
    const [glon, glat] = g.center, [ax, ay] = g.axis_en;
    const mx = 111320 * Math.cos(glat * Math.PI / 180), my = 110950;
    let nx = -ay, ny = ax;                                         // footprint normal; point it away from the campus
    const cc = CONFIG.campusCenter ?? { lon: 127.0818, lat: 37.2427 };
    if (nx * (cc.lon - glon) * mx + ny * (cc.lat - glat) * my > 0) { nx = -nx; ny = -ny; }
    // look direction = inward normal turned 45° towards the turf field (south-east of the gate)
    const turf = { lon: 127.0793, lat: 37.2465 };
    const tE = (turf.lon - glon) * mx, tN = (turf.lat - glat) * my;
    const rot = (a) => [(-nx) * Math.cos(a) - (-ny) * Math.sin(a), (-nx) * Math.sin(a) + (-ny) * Math.cos(a)];
    let [dx, dy] = rot(Math.PI / 4);
    const [ex, ey] = rot(-Math.PI / 4);
    if (ex * tE + ey * tN > dx * tE + dy * tN) [dx, dy] = [ex, ey];
    const back = 105, up = 75;                                     // metres behind the gate along the view line / above ground
    const lon = glon - dx * back / mx, lat = glat - dy * back / my;
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(lon, lat, dem.heightEllipsoid(lon, lat) + up),
      orientation: { heading: Math.atan2(dx, dy), pitch: Cesium.Math.toRadians(-24), roll: 0 },
    });
  }

  // ---------------- layer toggles ----------------
  const layerMap = {
    buildings: () => layers.buildingPrimitives, labels: () => [layers.labels], roads: () => layers.roadPrimitives,
    landcover: () => layers.landcoverPrimitives, trees: () => [layers.treePrimitive], cherries: () => layers.cherryPrimitives,
    boundary: () => [layers.boundaryPrimitive],
    pois: () => [layers.pois],
  };
  function setLayer(name, on) {
    if (name === "trees" && on) layers.loadTrees();
    for (const p of layerMap[name]()) if (p) p.show = on;
    const cb = document.querySelector(`[data-layer="${name}"]`);
    if (cb) cb.checked = on;
    if (name === "buildings") $("#btnBuildings").classList.toggle("on", on);
  }
  document.querySelectorAll("[data-layer]").forEach((cb) => { cb.onchange = () => setLayer(cb.dataset.layer, cb.checked); });
  // start with the 3D only: labels, icons and the boundary line are off until switched on in Layers;
  // light mode also leaves vegetation off (built on demand)
  if (LIGHT) document.querySelector('[data-layer="trees"]').checked = false;
  document.querySelectorAll("[data-layer]").forEach((cb) => { if (!cb.checked) setLayer(cb.dataset.layer, false); });
  if (!LIGHT) layers.loadTrees();
  const qb = $("#btnDetail");
  qb.classList.toggle("on", !LIGHT);
  qb.onclick = () => { safeSet("detail", LIGHT ? "full" : "light"); location.reload(); };
  $("#colorSel").onchange = (e) => { layers.setBuildingColorMode(e.target.value); $("#colorLegend").classList.toggle("hidden", e.target.value !== "status"); };

  // ---------------- bottom bar ----------------
  $("#btnReset").onclick = () => cam.flyHome();
  $("#btnBuildings").onclick = () => setLayer("buildings", !layers.buildingPrimitives[0].show);
  $("#btnImagery").onclick = () => {
    const next = state.imagery === "none" ? state.lastImagery : "none";
    sel.value = next; setImagery(next);
  };
  $("#btnElevation").onclick = () => applyViz(state.viz === "realistic" ? "elevation" : "realistic");
  $("#btnTerrainOnly").onclick = () => {
    state.terrainOnly = !state.terrainOnly;
    for (const n of ["buildings", "labels", "trees", "cherries"]) setLayer(n, !state.terrainOnly);
    $("#btnTerrainOnly").classList.toggle("on", state.terrainOnly);
  };
  $("#btnFullscreen").onclick = () => {
    if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.();
  };
  $("#toggleLeft").onclick = () => $("#left").classList.toggle("collapsed");
  if (isMobile) $("#left").classList.add("collapsed");
  document.querySelectorAll(".tab").forEach((t) => t.onclick = () => {
    $("#right").classList.add("hidden");   // details sit over the section content: a tab click returns to it
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("active", p.id === `tab-${t.dataset.tab}`));
  });

  // ---------------- overview ----------------
  const cs = summary.campus;
  $("#overviewStats").innerHTML = kv([
    ["Campus", `${esc(cs.name_ko)}<br><span class="dim">${esc(cs.name_en)}</span>`],
    ["Address", esc(cs.address)],
    ["Boundary", `${(cs.area_m2 / 1e4).toFixed(1)} ha · ${(cs.perimeter_m / 1000).toFixed(2)} km perimeter`],
    ["Buildings", `${cs.buildings_in_campus} university buildings`],
    ["Official map", `${cs.official_matched}/${cs.official_building_entries} buildings matched`],
    ["Elevation", `${cs.elevation.min.toFixed(0)}–${cs.elevation.max.toFixed(0)} m (relief ${cs.elevation.relief.toFixed(0)} m)`],
    ["Terrain", `FABDEM V1-2 · 1″ (${dem.meta.spacing_m.x.toFixed(1)} × ${dem.meta.spacing_m.y.toFixed(1)} m) with estimated local grades`],
    ["OSM data", esc(summary.osm_timestamp?.slice(0, 10))],
  ], true);

  // ---------------- building list & search ----------------
  const all = [...layers.buildings.values()];
  const label = (p) => (p.name_ko || p.official_name_ko || "Unnamed building").replace("경희대학교 국제캠퍼스 ", "");
  function renderList() {
    const q = $("#search").value.trim().toLowerCase();
    const items = all.filter((r) => {
      const p = r.props;
      if (!p.in_campus) return false;
      if (!q) return true;
      return [p.name_ko, p.name_en, p.official_name_ko, p.id, p.official_no && String(p.official_no), p.building_type]
        .some((s) => s && String(s).toLowerCase().includes(q));
    }).slice(0, 400);
    $("#buildingCount").textContent = `${items.length} building${items.length === 1 ? "" : "s"}${items.length === 400 ? " (first 400)" : ""}`;
    const ul = $("#buildingList");
    ul.innerHTML = items.map((r) => {
      const p = r.props;
      return `<li data-id="${esc(p.id)}" class="${layers.selected === p.id ? "sel" : ""}"><span class="no">${p.official_no ?? ""}</span>
        <span class="nm">${esc(label(p))}${p.name_en ? `<span class="en">${esc(p.name_en)}</span>` : ""}</span>
        <span class="h">${p.height_m.toFixed(0)} m${p.height_status === "estimated" ? "*" : ""}</span></li>`;
    }).join("");
    ul.querySelectorAll("li").forEach((li) => li.onclick = () => selectBuilding(li.dataset.id, true));
  }
  $("#search").oninput = () => { $("#right").classList.add("hidden"); renderList(); };
  $("#search").onkeydown = (e) => { if (e.key === "Enter") { const f = $("#buildingList li"); if (f) selectBuilding(f.dataset.id, true); } };
  renderList();

  // ---------------- details panel ----------------
  function selectBuilding(id, fly) {
    const rec = layers.buildings.get(id);
    if (!rec) return;
    layers.highlight(id);
    if (fly) cam.focusBuilding(rec);
    showBuilding(rec);
    renderList();
    history.replaceState(null, "", `#b=${encodeURIComponent(id)}`);
  }
  function showBuilding(rec) {
    const p = rec.props;
    const [lon, lat] = p.centroid;
    const tm = toEpsg5186(lon, lat);
    const N = rec.N;
    const conf = { documented: "documented", derived: "derived", estimated: "estimated" }[p.height_status];
    const osmUrl = `https://www.openstreetmap.org/${p.id}`;
    $("#details").innerHTML = `
      <h2>${esc(label(p))}</h2>
      <div class="sub">${p.name_en ? esc(p.name_en) + " · " : ""}${p.in_campus ? "Global Campus" : "Outside campus boundary (context)"}</div>
      ${kv([
        ["Official map no.", p.official_no ? `${p.official_no} · ${esc(p.official_name_ko)}` : "<span class='dim'>not matched</span>"],
        ["Identifier", p.construction ? `${esc(p.id)} <span class="dim">(not in OSM yet)</span>`
          : `<a href="${osmUrl}" target="_blank" rel="noopener">OSM ${esc(p.id)}</a>`],
        ...(p.construction ? [["Status", `${esc(p.construction.status)} <span class="badge estimated">planned</span> · groundbreaking ${esc(p.construction.groundbreaking)}, completion planned ${esc(p.construction.completion_planned)}`],
          ["Sources", p.construction.sources.map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">news ${i + 1}</a>`).join(" · ")]] : []),
        ["Type", esc(p.building_type)],
      ], true)}
      <div class="sec">Geometry</div>
      ${kv([
        ["Centroid (WGS84)", fmtLonLat(lon, lat)],
        ["EPSG:5186", `E ${tm.x.toFixed(2)} · N ${tm.y.toFixed(2)}`],
        ["Footprint area", `${p.footprint_area_m2.toLocaleString(undefined, { maximumFractionDigits: 0 })} m²`],
        ["Height", `${p.height_m.toFixed(1)} m <span class="badge ${conf}">${p.height_status}</span>`],
        ["Floors", p.levels ? (p.levels_status === "counted from photographs" ? `${p.levels} <span class="badge estimated">counted from photos</span>` : `${p.levels} <span class="badge documented">${esc(p.levels_source || "OSM")}</span>`) : "<span class='dim'>unknown</span>"],
        ["Roof", esc(rec.roofShape || p.roof_shape)],
        ...(rec.detailed ? [["Appearance", `${esc(rec.appearance || "stylised facade")} <span class="badge estimated">stylised</span>`]] : []),
        ...(rec.modelHeight ? [["Model height", `${rec.modelHeight.toFixed(1)} m <span class="badge estimated">illustrative</span>`]] : []),
      ], true)}
      <div class="sec">Elevation (orthometric, EGM2008)</div>
      ${kv([
        ["Ground min / max", `${p.ground_min_m.toFixed(1)} / ${p.ground_max_m.toFixed(1)} m`],
        ["Ground slope span", `${(p.ground_max_m - p.ground_min_m).toFixed(1)} m across footprint`],
        ["Roof top (est.)", `${(p.ground_min_m + p.height_m).toFixed(1)} m`],
        ["Geoid N", `${N.toFixed(2)} m (ellipsoidal = H + N)`],
      ], true)}
      <div class="sec">Provenance</div>
      ${kv([
        ["Footprint", esc(p.footprint_source)],
        ["Height source", esc(p.height_source)],
        ["Confidence", esc(p.height_confidence)],
        ["Ground", p.ground_adjusted ? "FABDEM V1-2 with an estimated site grade" : "FABDEM V1-2 sampled across the footprint"],
      ], true)}
      <div class="actions">
        <button id="dFocus">Focus</button><button id="dWalk">Walk here</button>
        <button id="dCopy">Copy coordinates</button>
      </div>`;
    $("#right").classList.remove("hidden");
    $("#dFocus").onclick = () => cam.focusBuilding(rec);
    $("#dWalk").onclick = () => {
      const s = Cesium.Cartographic.fromCartesian(rec.sphere.center);
      const off = rec.sphere.radius + 12;
      const lat2 = Cesium.Math.toDegrees(s.latitude) - off / 110950;
      const lon2 = Cesium.Math.toDegrees(s.longitude);
      cam.setMode("walk");
      viewer.camera.flyTo({ destination: Cesium.Cartesian3.fromDegrees(lon2, lat2, dem.heightEllipsoid(lon2, lat2) + 1.7), orientation: { heading: 0, pitch: 0.05, roll: 0 }, duration: 1.5 });
    };
    $("#dCopy").onclick = () => navigator.clipboard?.writeText(`${lat.toFixed(7)}, ${lon.toFixed(7)}`);
  }
  function showGeneric(title, rows) {
    $("#details").innerHTML = `<h2>${esc(title)}</h2>${kv(rows, true)}`;
    $("#right").classList.remove("hidden");
  }
  function showPoint(cart) {
    const c = Cesium.Cartographic.fromCartesian(cart);
    const lon = Cesium.Math.toDegrees(c.longitude), lat = Cesium.Math.toDegrees(c.latitude);
    const H = dem.heightOrtho(lon, lat), N = dem.geoidN(lon, lat), tm = toEpsg5186(lon, lat);
    const adjusted = Math.abs(H - dem.heightOrtho(lon, lat, false)) > 0.01;
    showGeneric("Terrain point", [
      ["WGS84", fmtLonLat(lon, lat)], ["EPSG:5186", `E ${tm.x.toFixed(2)} · N ${tm.y.toFixed(2)}`],
      ["Ground height", `${H.toFixed(2)} m (EGM2008)`], ["Ellipsoidal", `${(H + N).toFixed(2)} m (WGS84)`],
      ["Source", adjusted ? "Estimated local grade from FABDEM V1-2 and site references" :
        dem.contains(lon, lat) ? "FABDEM V1-2, bilinear (±2–5 m typical)" : "Outside the DEM window (faded)"],
    ]);
  }
  $("#closeRight").onclick = () => { $("#right").classList.add("hidden"); layers.highlight(null); renderList(); history.replaceState(null, "", location.pathname); };

  // ---------------- picking ----------------
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.canvas);
  handler.setInputAction((e) => {
    if (cam.isFree()) return;
    const picked = scene.pick(e.position);
    const id = picked?.id;
    if (id?.kind === "building" || id?.bid) return selectBuilding(id.bid, false);
    layers.highlight(null);
    if (id?.kind === "landmark") {
      const p = id.props;
      return showGeneric(p.name, [["OSM", `<a href="https://www.openstreetmap.org/${p.id}" target="_blank" rel="noopener">${p.id}</a> (position &amp; outline)`],
        ...(p.height ? [["Height", `${p.height} m <span class="badge documented">documented</span>`], ["Height source", esc(p.source)]] : [["Source", esc(p.source)]]),
        ["Ground (DTM)", `${p.ground.toFixed(1)} m`], ["Form", "modelled from photographs <span class='badge estimated'>illustrative</span>"]]);
    }
    if (id?.kind === "ground") {
      const p = id.props;
      const photoSurface = {
        "main-gate-paving": "Main gate paving", "main-gate-street": "Deogyeong-daero",
        "woojungwon-foreign-languages-walk": "Woojungwon to Foreign Languages walk",
      }[p.id];
      if (photoSurface) {
        return showGeneric(photoSurface, [["Source", "Estimated outline from campus photos and aerial imagery"]]);
      }
      return showGeneric(p.kind.replace("_", " "), [["OSM", p.id ? `<a href="https://www.openstreetmap.org/${p.id}" target="_blank" rel="noopener">${p.id}</a>` : "–"],
        ...(p.width ? [["Width", `${p.width} m`]] : []), ["Note", "surface on OSM geometry; markings are standard layouts fitted to the outline <span class='badge estimated'>illustrative</span>"]]);
    }
    if (id?.kind === "poi") {
      const p = id.props;
      return showGeneric(p.name || p.kind.replace("_", " "), [["Kind", p.kind], ["OSM", `<a href="https://www.openstreetmap.org/${p.id}" target="_blank" rel="noopener">${p.id}</a>`],
        ["DTM height", `${p.dtm_m} m`], ...(p.ele_osm ? [["OSM ele tag", `${p.ele_osm} m (Δ ${(p.dtm_m - p.ele_osm).toFixed(1)} m)`]] : [])]);
    }
    if (id?.kind === "landcover" || id?.kind === "road" || id?.kind === "boundary") {
      const p = id.props;
      if (id.kind === "road") return showGeneric(p.name || p.highway, [["Class", p.highway], ["Width", `${p.width_m} m · ${esc(p.width_status)}`], ["Surface", p.surface || "–"], ["Length", p.length_m ? `${p.length_m} m` : "area"], ["OSM", p.id]]);
      if (id.kind === "boundary") return showGeneric(p.name_ko, [["Area", `${(p.area_m2 / 1e4).toFixed(2)} ha`], ["Perimeter", `${p.perimeter_m} m`], ["Source", esc(p.source)]]);
      return showGeneric(p.name || p.official_name_ko || p.class, [["Class", p.class], ["OSM tag", p.osm_tag], ["Area", `${p.area_m2.toLocaleString()} m²`], ["Official map no.", p.official_no ?? "–"], ["OSM", p.id]]);
    }
    const cart = scene.pickPosition(e.position) || viewer.camera.pickEllipsoid(e.position);
    const ray = viewer.camera.getPickRay(e.position);
    const g = ray && globe.pick(ray, scene);
    if (g || cart) showPoint(g || cart);
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  // cursor readout
  let pending = null;
  handler.setInputAction((e) => { pending = e.endPosition; }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  scene.postRender.addEventListener(() => {
    const c = viewer.camera.positionCartographic;
    const clon = Cesium.Math.toDegrees(c.longitude), clat = Cesium.Math.toDegrees(c.latitude);
    const agl = c.height - dem.heightEllipsoid(clon, clat);
    let txt = `cam ${agl.toFixed(0)} m AGL · heading ${Cesium.Math.toDegrees(viewer.camera.heading).toFixed(0)}°`;
    if (pending) {
      const ray = viewer.camera.getPickRay(pending);
      const g = ray && globe.pick(ray, scene);
      if (g) {
        const k = Cesium.Cartographic.fromCartesian(g);
        const lon = Cesium.Math.toDegrees(k.longitude), lat = Cesium.Math.toDegrees(k.latitude);
        txt = `${fmtLonLat(lon, lat)} · DTM ${dem.heightOrtho(lon, lat).toFixed(1)} m · ${txt}`;
      }
    }
    $("#cursor").textContent = txt;
  });

  // ---------------- about / provenance ----------------
  $("#openAbout").onclick = () => { $("#aboutBody").innerHTML = aboutHtml(summary, dem); $("#about").showModal(); };

  applyViz("realistic");
  // deep link #b=<osm id>
  const m = location.hash.match(/b=([^&]+)/);
  const whenReady = () => new Promise((res) => {
    const chk = () => (layers.buildingsReady ? res() : setTimeout(chk, 150));
    chk();
  });
  await whenReady();
  layers.setBuildingColorMode("realistic");
  if (m) selectBuilding(decodeURIComponent(m[1]), true);
  $("#loading").classList.add("done");
  document.body.dataset.ready = "1";
}

const isTouch = matchMedia("(pointer: coarse)").matches;

/** Start the campus walk just outside the main gate, looking in through the opening. */
function gateWalkStart(details) {
  const g = details?.gate;
  if (!g) return null;
  const [ax, ay] = g.axis_en;
  const mid = (g.opening_m[0] + g.opening_m[1]) / 2;
  const mx = 111320 * Math.cos(g.center[1] * Math.PI / 180), my = 110950;
  const cE = ax * mid, cN = ay * mid;
  // perpendicular pointing towards the campus centre
  let pE = -ay, pN = ax;
  const toE = (127.0818 - g.center[0]) * mx, toN = (37.2427 - g.center[1]) * my;
  if (pE * toE + pN * toN < 0) { pE = -pE; pN = -pN; }
  const back = 20;
  return { lon: g.center[0] + (cE - pE * back) / mx, lat: g.center[1] + (cN - pN * back) / my, heading: Math.atan2(pE, pN) };
}

/** Earth-coloured side walls along the campus cut so the cropped terrain reads as a solid block. */
function addDioramaSides(viewer, dem, rings) {
  for (const r of rings) addSideWall(viewer, dem, r);
}
function addSideWall(viewer, dem, ring) {
  const pts = [];
  for (let k = 0; k < ring.length - 1; k++) {
    const [a, b] = [ring[k], ring[k + 1]];
    const d = Math.hypot((b[0] - a[0]) * 88600, (b[1] - a[1]) * 110950);
    const n = Math.max(1, Math.ceil(d / 8));
    for (let j = 0; j < n; j++) pts.push([a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n]);
  }
  pts.push(ring[0]);
  const hs = pts.map(([lo, la]) => dem.heightEllipsoid(lo, la));
  const floor = Math.min(...hs) - 35;
  const positions = pts.map(([lo, la], i) => Cesium.Cartesian3.fromDegrees(lo, la, hs[i]));
  const mk = (minH, maxH, css) => new Cesium.GeometryInstance({
    geometry: new Cesium.WallGeometry({ positions, minimumHeights: minH, maximumHeights: maxH, vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT }),
    attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString(css)) },
  });
  viewer.scene.primitives.add(new Cesium.Primitive({
    geometryInstances: [
      mk(hs.map(() => floor), hs.map((h) => h - 2.2), "#6e5640"),
      mk(hs.map((h) => h - 2.2), hs.map((h) => h - 0.3), "#4f5b33"),
    ],
    appearance: new Cesium.PerInstanceColorAppearance({ translucent: false, closed: false, faceForward: true }),
    asynchronous: false,
  }));
}

function kv(rows, raw = false) {
  return `<div class="kv">${rows.map(([k, v]) => `<div class="k">${esc(k)}</div><div class="v">${raw ? v : esc(v)}</div>`).join("")}</div>`;
}

function aboutHtml(s, dem) {
  const ds = s.datasets.map((d) => `<tr><td><b>${esc(d.name)}</b><br><span class="dim">${esc(d.role)}</span></td>
    <td>${esc(d.resolution)}<br><span class="dim">${esc(d.crs)}</span></td><td>${esc(d.date)}</td>
    <td>${esc(d.license)}</td><td>${esc(d.limitations)}</td></tr>`).join("");
  const checks = s.checks.map((c) => `<tr><td>${esc(c.name)}</td><td><span class="badge ${c.status === "pass" ? "verified" : "approx"}">${esc(c.status)}</span></td><td>${esc(c.detail)}</td></tr>`).join("");
  return `<h2>Data sources, accuracy &amp; limitations</h2>
  <p>Geographic correctness comes first. Every feature in this scene comes from a real dataset listed below, and nothing is procedurally invented except vegetation instances, which are labelled as a visual approximation. The full machine-readable record for each feature is in <a href="data/accuracy_report.json" target="_blank">accuracy_report.json</a>, and the dataset provenance is in <a href="data/summary.json" target="_blank">summary.json</a>.</p>
  <h3>Datasets</h3><table><tr><th>Dataset</th><th>Resolution / CRS</th><th>Date</th><th>Licence</th><th>Known limitations</th></tr>${ds}</table>
  <h3>Automated validation checks</h3><table><tr><th>Check</th><th>Status</th><th>Result</th></tr>${checks}</table>
  <h3>Coordinate handling</h3>
  <p>Horizontal: WGS84 geographic (EPSG:4326). The EPSG:5186 readouts use a Krüger-series Transverse Mercator implementation that was checked against PROJ to better than 0.01 mm. Vertical: the DEM heights are EGM2008 orthometric heights (EPSG:3855). Cesium needs WGS84 ellipsoidal heights, so the viewer adds the EGM2008 undulation N (${dem.meta.geoid.N_m.flat().reduce((a, b) => Math.min(a, b)).toFixed(2)}–${dem.meta.geoid.N_m.flat().reduce((a, b) => Math.max(a, b)).toFixed(2)} m across the terrain window), bilinearly interpolated from a PROJ-derived grid. Terrain, buildings, roads and imagery all use the same transformations.</p>
  <h3>What this model is not</h3>
  <p>It is not survey-grade. The terrain resolution is about 30 m, so short retaining walls, stairs and building platforms cut into slopes are smoothed. Building masses are LOD1 extrusions with flat roofs. Most campus building heights are <b>estimated</b>, because neither OSM nor the official campus pages publish heights or floor counts for them. Documented values can be added in <code>scripts/height_overrides.json</code>, for example from the 건축물대장 building register, and the pipeline re-run. Imagery is streamed from third-party tile services under their own terms, and it may be misaligned with OSM footprints by a few metres.</p>`;
}

function safeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function safeSet(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } }

main().catch((e) => {
  console.error(e);
  setLoading(`Failed to start: ${e.message}`);
  document.body.dataset.ready = "error";
});
