// "Export GLB": the whole 3D campus as one binary glTF file in which every item is its own named node
// (terrain, each building and landmark, each ground surface, road line, ground object, water feature and
// tree), grouped under parent nodes per category. Built in the browser from the same geometry the viewer
// draws (baked items or the procedural generators), so nothing is uploaded anywhere.
//
// Coordinates: metres in a local east-north-up frame at the campus centre on the terrain, written in glTF
// axes (+X east, +Y up, -Z north). The origin's longitude, latitude and ellipsoidal height are in the
// scene extras, so the file can be georeferenced again. Colours are the model base colours; the window,
// masonry and lettering patterns are drawn by the site's shader per pixel and are not part of the geometry.
import { GlbBuilder } from "./glb_writer.js";
import { itemArrays, meshArrays } from "./baked.js";
import { buildKhuItems } from "./khu_buildings.js";
import { groundObjectItems } from "./ground_objects.js";
import { treeItems, treeFilter } from "./trees.js";
import { GROUND_FILL, GROUND_LINE, loadJSON } from "./layers.js";
import { CONFIG } from "./config.js";

const Cesium = window.Cesium;
const yieldUI = () => new Promise((r) => setTimeout(r, 0));
const srgbToLinear = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));

/** ECEF -> local glTF axes. */
function makeFrame(dem) {
  const { lon, lat } = CONFIG.campusCenter;
  const h = dem.heightEllipsoid(lon, lat);
  const M = Cesium.Transforms.eastNorthUpToFixedFrame(Cesium.Cartesian3.fromDegrees(lon, lat, h));
  const inv = Cesium.Matrix4.inverseTransformation(M, new Cesium.Matrix4());
  const r = Cesium.Matrix4.getMatrix3(inv, new Cesium.Matrix3());
  const tmp = new Cesium.Cartesian3();
  return {
    origin: { lon, lat, height_ellipsoid_m: +h.toFixed(3) },
    /** Float64Array ECEF xyz -> Float32Array glTF xyz */
    points(p) {
      const out = new Float32Array(p.length);
      for (let i = 0; i < p.length; i += 3) {
        tmp.x = p[i]; tmp.y = p[i + 1]; tmp.z = p[i + 2];
        Cesium.Matrix4.multiplyByPoint(inv, tmp, tmp);
        out[i] = tmp.x; out[i + 1] = tmp.z; out[i + 2] = -tmp.y;
      }
      return out;
    },
    normals(n) {
      const out = new Float32Array(n.length);
      for (let i = 0; i < n.length; i += 3) {
        tmp.x = n[i]; tmp.y = n[i + 1]; tmp.z = n[i + 2];
        Cesium.Matrix3.multiplyByVector(r, tmp, tmp);
        const l = Math.hypot(tmp.x, tmp.y, tmp.z) || 1;
        out[i] = tmp.x / l; out[i + 1] = tmp.z / l; out[i + 2] = -tmp.y / l;
      }
      return out;
    },
    lonLatH(lon, lat, hh) { return Cesium.Cartesian3.fromDegrees(lon, lat, hh); },
  };
}

/** Facade-style arrays (from baked.js itemArrays / meshArrays) -> GLB mesh with per-vertex base colours. */
function facadeMesh(frame, a) {
  const colors = new Uint8Array((a.p.length / 3) * 4);
  for (let v = 0; v < a.p.length / 3; v++) {
    for (let k = 0; k < 3; k++) colors[4 * v + k] = Math.round(255 * srgbToLinear(Math.min(1, Math.max(0, a.w[4 * v + k]))));
    colors[4 * v + 3] = 255;
  }
  return { positions: frame.points(a.p), normals: frame.normals(a.n), colors, indices: a.idx };
}

