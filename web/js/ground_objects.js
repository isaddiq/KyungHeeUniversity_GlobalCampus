// 3D ground details use mapped outlines where available and estimated geometry from campus photographs.
import { Mesh, Frame, Local, STY, hex, createFacadeAppearance } from "./mesh.js";
import { figure } from "./khu_landmarks.js";
import { geometryFromItems } from "./baked.js";
const Cesium = window.Cesium;

const GRANITE = hex("#dcd8cf"), TILE = hex("#3d8fc0"), WHITE = hex("#f3f1ec"), HEDGE = hex("#3c6a2c"), JET = hex("#e8f4fb");

function centroidOf(ring) {
  let x = 0, y = 0;
  const pts = ring.slice(0, -1);
  for (const [a, b] of pts) { x += a; y += b; }
  return [x / pts.length, y / pts.length];
}

/** Annulus top (flat ring) between radii r0 < r1 at height z. */
function annulus(G, r0, r1, z, col, seg = 40) {
  for (let k = 0; k < seg; k++) {
    const A = k / seg * 2 * Math.PI, B = (k + 1) / seg * 2 * Math.PI;
    const P = (r, a) => [Math.cos(a) * r, Math.sin(a) * r, z];
    G.quad(P(r0, A), P(r0, B), P(r1, B), P(r1, A), [0, 0, 1], [[A * r1, 0], [B * r1, 0], [B * r1, r1 - r0], [A * r1, r1 - r0]], col, STY.STATUE, 1, 2 * Math.PI * r1);
  }
}

function fountain(mesh, water, o, dem) {
  const ring = o.c;
  const [clon, clat] = centroidOf(ring);
  // basins are level: sit on the highest DTM point of the outline (the 30 m DTM slopes across small basins)
  const gmin = Math.max(...ring.map(([lo, la]) => dem.heightEllipsoid(lo, la)), dem.heightEllipsoid(clon, clat));
  const f = new Frame(clon, clat, gmin);
  const G = new Local(mesh, f, [1, 0]);
  // basin radius from the mapped outline area
  let area = 0;
  const loc = ring.map(([lo, la]) => f.local(lo, la));
  for (let k = 0; k < loc.length - 1; k++) area += loc[k][0] * loc[k + 1][1] - loc[k + 1][0] * loc[k][1];
  const R = Math.sqrt(Math.abs(area) / 2 / Math.PI), Ro = R + o.rim_w, zr = o.rim_h, zw = o.water;
  G.cyl({ s: 0, t: 0, z0: -1.5, z1: zr, r0: Ro, seg: 48, col: GRANITE, sty: STY.ASHLAR });          // outer rim wall
  G.cyl({ s: 0, t: 0, z0: -0.45, z1: zr, r0: R, seg: 48, col: TILE, sty: STY.STATUE });            // tiled inner wall
  annulus(G, R, Ro, zr, GRANITE, 48);
  G.cyl({ s: 0, t: 0, z0: -0.46, z1: -0.45, r0: R, seg: 48, col: TILE, sty: STY.STATUE, cap: true }); // basin floor
  const pos = Cesium.Cartesian3.fromDegreesArray(ring.slice(0, -1).flat());
  water.push(new Cesium.GeometryInstance({
    id: { kind: "landmark", props: { id: o.id, name: o.name || "분수 · Fountain", source: "OSM outline; rim, jets and centrepiece estimated from photographs", ground: gmin } },
    geometry: new Cesium.PolygonGeometry({ polygonHierarchy: new Cesium.PolygonHierarchy(pos), height: gmin + zw, vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT }),
    attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString("#5fb6e0").withAlpha(0.72)) },
  }));
  if (o.jets_ring) {                       // ring of nozzles with arcs of water towards the centre
    const n = 28, rj = R * 0.8;
    for (let k = 0; k < n; k++) {
      const a = k / n * 2 * Math.PI, c = Math.cos(a), s = Math.sin(a);
      const p0 = [c * rj, s * rj, zw], p1 = [c * rj * 0.72, s * rj * 0.72, zw + 1.5], p2 = [c * rj * 0.35, s * rj * 0.35, zw + 0.9];
      G.cylBetween(p0, p1, 0.016, JET, STY.STATUE, 4);
      G.cylBetween(p1, p2, 0.014, JET, STY.STATUE, 4);
    }
  }
  const cp = o.centre;
  if (cp?.type === "obelisk") {
    // figure faces along `facing` (unit E,N) - towards the open side of the plaza
    const fa = cp.facing ?? [0.6, -0.8];
    const P = new Local(mesh, f, [-fa[1], fa[0]]);                          // +t = facing direction
    const b = cp.base, z0 = zw - 0.2, zp = zw + 1.3;
    P.box({ s0: -b / 2 - 0.15, s1: b / 2 + 0.15, t0: -b / 2 - 0.15, t1: b / 2 + 0.15, z0, z1: zw + 0.25, col: WHITE, sty: STY.STATUE });
    P.box({ s0: -b / 2, s1: b / 2, t0: -b / 2, t1: b / 2, z0: zw + 0.25, z1: zp, col: WHITE, sty: STY.STATUE });
    P.box({ s0: -b / 2 - 0.08, s1: b / 2 + 0.08, t0: -b / 2 - 0.08, t1: b / 2 + 0.08, z0: zp, z1: zp + 0.12, col: WHITE, sty: STY.CORNICE });
    const top = cp.h - 0.45 + zw - 0.2;
    P.cyl({ s: 0, t: 0, z0: zp + 0.12, z1: top, r0: 0.3 * Math.SQRT2, r1: 0.2 * Math.SQRT2, seg: 4, a0: Math.PI / 4, col: WHITE, sty: STY.OBELISK });
    P.cyl({ s: 0, t: 0, z0: top, z1: top + 0.45, r0: 0.2 * Math.SQRT2, r1: 0.02, seg: 4, a0: Math.PI / 4, col: WHITE, sty: STY.STATUE });
    if (cp.figure === "seated") {
      P.box({ s0: -0.45, s1: 0.45, t0: b / 2, t1: b / 2 + 0.55, z0: zw + 0.25, z1: zw + 0.55, col: WHITE, sty: STY.STATUE });
      figure(P, 0, b / 2 + 0.3, zw + 0.55, 1.15, "seated", WHITE);
    }
  }
}

