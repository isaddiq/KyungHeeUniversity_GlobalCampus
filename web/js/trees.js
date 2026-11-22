// Vegetation instances (VISUAL APPROXIMATION - positions are synthetic, see data/trees.json).
// Mix of Korean red pine (layered conifer crowns) and broadleaf trees (irregular lobed crowns),
// per-tree colour/size variation, rendered with the shared material shader (foliage style).
import { Mesh, Frame, Local, STY, createFacadeAppearance } from "./mesh.js";
import { geometryFromItems } from "./baked.js";
const Cesium = window.Cesium;

function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Trees inside the campus crop and outside the mapped cherry plantings (those have their own models). */
export function treeFilter(clipRings, cherries) {
  return (lon, lat) => (!clipRings || clipRings.some((r) => pointInRing(lon, lat, r))) &&
    !(cherries ?? []).some(({ p }) => Math.hypot((lon - p[0]) * 88700, (lat - p[1]) * 111000) < 3.5);
}

// Bark and foliage colours (sRGB 0-1), varied per tree.
const PINE_BARK_LOW = [0.30, 0.25, 0.22], PINE_BARK_HIGH = [0.66, 0.36, 0.22];   // grey-brown plates, red-orange above
const BROAD_BARK = [0.40, 0.37, 0.33];                                             // zelkova / oak: grey-brown

/** A bent stem as a chain of tapered segments through `pts` ([s,t,z] each). Returns nothing. */
function stem(G, pts, r0, r1, col, sty, seg) {
  for (let k = 0; k < pts.length - 1; k++) {
    const ra = r0 + (r1 - r0) * k / (pts.length - 1), rb = r0 + (r1 - r0) * (k + 1) / (pts.length - 1);
    G.cylBetween(pts[k], pts[k + 1], ra, col, sty, seg, rb);
  }
}

/** Leaf clump: a flattened, jittered sphere drawn with the leaf material (ragged, see-through edges). */
function clump(G, s, t, z, r, col, rnd, { sz = 0.8, seg = 6, sty = STY.LEAF } = {}) {
  G.sphere({ s, t, z, r, col, sty, seg, sz, jit: 0.28, ph: rnd() * 6.28 });
}

function addTree(mesh, f, dem, meta, arr, i) {
  const stride = 4;
  const lon = meta.origin_lon + arr[i * stride], lat = meta.origin_lat + arr[i * stride + 1];
  let seed = (i * 2654435761) >>> 0 || 1;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const th = arr[i * stride + 3] * (0.9 + 0.25 * rnd());
  const z = dem.heightEllipsoid(lon, lat) - 0.3;
  const [e, n] = f.local(lon, lat);
  const G = new Local(mesh, f, [1, 0], [e, n]);
  const pine = rnd() < 0.5;
  if (pine) {
    // Korean red pine (소나무, Pinus densiflora): leaning, slightly bent trunk, grey plated bark low and
    // red-orange higher up, an irregular flat-topped crown of horizontal needle pads near the top
    const la = rnd() * 6.28, lean = th * (0.05 + 0.12 * rnd());
    const lx = Math.cos(la) * lean, ly = Math.sin(la) * lean, bend = (rnd() - 0.5) * th * 0.06;
    const P = (k) => [lx * k * k + bend * Math.sin(k * 3.1), ly * k * k - bend * Math.cos(k * 3.1), z + th * 0.86 * k];
    const r0 = 0.032 * th + 0.08;
    stem(G, [P(0), P(0.3)], r0, r0 * 0.82, PINE_BARK_LOW, STY.BARK, 6);
    stem(G, [P(0.3), P(0.62), P(1)], r0 * 0.82, r0 * 0.35, PINE_BARK_HIGH, STY.BARK, 6);
    const g = 0.17 + 0.06 * rnd();
    const needles = [g * 0.95, g * 1.55 + 0.04, g * 0.82];
    const pads = 4 + Math.floor(rnd() * 3);
    for (let k = 0; k < pads; k++) {
      const hk = 0.55 + 0.4 * k / (pads - 1) + (rnd() - 0.5) * 0.05;   // up the trunk
      const base = P(Math.min(1, hk / 0.86));
      const a = la + k * 2.4 + (rnd() - 0.5) * 0.8, reach = th * (0.2 - 0.1 * k / pads) * (0.7 + 0.5 * rnd());
      const tip = [base[0] + Math.cos(a) * reach, base[1] + Math.sin(a) * reach, base[2] + th * (0.02 + 0.04 * rnd())];
      if (k < pads - 1) G.cylBetween(base, tip, r0 * 0.28, PINE_BARK_HIGH, STY.BARK, 4, r0 * 0.12);
      const r = th * (0.15 + 0.07 * rnd()) * (k === pads - 1 ? 1.15 : 1);
      const shade = 0.85 + 0.3 * (k / pads) + 0.1 * rnd();      // lower pads sit in shade
      clump(G, tip[0], tip[1], tip[2] + r * 0.12, r, needles.map((c) => c * shade), rnd, { sz: 0.38 });
    }
  } else {
    // broadleaf (느티나무 zelkova / oak): short trunk forking into a vase of ascending limbs, a broad domed
    // crown built from leaf clumps (lighter on top, darker underneath)
    const r0 = 0.04 * th + 0.1, fork = z + th * (0.28 + 0.1 * rnd());
    const a0 = rnd() * 6.28;
    stem(G, [[0, 0, z], [(rnd() - 0.5) * 0.3, (rnd() - 0.5) * 0.3, fork]], r0, r0 * 0.78, BROAD_BARK, STY.BARK, 6);
    const g = 0.22 + 0.08 * rnd();
    const leaf = [g * 1.0, g * 1.55 + 0.05, g * 0.62];
    const R = th * (0.34 + 0.06 * rnd()), zc = z + th * 0.68;
    const limbs = 3 + Math.floor(rnd() * 2);
    const tips = [];
    for (let k = 0; k < limbs; k++) {
      const a = a0 + k * 6.28 / limbs + (rnd() - 0.5) * 0.6;
      const mid = [Math.cos(a) * R * 0.35, Math.sin(a) * R * 0.35, fork + th * 0.16];
      const tip = [Math.cos(a) * R * (0.62 + 0.15 * rnd()), Math.sin(a) * R * (0.62 + 0.15 * rnd()), zc + th * (0.02 + 0.08 * rnd())];
      stem(G, [[0, 0, fork], mid, tip], r0 * 0.6, r0 * 0.18, BROAD_BARK, STY.BARK, 5);
      tips.push(tip);
    }
    // clumps: one on each limb tip, a ring under the dome and a crown on top
    const n = limbs + 3;
    for (let k = 0; k < n; k++) {
      let s, t, zz, r, shade;
      if (k < limbs) { [s, t, zz] = tips[k]; r = R * (0.5 + 0.12 * rnd()); shade = 0.95; }
      else if (k < n - 1) {
        const a = a0 + (k - limbs + 0.5) * 6.28 / (n - 1 - limbs) + rnd();
        s = Math.cos(a) * R * 0.5; t = Math.sin(a) * R * 0.5; zz = zc - th * 0.06; r = R * 0.46; shade = 0.8;
      } else { s = (rnd() - 0.5) * R * 0.2; t = (rnd() - 0.5) * R * 0.2; zz = zc + R * 0.42; r = R * 0.55; shade = 1.12; }
      clump(G, s, t, zz, r, leaf.map((c) => c * shade * (0.92 + 0.16 * rnd())), rnd, { sz: 0.78 });
    }
  }
  return { lon, lat, pine };
}