/** Cesium geometry description (+ optional modelMatrix) -> GLB mesh. */
function cesiumGeometryMesh(frame, inst) {
  const geo = inst.geometry.constructor.createGeometry(inst.geometry);
  if (!geo) return null;
  const pos = geo.attributes.position.values;
  let p = pos;
  if (inst.modelMatrix) {
    p = new Float64Array(pos.length);
    const t = new Cesium.Cartesian3();
    for (let i = 0; i < pos.length; i += 3) {
      t.x = pos[i]; t.y = pos[i + 1]; t.z = pos[i + 2];
      Cesium.Matrix4.multiplyByPoint(inst.modelMatrix, t, t);
      p[i] = t.x; p[i + 1] = t.y; p[i + 2] = t.z;
    }
  }
  let normals;
  if (geo.attributes.normal) {
    let n = geo.attributes.normal.values;
    if (inst.modelMatrix) {
      const r = Cesium.Matrix4.getMatrix3(inst.modelMatrix, new Cesium.Matrix3()), t = new Cesium.Cartesian3();
      const nn = new Float32Array(n.length);
      for (let i = 0; i < n.length; i += 3) {
        t.x = n[i]; t.y = n[i + 1]; t.z = n[i + 2]; Cesium.Matrix3.multiplyByVector(r, t, t);
        nn[i] = t.x; nn[i + 1] = t.y; nn[i + 2] = t.z;
      }
      n = nn;
    }
    normals = frame.normals(n);
  }
  const indices = geo.indices ?? Uint32Array.from({ length: pos.length / 3 }, (_, i) => i);
  return { positions: frame.points(p), normals, indices };
}

/** Surface polygon draped on the terrain: triangulated, split to <= maxEdge metres, lifted `lift` m. */
function drapedPolygon(frame, dem, rings, lift, maxEdge = 4) {
  const { lon: lon0, lat: lat0 } = CONFIG.campusCenter;
  const mx = 111320 * Math.cos(lat0 * Math.PI / 180), my = 110950;
  const flat = [], holes = [];
  rings.forEach((ring, k) => {
    if (k > 0) holes.push(flat.length);
    for (const [lo, la] of ring.slice(0, -1)) flat.push(new Cesium.Cartesian2((lo - lon0) * mx, (la - lat0) * my));
  });
  let tri;
  try { tri = Cesium.PolygonPipeline.triangulate(flat, holes); } catch { return null; }
  if (!tri?.length) return null;
  const pts = flat.map((q) => [q.x, q.y]), idx = [];
  const mid = new Map();
  const midpoint = (a, b) => {
    const key = a < b ? `${a},${b}` : `${b},${a}`;
    let m = mid.get(key);
    if (m === undefined) { m = pts.length; pts.push([(pts[a][0] + pts[b][0]) / 2, (pts[a][1] + pts[b][1]) / 2]); mid.set(key, m); }
    return m;
  };
  const len2 = (a, b) => (pts[a][0] - pts[b][0]) ** 2 + (pts[a][1] - pts[b][1]) ** 2;
  const stack = [];
  for (let k = 0; k < tri.length; k += 3) stack.push([tri[k], tri[k + 1], tri[k + 2]]);
  let guard = 0;
  while (stack.length) {
    const [a, b, c] = stack.pop();
    const ab = len2(a, b), bc = len2(b, c), ca = len2(c, a), m = Math.max(ab, bc, ca);
    if (m <= maxEdge * maxEdge || ++guard > 400000) { idx.push(a, b, c); continue; }
    if (m === ab) { const d = midpoint(a, b); stack.push([a, d, c], [d, b, c]); }
    else if (m === bc) { const d = midpoint(b, c); stack.push([a, b, d], [a, d, c]); }
    else { const d = midpoint(c, a); stack.push([a, b, d], [d, b, c]); }
  }
  const ecef = new Float64Array(pts.length * 3);
  pts.forEach(([e, n], i) => {
    const lo = lon0 + e / mx, la = lat0 + n / my;
    const c = frame.lonLatH(lo, la, dem.heightEllipsoid(lo, la) + lift);
    ecef[3 * i] = c.x; ecef[3 * i + 1] = c.y; ecef[3 * i + 2] = c.z;
  });
  // flat-ish surfaces: up normals (the terrain node carries the real shading)
  const positions = frame.points(ecef);
  const normals = new Float32Array(positions.length);
  for (let i = 1; i < normals.length; i += 3) normals[i] = 1;
  return { positions, normals, indices: pts.length > 65535 ? Uint32Array.from(idx) : Uint16Array.from(idx) };
}

