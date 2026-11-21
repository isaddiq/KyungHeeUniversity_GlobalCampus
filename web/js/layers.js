// Geographic feature layers built from the preprocessed GeoJSON (OSM-derived) and DEM.
import { buildKhuPrimitives } from "./khu_buildings.js";
import { buildTrees } from "./trees.js";
import { buildGroundObjects } from "./ground_objects.js";
const Cesium = window.Cesium;

export async function loadJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

const C = (css, a = 1) => Cesium.Color.fromCssColorString(css).withAlpha(a);

export const BUILDING_STYLES = {
  realistic: (p) => p.in_campus ? C("#ece6da") : (p.building_type === "apartments" ? C("#d9dcdf") : C("#cfcac2")),
  status: (p) => ({ documented: C("#2fa36b"), derived: C("#3b7fd1"), estimated: C("#e08a2c") }[p.height_status] || C("#999")),
  height: (p) => {
    const t = Math.min(1, p.height_m / 80);
    return Cesium.Color.lerp(C("#fde9a9"), C("#b4235a"), t, new Cesium.Color());
  },
};
const HIGHLIGHT = C("#ffc933");

const ROAD_STYLE = {
  trunk: ["#f0b35a", 0.85], primary: ["#f3c46b", 0.85], secondary: ["#f5d27e", 0.8],
  tertiary: ["#f7e0a0", 0.75], residential: ["#ffffff", 0.6], unclassified: ["#ffffff", 0.6],
  living_street: ["#f2f2f2", 0.55], service: ["#e8e8e8", 0.55], pedestrian: ["#d8cfe8", 0.65],
  footway: ["#f28f8f", 0.7], path: ["#c98f5a", 0.75], steps: ["#ff5a5a", 0.9], cycleway: ["#7fb3ff", 0.7],
  track: ["#b08a5a", 0.7],
};
const MAJOR = new Set(["trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link", "residential", "unclassified", "living_street", "service"]);

const LANDCOVER_STYLE = {
  forest: ["#2f6b33", 0.55], scrub: ["#5c8a3a", 0.5], grass: ["#7fbf5a", 0.5], garden: ["#a3d36b", 0.55],
  park: ["#9ccf7e", 0.35], golf: ["#9fd48c", 0.4], sport: ["#d9734a", 0.55], parking: ["#8d8d99", 0.55],
  water: ["#3d8fd6", 0.7], residential: ["#c9b7a6", 0.25], industrial: ["#b6a1c4", 0.3],
  construction: ["#c7b27a", 0.35], cemetery: ["#a6bf9c", 0.4], farmland: ["#d8cf8a", 0.4],
  school: ["#e6d7a6", 0.25], plaza: ["#e3dccf", 0.6],
};

function ringsOf(geom) {
  if (geom.type === "Polygon") return [geom.coordinates];
  if (geom.type === "MultiPolygon") return geom.coordinates;
  return [];
}

function hierarchy(poly) {
  const toPos = (ring) => Cesium.Cartesian3.fromDegreesArray(ring.slice(0, -1).flat());
  return new Cesium.PolygonHierarchy(toPos(poly[0]), poly.slice(1).map((h) => new Cesium.PolygonHierarchy(toPos(h))));
}

export class CampusLayers {
  constructor(viewer, dem, { mobile }) {
    this.viewer = viewer;
    this.dem = dem;
    this.mobile = mobile;
    this.buildings = new Map(); // id -> {props, feature, parts: [idObj], sphere}
    this.selected = null;
    this.colorMode = "realistic";
    this.footprintIndex = [];
  }

