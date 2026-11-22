// Enhanced Kyung Hee campus buildings.
// Geometry: the real OSM footprint, extruded from the real DTM ground (same as LOD1).
// Appearance: STYLISED procedural facades coloured by building role. Landmarks (main gate, library,
// obelisks, fountain, amphitheatre, observatory) get dedicated models - see khu_landmarks.js.
import { Mesh, Frame, STY, hex, createFacadeAppearance } from "./mesh.js";
import { geometryFromItems } from "./baked.js";
import { buildGateModel, buildLibraryModel, buildObelisk, buildTheatre, addPondRocks, buildPeaceHall, buildArtDesign, buildPhotoModel } from "./khu_landmarks.js";
const Cesium = window.Cesium;

// style ids: 0 granite/arched, 1 modern ribbon glass, 2 residential, 3 greenhouse, 4 rusticated stone
export function khuStyle(p) {
  const n = (p.official_name_ko || p.name_ko || "");
  const S = (style, wall, roof, fh, bw, label) => ({ style, wall: hex(wall), roof: hex(roof), fh, bw, label });
  if (/도서관/.test(n)) return S(0, "#e4ddcf", "#6e8a7d", 4.4, 4.2, "granite, tall arched windows");
  if (/예술|디자인/.test(n) && !/도예/.test(n)) return S(1, "#cfcdc6", "#8a8d8e", 4.2, 3.0, "modern concrete + glass");
  if (/기숙사|우정원|애지원/.test(n) || p.building_type === "dormitory") return S(2, "#e8dccb", "#8e6a58", 3.0, 3.3, "residential");
  if (/온실/.test(n) || p.building_type === "greenhouse") return S(3, "#dbe7ea", "#cfe0e4", 5.0, 2.4, "glass greenhouse");
  if (/천문/.test(n)) return S(0, "#f1f1ed", "#e6e6e2", 4.2, 5.2, "white observatory drum");
  if (/선승관|체육/.test(n)) return S(0, "#d9d1c1", "#7a8481", 4.6, 5.5, "granite, sports hall");
  if (/Emart|편의/.test(n)) return S(1, "#d3d0c8", "#8a8d8e", 3.5, 3.0, "small commercial");
  if (/전자정보|공학|실험|원자로/.test(n)) return S(0, "#d4cbbb", "#7b827f", 3.9, 3.4, "granite, engineering");
  if (/외국어|국제|학생회관|멀티미디어|글로벌|생명/.test(n)) return S(0, "#ddd5c6", "#78817d", 3.8, 3.6, "granite");
  if (p.footprint_area_m2 < 120) return S(4, "#cfc7b8", "#7f7a72", 3.5, 3.0, "small structure");
  return S(0, "#d8d0c1", "#7d8580", 3.8, 3.6, "granite");
}

/** Per-building record (ellipsoidal heights). Shared with the offline baker (tools/bake.js); layers.js uses it for every building. */
export function buildingRec(f, dem) {
  const p = f.properties;
  const [clon, clat] = p.centroid;
  const N = dem.geoidN(clon, clat);
  return { props: p, feature: f, parts: [], N, base: p.ground_min_m - 1.5 + N, // embed slightly: no floating on sloped sites
    top: p.ground_min_m + p.height_m + N, positions: [], detailed: p.in_campus };
}

function ringsOf(geom) {
  if (geom.type === "Polygon") return [geom.coordinates];
  if (geom.type === "MultiPolygon") return geom.coordinates;
  return [];
}