/** One item per tree (for baking and the GLB export). `tree` = index in trees_campus.bin (mobile keeps every 3rd). */
export function treeItems(dem, meta, arr, keep) {
  const f = new Frame(127.0818, 37.2427, 0);
  const items = [];
  for (let i = 0; i < arr.length / 4; i++) {
    const lon = meta.origin_lon + arr[i * 4], lat = meta.origin_lat + arr[i * 4 + 1];
    if (!keep(lon, lat)) continue;
    const mesh = new Mesh();
    const t = addTree(mesh, f, dem, meta, arr, i);
    items.push({ key: `tree-${i}`, name: `${t.pine ? "Pine" : "Broadleaf"} tree ${i}`, kind: t.pine ? "pine" : "broadleaf",
      group: "trees", pick: { kind: "trees" }, tree: i, lonlat: [+lon.toFixed(7), +lat.toFixed(7)], mesh });
  }
  return items;
}

/** Spatially compact chunks (~150 m cells) so Cesium can frustum-cull whole chunks of trees. */
function chunkByCell(recs, lonlatOf, maxPerChunk) {
  const cells = new Map();
  for (const r of recs) {
    const [lon, lat] = lonlatOf(r);
    const k = `${Math.floor(lon * 88700 / 150)},${Math.floor(lat * 111000 / 150)}`;
    if (!cells.has(k)) cells.set(k, []);
    cells.get(k).push(r);
  }
  const chunks = [];
  for (const list of cells.values()) for (let i = 0; i < list.length; i += maxPerChunk) chunks.push(list.slice(i, i + maxPerChunk));
  return chunks;
}

function treePrimitive(geometry, mobile) {
  const attributes = { color: Cesium.ColorGeometryInstanceAttribute.fromColor(new Cesium.Color(1, 1, 1, 0)) };
  return new Cesium.Primitive({
    geometryInstances: new Cesium.GeometryInstance({ id: { kind: "trees" }, geometry, attributes }),
    appearance: createFacadeAppearance(), asynchronous: false, compressVertices: false,
    shadows: mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.ENABLED,
  });
}

/**
 * Adds the trees to `coll` (a PrimitiveCollection) chunk by chunk, yielding to the browser between chunks.
 * `baked` = { group, recs } uses the pre-baked meshes; otherwise trees are generated here. Resolves with
 * the number of trees.
 */
export async function buildTrees(viewer, dem, meta, arr, inClip, mobile, coll, { baked = null } = {}) {
  const thin = mobile ? 3 : 1;
  let total = 0;
  if (baked) {
    const recs = baked.recs.filter((r) => r.tree % thin === 0);
    for (const chunk of chunkByCell(recs, (r) => r.lonlat, 600)) {
      coll.add(treePrimitive(geometryFromItems(baked.group, chunk), mobile));
      total += chunk.length;
      viewer.scene.requestRender();
      await new Promise((r) => setTimeout(r, 0));
    }
    return total;
  }
  const f = new Frame(127.0818, 37.2427, 0);
  const idx = [];
  for (let i = 0; i < arr.length / 4; i += thin) {
    const lon = meta.origin_lon + arr[i * 4], lat = meta.origin_lat + arr[i * 4 + 1];
    if (inClip(lon, lat)) idx.push(i);
  }
  for (const chunk of chunkByCell(idx, (i) => [meta.origin_lon + arr[i * 4], meta.origin_lat + arr[i * 4 + 1]], 250)) {
    const mesh = new Mesh();
    for (const i of chunk) addTree(mesh, f, dem, meta, arr, i);
    coll.add(treePrimitive(mesh.geometry(), mobile));
    total += chunk.length;
    viewer.scene.requestRender();
    await new Promise((r) => setTimeout(r, 0));
  }
  return total;
}