/** Road / marking line as a draped ribbon of width w. */
function drapedLine(frame, dem, coords, w, lift) {
  const { lon: lon0, lat: lat0 } = CONFIG.campusCenter;
  const mx = 111320 * Math.cos(lat0 * Math.PI / 180), my = 110950;
  const P = coords.map(([lo, la]) => [(lo - lon0) * mx, (la - lat0) * my]);
  const S = [];
  for (let k = 0; k < P.length - 1; k++) {
    const [ax, ay] = P[k], [bx, by] = P[k + 1], n = Math.max(1, Math.ceil(Math.hypot(bx - ax, by - ay) / 3));
    for (let j = 0; j < n; j++) S.push([ax + (bx - ax) * j / n, ay + (by - ay) * j / n]);
  }
  S.push(P.at(-1));
  if (S.length < 2) return null;
  const ecef = new Float64Array(S.length * 6), idx = [];
  S.forEach(([x, y], i) => {
    const [px, py] = S[Math.max(0, i - 1)], [qx, qy] = S[Math.min(S.length - 1, i + 1)];
    let dx = qx - px, dy = qy - py; const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
    for (const [side, o] of [[0, w / 2], [1, -w / 2]]) {
      const lo = lon0 + (x - dy * o) / mx, la = lat0 + (y + dx * o) / my;
      const c = frame.lonLatH(lo, la, dem.heightEllipsoid(lo, la) + lift);
      ecef.set([c.x, c.y, c.z], 6 * i + 3 * side);
    }
    if (i) { const a = 2 * (i - 1); idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  });
  const positions = frame.points(ecef), normals = new Float32Array(positions.length);
  for (let i = 1; i < normals.length; i += 3) normals[i] = 1;
  return { positions, normals, indices: Uint32Array.from(idx) };
}

/** Terrain inside the campus crop as a regular grid (step m), triangles kept where all corners are inside. */
function terrainMesh(frame, dem, bbox, inClip, step = 3) {
  const [w, s, e, n] = bbox;
  const mx = 111320 * Math.cos((s + n) / 2 * Math.PI / 180), my = 110950;
  const cols = Math.ceil((e - w) * mx / step) + 1, rows = Math.ceil((n - s) * my / step) + 1;
  const ecef = new Float64Array(cols * rows * 3), inside = new Uint8Array(cols * rows);
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const lo = w + (e - w) * c / (cols - 1), la = n - (n - s) * r / (rows - 1), i = r * cols + c;
    const p = frame.lonLatH(lo, la, dem.heightEllipsoid(lo, la));
    ecef[3 * i] = p.x; ecef[3 * i + 1] = p.y; ecef[3 * i + 2] = p.z;
    inside[i] = inClip(lo, la) ? 1 : 0;
  }
  const idx = [];
  for (let r = 0; r < rows - 1; r++) for (let c = 0; c < cols - 1; c++) {
    const a = r * cols + c, b = a + 1, d = a + cols, f = d + 1;
    if (inside[a] && inside[b] && inside[d]) idx.push(a, d, b);
    if (inside[b] && inside[d] && inside[f]) idx.push(b, d, f);
  }
  const positions = frame.points(ecef);
  // smooth normals from the triangles
  const normals = new Float32Array(positions.length);
  for (let k = 0; k < idx.length; k += 3) {
    const [i0, i1, i2] = [idx[k] * 3, idx[k + 1] * 3, idx[k + 2] * 3];
    const ux = positions[i1] - positions[i0], uy = positions[i1 + 1] - positions[i0 + 1], uz = positions[i1 + 2] - positions[i0 + 2];
    const vx = positions[i2] - positions[i0], vy = positions[i2 + 1] - positions[i0 + 1], vz = positions[i2 + 2] - positions[i0 + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const i of [i0, i1, i2]) { normals[i] += nx; normals[i + 1] += ny; normals[i + 2] += nz; }
  }
  for (let i = 0; i < normals.length; i += 3) {
    const l = Math.hypot(normals[i], normals[i + 1], normals[i + 2]) || 1;
    normals[i] /= l; normals[i + 1] /= l; normals[i + 2] /= l;
    if (normals[i + 1] < 0) { normals[i] *= -1; normals[i + 1] *= -1; normals[i + 2] *= -1; }
  }
  return { positions, normals, indices: Uint32Array.from(idx) };
}

const rgba = (css, a = 1) => {
  const c = Cesium.Color.fromCssColorString(css);
  return [srgbToLinear(c.red), srgbToLinear(c.green), srgbToLinear(c.blue), a];
};

/**
 * Builds the GLB. `layers` is the CampusLayers instance of the page; `onProgress(fraction, text)`.
 * Resolves with { blob, nodes, triangles }.
 */