  async load(base, onProgress = () => {}) {
    // campus-only browser subsets (scripts/build_web_subset.py); the full files are the fallback
    const sub = (name) => loadJSON(`${base}/${name}_campus.geojson`).catch(() => loadJSON(`${base}/${name}.geojson`));
    let [boundary, buildings, roads, landcover, pois, details] = await Promise.all([
      loadJSON(`${base}/boundary.geojson`), sub("buildings"), sub("roads"), sub("landcover"),
      loadJSON(`${base}/pois.geojson`), loadJSON(`${base}/campus_details.json`).catch(() => null),
    ]);
    const ground = await loadJSON(`${base}/ground.json`).catch(() => null);
    this.details = details;
    // crop: keep only the university (campus boundary + 30 m)
    const clipRings = details?.clip?.rings ?? null;
    this.inClip = (lon, lat) => !clipRings || clipRings.some((r) => pointInRing(lon, lat, r));
    buildings = { ...buildings, features: buildings.features.filter((f) => f.properties.in_campus) };
    roads = { ...roads, features: roads.features.filter((f) => f.properties.in_campus) };
    landcover = { ...landcover, features: landcover.features.filter((f) => f.properties.in_campus) };
    pois = { ...pois, features: pois.features.filter((f) => this.inClip(...f.geometry.coordinates)) };
    this.boundaryFC = boundary;
    onProgress("Building terrain-draped layers…");
    if (ground) this.addGround(ground);
    else { this.addLandcover(landcover); this.addRoads(roads); this.landcoverPrimitives = [this.landcoverPrimitive]; }
    this.addBoundary(boundary);
    onProgress("Extruding building footprints…");
    this.addBuildings(buildings);
    this.addLabels();
    this.addPois(pois);
    // vegetation is added after the campus is on screen, in small chunks between frames (it used to block
    // the main thread for ~3 s); treePrimitive is a collection so layer toggles work while it fills
    this.treePrimitive = this.viewer.scene.primitives.add(new Cesium.PrimitiveCollection());
    this.treeCount = 0;
    this.base = base;
    return { boundary, buildings };
  }

  /** Builds the vegetation once (light mode skips this until vegetation is switched on). */
  loadTrees() {
    const base = this.base;
    return this.treesReady ??= (async () => {
      let meta, buf;
      try {
        meta = await loadJSON(`${base}/trees_campus.json`);
        buf = await (await fetch(`${base}/trees_campus.bin`)).arrayBuffer();
      } catch {
        meta = await loadJSON(`${base}/trees.json`);
        buf = await (await fetch(`${base}/trees.bin`)).arrayBuffer();
      }
      await new Promise((r) => setTimeout(r, 250));
      this.treeCount = await buildTrees(this.viewer, this.dem, meta, new Float32Array(buf), this.inClip, this.mobile, this.treePrimitive);
    })();
  }

