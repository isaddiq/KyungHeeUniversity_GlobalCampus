// Pre-baked campus geometry: encoder (used offline by scripts/bake_models.py through tools/bake.html) and
// decoder (used by the site at run time). One manifest + one binary per group (buildings, ground objects).
//
// An "item" is one selectable/exportable object (a building, a landmark, a fountain, a hedge ...):
//   { key, name, group, pick, patch?, kind?, mesh: { p, n, st, w, s, e, i } }   (Mesh layout from mesh.js)
// Binary layout per group (every section 4-byte aligned; GitHub Pages gzips it in transit). Quantised and
// delta-coded so that gzip finds the regularity of the procedural meshes (measured: positions 1240 -> ~720 kB,
// indices 1073 -> ~30 kB gzipped for the buildings, against plain int16 / high-water codes):
//   pos  Int16 planar (all x, all y, all z): per-item running deltas of the position relative to the item
//        centre, in steps of the item's `q` metres (< 4 mm here)
//   nrm  Int8    x4  unit normal * 127 (4th byte padding)
//   st   Int16 planar (all u, all h): per-item running deltas of the facade coordinates (metres along the
//        wall, metres above the datum) in steps of the item's qu / qh (a few mm)
//   edge Int16   x2  wall length and ground level under the wall, in centimetres
//   tup  Uint16  x1  index into the group's (wall rgba, style4) table: few distinct values per item
//   idx  per item Uint16 (Uint32 if a code does not fit): zigzag deltas of consecutive local indices
//   tab  Float32 x8  the (wall, style) table
export const BAKE_VERSION = 4;
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
  let V = 0, idxBytes = 0, dupSaved = 0;
  const meshes = items.map((it) => {
    const m = dedupe(it.mesh);
    dupSaved += it.mesh.p.length / 3 - m.p.length / 3;
    V += m.p.length / 3;
    // zigzag deltas of consecutive indices
    m.codes = new Uint32Array(m.i.length);
    let prev = 0, wide = false;
    for (let a = 0; a < m.i.length; a++) {
      const d = m.i[a] - prev; prev = m.i[a];
      const z = d >= 0 ? 2 * d : -2 * d - 1;
      m.codes[a] = z;
      if (z > 0xffff) wide = true;
    }
    m.wide = wide;
    idxBytes = align4(idxBytes + m.i.length * (wide ? 4 : 2));
    return m;
  });
  const off = { pos: 0 };
  off.nrm = align4(off.pos + V * 6);
  off.st = off.nrm + V * 4;
  off.edge = off.st + V * 4;
  off.tup = off.edge + V * 4;
  off.idx = align4(off.tup + V * 2);
  off.tab = off.idx + idxBytes;
  const pos = new Int16Array(V * 3), nrm = new Int8Array(V * 4), st = new Int16Array(V * 2), edge = new Int16Array(V * 2);
  const tupV = new Uint16Array(V);
  const idxBuf = new ArrayBuffer(idxBytes);
  const cm = (x) => {
    const q = Math.round(x * 100);
    if (q < -32768 || q > 32767) throw new Error(`${group}: edge value ${x} outside the int16 centimetre range`);
    return q;
  };
  let vo = 0, ib = 0;
  items.forEach((it, k) => {
    const m = meshes[k], nv = m.p.length / 3;
    // item centre (middle of the bounding box, doubles in the manifest) and position step
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    for (let v = 0; v < nv; v++) {
      const x = m.p[3 * v], y = m.p[3 * v + 1], z = m.p[3 * v + 2];
      if (x < x0) x0 = x; if (y < y0) y0 = y; if (z < z0) z0 = z; if (x > x1) x1 = x; if (y > y1) y1 = y; if (z > z1) z1 = z;
    }
    const c = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2].map((q) => Math.round(q * 1000) / 1000);
    const half = Math.max(x1 - c[0], c[0] - x0, y1 - c[1], c[1] - y0, z1 - c[2], c[2] - z0, 1e-3);
    const q = half / 32000;
    let mu = 1e-3, mh = 1e-3;
    for (let v = 0; v < nv; v++) { mu = Math.max(mu, Math.abs(m.st[2 * v])); mh = Math.max(mh, Math.abs(m.st[2 * v + 1])); }
    const qu = mu / 32000, qh = mh / 32000;
    for (let v = 0; v < nv; v++) {
      const g = vo + v;
      for (let a = 0; a < 3; a++) pos[3 * g + a] = Math.round((m.p[3 * v + a] - c[a]) / q);
      for (let a = 0; a < 3; a++) nrm[4 * g + a] = Math.max(-127, Math.min(127, Math.round(m.n[3 * v + a] * 127)));
      st[2 * g] = Math.round(m.st[2 * v] / qu); st[2 * g + 1] = Math.round(m.st[2 * v + 1] / qh);
      edge[2 * g] = cm(m.e[2 * v]); edge[2 * g + 1] = cm(m.e[2 * v + 1]);
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
    const wide = m.wide;
    const idx = wide ? new Uint32Array(idxBuf, ib, m.i.length) : new Uint16Array(idxBuf, ib, m.i.length);
    idx.set(m.codes);
    const rec = { key: it.key, name: it.name, pick: it.pick, c, q, qu, qh, vo, v: nv, ib, iw: wide ? 4 : 2, i: m.i.length };
    for (const [kk, val] of Object.entries(it)) if (!(kk in rec) && kk !== "mesh" && kk !== "group" && val !== undefined) rec[kk] = val;
    recs.push(rec);
    vo += nv; ib = align4(ib + m.i.length * (wide ? 4 : 2));
  });
  // planar, per-item running deltas (Int16 storage wraps; the decoder wraps the same way)
  const planarDelta = (src, k) => {
    const out = new Int16Array(V * k);
    for (const r of recs) for (let a = 0; a < k; a++) {
      let prev = 0;
      for (let v = 0; v < r.v; v++) { const x = src[k * (r.vo + v) + a]; out[a * V + r.vo + v] = x - prev; prev = x; }
    }
    return out;
  };
  const posD = planarDelta(pos, 3), stD = planarDelta(st, 2);
  const total = off.tab + tab.length * 4;
  const bytes = new Uint8Array(total);
  const put = (o, a) => bytes.set(new Uint8Array(a.buffer, a.byteOffset, a.byteLength), o);
  put(off.pos, posD); put(off.nrm, nrm); put(off.st, stD); put(off.edge, edge); put(off.tup, tupV);
  bytes.set(new Uint8Array(idxBuf), off.idx); put(off.tab, new Float32Array(tab));
  return {
    manifest: { version: BAKE_VERSION, group, vertices: V, indices: recs.reduce((a, r) => a + r.i, 0), tuples: tab.length / 8,
      offsets: off, bytes: total, duplicateVerticesRemoved: dupSaved, items: recs },
    bytes,
  };
}