/** Extruded footprint with facade attributes (heights are ellipsoidal; frame.h = 0). */
function addExtrusion(mesh, frame, polys, { bottom, top, roof, datum, style, groundAt }) {
  const H = top - datum;
  const st4 = [style.fh, style.bw, style.style, H];
  const wall = [...style.wall, 1];
  const roofC = [...style.roof, 0];
  for (const poly of polys) {
    poly.forEach((ring, ri) => {
      const pts = ring.slice(0, -1).map(([lo, la]) => ({ lo, la, l: frame.local(lo, la) }));
      let area = 0;
      for (let k = 0; k < pts.length; k++) { const a = pts[k].l, b = pts[(k + 1) % pts.length].l; area += a[0] * b[1] - b[0] * a[1]; }
      const outward = ri === 0 ? area > 0 : area <= 0;
      for (let k = 0; k < pts.length; k++) {
        const A = pts[k], B = pts[(k + 1) % pts.length];
        const dx = B.l[0] - A.l[0], dy = B.l[1] - A.l[1];
        const len = Math.hypot(dx, dy);
        if (len < 0.05) continue;
        const nx = outward ? dy / len : -dy / len, ny = outward ? -dx / len : dx / len;
        const nrm = frame.dir(nx, ny, 0);
        const gA = groundAt(A.lo, A.la) - datum, gB = groundAt(B.lo, B.la) - datum;
        const b0 = mesh.v(frame.pt(A.l[0], A.l[1], bottom), nrm, 0, bottom - datum, wall, st4, [len, gA]);
        const b1 = mesh.v(frame.pt(B.l[0], B.l[1], bottom), nrm, len, bottom - datum, wall, st4, [len, gB]);
        const t0 = mesh.v(frame.pt(A.l[0], A.l[1], top), nrm, 0, H, wall, st4, [len, gA]);
        const t1 = mesh.v(frame.pt(B.l[0], B.l[1], top), nrm, len, H, wall, st4, [len, gB]);
        mesh.tri(b0, b1, t1); mesh.tri(b0, t1, t0);
      }
    });
    const flat = [], holes = [];
    poly.forEach((ring, ri) => {
      if (ri > 0) holes.push(flat.length);
      for (const [lo, la] of ring.slice(0, -1)) { const l = frame.local(lo, la); flat.push(new Cesium.Cartesian2(l[0], l[1])); }
    });
    let idx;
    try { idx = Cesium.PolygonPipeline.triangulate(flat, holes); } catch { idx = []; }
    const up = frame.dir(0, 0, 1);
    const base = flat.map((q) => mesh.v(frame.pt(q.x, q.y, roof), up, q.x, q.y, roofC, st4, [0, 0]));
    for (let k = 0; k < idx.length; k += 3) mesh.tri(base[idx[k]], base[idx[k + 1]], base[idx[k + 2]]);
  }
}

const noTint = () => Cesium.ColorGeometryInstanceAttribute.fromColor(new Cesium.Color(1, 1, 1, 0));

/** Building fields that the models set (also stored with the baked geometry). */
export function applyPatch(rec, patch) {
  if (!patch) return;
  for (const [k, v] of Object.entries(patch)) {
    if (k === "name_en") rec.props.name_en ??= v;
    else rec[k] = v;
  }
}

/**
 * Procedural campus models as items: [{ key, name, group, pick, patch, mesh }]. This is what
 * scripts/bake_models.py stores in web/data/baked; the site only runs it with ?procedural=1 or when the
 * baked files are missing. Patches are applied to the records as a side effect (same as the baked path).
 */