export async function exportCampusGlb(layers, dem, onProgress = () => {}) {
  const B = new GlbBuilder();
  const frame = makeFrame(dem);
  const base = layers.base ?? "data";
  let triangles = 0, items = 0;
  const add = (parent, name, mesh, material, extras) => {
    if (!mesh) return;
    const mi = B.addMesh(name, mesh, material);
    if (mi < 0) return;
    triangles += mesh.indices.length / 3; items++;
    B.addNode(name, { parent, mesh: mi, extras });
  };
  const root = B.addNode("KHU Global Campus", {
    extras: { origin: frame.origin, axes: "glTF: +X east, +Y up, -Z north (local ENU at origin), metres",
      source: "KHU Global Campus 3D twin: FABDEM terrain, OpenStreetMap footprints, models from photographs (see the site's Data and accuracy panel)" },
  });
  const group = (name) => B.addNode(name, { parent: root });
  const M = {
    facade: B.material("facade", { name: "Facade (base colours)", color: [1, 1, 1, 1], roughness: 0.85 }),
    detail: B.material("detail", { name: "Ground objects (base colours)", color: [1, 1, 1, 1], roughness: 0.9 }),
    foliage: B.material("foliage", { name: "Vegetation", color: [1, 1, 1, 1], roughness: 0.95 }),
    terrain: B.material("terrain", { name: "Terrain", color: rgba("#8d9b62"), roughness: 1 }),
    water: B.material("water", { name: "Water", color: rgba("#4fb3e6", 0.82), alpha: "BLEND", roughness: 0.1 }),
    stone: B.material("stone", { name: "Stone", color: rgba("#e8e4da"), roughness: 0.8 }),
  };
  const step = async (f, t) => { onProgress(f, t); await yieldUI(); };

  // 1. terrain
  await step(0.02, "terrain");
  const bbox = layers.details?.clip?.bbox;
  if (bbox) add(group("Terrain"), "Terrain (FABDEM DTM with local grades, 3 m grid)", terrainMesh(frame, dem, bbox, layers.inClip), M.terrain);

  // 2. buildings and landmarks
  await step(0.15, "buildings");
  const gB = group("Buildings"), gL = group("Landmarks");
  const meta = (bid) => {
    const p = layers.buildings.get(bid)?.props;
    if (!p) return undefined;
    return { osm_id: p.id, name_ko: p.official_name_ko || p.name_ko || null, name_en: p.name_en || null, official_no: p.official_no ?? null,
      height_m: p.height_m, height_status: p.height_status, ground_min_m: p.ground_min_m };
  };
  const bakedB = await layers.bakedGroup?.("buildings");
  if (bakedB) {
    for (const r of bakedB.manifest.items) {
      const isB = !!r.pick?.bid;
      add(isB ? gB : gL, r.name, facadeMesh(frame, itemArrays(bakedB, r)), M.facade, isB ? meta(r.pick.bid) : { id: r.key });
    }
  } else {
    const details = layers.details?.slim ? await loadJSON(`${base}/campus_details.json`) : layers.details;
    for (const it of buildKhuItems(dem, layers.campusRecs, details)) {
      const isB = !!it.pick?.bid;
      add(isB ? gB : gL, it.name, facadeMesh(frame, meshArrays(it.mesh)), M.facade, isB ? meta(it.pick.bid) : { id: it.key });
    }
  }
  for (const rec of layers.buildings.values()) {         // any building drawn as a plain extrusion
    if (rec.detailed || !rec.primitive) continue;
    for (const [k, poly] of (rec.feature.geometry.type === "Polygon" ? [rec.feature.geometry.coordinates] : rec.feature.geometry.coordinates).entries()) {
      const inst = { geometry: new Cesium.PolygonGeometry({ polygonHierarchy: new Cesium.PolygonHierarchy(
        Cesium.Cartesian3.fromDegreesArray(poly[0].slice(0, -1).flat())), height: rec.base, extrudedHeight: rec.top,
        vertexFormat: Cesium.VertexFormat.POSITION_AND_NORMAL }) };
      add(gB, `${rec.props.name_ko || rec.props.id} (${k})`, cesiumGeometryMesh(frame, inst), M.stone, meta(rec.props.id));
    }
  }

  // 3. water features and other small Cesium-geometry parts
  await step(0.3, "water features");
  const gW = group("Water features");
  for (const e of layers.exportGeoms ?? []) {
    const insts = Array.isArray(e.inst) ? e.inst : [e.inst];
    for (const inst of insts) {
      if (!inst?.geometry) continue;
      const col = inst.attributes?.color?.value;
      const translucent = col && col[3] < 250;
      const parent = e.group === "Buildings" ? gB : gW;
      try { add(parent, e.name, cesiumGeometryMesh(frame, inst), translucent ? M.water : M.stone); } catch (err) { console.warn("export: skipped", e.name, err); }
    }
  }

  // 4. ground surfaces and road lines
  await step(0.35, "ground surfaces");
  let ground = layers.ground;
  if (!ground) ground = await loadJSON(`${base}/ground.json`).catch(() => null);
  if (ground) {
    const gS = group("Ground surfaces"), sub = new Map();
    const fills = ground.fills ?? [];
    for (let k = 0; k < fills.length; k++) {
      const f = fills[k];
      if (!sub.has(f.k)) sub.set(f.k, B.addNode(f.k.replace(/_/g, " "), { parent: gS }));
      const mat = B.material(`fill:${f.k}`, { name: `Surface: ${f.k}`, color: rgba(GROUND_FILL[f.k] || "#999999"), roughness: 0.95 });
      add(sub.get(f.k), `${f.k} ${f.src ?? k}`, drapedPolygon(frame, dem, f.c, 0.06), mat, { kind: f.k, osm: f.src ?? null });
      if (k % 100 === 0) await step(0.35 + 0.25 * k / fills.length, `ground surfaces ${k}/${fills.length}`);
    }
    if ((ground.lines ?? []).length) {
      const gR = group("Road surfaces and markings");
      for (const [k, l] of ground.lines.entries()) {
        if (l.c.length < 2) continue;
        const mat = B.material(`line:${l.k}`, { name: `Line: ${l.k}`, color: rgba(GROUND_LINE[l.k] || "#ffffff"), roughness: 0.9 });
        add(gR, `${l.k} ${l.src ?? k}`, drapedLine(frame, dem, l.c, l.w, l.k.startsWith("road_") ? 0.08 : 0.1), mat, { kind: l.k, width_m: l.w, osm: l.src ?? null });
      }
    }
  }

  // 5. ground objects and cherry trees
  await step(0.62, "ground objects");
  const gO = group("Ground objects"), gC = group("Cherry trees");
  const bakedO = await layers.bakedGroup?.("ground_objects");
  if (bakedO) {
    for (const r of bakedO.manifest.items) add(r.kind === "cherry" ? gC : gO, r.name, facadeMesh(frame, itemArrays(bakedO, r)), M.detail, { kind: r.kind });
  } else {
    const full = ground?.objects?.some((o) => o.k !== "fountain") ? ground : await loadJSON(`${base}/ground.json`).catch(() => ground);
    for (const it of [...groundObjectItems(dem, full?.objects), ...groundObjectItems(dem, full?.cherries)]) {
      add(it.kind === "cherry" ? gC : gO, it.name, facadeMesh(frame, meshArrays(it.mesh)), M.detail, { kind: it.kind });
    }
  }

  // 6. vegetation: one node per tree (generated here, also when the vegetation layer is off)
  await step(0.72, "trees");
  try {
    const tmeta = await loadJSON(`${base}/trees_campus.json`);
    const arr = new Float32Array(await (await fetch(`${base}/trees_campus.bin`)).arrayBuffer());
    const keep = treeFilter(layers.details?.clip?.rings ?? null, ground?.cherries ?? layers.cherries);
    const trees = treeItems(dem, tmeta, arr, keep);
    const gT = group("Vegetation (illustrative positions)");
    for (const [k, it] of trees.entries()) {
      add(gT, `${it.kind === "pine" ? "Pine" : "Broadleaf"} tree ${it.tree}`, facadeMesh(frame, meshArrays(it.mesh)), M.foliage,
        { lon: it.lonlat[0], lat: it.lonlat[1], note: "synthetic position (see data/trees.json)" });
      if (k % 300 === 0) await step(0.72 + 0.2 * k / trees.length, `trees ${k}/${trees.length}`);
    }
  } catch (e) { console.warn("export: vegetation skipped", e); }

  await step(0.95, "writing file");
  const blob = B.toBlob({ origin: frame.origin, items, triangles });
  onProgress(1, "done");
  return { blob, nodes: B.nodes.length, items, triangles };
}
