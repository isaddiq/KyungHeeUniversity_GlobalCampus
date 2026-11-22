// Pre-baked campus geometry: encoder (used offline by scripts/bake_models.py through tools/bake.html) and
// decoder (used by the site at run time). One manifest + one binary per group (buildings, ground objects,
// trees) so the groups can load progressively.
//
// An "item" is one selectable/exportable object (a building, a landmark, a fountain, a tree ...):
//   { key, name, group, pick, patch?, tree?, mesh: { p, n, st, w, s, e, i } }   (Mesh layout from mesh.js)
// Binary layout per group (planar, every section 4-byte aligned; gzip on GitHub Pages compresses it well):
//   pos  Float32 x3  vertex position relative to the item centre (ECEF metres; float32 is ~1e-5 m here)
//   nrm  Int8    x4  unit normal * 127 (4th byte padding)
//   st   Float32 x2  facade coordinates (metres along the wall, metres above the datum)
//   edge Float32 x2  wall length, ground level under the wall
//   tup  Uint16  x1  index into the group's (wall rgba, style4) table: few distinct values per item
//   idx  Uint16|Uint32 per item (local vertex indices)
//   tab  Float32 x8  the (wall, style) table
export const BAKE_VERSION = 1;
const Cesium = window.Cesium;

const align4 = (n) => (n + 3) & ~3;

/** Removes exactly duplicated vertices (same position and attributes) inside one mesh. */
function dedupe(m) {
  const nV = m.p.length / 3, remap = new Int32Array(nV), keep = [], seen = new Map();
  for (let v = 0; v < nV; v++) {
    const k = [m.p[3 * v], m.p[3 * v + 1], m.p[3 * v + 2], m.n[3 * v], m.n[3 * v + 1], m.n[3 * v + 2],
      m.st[2 * v], m.st[2 * v + 1], m.e[2 * v], m.e[2 * v + 1], ...m.w.slice(4 * v, 4 * v + 4), ...m.s.slice(4 * v, 4 * v + 4)].join(",");
    const j = seen.get(k);
    if (j === undefined) { seen.set(k, keep.length); remap[v] = keep.length; keep.push(v); } else remap[v] = j;
  }
  if (keep.length === nV) return m;
  const pick = (arr, n) => { const o = []; for (const v of keep) for (let c = 0; c < n; c++) o.push(arr[n * v + c]); return o; };
  return { p: pick(m.p, 3), n: pick(m.n, 3), st: pick(m.st, 2), e: pick(m.e, 2), w: pick(m.w, 4), s: pick(m.s, 4), i: m.i.map((x) => remap[x]) };
}

/** Encodes the items of one group; returns { manifest, bytes: Uint8Array }. */
export function encodeGroup(group, items) {
  const tab = [], tabIndex = new Map();
  const recs = [];
  let V = 0, I = 0, big = false, dupSaved = 0;
  const meshes = items.map((it) => {
    const m = dedupe(it.mesh);
    dupSaved += it.mesh.p.length / 3 - m.p.length / 3;
    return m;
  });
  meshes.forEach((m) => { const nv = m.p.length / 3; V += nv; I += m.i.length; if (nv > 65535) big = true; });
  const off = { pos: 0 };
  off.nrm = off.pos + V * 12;
  off.st = off.nrm + V * 4;
  off.edge = off.st + V * 8;
  off.tup = off.edge + V * 8;
  off.idx = align4(off.tup + V * 2);
  off.tab = align4(off.idx + I * (big ? 4 : 2));
  const tupV = new Uint16Array(V);
  const pos = new Float32Array(V * 3), nrm = new Int8Array(V * 4), st = new Float32Array(V * 2), edge = new Float32Array(V * 2);
  const idx = big ? new Uint32Array(I) : new Uint16Array(I);
  let vo = 0, io = 0;
  items.forEach((it, k) => {
    const m = meshes[k], nv = m.p.length / 3;
    // item centre: middle of the bounding box (doubles, kept in the manifest)
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    for (let v = 0; v < nv; v++) {
      const x = m.p[3 * v], y = m.p[3 * v + 1], z = m.p[3 * v + 2];
      if (x < x0) x0 = x; if (y < y0) y0 = y; if (z < z0) z0 = z; if (x > x1) x1 = x; if (y > y1) y1 = y; if (z > z1) z1 = z;
    }
    const c = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2].map((q) => Math.round(q * 1000) / 1000);
    for (let v = 0; v < nv; v++) {
      const g = vo + v;
      for (let q = 0; q < 3; q++) pos[3 * g + q] = m.p[3 * v + q] - c[q];
      for (let q = 0; q < 3; q++) nrm[4 * g + q] = Math.max(-127, Math.min(127, Math.round(m.n[3 * v + q] * 127)));
      st[2 * g] = m.st[2 * v]; st[2 * g + 1] = m.st[2 * v + 1];
      edge[2 * g] = m.e[2 * v]; edge[2 * g + 1] = m.e[2 * v + 1];
      const tk = `${m.w[4 * v]},${m.w[4 * v + 1]},${m.w[4 * v + 2]},${m.w[4 * v + 3]},${m.s[4 * v]},${m.s[4 * v + 1]},${m.s[4 * v + 2]},${m.s[4 * v + 3]}`;
      let t = tabIndex.get(tk);
      if (t === undefined) {
        t = tab.length / 8;
        if (t > 65535) throw new Error(`${group}: more than 65536 distinct wall/style values`);
        tabIndex.set(tk, t);
        tab.push(m.w[4 * v], m.w[4 * v + 1], m.w[4 * v + 2], m.w[4 * v + 3], m.s[4 * v], m.s[4 * v + 1], m.s[4 * v + 2], m.s[4 * v + 3]);
      }
      tupV[g] = t;
    }
    for (let q = 0; q < m.i.length; q++) idx[io + q] = m.i[q];
    const rec = { key: it.key, name: it.name, pick: it.pick, c, vo, v: nv, io, i: m.i.length };
    if (it.patch) rec.patch = it.patch;
    if (it.tree !== undefined) rec.tree = it.tree;
    if (it.kind) rec.kind = it.kind;
    recs.push(rec);
    vo += nv; io += m.i.length;
  });
  const total = off.tab + tab.length * 4;
  const bytes = new Uint8Array(total);
  const put = (o, a) => bytes.set(new Uint8Array(a.buffer, a.byteOffset, a.byteLength), o);
  put(off.pos, pos); put(off.nrm, nrm); put(off.st, st); put(off.edge, edge); put(off.tup, tupV);
  put(off.idx, idx); put(off.tab, new Float32Array(tab));
  return {
    manifest: { version: BAKE_VERSION, group, vertices: V, indices: I, idx32: big, tuples: tab.length / 8, offsets: off,
      bytes: total, duplicateVerticesRemoved: dupSaved, items: recs },
    bytes,
  };
}