export function buildKhuItems(dem, campusRecs, details) {
  const center = campusRecs[0]?.props.centroid ?? [127.0818, 37.2427];
  const frame = new Frame(center[0], center[1], 0);
  const items = [];
  const groundAt = (lo, la) => dem.heightEllipsoid(lo, la);
  const photoModels = details?.photo_buildings ?? {};
  const special = new Set([details?.gate?.id, details?.amphitheatre?.id, details?.library?.id, details?.peacehall?.id, details?.artdesign?.id, ...Object.keys(photoModels)].filter(Boolean));
  const byId = new Map(campusRecs.map((r) => [r.props.id, r]));
  const nameOf = (rec) => [rec.props.official_name_ko || rec.props.name_ko, rec.props.name_en].filter(Boolean).join(" · ") || rec.props.id;
  const push = (rec, mesh, patch) => {
    applyPatch(rec, patch);
    items.push({ key: rec.props.id, name: nameOf(rec), group: "buildings", pick: { bid: rec.props.id, part: 0, kind: "building" }, patch, mesh });
  };
  for (const rec of campusRecs) {
    const p = rec.props;
    if (special.has(p.id)) continue;
    const style = khuStyle(p);
    const mesh = new Mesh();
    addExtrusion(mesh, frame, ringsOf(rec.feature.geometry), {
      bottom: rec.base, top: rec.top, roof: rec.top - 0.9, datum: p.ground_min_m + rec.N, style, groundAt,
    });
    push(rec, mesh, { appearance: style.label });
  }
  // main gate
  if (details?.gate && byId.has(details.gate.id)) {
    const rec = byId.get(details.gate.id);
    const { mesh, topEll } = buildGateModel(details.gate, dem);
    push(rec, mesh, {
      appearance: "triumphal arch with a coffered vault and carved Corinthian capitals; rooftop figures with a staff, book, scroll and dove; feathered spandrel figures and bronze medallions; pavilion reliefs, armillary spheres and eagles above the tablets",
      modelHeight: 22.5, top: topEll,
    });
  }
  // central library
  if (details?.library && byId.has(details.library.id)) {
    const rec = byId.get(details.library.id);
    const { mesh, topEll } = buildLibraryModel(details.library, rec, dem);
    push(rec, mesh, { appearance: "classical library modelled from photographs: 17-column giant colonnade facing 사색의 광장, arched end pavilions, grand stairs, roof penthouse", top: topEll });
  }
  // 평화노천극장: Greek-style theatre + rock-lined pond with jets
  if (details?.theatre && byId.has(details.theatre.id)) {
    const rec = byId.get(details.theatre.id);
    const { mesh, topEll } = buildTheatre(details.theatre, dem);
    const pd = details.theatre.pond;
    if (pd.coords.length) addPondRocks(mesh, pd.coords, pd.ground_mean_m, dem);
    push(rec, mesh, {
      appearance: "Greek-style theatre modelled from photographs: semicircular cavea with radial stair aisles, cross-aisle and balustrades, raised half-round stage, curved Corinthian colonnade with relief pavilions; seats follow the real DTM; stage axis towards the OSM pond",
      top: topEll, modelHeight: topEll - (rec.props.ground_min_m + rec.N),
    });
  }
  // 선승관 (photographed as "Peace Hall")
  if (details?.peacehall && byId.has(details.peacehall.id)) {
    const rec = byId.get(details.peacehall.id);
    const { mesh, topEll } = buildPeaceHall(details.peacehall, rec, dem);
    push(rec, mesh, {
      appearance: "brick arcade hall with a shallow ribbed metal roof, gold frieze and clock tower with an open belfry",
      focusHeading: 231, roofShape: "Shallow ribbed metal roof (estimated)", top: topEll, modelHeight: topEll - (rec.props.ground_min_m + rec.N),
    });
  }
  // 예술·디자인대학관 (College of Art & Design)
  if (details?.artdesign && byId.has(details.artdesign.id)) {
    const rec = byId.get(details.artdesign.id);
    const { mesh, topEll } = buildArtDesign(details.artdesign, rec, dem);
    push(rec, mesh, {
      appearance: "white neoclassical complex modelled from photographs: Ionic colonnaded base, temple portico with pediment and medallion, grand stairs, ~8-storey main block with corner towers and top loggia",
      top: topEll, modelHeight: topEll - (rec.props.ground_min_m + rec.N),
    });
  }
  // photo-based models of the other campus buildings (description in campus_details.photo_buildings)
  for (const [oid, pm] of Object.entries(photoModels)) {
    if (!byId.has(oid)) continue;
    const rec = byId.get(oid);
    const { mesh, topEll } = buildPhotoModel(pm, rec, dem);
    const patch = { appearance: pm.appearance, roofShape: pm.roof_shape, focusHeading: pm.focus_heading, focusPitch: pm.focus_pitch,
      top: topEll, modelHeight: topEll - (rec.props.ground_min_m + rec.N) };
    if (pm.name_en) patch.name_en = pm.name_en;
    for (const k of Object.keys(patch)) if (patch[k] === undefined) delete patch[k];
    push(rec, mesh, patch);
  }
  // plaza obelisks (사색의 광장)
  for (const ob of details?.plaza?.obelisks ?? []) {
    const mesh = new Mesh();
    buildObelisk(mesh, ob, details.plaza.obelisk_height_m, dem);
    items.push({ key: ob.id, name: "오벨리스크 · Obelisk (사색의 광장)", group: "buildings",
      pick: { kind: "landmark", props: { id: ob.id, name: "오벨리스크 · Obelisk (사색의 광장)", height: details.plaza.obelisk_height_m, source: details.plaza.obelisk_height_source, ground: ob.ground_m } },
      mesh });
  }
  return items;
}

/**
 * Cesium primitives for the campus models. `baked` = a decoded group (baked.js) from the pre-baked files,
 * or null to generate the models in the browser. One GeometryInstance per building keeps per-building
 * picking and highlighting; all of them share one Primitive (one shader, batched by Cesium's workers).
 * Returns { prims, exportGeoms } (exportGeoms: the small Cesium-geometry parts, for the GLB export).
 */
