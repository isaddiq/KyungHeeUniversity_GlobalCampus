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
  const bark = pine ? [0.45, 0.28, 0.2] : [0.36, 0.29, 0.22];
  if (pine) {
    // Korean red pine: tall reddish trunk, flattened layered crowns near the top
    G.cyl({ s: 0, t: 0, z0: z, z1: z + th * 0.8, r0: 0.07 * th + 0.08, r1: 0.04 * th, seg: 6, col: bark, sty: STY.STATUE });
    const g = 0.22 + 0.08 * rnd();
    const leaf = [g * 0.85, g * 1.45 + 0.05, g * 0.75];
    const tiers = 2 + Math.floor(rnd() * 2);
    for (let k = 0; k < tiers; k++) {
      const zc = z + th * (0.5 + 0.17 * k), r = th * (0.26 - 0.05 * k) * (0.85 + 0.3 * rnd());
      const off = (rnd() - 0.5) * th * 0.08;
      G.sphere({ s: off, t: (rnd() - 0.5) * th * 0.08, z: zc, r, col: leaf, sty: 21, seg: 7, sz: 0.42, jit: 0.25, ph: rnd() * 6 });
    }
  } else {
    // broadleaf (oak / zelkova / cherry): short trunk, broad irregular crown made of lobes
    G.cyl({ s: 0, t: 0, z0: z, z1: z + th * 0.5, r0: 0.06 * th + 0.1, r1: 0.04 * th, seg: 6, col: bark, sty: STY.STATUE });
    const g = 0.28 + 0.1 * rnd();
    const leaf = [g * 0.95, g * 1.5 + 0.06, g * 0.62];
    const R = th * 0.3;
    G.sphere({ s: 0, t: 0, z: z + th * 0.66, r: R, col: leaf, sty: 21, seg: 8, sz: 0.85, jit: 0.22, ph: rnd() * 6 });
    if (th > 7) for (let k = 0; k < 2; k++) {
      const a = rnd() * 6.28;
      G.sphere({ s: Math.cos(a) * R * 0.55, t: Math.sin(a) * R * 0.55, z: z + th * (0.55 + 0.15 * rnd()), r: R * 0.68, col: leaf.map((c) => c * (0.9 + 0.15 * rnd())), sty: 21, seg: 7, sz: 0.85, jit: 0.25, ph: rnd() * 6 });
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