function hedge(mesh, o, dem) {
  const ring = o.c;
  const [clon, clat] = centroidOf(ring);
  const f = new Frame(clon, clat, 0);
  const loc = ring.map(([lo, la]) => [...f.local(lo, la), dem.heightEllipsoid(lo, la)]);
  let area = 0;
  for (let k = 0; k < loc.length - 1; k++) area += loc[k][0] * loc[k + 1][1] - loc[k + 1][0] * loc[k][1];
  const ccw = area > 0;
  for (let k = 0; k < loc.length - 1; k++) {
    const a = loc[k], b = loc[k + 1];
    const L = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (L < 0.2) continue;
    const ax = [(b[0] - a[0]) / L, (b[1] - a[1]) / L];
    const G = new Local(mesh, f, ax, [a[0], a[1]]);
    const tin = ccw ? 1 : -1;                                                // left normal points inward on a CCW ring
    const z = Math.min(a[2], b[2]);
    G.box({ s0: -0.1, s1: L + 0.1, t0: Math.min(0, tin * o.w), t1: Math.max(0, tin * o.w), z0: z - 1.2, z1: z + o.h, col: HEDGE, sty: STY.FOLIAGE });
    // scalloped edge: rounded bulges along the hedge (as in the photographs)
    for (let s = 0.6; s < L - 0.3; s += 1.4) G.sphere({ s, t: tin * o.w * 0.5, z: z + o.h * 0.75, r: o.w * 0.75, col: HEDGE, sty: STY.FOLIAGE, seg: 7, sz: 0.8 });
  }
}