export function buildKhuPrimitives(viewer, dem, campusRecs, details, mobile, baked = null) {
  const instances = [];
  const attrs = () => ({ color: noTint() });
  const byId = new Map(campusRecs.map((r) => [r.props.id, r]));
  if (baked) {
    for (const r of baked.manifest.items) {
      const rec = r.pick?.bid ? byId.get(r.pick.bid) : null;
      if (r.pick?.bid && !rec) continue;          // not in this campus subset
      if (rec) { applyPatch(rec, r.patch); rec.parts = [r.pick]; }
      instances.push(new Cesium.GeometryInstance({ id: r.pick, geometry: geometryFromItems(baked, [r]), attributes: attrs() }));
    }
  } else {
    for (const it of buildKhuItems(dem, campusRecs, details)) {
      const rec = it.pick?.bid ? byId.get(it.pick.bid) : null;
      if (rec) rec.parts = [it.pick];
      instances.push(new Cesium.GeometryInstance({ id: it.pick, geometry: it.mesh.geometry(), attributes: attrs() }));
    }
  }
  const prims = [];
  const facade = viewer.scene.primitives.add(new Cesium.Primitive({
    geometryInstances: instances,
    appearance: createFacadeAppearance(),
    asynchronous: true,   // geometry batched in Cesium web workers: keeps the first frame from blocking ~2 s
    compressVertices: false,
    shadows: mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.ENABLED,
  }));
  prims.push(facade);
  for (const rec of campusRecs) if (!rec.primitive) rec.primitive = facade;
  const pools = [...(details?.plaza?.fountains ?? []).map((p) => ({ ...p, kind: "fountain" }))];
  const pd = details?.theatre?.pond;
  if (details?.theatre && byId.has(details.theatre.id) && pd?.coords.length) {
    pools.push({ id: pd.id, coords: pd.coords, ground_min_m: pd.ground_min_m, ground_mean_m: pd.ground_mean_m, kind: "pond" });
  }
  const exportGeoms = [];

  // fountain pool(s): water surface + stone rim + central basin with jets
  const water = [], stone = [];
  for (const fnt of pools) {
    const ring = fnt.coords.slice(0, -1);
    const N = dem.geoidN(ring[0][0], ring[0][1]);
    const zw = (fnt.kind === "pond" ? fnt.ground_mean_m + 0.45 : fnt.ground_mean_m + 0.3) + N;
    const pos = Cesium.Cartesian3.fromDegreesArray(ring.flat());
    stone.push(new Cesium.GeometryInstance({
      geometry: new Cesium.PolygonGeometry({ polygonHierarchy: new Cesium.PolygonHierarchy(pos), height: fnt.ground_min_m - 0.6 + N, extrudedHeight: zw - 0.6, vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT }),
      attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString("#7fa9c2")) },
    }));
    const isPond = fnt.kind === "pond";
    if (!isPond) stone.push(new Cesium.GeometryInstance({
      geometry: new Cesium.WallGeometry({ positions: [...pos, pos[0]], minimumHeights: Array(pos.length + 1).fill(fnt.ground_min_m - 0.6 + N), maximumHeights: Array(pos.length + 1).fill(zw + 0.25), vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT }),
      attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString("#e8e4da")) },
    }));
    water.push(new Cesium.GeometryInstance({
      id: { kind: "landmark", props: { id: fnt.id, name: fnt.kind === "pond" ? "연못 · Theatre pond" : "분수 · Fountain pool (사색의 광장)", source: fnt.kind === "pond" ? "OSM natural=water outline" : "OSM amenity=fountain outline", ground: fnt.ground_mean_m } },
      geometry: new Cesium.PolygonGeometry({ polygonHierarchy: new Cesium.PolygonHierarchy(pos), height: zw, vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT }),
      attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString("#4fb3e6").withAlpha(0.82)) },
    }));
    // central fountain basin + jets (illustrative)
    let cx = 0, cy = 0;
    for (const [x, y] of ring) { cx += x; cy += y; }
    cx /= ring.length; cy /= ring.length;
    const mm = (h) => Cesium.Transforms.eastNorthUpToFixedFrame(Cesium.Cartesian3.fromDegrees(cx, cy, h));
    if (!isPond) stone.push(new Cesium.GeometryInstance({
      geometry: new Cesium.CylinderGeometry({ length: 0.8, topRadius: 2.2, bottomRadius: 2.6, vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT }),
      modelMatrix: mm(zw + 0.2), attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString("#ece8df")) },
    }));
    const jets = isPond
      ? [[0, 0, 3.0], [9, 6, 2.0], [-9, -6, 2.0], [7, -8, 1.6], [-7, 8, 1.6], [12, -2, 1.4], [-12, 2, 1.4]]
      : [[0, 0, 5.5], [3.5, 0, 2.2], [-3.5, 0, 2.2], [0, 3.5, 2.2], [0, -3.5, 2.2]];
    for (const [dxm, dym, hj] of jets) {
      const lo = cx + dxm / (111320 * Math.cos(cy * Math.PI / 180)), la = cy + dym / 110950;
      water.push(new Cesium.GeometryInstance({
        geometry: new Cesium.CylinderGeometry({ length: hj, topRadius: 0.05, bottomRadius: 0.22, vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT }),
        modelMatrix: Cesium.Transforms.eastNorthUpToFixedFrame(Cesium.Cartesian3.fromDegrees(lo, la, zw + hj / 2)),
        attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.WHITE.withAlpha(0.55)) },
      }));
    }
  }
  for (const inst of stone) exportGeoms.push({ group: "Water features", name: "Pool rim / basin", inst });
  for (const inst of water) exportGeoms.push({ group: "Water features", name: inst.id?.props?.name ?? "Water jet", inst });
  if (stone.length) prims.push(viewer.scene.primitives.add(new Cesium.Primitive({ geometryInstances: stone, appearance: new Cesium.PerInstanceColorAppearance({ translucent: false, closed: false }), asynchronous: false })));
  if (water.length) prims.push(viewer.scene.primitives.add(new Cesium.Primitive({ geometryInstances: water, appearance: new Cesium.PerInstanceColorAppearance({ translucent: true, closed: false, flat: false }), asynchronous: false })));

  // legacy terrace slicing (used only when no theatre layout is available)
  if (!details?.theatre && details?.amphitheatre && byId.has(details.amphitheatre.id)) {
    const rec = byId.get(details.amphitheatre.id);
    const inst = [];
    rec.parts = [];
    const lowest = Math.min(...details.amphitheatre.tiers.map((t) => t.top_m));
    details.amphitheatre.tiers.forEach((t, k) => {
      const ring0 = t.coords[0][0];
      const N = dem.geoidN(ring0[0], ring0[1]);
      const id = { bid: rec.props.id, part: k, kind: "building" };
      rec.parts.push(id);
      const stage = t.top_m === lowest;
      const lvl = Math.round((t.top_m - lowest) / details.amphitheatre.band_m);
      inst.push(new Cesium.GeometryInstance({
        id,
        geometry: new Cesium.PolygonGeometry({
          polygonHierarchy: new Cesium.PolygonHierarchy(
            Cesium.Cartesian3.fromDegreesArray(t.coords[0].slice(0, -1).flat()),
            t.coords.slice(1).map((h) => new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(h.slice(0, -1).flat())))),
          height: t.top_m - 1.4 + N, extrudedHeight: t.top_m + N,
          vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT,
        }),
        attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString(stage ? "#9c8466" : (lvl % 2 ? "#d6cfbf" : "#ebe6da"))) },
      }));
    });
    rec.appearance = `terraced seating: footprint sliced by ${details.amphitheatre.band_m} m bands of the real DTM; lowest terrace = stage floor`;
    rec.top = Math.max(...details.amphitheatre.tiers.map((t) => t.top_m)) + rec.N;
    const amp = viewer.scene.primitives.add(new Cesium.Primitive({
      geometryInstances: inst,
      appearance: new Cesium.PerInstanceColorAppearance({ translucent: false, closed: true }),
      shadows: mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.ENABLED,
      asynchronous: false,
    }));
    rec.primitive = amp;
    rec.tintMode = "replace";
    prims.push(amp);
  }

  // observatory dome on the circular 천문대 footprint
  if (details?.observatory && byId.has(details.observatory.id) && !details?.photo_buildings?.[details.observatory.id]) {
    const rec = byId.get(details.observatory.id);
    const [lon, lat] = details.observatory.center;
    const r = Math.min(7.5, details.observatory.footprint_radius_m * 0.36);
    const mm = Cesium.Transforms.eastNorthUpToFixedFrame(Cesium.Cartesian3.fromDegrees(lon, lat, rec.top - 0.9));
    prims.push(viewer.scene.primitives.add(new Cesium.Primitive({
      geometryInstances: new Cesium.GeometryInstance({
        id: { bid: rec.props.id, part: 1, kind: "building" },
        geometry: new Cesium.EllipsoidGeometry({ radii: new Cesium.Cartesian3(r, r, r), maximumCone: Math.PI / 2, vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT, stackPartitions: 24, slicePartitions: 36 }),
        modelMatrix: mm,
        attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString("#f3f5f6")) },
      }),
      appearance: new Cesium.PerInstanceColorAppearance({ translucent: false, closed: false }),
      shadows: mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.ENABLED,
      asynchronous: false,
    })));
    exportGeoms.push({ group: "Buildings", name: "천문대 dome · Observatory dome", inst: prims.at(-1).geometryInstances });
    rec.appearance = (rec.appearance || "") + "; dome (illustrative, radius " + r.toFixed(1) + " m)";
    rec.top += r;
  }
  return { prims, exportGeoms };
}