  // ---------------------------------------------------------------- buildings
  addBuildings(fc) {
    const instances = [];
    const campusRecs = [];
    const noCollide = new Set([this.details?.gate?.id, this.details?.amphitheatre?.id].filter(Boolean));
    for (const f of fc.features) {
      const p = f.properties;
      const [clon, clat] = p.centroid;
      const N = this.dem.geoidN(clon, clat);
      const base = p.ground_min_m - 1.5 + N; // embed slightly: no floating on sloped sites
      const top = p.ground_min_m + p.height_m + N;
      const rec = { props: p, feature: f, parts: [], N, base, top, positions: [], detailed: p.in_campus };
      const courtyard = this.details?.photo_buildings?.[p.id]?.open_courtyard;
      ringsOf(f.geometry).forEach((poly, k) => {
        const id = { bid: p.id, part: k, kind: "building" };
        rec.parts.push(id);
        const h = hierarchy(poly);
        rec.positions.push(...h.positions);
        if (!noCollide.has(p.id)) {
          const holes = poly.slice(1);
          if (courtyard) holes.push(courtyard);
          this.footprintIndex.push({ id: p.id, ring: poly[0], holes, bbox: bboxOf(poly[0]) });
        }
        if (rec.detailed) return; // campus buildings get the enhanced facade model
        instances.push(new Cesium.GeometryInstance({
          id,
          geometry: new Cesium.PolygonGeometry({
            polygonHierarchy: h, height: base, extrudedHeight: top,
            vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT,
          }),
          attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(BUILDING_STYLES[this.colorMode](p)) },
        }));
      });
      const s = Cesium.BoundingSphere.fromPoints(rec.positions);
      const mid = Cesium.Cartographic.fromCartesian(s.center);
      rec.sphere = new Cesium.BoundingSphere(
        Cesium.Cartesian3.fromRadians(mid.longitude, mid.latitude, (base + top) / 2),
        Math.max(s.radius, (top - base) / 2) + 5);
      this.buildings.set(p.id, rec);
      if (rec.detailed) campusRecs.push(rec);
    }
    this.buildingPrimitive = instances.length === 0 ? null : this.viewer.scene.primitives.add(new Cesium.Primitive({
      geometryInstances: instances,
      appearance: new Cesium.PerInstanceColorAppearance({ translucent: false, closed: true }),
      shadows: this.mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.ENABLED,
      releaseGeometryInstances: true,
      asynchronous: true,
    }));
    for (const rec of this.buildings.values()) if (!rec.detailed) rec.primitive = this.buildingPrimitive;
    this.khuPrimitives = buildKhuPrimitives(this.viewer, this.dem, campusRecs, this.details, this.mobile);
    this.buildingPrimitives = [this.buildingPrimitive, ...this.khuPrimitives].filter(Boolean);
  }

  get buildingsReady() { return this.buildingPrimitives.every((p) => p.ready); }

  colorFor(rec, selected) {
    if (rec.detailed) {
      if (selected) return HIGHLIGHT.withAlpha(0.38);
      if (this.colorMode === "realistic") return null;
      return BUILDING_STYLES[this.colorMode](rec.props).withAlpha(0.82);
    }
    return selected ? HIGHLIGHT : BUILDING_STYLES[this.colorMode](rec.props);
  }

  setBuildingColorMode(mode) {
    this.colorMode = mode;
    if (!this.buildingsReady) return;
    for (const rec of this.buildings.values()) this._paint(rec, this.colorFor(rec, this.selected === rec.props.id));
  }

  _paint(rec, color) {
    const prim = rec.primitive;
    if (!prim?.ready) return;
    rec.parts.forEach((id, k) => {
      const a = prim.getGeometryInstanceAttributes(id);
      if (!a) return;
      if (rec.tintMode === "replace") {
        rec.partColors ??= rec.parts.map(() => null);
        rec.partColors[k] ??= Cesium.Color.fromBytes(a.color[0], a.color[1], a.color[2], a.color[3]);
      }
      let c = color;
      if (!c) c = rec.partColors ? rec.partColors[k] : new Cesium.Color(1, 1, 1, 0);
      else if (rec.tintMode === "replace") c = Cesium.Color.lerp(rec.partColors[k], c.withAlpha(1), 0.55, new Cesium.Color());
      a.color = Cesium.ColorGeometryInstanceAttribute.toValue(c, a.color);
    });
  }

  highlight(id) {
    if (!this.buildingsReady) return;
    if (this.selected && this.buildings.has(this.selected)) {
      const prev = this.buildings.get(this.selected);
      this._paint(prev, this.colorFor(prev, false));
    }
    this.selected = id;
    if (id && this.buildings.has(id)) { const r = this.buildings.get(id); this._paint(r, this.colorFor(r, true)); }
  }

  /** true when lon/lat is inside any building footprint (used for walk-mode collision) */
  insideBuilding(lon, lat) {
    for (const f of this.footprintIndex) {
      const b = f.bbox;
      if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
      if (pointInRing(lon, lat, f.ring) && !f.holes.some((hole) => pointInRing(lon, lat, hole))) return f.id;
    }
    return null;
  }

  // ---------------------------------------------------------------- labels
  addLabels() {
    this.labels = this.viewer.scene.primitives.add(new Cesium.LabelCollection());
    for (const rec of this.buildings.values()) {
      const p = rec.props;
      if (!p.in_campus || !(p.official_name_ko || p.name_ko)) continue;
      const [lon, lat] = p.centroid;
      this.labels.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, rec.top + 4),
        text: (p.official_no ? `${p.official_no}  ` : "") + (p.name_ko || p.official_name_ko).replace("경희대학교 국제캠퍼스 ", ""),
        font: "600 13px 'Noto Sans KR', 'Malgun Gothic', sans-serif",
        fillColor: Cesium.Color.WHITE,
        outlineColor: Cesium.Color.fromCssColorString("#111"),
        outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 4200),
        scaleByDistance: new Cesium.NearFarScalar(250, 1.05, 4000, 0.62),
        disableDepthTestDistance: 0, // labels are hidden behind structures and terrain
        id: { bid: p.id, kind: "building" },
      });
      if (p.name_en) this.labels.add({      // English name: second, smaller line, only when close enough to read
        position: Cesium.Cartesian3.fromDegrees(lon, lat, rec.top + 4),
        text: p.name_en,
        font: "500 11.5px 'IBM Plex Sans KR', 'Noto Sans KR', sans-serif",
        fillColor: Cesium.Color.fromCssColorString("#f3f3f0"),
        outlineColor: Cesium.Color.fromCssColorString("#111"),
        outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.TOP,
        pixelOffset: new Cesium.Cartesian2(0, 2),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 900),
        scaleByDistance: new Cesium.NearFarScalar(250, 1.0, 900, 0.8),
        disableDepthTestDistance: 0,
        id: { bid: p.id, kind: "building" },
      });
    }
  }

  // ---------------------------------------------------------------- roads
  addRoads(fc) {
    const major = [], minor = [], areas = [];
    for (const f of fc.features) {
      const p = f.properties;
      if (p.tunnel === "yes" || p.tunnel === "building_passage") continue; // underground: not draped
      const [css, a] = ROAD_STYLE[p.highway] || ["#dddddd", 0.6];
      const color = Cesium.ColorGeometryInstanceAttribute.fromColor(C(css, a));
      if (f.geometry.type === "Polygon") {
        areas.push(new Cesium.GeometryInstance({
          id: { kind: "road", props: p },
          geometry: new Cesium.PolygonGeometry({ polygonHierarchy: hierarchy(f.geometry.coordinates) }),
          attributes: { color },
        }));
        continue;
      }
      const coords = f.geometry.coordinates;
      if (coords.length < 2) continue;
      const inst = new Cesium.GeometryInstance({
        id: { kind: "road", props: p },
        geometry: new Cesium.GroundPolylineGeometry({
          positions: Cesium.Cartesian3.fromDegreesArray(coords.flat()),
          width: Math.max(1.2, p.width_m),
        }),
        attributes: { color },
      });
      (MAJOR.has(p.highway) ? major : minor).push(inst);
    }
    const prims = this.viewer.scene.primitives;
    this.roadPrimitives = [];
    if (areas.length) this.roadPrimitives.push(prims.add(new Cesium.GroundPrimitive({
      geometryInstances: areas, classificationType: Cesium.ClassificationType.TERRAIN,
      appearance: new Cesium.PerInstanceColorAppearance({ flat: true, translucent: true }),
    })));
    for (const set of [major, minor]) if (set.length) this.roadPrimitives.push(prims.add(new Cesium.GroundPolylinePrimitive({
      geometryInstances: set, classificationType: Cesium.ClassificationType.TERRAIN,
      appearance: new Cesium.PolylineColorAppearance({ translucent: true }),
    })));
  }

  // ---------------------------------------------------------------- ground surfaces (fields, courts, parking, roads, markings)
  addGround(g) {
    const FILL = { grass: "#6e9a4c", garden: "#7cab55", plaza: "#dcd7cb", paving: "#d4cec1", dirt: "#c6a57b", turf: "#3d9140",
      court_surround: "#4d7f69", court_out: "#3f7a5c", court_in: "#3a6d9c", court_bb: "#c4703e", parking: "#56595d", forest: "#4b5e35", water: "#4f8fb8",
      turf2: "#4aa047", court_bbg: "#3fae7c", court_key: "#c9654b", brick: "#c48c78",
      asphalt: "#4a4d51", gravel: "#bba98a", path: "#b99c76", steps: "#d2ccbf", asphalt_red: "#a85a4a", tread: "#8a857b",
      line_white: "#f4f4f4", line_yellow: "#f2c230", line_dark: "#262626", sidewalk: "#9b625b", kerb: "#d3cfc6",
      terrace: "#a9a8a1", sand: "#d3b98e", field: "#6a9a46" };
    const LINE = { road_asphalt: "#4a4d51", road_paving: "#d8d2c5", road_gravel: "#bba98a", road_path: "#b99c76", road_steps: "#d2ccbf",
      road_asphalt_red: "#a85a4a", centre_yellow: "#f2c230", centre_white: "#f4f4f4", paint: "#ffffff", net: "#262626",
      stall: "#f0f0f0", tread: "#8a857b" };
    const col = (c) => Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString(c));
    const fills = [], forest = [];
    for (const f of g.fills) {
      try {
        const geometry = new Cesium.PolygonGeometry({ polygonHierarchy: new Cesium.PolygonHierarchy(
          Cesium.Cartesian3.fromDegreesArray(f.c[0].slice(0, -1).flat()),
          f.c.slice(1).map((h) => new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(h.slice(0, -1).flat())))) });
        // a polygon whose geometry comes out empty is dropped by Cesium inside the batch, which shifts the
        // per-instance colours/ids of the following instances (e.g. a plaza drawn in the park's grass colour)
        if (!Cesium.PolygonGeometry.createGeometry(geometry)) continue;
        (f.k === "forest" ? forest : fills).push(new Cesium.GeometryInstance({
          id: { kind: "ground", props: { kind: f.k, id: f.src } }, geometry,
          attributes: { color: col(FILL[f.k] || "#999999") },
        }));
      } catch { /* degenerate polygon */ }
    }
    const surf = [], marks = [];
    for (const l of g.lines) {
      if (l.c.length < 2) continue;
      const inst = new Cesium.GeometryInstance({
        id: l.k.startsWith("road_") ? { kind: "ground", props: { kind: l.k.replace("road_", "") + " surface", id: l.src, width: l.w } } : undefined,
        geometry: new Cesium.GroundPolylineGeometry({ positions: Cesium.Cartesian3.fromDegreesArray(l.c.flat()), width: l.w }),
        attributes: { color: col(LINE[l.k] || "#ffffff") },
      });
      (l.k.startsWith("road_") ? surf : marks).push(inst);
    }
    const prims = this.viewer.scene.primitives;
    const T = Cesium.ClassificationType.TERRAIN;
    this.forestPrimitive = forest.length ? prims.add(new Cesium.GroundPrimitive({
      geometryInstances: forest, classificationType: T,
      appearance: new Cesium.PerInstanceColorAppearance({ flat: true, translucent: false }), show: false,
    })) : null;
    // one primitive per surface kind: if Cesium drops a degenerate instance inside a batch, the per-instance
    // attributes of the following instances shift; within a single-colour batch that cannot recolour anything
    const byKind = new Map();
    for (const inst of fills) { const k = inst.id.props.kind; if (!byKind.has(k)) byKind.set(k, []); byKind.get(k).push(inst); }
    this.landcoverPrimitives = [...byKind.values()].map((arr) => prims.add(new Cesium.GroundPrimitive({
      geometryInstances: arr, classificationType: T,
      appearance: new Cesium.PerInstanceColorAppearance({ flat: true, translucent: false }),
    })));
    this.roadPrimitives = [surf, marks].filter((a) => a.length).map((a) => prims.add(new Cesium.GroundPolylinePrimitive({
      geometryInstances: a, classificationType: T, appearance: new Cesium.PolylineColorAppearance({ translucent: false }),
    })));
    this.groundObjectPrimitives = buildGroundObjects(this.viewer, this.dem, g.objects, this.mobile);
  }

  // ---------------------------------------------------------------- landcover
  addLandcover(fc) {
    const inst = [];
    for (const f of fc.features) {
      const p = f.properties;
      const [css, a] = LANDCOVER_STYLE[p.class] || ["#999999", 0.3];
      inst.push(new Cesium.GeometryInstance({
        id: { kind: "landcover", props: p },
        geometry: new Cesium.PolygonGeometry({ polygonHierarchy: hierarchy(f.geometry.coordinates) }),
        attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(C(css, a)) },
      }));
    }
    this.landcoverPrimitive = this.viewer.scene.primitives.add(new Cesium.GroundPrimitive({
      geometryInstances: inst, classificationType: Cesium.ClassificationType.TERRAIN,
      appearance: new Cesium.PerInstanceColorAppearance({ flat: true, translucent: true }),
      show: false,
    }));
  }

  // ---------------------------------------------------------------- boundary
  addBoundary(fc) {
    const inst = [];
    for (const f of fc.features) {
      for (const poly of ringsOf(f.geometry)) {
        inst.push(new Cesium.GeometryInstance({
          id: { kind: "boundary", props: f.properties },
          geometry: new Cesium.GroundPolylineGeometry({
            positions: Cesium.Cartesian3.fromDegreesArray(poly[0].flat()), width: 4.5, loop: false,
          }),
          attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(C("#ff6a3d", 0.95)) },
        }));
      }
    }
    this.boundaryPrimitive = this.viewer.scene.primitives.add(new Cesium.GroundPolylinePrimitive({
      geometryInstances: inst, classificationType: Cesium.ClassificationType.TERRAIN,
      appearance: new Cesium.PolylineColorAppearance({ translucent: true }),
    }));
  }

  // ---------------------------------------------------------------- POIs
  addPois(fc) {
    this.pois = this.viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
    const col = { entrance: "#ff4d4d", bus_stop: "#3fa9ff", peak: "#ffffff", tree: "#58d36b" };
    for (const f of fc.features) {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      const h = this.dem.heightEllipsoid(lon, lat) + (p.kind === "tree" ? 2 : 1.5);
      this.pois.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, h),
        color: C(col[p.kind] || "#fff"), pixelSize: p.kind === "peak" ? 9 : 7,
        outlineColor: Cesium.Color.BLACK, outlineWidth: 1.5,
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 3000),
        disableDepthTestDistance: 1200,
        id: { kind: "poi", props: p },
      });
    }
  }

  // ---------------------------------------------------------------- trees
  /** Visual vegetation instances. Positions are synthetic (see trees.json), NOT surveyed. */
  addTrees(meta, arr) {
    const stride = 4;
    let count = arr.length / stride;
    const keepEvery = this.mobile ? 3 : 1;
    const c = Cesium.Cartesian3.fromDegrees(127.082, 37.243);
    const carto = Cesium.Cartographic.fromCartesian(c);
    const lam = carto.longitude, phi = carto.latitude;
    const E = [-Math.sin(lam), Math.cos(lam), 0];
    const Nn = [-Math.sin(phi) * Math.cos(lam), -Math.sin(phi) * Math.sin(lam), Math.cos(phi)];
    const U = [Math.cos(phi) * Math.cos(lam), Math.cos(phi) * Math.sin(lam), Math.sin(phi)];
    const SEG = 6;
    const crownV = 2 + SEG * 2, trunkV = 8;
    const groups = [[], [], []];
    for (let i = 0; i < count; i += keepEvery) {
      if (!this.inClip(meta.origin_lon + arr[i * stride], meta.origin_lat + arr[i * stride + 1])) continue;
      groups[(i * 2654435761 >>> 0) % 3].push(i);
    }
    const shades = ["#3d6b2f", "#4f7d35", "#2f5a2a"];
    const crownInstances = [];
    const trunkPos = [], trunkNrm = [], trunkIdx = [];
    const tmp = new Cesium.Cartesian3();
    groups.forEach((g, gi) => {
      const pos = new Float64Array(g.length * crownV * 3);
      const nrm = new Float32Array(g.length * crownV * 3);
      const idx = new Uint32Array(g.length * SEG * 4 * 3);
      let pv = 0, pi = 0;
      g.forEach((i) => {
        const lon = meta.origin_lon + arr[i * stride], lat = meta.origin_lat + arr[i * stride + 1];
        const H = arr[i * stride + 2], th = arr[i * stride + 3];
        const ground = H + this.dem.geoidN(lon, lat);
        Cesium.Cartesian3.fromDegrees(lon, lat, ground - 0.3, undefined, tmp);
        const bx = tmp.x, by = tmp.y, bz = tmp.z;
        const r = th * 0.28 + 0.6;
        const crownBase = th * 0.28, ring1 = th * 0.5, ring2 = th * 0.78;
        const rot = (i % 7) * 0.4;
        const v0 = pv / 3;
        const put = (e, n, u, ne, nn, nu) => {
          pos[pv] = bx + E[0] * e + Nn[0] * n + U[0] * u;
          pos[pv + 1] = by + E[1] * e + Nn[1] * n + U[1] * u;
          pos[pv + 2] = bz + E[2] * e + Nn[2] * n + U[2] * u;
          const nx = E[0] * ne + Nn[0] * nn + U[0] * nu, ny = E[1] * ne + Nn[1] * nn + U[1] * nu, nz = E[2] * ne + Nn[2] * nn + U[2] * nu;
          const l = Math.hypot(nx, ny, nz) || 1;
          nrm[pv] = nx / l; nrm[pv + 1] = ny / l; nrm[pv + 2] = nz / l;
          pv += 3;
        };
        put(0, 0, crownBase, 0, 0, -1);
        for (let k = 0; k < SEG; k++) { const a = rot + k * 2 * Math.PI / SEG; put(Math.cos(a) * r, Math.sin(a) * r, ring1, Math.cos(a), Math.sin(a), 0.1); }
        for (let k = 0; k < SEG; k++) { const a = rot + (k + 0.5) * 2 * Math.PI / SEG; put(Math.cos(a) * r * 0.72, Math.sin(a) * r * 0.72, ring2, Math.cos(a), Math.sin(a), 0.6); }
        put(0, 0, th, 0, 0, 1);
        for (let k = 0; k < SEG; k++) {
          const a = v0 + 1 + k, b = v0 + 1 + (k + 1) % SEG, a2 = v0 + 1 + SEG + k, b2 = v0 + 1 + SEG + (k + 1) % SEG, top = v0 + 1 + 2 * SEG;
          idx[pi++] = v0; idx[pi++] = b; idx[pi++] = a;
          idx[pi++] = a; idx[pi++] = b; idx[pi++] = a2;
          idx[pi++] = b; idx[pi++] = b2; idx[pi++] = a2;
          idx[pi++] = a2; idx[pi++] = b2; idx[pi++] = top;
        }
        if (!this.mobile) { // trunk: 4-sided prism
          const t0 = trunkPos.length / 3, tr = Math.max(0.15, th * 0.025);
          for (const u of [0, crownBase + 0.5]) for (let k = 0; k < 4; k++) {
            const a = k * Math.PI / 2 + rot, e = Math.cos(a) * tr, n = Math.sin(a) * tr;
            trunkPos.push(bx + E[0] * e + Nn[0] * n + U[0] * u, by + E[1] * e + Nn[1] * n + U[1] * u, bz + E[2] * e + Nn[2] * n + U[2] * u);
            trunkNrm.push(E[0] * Math.cos(a) + Nn[0] * Math.sin(a), E[1] * Math.cos(a) + Nn[1] * Math.sin(a), E[2] * Math.cos(a) + Nn[2] * Math.sin(a));
          }
          for (let k = 0; k < 4; k++) { const a = t0 + k, b = t0 + (k + 1) % 4; trunkIdx.push(a, b, a + 4, b, b + 4, a + 4); }
        }
      });
      if (!g.length) return;
      crownInstances.push(new Cesium.GeometryInstance({
        id: { kind: "trees" },
        geometry: makeGeometry(pos, nrm, idx),
        attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(C(shades[gi])) },
      }));
    });
    if (trunkPos.length) crownInstances.push(new Cesium.GeometryInstance({
      id: { kind: "trees" },
      geometry: makeGeometry(new Float64Array(trunkPos), new Float32Array(trunkNrm), new Uint32Array(trunkIdx)),
      attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(C("#5a4330")) },
    }));
    this.treeCount = groups.reduce((a, g) => a + g.length, 0);
    this.treePrimitive = this.viewer.scene.primitives.add(new Cesium.Primitive({
      geometryInstances: crownInstances,
      appearance: new Cesium.PerInstanceColorAppearance({ translucent: false, closed: false }),
      shadows: this.mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.CAST_ONLY,
      asynchronous: false,
      compressVertices: false,
    }));
  }
}

function makeGeometry(pos, nrm, idx) {
  return new Cesium.Geometry({
    attributes: {
      position: new Cesium.GeometryAttribute({ componentDatatype: Cesium.ComponentDatatype.DOUBLE, componentsPerAttribute: 3, values: pos }),
      normal: new Cesium.GeometryAttribute({ componentDatatype: Cesium.ComponentDatatype.FLOAT, componentsPerAttribute: 3, values: nrm }),
    },
    indices: idx,
    primitiveType: Cesium.PrimitiveType.TRIANGLES,
    boundingSphere: Cesium.BoundingSphere.fromVertices(pos),
  });
}

function bboxOf(ring) {
  let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
  for (const [x, y] of ring) { if (x < a) a = x; if (y < b) b = y; if (x > c) c = x; if (y > d) d = y; }
  return [a, b, c, d];
}

function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
window.__CL = CampusLayers; // timing hook for automated checks