/**
 * Fetches and decodes one group listed in web/data/baked/manifest.json ({ manifest, bin } file names,
 * content-hashed so a new bake never mixes with a cached old file).
 */
export async function loadBakedGroup(dir, entry, signal) {
  const [manifest, buffer] = await Promise.all([
    fetch(`${dir}/${entry.manifest}`, { signal }).then((r) => { if (!r.ok) throw new Error(`${entry.manifest}: HTTP ${r.status}`); return r.json(); }),
    fetch(`${dir}/${entry.bin}`, { signal }).then((r) => { if (!r.ok) throw new Error(`${entry.bin}: HTTP ${r.status}`); return r.arrayBuffer(); }),
  ]);
  if (manifest.version !== BAKE_VERSION) throw new Error(`baked ${manifest.group}: version ${manifest.version}`);
  return decodeGroup(manifest, buffer);
}

/** Top-level manifest, or null when there is no bake (the site then generates the models itself). */
export async function loadBakedIndex(dir) {
  if (/[?&]procedural=1/.test(location.search)) return null;
  try {
    const r = await fetch(`${dir}/manifest.json`, { cache: "no-cache" });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

/** Decoded group: typed-array views shared by all items (no per-vertex JS objects). */
export function decodeGroup(manifest, buffer) {
  const o = manifest.offsets, V = manifest.vertices;
  const undelta = (at, k) => {
    const d = new Int16Array(buffer, at, V * k), out = new Int16Array(V * k);
    for (const r of manifest.items) for (let a = 0; a < k; a++) {
      let acc = 0;
      for (let v = 0; v < r.v; v++) { acc = (acc + d[a * V + r.vo + v]) << 16 >> 16; out[k * (r.vo + v) + a] = acc; }
    }
    return out;
  };
  return {
    manifest, buffer,
    pos: undelta(o.pos, 3),
    nrm: new Int8Array(buffer, o.nrm, V * 4),
    st: undelta(o.st, 2),
    edge: new Int16Array(buffer, o.edge, V * 2),
    tup: new Uint16Array(buffer, o.tup, V),
    tab: new Float32Array(buffer, o.tab, manifest.tuples * 8),
  };
}

/** Local indices of one item (decodes the zigzag deltas). */
function itemIndices(g, r) {
  const at = g.manifest.offsets.idx + r.ib;
  const codes = r.iw === 4 ? new Uint32Array(g.buffer, at, r.i) : new Uint16Array(g.buffer, at, r.i);
  const out = r.v > 65535 ? new Uint32Array(r.i) : new Uint16Array(r.i);
  for (let a = 0, prev = 0; a < r.i; a++) {
    const z = codes[a];
    prev += z % 2 ? -(z + 1) / 2 : z / 2;
    out[a] = prev;
  }
  return out;
}

/**
 * Builds one Cesium.Geometry (facade shader layout) from several items of a decoded group.
 * Merging items here (instead of one GeometryInstance per item) keeps Cesium's batching work small.
 */
export function geometryFromItems(g, recs) {
  let V = 0, I = 0;
  for (const r of recs) { V += r.v; I += r.i; }
  const p = new Float64Array(V * 3), n = new Float32Array(V * 3), st = new Float32Array(V * 2), e = new Float32Array(V * 2);
  const w = new Float32Array(V * 4), s = new Float32Array(V * 4);
  const idx = V > 65535 ? new Uint32Array(I) : new Uint16Array(I);
  let vo = 0, io = 0;
  for (const r of recs) {
    const [cx, cy, cz] = r.c, q = r.q;
    for (let v = 0; v < r.v; v++) {
      const src = r.vo + v, dst = vo + v;
      p[3 * dst] = cx + g.pos[3 * src] * q; p[3 * dst + 1] = cy + g.pos[3 * src + 1] * q; p[3 * dst + 2] = cz + g.pos[3 * src + 2] * q;
      n[3 * dst] = g.nrm[4 * src] / 127; n[3 * dst + 1] = g.nrm[4 * src + 1] / 127; n[3 * dst + 2] = g.nrm[4 * src + 2] / 127;
      e[2 * dst] = g.edge[2 * src] / 100; e[2 * dst + 1] = g.edge[2 * src + 1] / 100;
      const t = g.tup[src] * 8;
      for (let a = 0; a < 4; a++) { w[4 * dst + a] = g.tab[t + a]; s[4 * dst + a] = g.tab[t + 4 + a]; }
    }
    for (let v = 0; v < r.v; v++) { st[2 * (vo + v)] = g.st[2 * (r.vo + v)] * r.qu; st[2 * (vo + v) + 1] = g.st[2 * (r.vo + v) + 1] * r.qh; }
    const li = itemIndices(g, r);
    for (let a = 0; a < r.i; a++) idx[io + a] = li[a] + vo;
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

/** One item's vertices for the GLB export: ECEF positions, normals, wall rgba and style, indices. */
export function itemArrays(g, r) {
  const p = new Float64Array(r.v * 3), n = new Float32Array(r.v * 3), w = new Float32Array(r.v * 4), s = new Float32Array(r.v * 4);
  for (let v = 0; v < r.v; v++) {
    const src = r.vo + v;
    for (let a = 0; a < 3; a++) { p[3 * v + a] = r.c[a] + g.pos[3 * src + a] * r.q; n[3 * v + a] = g.nrm[4 * src + a] / 127; }
    const t = g.tup[src] * 8;
    for (let a = 0; a < 4; a++) { w[4 * v + a] = g.tab[t + a]; s[4 * v + a] = g.tab[t + 4 + a]; }
  }
  return { p, n, w, s, idx: itemIndices(g, r) };
}

/** Same arrays from a procedural Mesh (mesh.js), for the GLB export of generated items (e.g. trees). */
export function meshArrays(m) {
  return { p: Float64Array.from(m.p), n: Float32Array.from(m.n), w: Float32Array.from(m.w), s: Float32Array.from(m.s),
    idx: m.p.length / 3 > 65535 ? Uint32Array.from(m.i) : Uint16Array.from(m.i) };
}