function planter(mesh, o, dem) {
  const [lon, lat] = o.p;
  const f = new Frame(lon, lat, dem.heightEllipsoid(lon, lat));
  const G = new Local(mesh, f, [1, 0]);
  const r = Math.min(1.6, Math.max(0.5, o.r));
  G.cyl({ s: 0, t: 0, z0: -1.2, z1: 0.15, r0: r * 0.55, r1: r * 0.7, seg: 18, col: GRANITE, sty: STY.ASHLAR });
  G.cyl({ s: 0, t: 0, z0: 0.15, z1: 0.6, r0: r * 0.7, r1: r, seg: 18, col: GRANITE, sty: STY.ASHLAR });
  G.sphere({ s: 0, t: 0, z: 0.55, r: r * 0.82, col: hex("#557a36"), sty: STY.FOLIAGE, seg: 9, sz: 0.38, jit: 0.15 });
}

/** Ball-stop net along a line: steel posts every 4 m, top rail, see-through net (NET shader style). */
function net(mesh, o, dem) {
  const [a0, b0] = [o.c[0], o.c[o.c.length - 1]];
  const f = new Frame(a0[0], a0[1], 0);
  const A = f.local(...a0), B = f.local(...b0);
  const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
  const ax = [(B[0] - A[0]) / L, (B[1] - A[1]) / L];
  const G = new Local(mesh, f, ax, A);
  const zAt = (s) => { const [lo, la] = f.lonlat(A[0] + ax[0] * s, A[1] + ax[1] * s); return dem.heightEllipsoid(lo, la); };
  const n = Math.max(1, Math.round(L / (o.post_spacing ?? 4)));
  const POST = hex("#5b6a62"), NETC = hex("#2f6e4e");
  for (let k = 0; k < n; k++) {
    const s0 = k * L / n, s1 = (k + 1) * L / n, z0 = Math.min(zAt(s0), zAt(s1)) - 1.0, z1 = Math.max(zAt(s0), zAt(s1)) + o.h;
    G.quad([s0, 0, z0], [s1, 0, z0], [s1, 0, z1], [s0, 0, z1], [0, 1, 0], [[0, 0], [s1 - s0, 0], [s1 - s0, z1 - z0], [0, z1 - z0]], NETC, STY.NET, z1 - z0, s1 - s0);
  }
  for (let k = 0; k <= n; k++) { const s = k * L / n, z = zAt(s); G.cyl({ s, t: 0, z0: z - 1.2, z1: z + o.h + 0.1, r0: 0.06, seg: 6, col: POST, sty: STY.STATUE }); }
  G.cylBetween([0, 0, zAt(0) + o.h], [L, 0, zAt(L) + o.h], 0.04, POST, STY.STATUE, 5);
}

const TERRACE_TOP = {
  tread: "#b8bab6", nosing: "#d3d4ce", landing: "#bfc1bc", rim: "#dbddd5",
  grass: "#648849", stone: "#828585", soil: "#8c8268", brick: "#bd8a74",
};