/** Decoded group: typed-array views shared by all items (no per-vertex JS objects). */
export function decodeGroup(manifest, buffer) {
  const o = manifest.offsets, V = manifest.vertices, I = manifest.indices;
  return {
    manifest,
    pos: new Float32Array(buffer, o.pos, V * 3),
    nrm: new Int8Array(buffer, o.nrm, V * 4),
    st: new Float32Array(buffer, o.st, V * 2),
    edge: new Float32Array(buffer, o.edge, V * 2),
    tup: new Uint16Array(buffer, o.tup, V),
    idx: manifest.idx32 ? new Uint32Array(buffer, o.idx, I) : new Uint16Array(buffer, o.idx, I),
    tab: new Float32Array(buffer, o.tab, manifest.tuples * 8),
  };
}

/**
 * Builds one Cesium.Geometry (facade shader layout) from several items of a decoded group.
 * Merging items here (instead of one GeometryInstance per item) keeps Cesium's batching work tiny.
 */
export function geometryFromItems(g, recs) {
  let V = 0, I = 0;
  for (const r of recs) { V += r.v; I += r.i; }
  const p = new Float64Array(V * 3), n = new Float32Array(V * 3), st = new Float32Array(V * 2), e = new Float32Array(V * 2);
  const w = new Float32Array(V * 4), s = new Float32Array(V * 4);
  const idx = V > 65535 ? new Uint32Array(I) : new Uint16Array(I);
  let vo = 0, io = 0;
  for (const r of recs) {
    const [cx, cy, cz] = r.c;
    for (let v = 0; v < r.v; v++) {
      const src = r.vo + v, dst = vo + v;
      p[3 * dst] = cx + g.pos[3 * src]; p[3 * dst + 1] = cy + g.pos[3 * src + 1]; p[3 * dst + 2] = cz + g.pos[3 * src + 2];
      n[3 * dst] = g.nrm[4 * src] / 127; n[3 * dst + 1] = g.nrm[4 * src + 1] / 127; n[3 * dst + 2] = g.nrm[4 * src + 2] / 127;
      const t = g.tup[src] * 8;
      for (let q = 0; q < 4; q++) { w[4 * dst + q] = g.tab[t + q]; s[4 * dst + q] = g.tab[t + 4 + q]; }
    }
    st.set(g.st.subarray(2 * r.vo, 2 * (r.vo + r.v)), 2 * vo);
    e.set(g.edge.subarray(2 * r.vo, 2 * (r.vo + r.v)), 2 * vo);
    for (let q = 0; q < r.i; q++) idx[io + q] = g.idx[r.io + q] + vo;
    vo += r.v; io += r.i;
  }
  return arraysToGeometry({ p, n, st, e, w, s, idx });
}

export function arraysToGeometry({ p, n, st, e, w, s, idx }) {
  const F = Cesium.ComponentDatatype.FLOAT;
  const A = (values, k, dt = F) => new Cesium.GeometryAttribute({ componentDatatype: dt, componentsPerAttribute: k, values });
  return new Cesium.Geometry({
    attributes: {
      position: A(p, 3, Cesium.ComponentDatatype.DOUBLE), normal: A(n, 3), st: A(st, 2),
      wall: A(w, 4), style: A(s, 4), edge: A(e, 2),
    },
    indices: idx,
    primitiveType: Cesium.PrimitiveType.TRIANGLES,
    boundingSphere: Cesium.BoundingSphere.fromVertices(p),
  });
}

/** Item vertices in a local ENU frame (for the GLB export): positions, normals and base colours. */
export function itemArrays(g, r) {
  const p = new Float64Array(r.v * 3), n = new Float32Array(r.v * 3), w = new Float32Array(r.v * 4), s = new Float32Array(r.v * 4);
  for (let v = 0; v < r.v; v++) {
    const src = r.vo + v;
    for (let q = 0; q < 3; q++) { p[3 * v + q] = r.c[q] + g.pos[3 * src + q]; n[3 * v + q] = g.nrm[4 * src + q] / 127; }
    const t = g.tup[src] * 8;
    for (let q = 0; q < 4; q++) { w[4 * v + q] = g.tab[t + q]; s[4 * v + q] = g.tab[t + 4 + q]; }
  }
  const idx = g.idx.subarray(r.io, r.io + r.i);
  return { p, n, w, s, idx };
}