/** Polygonal treads with a level run and a terrain-derived crossfall. */
function terrace(mesh, o, dem) {
  const f = new Frame(...o.p);
  const G = new Local(mesh, f, o.axis);
  const [ax, ay] = o.axis;
  const height = (s, t) => dem.heightEllipsoid(...f.lonlat(ax * s - ay * t, ay * s + ax * t));
  const castConcrete = hex("#adb0a9"), rimWall = hex("#cbcec5");
  for (const part of o.surfaces) {
    const points = [], holes = [];
    const top = hex(TERRACE_TOP[part.k]);
    const topAt = (s, t) => height(s, part.t ?? t) + part.lift;
    const sty = part.k === "grass" ? STY.FOLIAGE : STY.STATUE;
    const wall = part.k === "rim" ? rimWall : castConcrete;
    for (const ring of part.c) {
      if (points.length) holes.push(points.length);
      points.push(...ring.slice(0, -1));
      for (let i = 0; i < ring.length - 1; i++) {
        const [s0, t0] = ring[i], [s1, t1] = ring[i + 1];
        const ds = s1 - s0, dt = t1 - t0, len = Math.hypot(ds, dt);
        if (len < 0.002) continue;
        const z0 = topAt(s0, t0), z1 = topAt(s1, t1), depth = 4.5;
        G.quad([s0, t0, z0 - depth], [s1, t1, z1 - depth], [s1, t1, z1], [s0, t0, z0],
          [dt / len, -ds / len, 0], [[0, 0], [len, 0], [len, depth], [0, depth]], wall, STY.STATUE, depth, len);
      }
    }
    const tri = Cesium.PolygonPipeline.triangulate(points.map(([s, t]) => new Cesium.Cartesian2(s, t)), holes);
    const up = G.D(0, 0, 1);
    const ids = points.map(([s, t]) => mesh.v(G.P(s, t, topAt(s, t)), up, s, t, [...top, 1],
      [3.6, 3.6, sty, 1], [0, -99]));
    for (let i = 0; i < tri.length; i += 3) mesh.tri(ids[tri[i]], ids[tri[i + 1]], ids[tri[i + 2]]);
  }
  const bark = hex("#665143"), leaves = hex("#58783c");
  for (const tree of o.trees) {
    const [s, t] = tree.p, z = height(s, tree.t) + 0.2;
    G.cyl({ s, t, z0: z - 0.07, z1: z + 3.05, r0: 0.18, r1: 0.12, col: bark, sty: STY.STATUE });
    for (const [ds, dt, dz, r] of [[-0.62, 0.2, 3.1, 1.4], [0.68, 0.35, 3.35, 1.48], [0, -0.54, 3.65, 1.46]]) {
      G.sphere({ s: s + ds, t: t + dt, z: z + dz, r, col: leaves, sty: STY.FOLIAGE, seg: 9, sz: 0.72, jit: 0.14 });
    }
  }
}

const KERBC = hex("#cfcbc2");
/** Granite kerb (0.2 m wide, 0.15 m upstand) following the DTM along a road edge, in <= 4 m pieces. */
function kerb(mesh, o, dem) {
  const f = new Frame(o.c[0][0], o.c[0][1], 0);
  const pts = o.c.map(([lo, la]) => f.local(lo, la));
  for (let k = 0; k < pts.length - 1; k++) {
    const A = pts[k], B = pts[k + 1];
    const L = Math.hypot(B[0] - A[0], B[1] - A[1]);
    if (L < 0.05) continue;
    const ax = [(B[0] - A[0]) / L, (B[1] - A[1]) / L];
    const G = new Local(mesh, f, ax, A);
    const n = Math.max(1, Math.ceil(L / 4));
    for (let j = 0; j < n; j++) {
      const s0 = j * L / n, s1 = (j + 1) * L / n;
      const [l0, a0] = f.lonlat(A[0] + ax[0] * s0, A[1] + ax[1] * s0), [l1, a1] = f.lonlat(A[0] + ax[0] * s1, A[1] + ax[1] * s1);
      const z0 = dem.heightEllipsoid(l0, a0), z1 = dem.heightEllipsoid(l1, a1);
      G.box({ s0, s1, t0: -0.1, t1: 0.1, z0: Math.min(z0, z1) - 0.25, z1: (z0 + z1) / 2 + 0.15, col: KERBC, sty: STY.STATUE });
    }
  }
}

/** Korean stone pagoda (석탑): two-stage podium, body stones and thin roof stones per tier, finial; hedge ring. */
function pagoda(mesh, o, dem) {
  const [lon, lat] = o.p;
  const f = new Frame(lon, lat, dem.heightEllipsoid(lon, lat));
  const G = new Local(mesh, f, o.axis ?? [1, 0]);
  const ST = hex("#b8b3a8"), DK = hex("#a39e93");
  const H = o.h, n = o.tiers;
  G.box({ s0: -1.5, s1: 1.5, t0: -1.5, t1: 1.5, z0: -0.4, z1: 0.35, col: ST, sty: STY.ASHLAR });
  G.box({ s0: -1.1, s1: 1.1, t0: -1.1, t1: 1.1, z0: 0.35, z1: 0.95, col: ST, sty: STY.ASHLAR });
  G.box({ s0: -1.25, s1: 1.25, t0: -1.25, t1: 1.25, z0: 0.95, z1: 1.1, col: DK, sty: STY.STATUE });
  let z = 1.1;
  const tierH = (H - 1.1 - 0.7) / n;
  for (let k = 0; k < n; k++) {
    const w = 1.15 - k * 0.09, bw = w * 0.55;
    const bh = k === 0 ? tierH * 1.25 : tierH * 0.6;
    G.box({ s0: -bw, s1: bw, t0: -bw, t1: bw, z0: z, z1: z + bh, col: ST, sty: STY.STATUE });      // body stone
    z += bh;
    G.box({ s0: -w, s1: w, t0: -w, t1: w, z0: z, z1: z + 0.12, col: DK, sty: STY.STATUE });          // roof stone
    G.cyl({ s: 0, t: 0, z0: z + 0.12, z1: z + 0.22, r0: w * Math.SQRT2, r1: w * 0.75 * Math.SQRT2, seg: 4, a0: Math.PI / 4, col: DK, sty: STY.STATUE });
    z += 0.22;
  }
  G.cyl({ s: 0, t: 0, z0: z, z1: z + 0.55, r0: 0.08, seg: 8, col: DK, sty: STY.STATUE });
  G.sphere({ s: 0, t: 0, z: z + 0.25, r: 0.16, col: DK, seg: 8 });
  G.sphere({ s: 0, t: 0, z: z + 0.5, r: 0.11, col: DK, seg: 8 });
  if (o.hedge) {                                   // clipped hedge blocks around the base, gaps on the path axes
    const r = o.hedge / 2, HC = hex("#3c6a2c");
    for (const [sa, ta] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
      G.box({ s0: Math.min(sa * 0.9, sa * r), s1: Math.max(sa * 0.9, sa * r), t0: Math.min(ta * (r - 0.6), ta * r), t1: Math.max(ta * (r - 0.6), ta * r), z0: -1.2, z1: 0.9, col: HC, sty: STY.FOLIAGE });
      G.box({ s0: Math.min(sa * (r - 0.6), sa * r), s1: Math.max(sa * (r - 0.6), sa * r), t0: Math.min(ta * 0.9, ta * r), t1: Math.max(ta * 0.9, ta * r), z0: -1.2, z1: 0.9, col: HC, sty: STY.FOLIAGE });
    }
  }
}

/** Football goal: two white posts 7.32 m apart and a crossbar at 2.44 m, across `axis`. */
function goal(mesh, o, dem) {
  const [lon, lat] = o.p;
  const f = new Frame(lon, lat, dem.heightEllipsoid(lon, lat));
  const G = new Local(mesh, f, o.axis ?? [1, 0]);
  const W = hex("#f4f4f2");
  for (const s of [-3.66, 3.66]) G.cyl({ s, t: 0, z0: -1.0, z1: 2.44, r0: 0.06, seg: 8, col: W, sty: STY.STATUE });
  G.cylBetween([-3.66, 0, 2.44], [3.66, 0, 2.44], 0.06, W, STY.STATUE, 8);
}

function pergola(mesh, o, dem) {
  const f = new Frame(...o.p, dem.heightEllipsoid(...o.p));
  const G = new Local(mesh, f, o.axis);
  const a = o.length / 2, b = o.width / 2, h = 2.68;
  const concrete = o.open_roof ? WHITE : hex("#c8c4b6");
  const box = (s0, s1, t0, t1, z0, z1, col = concrete) => G.box({s0, s1, t0, t1, z0, z1, col, sty: STY.STATUE});
  if (o.open_roof) {
    for (let t = -b + 0.22; t < b; t += (2 * b - 0.40) / 4) {
      G.profile([[-a + 0.25, -0.04], [-a + 0.51, -0.04], [-a - 0.14, h], [-a - 0.40, h]], t - 0.12, t + 0.12, concrete);
      G.profile([[a - 0.32, -0.04], [a - 0.06, -0.04], [a - 0.23, h], [a - 0.49, h]], t - 0.12, t + 0.12, concrete);
      box(-a - 0.52, a + 0.23, t - 0.13, t + 0.13, h - 0.07, h + 0.16);
    }
    for (const s of [-a + 0.42, 0, a - 0.48]) box(s - 0.06, s + 0.06, -b, b, h + 0.04, h + 0.15);
  } else {
    for (const s of [-a + 0.62, a - 0.62]) for (const t of [-b + 0.32, b - 0.32]) {
      box(s - 0.13, s + 0.13, t - 0.13, t + 0.13, -0.12, h);
    }
    box(-a, a, -b, b, h - 0.17, h + 0.05, hex("#736e62"));
  }
  for (const s of [-a + 0.6, a - 0.6]) {
    box(s - 0.26, s + 0.26, -b + 0.34, b - 0.34, 0.43, 0.55, hex("#806950"));
    for (const t of [-b + 0.49, b - 0.49]) box(s - 0.17, s + 0.17, t - 0.10, t + 0.10, 0.02, 0.44);
  }
}

function accessStair(mesh, o, dem) {
  const f = new Frame(...o.c[0]);
  const points = o.c.map((p) => f.local(...p));
  const lengths = points.slice(1).map(([x, y], i) => Math.hypot(x - points[i][0], y - points[i][1]));
  const total = lengths.reduce((a, b) => a + b, 0);
  const base = dem.heightEllipsoid(...o.c[0]) + 0.12;
  const rise = dem.heightEllipsoid(...o.c.at(-1)) + 0.04 - base;
  const stone = hex("#c1bfb5"), tread = hex("#dedacf"), rail = hex("#bcbbae");
  const half = o.w / 2;
  let station = 0;
  for (let i = 0; i < lengths.length; i++) {
    const [x, y] = points[i], [ex, ey] = points[i + 1], len = lengths[i];
    const G = new Local(mesh, f, [(ex - x) / len, (ey - y) / len], [x, y]);
    const lower = base + rise * station / total, upper = base + rise * (station + len) / total;
    const margin = i === lengths.length - 1 ? 0.35 : 0.95;
    const count = Math.max(1, Math.round((upper - lower) / 0.16));
    const run = (len - margin) / count;
    for (let j = 0; j < count; j++) {
      const z = lower + (upper - lower) * (j + 1) / count;
      const s0 = j * run;
      G.box({s0, s1: s0 + run, t0: -half, t1: half, z0: z - 0.9, z1: z, col: tread, sty: STY.STATUE});
    }
    G.box({s0: len - margin, s1: len + (i < lengths.length - 1 ? 0.7 : 0), t0: -half, t1: half,
      z0: upper - 1.0, z1: upper, col: stone, sty: STY.STATUE});
    for (const t of [-half + 0.06, half - 0.06]) {
      for (let s = 0.25; s < len - 0.15; s += 1.45) {
        const z = lower + (upper - lower) * s / len;
        G.cyl({s, t, z0: z - 0.1, z1: z + 0.93, r0: 0.033, seg: 6, col: rail, sty: STY.STATUE});
      }
      G.cylBetween([0, t, lower + 0.93], [len, t, upper + 0.93], 0.045, rail, STY.STATUE, 6);
    }
    station += len;
  }
}

/** White pavilion on a raised deck at the east end of the turf plaza (Engineering Annex renderings, 2026).
 *  Local frame: s along `axis` (south), t to the east; the anchor is the deck's north-east corner. */
function turfPavilion(mesh, o, dem) {
  const f = new Frame(...o.p, dem.heightEllipsoid(...o.p));
  const G = new Local(mesh, f, o.axis);
  const [S, T, H] = o.deck;
  const white = hex("#f1f0eb"), deckTop = hex("#d8d6cf"), stepC = hex("#ecebe5"), leaf = hex("#5f8a3e");
  const box = (s0, s1, t0, t1, z0, z1, col = white, sty = STY.STATUE) => G.box({ s0, s1, t0, t1, z0, z1, col, sty });
  box(0, S, -T, 0, -0.8, H - 0.06);                                     // deck
  box(0.15, S - 0.15, -T + 0.15, -0.15, H - 0.06, H, deckTop);
  const n = 6, run = 0.75;                                              // steps down to the west
  for (let k = 0; k < n; k++) box(0, S, -T - run * (k + 1), -T - run * k, -0.8, H * (n - k - 1) / n + 0.02, stepC);
  const roofZ = H + 3.2;                                                // flat-roofed pavilion on the east side
  box(1.0, 12.0, -1.0, -0.4, H, roofZ);                                 // solid back wall
  box(1.0, 1.5, -5.6, -0.4, H, roofZ);                                  // north end wall
  for (const s of [6.4, 11.6]) G.cyl({ s, t: -5.5, z0: H, z1: roofZ, r0: 0.14, seg: 10, col: white, sty: STY.STATUE });
  box(0.5, 12.5, -6.1, 0.1, roofZ, roofZ + 0.38);
  for (const s of [2.4, 6.0, 9.6]) {                                    // planters and small trees on the deck
    box(s - 0.8, s + 0.8, -8.2, -7.0, H, H + 0.55);
    G.sphere({ s, t: -7.6, z: H + 0.75, r: 0.75, col: leaf, sty: STY.FOLIAGE, seg: 8, sz: 0.6, jit: 0.2 });
  }
  for (const s of [4.2, 11.5]) {
    G.cyl({ s, t: -10.2, z0: H, z1: H + 2.6, r0: 0.12, r1: 0.08, col: hex("#6a5444"), sty: STY.STATUE, seg: 7 });
    G.sphere({ s, t: -10.2, z: H + 3.1, r: 1.25, col: leaf, sty: STY.FOLIAGE, seg: 9, sz: 0.75, jit: 0.15 });
  }
  const frameTop = H + 2.9;                                             // pergola frames over the steps
  for (const t of [-T - 0.5, -T - 2.4, -T - 4.3]) {
    for (const s of [0.4, S / 2, S - 0.4]) box(s - 0.13, s + 0.13, t - 0.13, t + 0.13, -0.3, frameTop);
    box(0.25, S - 0.25, t - 0.14, t + 0.14, frameTop - 0.25, frameTop);
  }
  for (const s of [0.4, S - 0.4]) box(s - 0.12, s + 0.12, -T - 4.45, -T + 0.2, frameTop - 0.22, frameTop - 0.02);
  for (let t = -1.5; t > -T - 12; t -= 6) {                            // pillars and hedges along the tennis fence
    box(S + 2.2, S + 2.7, t - 0.5, t + 0.5, -0.5, 3.3, hex("#e6e3da"), STY.RELIEF);
    if (t - 3 > -T - 12) box(S + 2.25, S + 2.65, t - 5.4, t - 0.6, -0.4, 0.85, hex("#3c6a2c"), STY.FOLIAGE);
  }
}

function cherry(mesh, o, dem) {
  const f = new Frame(...o.p, dem.heightEllipsoid(...o.p) - 0.2);
  const G = new Local(mesh, f, [1, 0]);
  const bark = hex("#685049"), height = o.h, spread = height * 0.36;
  const flowers = ["#f7d2dd", "#f5e6ed", "#ecc1d2", "#f8edf0"].map(hex);
  G.cyl({s: 0, t: 0, z0: 0, z1: height * 0.64, r0: height * 0.033, r1: 0.08, col: bark, sty: STY.STATUE, seg: 7});
  for (let i = 0; i < 6; i++) {
    const a = o.rot + i * 2.39996;
    const s = Math.cos(a) * spread * (0.64 + 0.19 * (i % 3));
    const t = Math.sin(a) * spread * (0.64 + 0.19 * (i % 3));
    const z = height * (0.61 + 0.055 * (i % 4));
    G.cylBetween([0, 0, height * 0.28], [s * 0.92, t * 0.92, z], 0.08, bark, STY.STATUE, 5);
    G.sphere({s, t, z, r: spread * 0.57, col: flowers[i % flowers.length], sty: STY.FOLIAGE, seg: 7, sz: 0.65, jit: 0.21, ph: a});
    G.sphere({s: s * 1.15, t: t * 1.15, z: z + spread * 0.31, r: spread * 0.40,
      col: flowers[(i + 1) % flowers.length], sty: STY.FOLIAGE, seg: 7, sz: 0.75, jit: 0.19, ph: a + 1});
  }
  G.sphere({s: 0.15, t: -0.18, z: height * 0.83, r: spread * 0.60, col: flowers[1], sty: STY.FOLIAGE, seg: 8, sz: 0.76, jit: 0.19});
}

const BUILDERS = { fountain: null, hedge, planter, net, terrace, kerb, pagoda, goal, pergola, stair: accessStair, turf_pavilion: turfPavilion, cherry };
const KIND_NAMES = { fountain: "Fountain", hedge: "Hedge", planter: "Planter", net: "Ball-stop net", terrace: "Terrace seating", kerb: "Kerb",
  pagoda: "Pavilion", goal: "Goal", pergola: "Pergola", stair: "Access stair", turf_pavilion: "Turf pavilion", cherry: "Cherry tree" };

/** One item per ground object (each is its own node in the GLB export): [{ key, name, kind, group, pick, mesh }]. */
export function groundObjectItems(dem, objects) {
  const items = [];
  (objects ?? []).forEach((o, i) => {
    if (!(o.k in BUILDERS)) return;
    const mesh = new Mesh();
    try {
      if (o.k === "fountain") fountain(mesh, [], o, dem);
      else BUILDERS[o.k](mesh, o, dem);
    } catch (e) { console.warn("ground object skipped", o.id, e.message); return; }
    if (mesh.empty) return;
    items.push({ key: o.id ?? `${o.k}-${i}`, name: `${o.name || KIND_NAMES[o.k]}${o.id ? ` (${o.id})` : ""}`, kind: o.k,
      group: "ground_objects", pick: { kind: "ground_detail" }, mesh });
  });
  return items;
}

/** Water surfaces of the fountains (translucent Cesium polygons, built at run time: they are tiny). */
function fountainWater(dem, objects) {
  const water = [];
  for (const o of objects ?? []) if (o.k === "fountain") try { fountain(new Mesh(), water, o, dem); } catch { /* skipped above too */ }
  return water;
}

/**
 * Ground details: from the baked group (`baked` = { group, recs }) or generated in the browser.
 * Kerbs are left out on mobile.
 */
export function buildGroundObjects(viewer, dem, objects, mobile, { baked = null } = {}) {
  const keep = (k) => !(mobile && k === "kerb");
  let geometry = null;
  if (baked) {
    const recs = baked.recs.filter((r) => keep(r.kind));
    if (recs.length) geometry = geometryFromItems(baked.group, recs);
  } else {
    const items = groundObjectItems(dem, (objects ?? []).filter((o) => keep(o.k)));
    if (items.length) {
      const mesh = new Mesh();
      for (const it of items) mesh.append(it.mesh);
      geometry = mesh.geometry();
    }
  }
  const water = fountainWater(dem, objects);
  const prims = [];
  const attributes = { color: Cesium.ColorGeometryInstanceAttribute.fromColor(new Cesium.Color(1, 1, 1, 0)) };
  if (geometry) prims.push(viewer.scene.primitives.add(new Cesium.Primitive({
    geometryInstances: new Cesium.GeometryInstance({ id: { kind: "ground_detail" }, geometry, attributes }),
    appearance: createFacadeAppearance(), asynchronous: true, compressVertices: false,
    shadows: mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.ENABLED,
  })));
  if (water.length) prims.push(viewer.scene.primitives.add(new Cesium.Primitive({
    geometryInstances: water, appearance: new Cesium.PerInstanceColorAppearance({ translucent: true, closed: false }), asynchronous: false,
  })));
  return { prims, exportGeoms: water.map((inst) => ({ group: "Water features", name: inst.id?.props?.name ?? "Fountain water", inst })) };
}
