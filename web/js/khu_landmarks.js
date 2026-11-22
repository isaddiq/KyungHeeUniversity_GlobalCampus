// Landmark models of Kyung Hee Global Campus.
// Placement, orientation and plan dimensions come from OSM footprints (campus_details.json); heights
// marked "documented" come from a published guidebook; all other proportions were measured from
// photographs (scaled to the documented height / footprint) and are labelled illustrative in the UI.
import { Mesh, Frame, Local, STY, hex } from "./mesh.js";
import { archMedallion, capitalCarving, cornerSculpture, crownSculptures, pavilionCrown,
  pavilionRelief, spandrelSculpture, tabletEagle } from "./gate_sculpture.js";
const Cesium = window.Cesium;

const STONE = hex("#ebe7de"), COLC = hex("#f3f0e9"), STAT = hex("#f6f4ef"), COF = hex("#ddd6c8");

/** Stylised statue (stone): standing, torch-bearer or seated figure of height h. */
export function figure(G, s, t, z, h, kind, col = STAT) {
  if (kind === "seated") {
    G.box({ s0: s - 0.22 * h, s1: s + 0.22 * h, t0: t - 0.2 * h, t1: t + 0.2 * h, z0: z, z1: z + 0.3 * h, col, sty: STY.STATUE });
    G.box({ s0: s - 0.16 * h, s1: s + 0.16 * h, t0: t - 0.42 * h, t1: t - 0.1 * h, z0: z + 0.22 * h, z1: z + 0.36 * h, col, sty: STY.STATUE });
    G.cyl({ s, t, z0: z + 0.3 * h, z1: z + 0.68 * h, r0: 0.12 * h, r1: 0.09 * h, seg: 9, col, sty: STY.STATUE });
    G.sphere({ s, t: t - 0.02 * h, z: z + 0.76 * h, r: 0.075 * h, col, seg: 8 });
    G.cylBetween([s + 0.1 * h, t, z + 0.62 * h], [s + 0.14 * h, t - 0.3 * h, z + 0.42 * h], 0.03 * h, col);
    G.cylBetween([s - 0.1 * h, t, z + 0.62 * h], [s - 0.12 * h, t - 0.28 * h, z + 0.45 * h], 0.03 * h, col);
    return;
  }
  G.cyl({ s, t, z0: z, z1: z + 0.52 * h, r0: 0.17 * h, r1: 0.11 * h, seg: 10, col, sty: STY.STATUE });   // robe
  G.cyl({ s, t, z0: z + 0.52 * h, z1: z + 0.8 * h, r0: 0.11 * h, r1: 0.1 * h, seg: 10, col, sty: STY.STATUE });
  G.sphere({ s, t, z: z + 0.88 * h, r: 0.07 * h, col, seg: 8 });
  if (kind === "torch") {
    G.cylBetween([s + 0.08 * h, t, z + 0.78 * h], [s + 0.13 * h, t, z + 1.08 * h], 0.03 * h, col);
    G.cyl({ s: s + 0.13 * h, t, z0: z + 1.06 * h, z1: z + 1.2 * h, r0: 0.025 * h, r1: 0.06 * h, seg: 8, col, sty: STY.STATUE });
    G.sphere({ s: s + 0.13 * h, t, z: z + 1.22 * h, r: 0.04 * h, col, seg: 6 });
    G.cylBetween([s - 0.09 * h, t, z + 0.78 * h], [s - 0.14 * h, t - 0.05 * h, z + 0.52 * h], 0.03 * h, col);
  } else {
    G.cylBetween([s + 0.09 * h, t, z + 0.78 * h], [s + 0.13 * h, t - 0.06 * h, z + 0.5 * h], 0.03 * h, col);
    G.cylBetween([s - 0.09 * h, t, z + 0.78 * h], [s - 0.2 * h, t - 0.1 * h, z + 0.95 * h], 0.03 * h, col);
  }
}

/** Same frame rotated 90 deg: s' = t, t' = -s (lets wall-plane helpers work on walls facing +-s). */
const rot90 = (G) => new Local(G.m, G.f, [-G.ax[1], G.ax[0]], G.off);

/**
 * Main gate 정문 · 새천년기념탑-네오르네상스문 (completed 2001).
 * Documented: total height 22.5 m, width 62 m (guidebook). Footprint frame, 59.2 m length, 5.5 m wing
 * depth and the 11.3 m opening: OSM. Proportions measured from frontal/oblique photographs.
 */
export function buildGateModel(gate, dem) {
  const [lon, lat] = gate.center;
  const g0 = gate.ground_center_m + dem.geoidN(lon, lat);
  const f = new Frame(lon, lat, g0);
  const mesh = new Mesh();
  const G = new Local(mesh, f, gate.axis_en);
  const [ax, ay] = gate.axis_en;
  const gz = (s, t = 0) => { const [lo, la] = f.lonlat(ax * s - ay * t, ay * s + ax * t); return dem.heightEllipsoid(lo, la) - g0; };
  const L = gate.length_m, D = gate.depth_m, [o0, o1] = gate.opening_m;
  const om = (o0 + o1) / 2, r = (o1 - o0) / 2;
  const PW = 4.6, tC = 4.0, tW = D / 2, PV = 6.3;
  const cs0 = o0 - PW, cs1 = o1 + PW;
  const zs = 7.4, ZA = 14.1, ZE = 15.2, ZT = 18.6, ZTC = 19.0;

  // ---- central triumphal arch ----
  for (const [a, b, outer] of [[cs0, o0, -1], [o1, cs1, 1]]) {
    const low = Math.min(gz(a), gz(b)) - 0.8;
    G.box({ s0: outer < 0 ? a - 0.4 : a, s1: outer < 0 ? b : b + 0.4, t0: -tC - 0.4, t1: tC + 0.4, z0: low, z1: 0.6, col: STONE });
    G.box({ s0: a, s1: b, t0: -tC, t1: tC, z0: 0.6, z1: ZA, col: STONE });
    // impost moulding at the springing line + pilaster strips framing the opening
    const inner = outer < 0 ? b : a;
    G.box({ s0: inner - 0.9, s1: inner + 0.9, t0: -tC - 0.15, t1: tC + 0.15, z0: zs - 0.45, z1: zs, col: COLC, sty: STY.CORNICE });
    for (const tf of [-1, 1]) {
      const ts = tf * tC;
      G.box({ s0: outer < 0 ? inner - 0.75 : inner, s1: outer < 0 ? inner : inner + 0.75, t0: Math.min(ts, ts + tf * 0.15), t1: Math.max(ts, ts + tf * 0.15), z0: 0.6, z1: zs - 0.45, col: COLC });
      // giant Corinthian column on a pedestal at the outer edge of each pier face
      const sc = outer < 0 ? a + 1.15 : b - 1.15, tcl = tf * (tC + 0.42);
      G.box({ s0: sc - 0.95, s1: sc + 0.95, t0: tcl - 0.95, t1: tcl + 0.95, z0: 0.6, z1: 2.5, col: STONE, faces: {} });
      G.box({ s0: sc - 1.05, s1: sc + 1.05, t0: tcl - 1.05, t1: tcl + 1.05, z0: 2.5, z1: 2.8, col: COLC, sty: STY.CORNICE });
      G.cyl({ s: sc, t: tcl, z0: 2.8, z1: ZA - 0.45, r0: 0.64, r1: 0.55, seg: 18, col: COLC });
      G.box({ s0: sc - 0.85, s1: sc + 0.85, t0: tcl - 0.85, t1: tcl + 0.85, z0: ZA - 0.45, z1: ZA, col: COLC, sty: STY.CORNICE });
      capitalCarving(G, sc, tcl, ZA - 1.24, 0.58, 0.8);
      // winged figure flying towards the keystone in each spandrel (photographed on both faces)
      spandrelSculpture(G, inner + outer * 0.59, tf * tC, 9.83, tf, -outer);
    }
    // engraved stone tablet with an eagle on a globe on the pier side face inside each wing
    const sf = outer < 0 ? a : b, of = outer < 0 ? -1 : 1;
    G.box({ s0: Math.min(sf, sf + of * 0.07), s1: Math.max(sf, sf + of * 0.07), t0: -0.75, t1: 0.75, z0: 2.6, z1: 5.0, col: COLC, sty: STY.TABLET,
      faces: { front: null, back: null, [of < 0 ? "left" : "right"]: STY.TABLET, [of < 0 ? "right" : "left"]: null } });
    tabletEagle(rot90(G), 0, -sf, 5.5, -of);
  }
  // spandrel faces with the semicircular arch cut out, coffered barrel vault
  const SEG = 32, arc = [];
  for (let k = 0; k <= SEG; k++) { const a = k / SEG * Math.PI; arc.push([om + r * Math.cos(a), zs + r * Math.sin(a)]); }
  const outline = [[o0, zs], [o0, ZA], [o1, ZA], [o1, zs], ...arc.slice(1, -1)];
  G.sFace(outline, -tC, -1, STONE, STY.ASHLAR);
  G.sFace(outline, tC, 1, STONE, STY.ASHLAR);
  const ds = Math.PI * r / SEG;
  for (let k = 0; k < SEG; k++) {
    const [sA, zA] = arc[k], [sB, zB] = arc[k + 1];
    const a = (k + 0.5) / SEG * Math.PI;
    G.quad([sA, -tC, zA], [sB, -tC, zB], [sB, tC, zB], [sA, tC, zA], [-Math.cos(a), 0, -Math.sin(a)],
      [[k * ds, 0], [(k + 1) * ds, 0], [(k + 1) * ds, 2 * tC], [k * ds, 2 * tC]], COF, STY.COFFER, 2 * tC, Math.PI * r);
  }
  // entablature, medallions, attic with inscription, crowning sculpture
  G.box({ s0: cs0 - 0.35, s1: cs1 + 0.35, t0: -tC - 0.5, t1: tC + 0.5, z0: ZA, z1: ZE, col: STONE, sty: STY.CORNICE, bottom: true });
  for (const tf of [-1, 1]) archMedallion(G, om, tf * tC, ZA - 0.64, tf);
  G.box({ s0: cs0 + 0.3, s1: cs1 - 0.3, t0: -tC + 0.3, t1: tC - 0.3, z0: ZE, z1: ZT, col: STONE, faces: { front: STY.ATTIC, back: STY.ATTIC } });
  G.box({ s0: cs0 + 0.05, s1: cs1 - 0.05, t0: -tC + 0.05, t1: tC - 0.05, z0: ZT, z1: ZTC, col: COLC, sty: STY.CORNICE, bottom: true });
  G.box({ s0: om - 1.9, s1: om + 1.9, t0: -1.1, t1: 1.1, z0: ZTC, z1: ZTC + 0.5, col: COLC, sty: STY.ASHLAR });
  crownSculptures(G, om, ZTC + 0.5);
  for (const side of [-1, 1]) for (const out of [-1, 1]) {
    cornerSculpture(G, side < 0 ? cs0 + 0.95 : cs1 - 0.95, out * (tC - 1.1), ZTC, out, side);
  }

  // ---- colonnaded wings + end pavilions ----
  for (const side of [-1, 1]) {
    const outerEnd = side * L / 2;
    const p0 = side < 0 ? outerEnd : outerEnd - PV, p1 = side < 0 ? outerEnd + PV : outerEnd;
    const c0 = side < 0 ? p1 : cs1, c1 = side < 0 ? cs0 : p0;
    const low = Math.min(gz(p0), gz(p1), gz(c0), gz(c1)) - 0.6;
    G.box({ s0: c0, s1: c1, t0: -tW, t1: tW, z0: low, z1: 0.7, col: STONE });
    // three-step stylobate along both faces of the wing (photographed on the street and campus sides)
    for (const tf of [-1, 1]) for (let k = 0; k < 3; k++) {
      const tout = tf * (tW + (3 - k) * 0.38);
      G.box({ s0: c0, s1: c1, t0: Math.min(tf * tW, tout), t1: Math.max(tf * tW, tout), z0: low, z1: 0.7 * (k + 1) / 3, col: STONE });
    }
    // 4 coupled pairs of columns per row (counted in the frontal photograph), front and back rows
    const n = 4;
    for (let k = 0; k < n; k++) {
      const pc = c0 + (k + 0.5) * (c1 - c0) / n;
      for (const sc of [pc - 0.82, pc + 0.82]) for (const tc of [-tW + 0.62, tW - 0.62]) {
        G.box({ s0: sc - 0.55, s1: sc + 0.55, t0: tc - 0.55, t1: tc + 0.55, z0: 0.7, z1: 1.05, col: COLC, sty: STY.STATUE });
        G.cyl({ s: sc, t: tc, z0: 1.05, z1: 8.0, r0: 0.44, r1: 0.38, seg: 16, col: COLC });
        G.box({ s0: sc - 0.55, s1: sc + 0.55, t0: tc - 0.55, t1: tc + 0.55, z0: 8.0, z1: 8.3, col: COLC, sty: STY.CORNICE });
        capitalCarving(G, sc, tc, 7.48, 0.397, 0.53);
      }
    }
    G.box({ s0: c0, s1: c1, t0: -tW + 0.05, t1: tW - 0.05, z0: 8.3, z1: 10.35, col: STONE, sty: STY.CORNICE, bottom: true });
    G.box({ s0: c0, s1: c1, t0: -tW - 0.35, t1: tW + 0.35, z0: 10.35, z1: 10.65, col: COLC, sty: STY.ASHLAR, bottom: true });
    // end pavilion: relief panel + bronze plaque on both faces, sculpture group with armillary ring
    G.box({ s0: p0, s1: p1, t0: -tW - 0.3, t1: tW + 0.3, z0: low, z1: 10.65, col: STONE });
    G.box({ s0: p0 - 0.3, s1: p1 + 0.3, t0: -tW - 0.6, t1: tW + 0.6, z0: 10.65, z1: 11.35, col: COLC, sty: STY.CORNICE, bottom: true });
    // each face: white figural relief on the outer half, framed stone tablet + eagle on the inner half
    const relC = side < 0 ? p0 + 2.4 : p1 - 2.4;
    const plq = side < 0 ? [p0 + 4.15, p0 + 5.65] : [p1 - 5.65, p1 - 4.15];
    for (const tf of [-1, 1]) {
      const tf0 = tf * (tW + 0.3);
      pavilionRelief(G, relC, tf0, 2.0, tf);
      G.box({ s0: plq[0], s1: plq[1], t0: Math.min(tf0, tf0 + tf * 0.07), t1: Math.max(tf0, tf0 + tf * 0.07), z0: 2.4, z1: 6.2, col: COLC, sty: STY.TABLET });
      tabletEagle(G, (plq[0] + plq[1]) / 2, tf0, 6.8, tf);
    }
    // tablet + eagle on the pavilion's inner face inside the wing
    const pf = side < 0 ? p1 : p0;
    G.box({ s0: Math.min(pf, pf - side * 0.07), s1: Math.max(pf, pf - side * 0.07), t0: -0.75, t1: 0.75, z0: 2.6, z1: 5.0, col: COLC, sty: STY.TABLET,
      faces: { front: null, back: null, [side < 0 ? "right" : "left"]: STY.TABLET, [side < 0 ? "left" : "right"]: null } });
    tabletEagle(rot90(G), 0, -pf, 5.5, side);
    const pc = (p0 + p1) / 2;
    G.box({ s0: pc - 2.0, s1: pc + 2.0, t0: -1.6, t1: 1.6, z0: 11.35, z1: 12.15, col: COLC, sty: STY.ASHLAR });
    pavilionCrown(G, pc, 12.15, side);
  }
  return { mesh, topEll: g0 + 22.5, datumEll: g0 };
}

/** Obelisk (사색의 광장): position + base size from OSM man_made=tower; height 23 m (guidebook). */
export function buildObelisk(mesh, ob, height, dem) {
  const [lon, lat] = ob.center;
  const g0 = ob.ground_m + dem.geoidN(lon, lat);
  const G = new Local(mesh, new Frame(lon, lat, g0), [1, 0]);
  const R = Math.min(9, ob.base_radius_m);
  G.cyl({ s: 0, t: 0, z0: -0.8, z1: 0.45, r0: 0.82 * R, seg: 8, col: STONE, sty: STY.ASHLAR, a0: Math.PI / 8, cap: true });
  G.cyl({ s: 0, t: 0, z0: 0.45, z1: 0.95, r0: 0.58 * R, seg: 8, col: STONE, sty: STY.ASHLAR, a0: Math.PI / 8, cap: true });
  G.cyl({ s: 0, t: 0, z0: 0.95, z1: 1.6, r0: 0.38 * R, seg: 8, col: COLC, sty: STY.ASHLAR, a0: Math.PI / 8, cap: true });
  G.box({ s0: -1.75, s1: 1.75, t0: -1.75, t1: 1.75, z0: 1.6, z1: 4.4, col: STONE, sty: STY.RELIEF });
  G.box({ s0: -1.95, s1: 1.95, t0: -1.95, t1: 1.95, z0: 4.4, z1: 4.75, col: COLC, sty: STY.CORNICE });
  for (const [a, b] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) figure(G, a * 2.7, b * 2.7, 0.95, 1.8, "seated");
  const top = height - 1.8;
  G.cyl({ s: 0, t: 0, z0: 4.75, z1: top, r0: 1.12 * Math.SQRT2, r1: 0.7 * Math.SQRT2, seg: 4, a0: Math.PI / 4, col: STONE, sty: STY.OBELISK });
  G.cyl({ s: 0, t: 0, z0: top, z1: height, r0: 0.7 * Math.SQRT2, r1: 0.02, seg: 4, a0: Math.PI / 4, col: COLC, sty: STY.STATUE });
}

/**
 * Central Library (중앙도서관 · 대학본부): classical colonnade facing 사색의 광장.
 * Footprint, facade line and portico recess (inside the footprint): OSM-derived. Height ~21 m and the
 * facade composition (giant colonnade, arched end pavilions, stairs, roof penthouse) from photographs.
 */
export function buildLibraryModel(lib, rec, dem) {
  const [olon, olat] = lib.origin;
  const N = rec.N;
  const fg = lib.facade_ground_m[0] + N;
  const f = new Frame(olon, olat, fg);
  const mesh = new Mesh();
  const [dx, dy] = lib.facade_dir, [ox, oy] = lib.facade_out, [px0, py0] = lib.facade_p0_m;
  const A = new Local(mesh, f, lib.facade_dir, lib.facade_p0_m);  // s along facade, t inward
  const toST = ([e, n]) => [(e - px0) * dx + (n - py0) * dy, -((e - px0) * ox + (n - py0) * oy)];
  const flen = lib.facade_len_m, pav = lib.pavilion_len_m, dep = lib.portico_depth_m;
  const topZ = rec.top - fg, baseZ = rec.base - fg, datum = rec.props.ground_min_m + N - fg;
  const P = 2.4, Hc = topZ - 4.4;
  const LIBC = hex("#e7e4dd"), ROOF = hex("#a5a7a3"), COLL = hex("#efece6");
  // ---- main mass (footprint minus portico recess), facade styles by edge role ----
  const ring_ = lib.mass_m.slice(0, -1);
  let area = 0;
  for (let k = 0; k < ring_.length; k++) { const a = ring_[k], b = ring_[(k + 1) % ring_.length]; area += a[0] * b[1] - b[0] * a[1]; }
  const ccw = area > 0;
  const span = flen - 2 * pav, ncol = 17, pitch = (span - 4.4) / (ncol - 1);
  for (let k = 0; k < ring_.length; k++) {
    const a = ring_[k], b = ring_[(k + 1) % ring_.length];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 0.05) continue;
    const [sa, ta] = toST(a), [sb, tb] = toST(b);
    let sty = STY.GRANITE, fh = 4.2, bw = 4.0, zref = datum;
    if (Math.abs(ta) < 0.5 && Math.abs(tb) < 0.5) { sty = STY.PAVILION; zref = 0; }
    else if (Math.abs(ta - dep) < 0.5 && Math.abs(tb - dep) < 0.5) { sty = STY.PORTICO; bw = pitch; zref = P; }
    else if (Math.abs(sa - sb) < 0.5 && Math.min(ta, tb) < dep + 0.5 && Math.max(ta, tb) < dep + 0.5) { sty = STY.ASHLAR; zref = 0; }
    const nx = (b[1] - a[1]) / len * (ccw ? 1 : -1), ny = -(b[0] - a[0]) / len * (ccw ? 1 : -1);
    const nrm = f.dir(nx, ny, 0);
    const H = topZ - zref;
    const gA = (() => { const [lo, la] = f.lonlat(a[0], a[1]); return dem.heightEllipsoid(lo, la) - fg - datum; })();
    const gB = (() => { const [lo, la] = f.lonlat(b[0], b[1]); return dem.heightEllipsoid(lo, la) - fg - datum; })();
    const gl = sty === STY.GRANITE ? [gA, gB] : [-99, -99];
    const W = [...LIBC, 1];
    const v = (p, z, u, g) => mesh.v(f.pt(p[0], p[1], z), nrm, u, z - zref, W, [fh, bw, sty, H], [len, g]);
    const i0 = v(a, baseZ, 0, gl[0]), i1 = v(b, baseZ, len, gl[1]), i2 = v(b, topZ, len, gl[1]), i3 = v(a, topZ, 0, gl[0]);
    mesh.tri(i0, i1, i2); mesh.tri(i0, i2, i3);
  }
  const flat = ring_.map(([e, n]) => new Cesium.Cartesian2(e, n));
  const tri = Cesium.PolygonPipeline.triangulate(flat, []);
  const up = f.dir(0, 0, 1);
  const rid = ring_.map(([e, n]) => mesh.v(f.pt(e, n, topZ - 0.9), up, e, n, [...ROOF, 0], [4, 4, STY.GRANITE, 1], [0, 0]));
  for (let k = 0; k < tri.length; k += 3) mesh.tri(rid[tri[k]], rid[tri[k + 1]], rid[tri[k + 2]]);

  // ---- portico: podium, 17 giant columns, entablature + attic, continuous cornice ----
  A.box({ s0: pav, s1: flen - pav, t0: 0, t1: dep, z0: baseZ, z1: P, col: LIBC, faces: { back: null } });
  for (let k = 0; k < ncol; k++) {
    const s = pav + 2.2 + k * pitch, t = 1.15;
    A.box({ s0: s - 0.95, s1: s + 0.95, t0: t - 0.95, t1: t + 0.95, z0: P, z1: P + 0.55, col: COLL, sty: STY.STATUE });
    A.cyl({ s, t, z0: P + 0.55, z1: Hc, r0: 0.78, r1: 0.68, seg: 18, col: COLL });
    A.box({ s0: s - 0.95, s1: s + 0.95, t0: t - 0.95, t1: t + 0.95, z0: Hc, z1: Hc + 0.35, col: COLL, sty: STY.CORNICE });
  }
  A.box({ s0: pav, s1: flen - pav, t0: 0, t1: dep, z0: Hc + 0.35, z1: Hc + 2.4, col: LIBC, sty: STY.CORNICE, bottom: true, faces: { back: null } });
  A.box({ s0: pav, s1: flen - pav, t0: 0, t1: dep, z0: Hc + 2.4, z1: topZ, col: LIBC, faces: { back: null } });
  A.box({ s0: -0.4, s1: flen + 0.4, t0: -0.55, t1: 0.3, z0: Hc + 1.85, z1: Hc + 2.45, col: COLL, sty: STY.CORNICE, bottom: true });
  A.box({ s0: -0.3, s1: flen + 0.3, t0: -0.35, t1: 0.2, z0: topZ - 0.35, z1: topZ, col: COLL, sty: STY.ASHLAR, bottom: true });

  // ---- grand stairs down to the plaza ----
  const foot = lib.stair_foot_ground_m - lib.facade_ground_m[0];
  const W = 0.38 * flen, c = flen / 2;
  const nSt = Math.max(4, Math.ceil((P - foot) / 0.3)), rise = (P - foot) / nSt, tread = 0.55;
  for (let k = 0; k < nSt; k++) {
    A.box({ s0: c - W / 2, s1: c + W / 2, t0: -(nSt - k) * tread, t1: 0, z0: foot - 0.6, z1: foot + (k + 1) * rise, col: LIBC, sty: STY.ASHLAR, faces: { back: null } });
  }
  for (const sc of [c - W / 2 - 1.2, c + W / 2]) A.box({ s0: sc, s1: sc + 1.2, t0: -nSt * tread - 0.4, t1: 0, z0: foot - 0.6, z1: P + 0.9, col: LIBC });

  // ---- roof penthouse + skylights ----
  let cs = 0, ct = 0;
  for (const p of ring_) { const [s, t] = toST(p); cs += s; ct += t; }
  cs /= ring_.length; ct /= ring_.length;
  A.box({ s0: cs - 0.2 * flen, s1: cs + 0.2 * flen, t0: ct - 8, t1: ct + 8, z0: topZ - 0.9, z1: topZ + 3.2, col: LIBC, sty: STY.ASHLAR });
  A.box({ s0: cs - 0.2 * flen - 0.3, s1: cs + 0.2 * flen + 0.3, t0: ct - 8.3, t1: ct + 8.3, z0: topZ + 3.2, z1: topZ + 3.6, col: COLL, sty: STY.CORNICE });
  for (let k = 0; k < 6; k++) for (const tt of [ct - 13, ct + 13]) {
    const s = cs - 0.3 * flen + k * 0.12 * flen;
    A.cyl({ s, t: tt, z0: topZ - 0.9, z1: topZ + 0.8, r0: 1.4, r1: 0.25, seg: 4, a0: Math.PI / 4, col: hex("#cfd8dc"), sty: STY.STATUE });
  }
  return { mesh, topEll: rec.top + 3.6 };
}

/** Annular sector solid in polar coords of a Local (s = r cos a, t = r sin a). */
function arcBand(G, { r0, r1, a0, a1, z0, z1, col, top = STY.STATUE, inner = STY.ASHLAR, outer = STY.ASHLAR, sides = STY.ASHLAR, bottom = null }) {
  const n = Math.max(1, Math.ceil((a1 - a0) * Math.max(r1, 1) / 1.4));
  const H = z1 - z0;
  const P = (r, a, z) => [r * Math.cos(a), r * Math.sin(a), z];
  for (let k = 0; k < n; k++) {
    const A = a0 + (a1 - a0) * k / n, B = a0 + (a1 - a0) * (k + 1) / n, M = (A + B) / 2;
    if (top !== null) G.quad(P(r0, A, z1), P(r0, B, z1), P(r1, B, z1), P(r1, A, z1), [0, 0, 1],
      [[A * r1, 0], [B * r1, 0], [B * r1, r1 - r0], [A * r1, r1 - r0]], col, top, H, (a1 - a0) * r1);
    if (bottom !== null) G.quad(P(r0, A, z0), P(r0, B, z0), P(r1, B, z0), P(r1, A, z0), [0, 0, -1],
      [[A * r1, 0], [B * r1, 0], [B * r1, r1 - r0], [A * r1, r1 - r0]], col, bottom, H, (a1 - a0) * r1);
    if (inner !== null && r0 > 0.01) G.quad(P(r0, A, z0), P(r0, B, z0), P(r0, B, z1), P(r0, A, z1), [-Math.cos(M), -Math.sin(M), 0],
      [[(A - a0) * r0, 0], [(B - a0) * r0, 0], [(B - a0) * r0, H], [(A - a0) * r0, H]], col, inner, H, (a1 - a0) * r0);
    if (outer !== null) G.quad(P(r1, A, z0), P(r1, B, z0), P(r1, B, z1), P(r1, A, z1), [Math.cos(M), Math.sin(M), 0],
      [[(A - a0) * r1, 0], [(B - a0) * r1, 0], [(B - a0) * r1, H], [(A - a0) * r1, H]], col, outer, H, (a1 - a0) * r1);
  }
  if (sides !== null) for (const [a, sg] of [[a0, -1], [a1, 1]]) {
    G.quad(P(r0, a, z0), P(r1, a, z0), P(r1, a, z1), P(r0, a, z1), [-Math.sin(a) * sg, Math.cos(a) * sg, 0],
      [[0, 0], [r1 - r0, 0], [r1 - r0, H], [0, H]], col, sides, H, r1 - r0);
  }
}

/**
 * 평화노천극장 - Greek-style open-air theatre. Stage axis from the OSM footprint towards the OSM pond;
 * seat rows rise with the real DTM (never below it); cavea radius limited by the footprint. Stage
 * colonnade (scaenae frons), pavilions with reliefs and balustrades are modelled from photographs.
 */
export function buildTheatre(th, dem) {
  const [lon, lat] = th.origin;
  const N = dem.geoidN(lon, lat);
  const f = new Frame(lon, lat, th.orchestra_ground_m + N);
  const mesh = new Mesh();
  const ax = [-th.to_pond_en[0], -th.to_pond_en[1]];          // s axis points into the cavea (uphill)
  const G = new Local(mesh, f, ax);
  const SEAT = hex("#eeebe4"), RISE = hex("#dcd7cc"), WALK = hex("#e4e0d8"), STG = hex("#d7d9dc");
  const deg = Math.PI / 180, SPAN = 100 * deg, gap = 1.3;
  const rows = [];
  let r = th.R0_m, k = 0;
  const nApprox = Math.floor((th.Rmax_m - th.R0_m) / th.tread_m);
  const kd = Math.round(nApprox * 0.5);
  let zPrev = 0;
  while (r < th.Rmax_m) {
    const tw = k === kd ? 2.4 : th.tread_m;
    const idx = Math.min(th.ring_dtm_max_rel_m.length - 1, Math.floor((r + tw - th.R0_m) / th.tread_m));
    let z = k === kd ? zPrev + 0.1 : Math.max(zPrev + 0.36, th.ring_dtm_max_rel_m[idx] + 0.15);
    z = Math.min(z, zPrev + 0.62);
    rows.push({ r0: r, r1: r + tw, z, zb: zPrev, walk: k === kd });
    zPrev = z; r += tw; k++;
  }
  for (const row of rows) {
    const upper = row.r0 > rows[kd].r0;
    const nW = upper ? 10 : 6;
    const rm = (row.r0 + row.r1) / 2;
    const bounds = Array.from({ length: nW + 1 }, (_, j) => -SPAN + j * (2 * SPAN / nW));
    if (row.walk) {
      arcBand(G, { r0: row.r0, r1: row.r1, a0: -SPAN, a1: SPAN, z0: row.zb - 1.2, z1: row.z, col: WALK, top: STY.ASHLAR, outer: null });
      continue;
    }
    for (let j = 0; j < nW; j++) {
      const a0 = bounds[j] + (j === 0 ? 0 : gap / 2 / rm), a1 = bounds[j + 1] - (j === nW - 1 ? 0 : gap / 2 / rm);
      arcBand(G, { r0: row.r0, r1: row.r1, a0, a1, z0: row.zb - 1.2, z1: row.z, col: SEAT, top: STY.STATUE, inner: STY.ASHLAR, outer: null, sides: STY.ASHLAR });
    }
    for (let j = 1; j < nW; j++) {         // radial stair aisles: two half-height steps per row
      const a0 = bounds[j] - gap / 2 / rm, a1 = bounds[j] + gap / 2 / rm, mid = (row.r0 + row.r1) / 2;
      arcBand(G, { r0: row.r0, r1: mid, a0, a1, z0: row.zb - 1.2, z1: (row.zb + row.z) / 2, col: RISE, top: STY.ASHLAR, outer: null, sides: null });
      arcBand(G, { r0: mid, r1: row.r1, a0, a1, z0: row.zb - 1.2, z1: row.z, col: RISE, top: STY.ASHLAR, outer: null, sides: null });
    }
  }
  const last = rows[rows.length - 1];
  arcBand(G, { r0: last.r1, r1: last.r1 + 2.2, a0: -SPAN - 4 * deg, a1: SPAN + 4 * deg, z0: last.z - 2, z1: last.z, col: WALK, top: STY.ASHLAR });
  arcBand(G, { r0: last.r1 + 2.2, r1: last.r1 + 2.5, a0: -SPAN - 4 * deg, a1: SPAN + 4 * deg, z0: last.z, z1: last.z + 1.05, col: SEAT, top: STY.ASHLAR, inner: STY.BALUSTRADE, outer: STY.BALUSTRADE });
  arcBand(G, { r0: rows[kd].r1 - 0.3, r1: rows[kd].r1, a0: -SPAN, a1: SPAN, z0: rows[kd].z, z1: rows[kd].z + 0.95, col: SEAT, top: STY.ASHLAR, inner: STY.BALUSTRADE, outer: STY.BALUSTRADE });
  for (const a of [-SPAN, SPAN]) {
    const sg = Math.sign(a);
    for (const row of rows) arcBand(G, { r0: row.r0, r1: row.r1, a0: a + (sg > 0 ? 0 : -0.35 / row.r0), a1: a + (sg > 0 ? 0.35 / row.r0 : 0), z0: row.zb - 1.2, z1: row.z + 1.0, col: SEAT, top: STY.ASHLAR, inner: STY.BALUSTRADE, outer: null, sides: STY.BALUSTRADE });
  }
  arcBand(G, { r0: 0, r1: th.R0_m, a0: -Math.PI / 2, a1: Math.PI / 2, z0: -1.2, z1: 0.05, col: WALK, top: STY.ASHLAR, inner: null, sides: null });
  const pondZ = th.pond.ground_min_m - th.orchestra_ground_m;
  arcBand(G, { r0: 0, r1: 12.2, a0: Math.PI / 2, a1: 1.5 * Math.PI, z0: pondZ - 0.5, z1: 0.05, col: WALK, top: STY.ASHLAR, inner: null, outer: STY.GRANITE, sides: null });
  arcBand(G, { r0: 0, r1: 11.4, a0: Math.PI / 2, a1: 1.5 * Math.PI, z0: 0.05, z1: 0.4, col: STG, top: STY.ASHLAR, inner: null, sides: STY.ASHLAR });
  arcBand(G, { r0: 0, r1: 10.9, a0: Math.PI / 2, a1: 1.5 * Math.PI, z0: 0.4, z1: 0.75, col: STG, top: STY.ASHLAR, inner: null, sides: STY.ASHLAR });
  const Rc = 9.4, half = 58 * deg, zc0 = 0.75, zc1 = 7.6;
  const COL = hex("#e9e7e1");
  for (const [rr, nCol] of [[Rc, 10], [Rc + 1.7, 8]]) {
    for (let j = 0; j < nCol; j++) {
      const a = Math.PI - half + 5 * deg + (2 * half - 10 * deg) * j / (nCol - 1);
      const s = rr * Math.cos(a), t = rr * Math.sin(a);
      G.cyl({ s, t, z0: zc0, z1: zc0 + 0.35, r0: 0.5, seg: 8, col: COL, sty: STY.STATUE });
      G.cyl({ s, t, z0: zc0 + 0.35, z1: zc1, r0: 0.33, r1: 0.29, seg: 14, col: COL });
    }
  }
  for (const a of [Math.PI - half, Math.PI + half]) {
    const cs = (Rc + 0.85) * Math.cos(a), ct = (Rc + 0.85) * Math.sin(a);
    const tE = [ax[0] * -Math.sin(a) - ax[1] * Math.cos(a), ax[1] * -Math.sin(a) + ax[0] * Math.cos(a)];
    const off = [ax[0] * cs - ax[1] * ct, ax[1] * cs + ax[0] * ct];
    const PV = new Local(mesh, f, tE, off);
    PV.box({ s0: -2.2, s1: 2.2, t0: -1.4, t1: 1.4, z0: pondZ - 0.5, z1: zc1 + 0.4, col: COL, sty: STY.ASHLAR });
    for (const tf of [-1, 1]) {
      const tt = tf * 1.4;
      PV.box({ s0: -1.3, s1: 1.3, t0: Math.min(tt, tt + tf * 0.12), t1: Math.max(tt, tt + tf * 0.12), z0: 2.2, z1: 6.6, col: hex("#f4f3ef"), sty: STY.RELIEF });
      for (const ss of [-2.0, 2.0]) PV.cyl({ s: ss, t: tf * 1.55, z0: zc0, z1: zc1, r0: 0.3, r1: 0.27, seg: 12, col: COL });
    }
  }
  arcBand(G, { r0: Rc - 0.6, r1: Rc + 2.4, a0: Math.PI - half - 3 * deg, a1: Math.PI + half + 3 * deg, z0: zc1, z1: zc1 + 1.3, col: COL, top: STY.ASHLAR, inner: STY.CORNICE, outer: STY.CORNICE, bottom: STY.ASHLAR });
  arcBand(G, { r0: Rc - 0.6, r1: Rc - 0.3, a0: Math.PI - half - 3 * deg, a1: Math.PI + half + 3 * deg, z0: zc1 + 1.3, z1: zc1 + 2.2, col: COL, top: STY.ASHLAR, inner: STY.BALUSTRADE, outer: STY.BALUSTRADE });
  arcBand(G, { r0: Rc + 2.1, r1: Rc + 2.4, a0: Math.PI - half - 3 * deg, a1: Math.PI + half + 3 * deg, z0: zc1 + 1.3, z1: zc1 + 2.2, col: COL, top: STY.ASHLAR, inner: STY.BALUSTRADE, outer: STY.BALUSTRADE });
  return { mesh, topEll: f.h + last.z + 1.0 };
}

/** Rock boulders along a pond edge (illustrative, as in photographs of the theatre pond). */
export function addPondRocks(mesh, coords, ground, dem) {
  const [lon0, lat0] = coords[0];
  const f = new Frame(lon0, lat0, ground + dem.geoidN(lon0, lat0));
  const G = new Local(mesh, f, [1, 0]);
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let k = 0; k < coords.length - 1; k++) {
    const a = f.local(...coords[k]), b = f.local(...coords[k + 1]);
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    for (let d = 0; d < len; d += 2.6) {
      const x = a[0] + (b[0] - a[0]) * d / len, y = a[1] + (b[1] - a[1]) * d / len;
      const r = 0.7 + rnd() * 0.8, g = 0.5 + rnd() * 0.12;
      G.sphere({ s: x + (rnd() - 0.5), t: y + (rnd() - 0.5), z: r * 0.35, r, col: [g, g * 0.98, g * 0.93], sty: STY.STATUE, seg: 7, sz: 0.75 });
    }
  }
}

/**
 * 선승관 (photographs supplied as "Peace Hall"): D-shaped brick arcade hall, white band + gold frieze,
 * inset dark-metal upper storey, clock tower with open belfry and copper pyramid roof.
 * Footprint: OSM way/585696506. Form and heights: estimated from photographs (labelled illustrative).
 */
export function buildPeaceHall(ph, rec, dem) {
  const [lon, lat] = ph.origin;
  const datum = rec.props.ground_min_m + rec.N;
  const f = new Frame(lon, lat, datum);
  const mesh = new Mesh();
  const BRICK = hex("#c99b80"), ROOF = hex("#5b6064"), WHITE = hex("#eeedea"), COPPER = hex("#5fa190");
  const HW = 14.0, HU = 19.5, base = -1.6;
  const [ea, eb] = ph.straight_end_m;
  const ex = eb[0] - ea[0], ey = eb[1] - ea[1], el = Math.hypot(ex, ey);
  const onEnd = (p) => Math.abs(((p[0] - ea[0]) * ey - (p[1] - ea[1]) * ex) / el) < 0.6;
  const walls = (ring, z0, z1, styleFor) => {
    const pts = ring.slice(0, -1);
    let area = 0;
    for (let k = 0; k < pts.length; k++) { const a = pts[k], b = pts[(k + 1) % pts.length]; area += a[0] * b[1] - b[0] * a[1]; }
    const ccw = area > 0;
    for (let k = 0; k < pts.length; k++) {
      const a = pts[k], b = pts[(k + 1) % pts.length];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (len < 0.05) continue;
      const nx = (b[1] - a[1]) / len * (ccw ? 1 : -1), ny = -(b[0] - a[0]) / len * (ccw ? 1 : -1);
      const nrm = f.dir(nx, ny, 0);
      const [sty, fh, bw, col] = styleFor(a, b, len);
      const H = z1 - (sty === STY.METAL ? z0 : 0);
      const W = [...col, 1], S4 = [fh, bw, sty, H];
      const h0 = sty === STY.METAL ? 0 : z0, h1 = sty === STY.METAL ? z1 - z0 : z1;
      const i0 = mesh.v(f.pt(a[0], a[1], z0), nrm, 0, h0, W, S4, [len, -99]);
      const i1 = mesh.v(f.pt(b[0], b[1], z0), nrm, len, h0, W, S4, [len, -99]);
      const i2 = mesh.v(f.pt(b[0], b[1], z1), nrm, len, h1, W, S4, [len, -99]);
      const i3 = mesh.v(f.pt(a[0], a[1], z1), nrm, 0, h1, W, S4, [len, -99]);
      mesh.tri(i0, i1, i2); mesh.tri(i0, i2, i3);
    }
  };
  const roof = (ring, z, col) => {
    const pts = ring.slice(0, -1);
    const tri = Cesium.PolygonPipeline.triangulate(pts.map(([e, n]) => new Cesium.Cartesian2(e, n)), []);
    const up = f.dir(0, 0, 1);
    const ids = pts.map(([e, n]) => mesh.v(f.pt(e, n, z), up, e, n, [...col, 0], [4, 4, 0, 1], [0, 0]));
    for (let k = 0; k < tri.length; k += 3) mesh.tri(ids[tri[k]], ids[tri[k + 1]], ids[tri[k + 2]]);
  };
  // brick arcade walls: grand arches on the straight end, regular arcade elsewhere
  walls(ph.ring_m, base, HW, (a, b) => (onEnd(a) && onEnd(b)) ? [STY.ARCADE, 10.8, 12.5, BRICK] : [STY.ARCADE, 8.6, 5.0, BRICK]);
  roof(ph.ring_m, HW - 0.8, ROOF);
  walls(ph.upper_m, HW - 0.8, HU, () => [STY.METAL, 3, 3, ROOF]);
  if (ph.roof_ridge_m) {
    const [[rx, a], [, b]] = ph.roof_ridge_m;
    const G = new Local(mesh, f);
    const eave = ph.upper_m;
    const cap = ([x, y]) => [rx + 0.024 * (x - rx), Cesium.Math.clamp(y, a, b), HU + 2.15];
    for (let k = 0; k + 1 < eave.length; k++) {
      const p = [...eave[k], HU], q = [...eave[k + 1], HU], c = cap(q), d = cap(p);
      const [dx, dy] = [q[0] - p[0], q[1] - p[1]];
      if (Math.hypot(dx, dy) < 0.02) continue;
      const n = [dy * (d[2] - p[2]), -dx * (d[2] - p[2]), dx * (d[1] - p[1]) - dy * (d[0] - p[0])];
      const sign = n[2] < 0 ? -1 : 1;
      G.quad(p, q, c, d, n.map((v) => v * sign), [p, q, c, d].map(([x, y]) => [x, y]),
        ROOF, STY.STATUE, 2.15, Math.hypot(dx, dy));
      // The radial joints are visible in the aerial view across the rounded metal roof.
      const span = Math.max(1, Math.round(Math.hypot(dx, dy) / 2.5));
      for (let j = 0; j < span; j++) {
        const s = j / span;
        const start = [p[0] + dx * s, p[1] + dy * s, HU + 0.037];
        const end = [d[0] + (c[0] - d[0]) * s, d[1] + (c[1] - d[1]) * s, d[2] + 0.037];
        G.cylBetween(start, end, 0.032, hex("#666c70"), STY.STATUE, 4);
      }
    }
  } else roof(ph.upper_m, HU, ROOF);
  // clock tower
  const T = new Local(mesh, f, ph.tower_axis, ph.tower_center_m);
  T.fh = 0; // plain brick shaft (no arcade arches)
  T.box({ s0: -3.6, s1: 3.6, t0: -3.6, t1: 3.6, z0: base, z1: 23.0, col: BRICK, sty: STY.ARCADE, faces: {}, top: false });
  T.box({ s0: -3.8, s1: 3.8, t0: -3.8, t1: 3.8, z0: 23.0, z1: 27.4, col: WHITE, sty: 20 });
  T.box({ s0: -4.0, s1: 4.0, t0: -4.0, t1: 4.0, z0: 27.4, z1: 27.8, col: WHITE, sty: STY.CORNICE });
  for (const [a, b] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) T.box({ s0: a * 3.4 - 0.4, s1: a * 3.4 + 0.4, t0: b * 3.4 - 0.4, t1: b * 3.4 + 0.4, z0: 27.8, z1: 31.6, col: WHITE, sty: STY.STATUE });
  T.box({ s0: -3.6, s1: 3.6, t0: -3.6, t1: 3.6, z0: 27.8, z1: 28.6, col: WHITE, sty: STY.BALUSTRADE, top: false });
  T.sphere({ s: 0, t: 0, z: 30.2, r: 0.9, col: hex("#b08a3a"), sty: STY.STATUE, seg: 10, sz: 1.2 });
  T.box({ s0: -4.0, s1: 4.0, t0: -4.0, t1: 4.0, z0: 31.6, z1: 32.2, col: WHITE, sty: STY.CORNICE, bottom: true });
  T.cyl({ s: 0, t: 0, z0: 32.2, z1: 37.4, r0: 4.1 * Math.SQRT2, r1: 0.06, seg: 4, a0: Math.PI / 4, col: COPPER, sty: STY.STATUE });
  return { mesh, topEll: datum + 37.4 };
}

/**
 * Generic photo-based building (description from build_campus_details.py -> campus_details.photo_buildings).
 * masses: OSM-footprint extrusions with a facade style (storey grid phased at floor0 above the datum);
 * prims : boxes, cylinders and profiles in the frame of a footprint edge (+t inward).
 * z = metres above ground_min (datum).
 */
export function buildPhotoModel(pm, rec, dem) {
  const [lon, lat] = pm.origin;
  const datum = rec.props.ground_min_m + rec.N;
  const f = new Frame(lon, lat, datum);
  const mesh = new Mesh();
  for (const m of pm.masses) {
    const rings = [m.ring, ...(m.holes ?? [])];
    const flat = [], holeStarts = [], f0 = m.floor0 ?? 0, H = m.z1 - f0;
    const gAt = (p) => { const [lo, la] = f.lonlat(p[0], p[1]); return dem.heightEllipsoid(lo, la) - datum - f0; };
    for (const [ri, ring] of rings.entries()) {
      const pts = ring.slice(0, -1);
      if (ri > 0) holeStarts.push(flat.length);
      flat.push(...pts.map(([e, n]) => new Cesium.Cartesian2(e, n)));
      let area = 0;
      for (let k = 0; k < pts.length; k++) {
        const a = pts[k], b = pts[(k + 1) % pts.length];
        area += a[0] * b[1] - b[0] * a[1];
      }
      const sign = (ri === 0 ? area > 0 : area <= 0) ? 1 : -1;
      for (let k = 0; k < pts.length; k++) {
        const a = pts[k], b = pts[(k + 1) % pts.length];
        const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (len < 0.05) continue;
        const nrm = f.dir((b[1] - a[1]) / len * sign, -(b[0] - a[0]) / len * sign, 0);
        const es = ri === 0 ? m.edge_sty?.[k] : null;
        const [sty, fh, bw, wallHex, phase = 0, span = len] = es ?? [m.sty, m.fh, m.bw, m.wall];
        const W = [...hex(wallHex), 1], S4 = [fh, bw, sty, H];
        const ga = m.z0 > 0.5 ? -99 : gAt(a), gb = m.z0 > 0.5 ? -99 : gAt(b);
        const i0 = mesh.v(f.pt(a[0], a[1], m.z0), nrm, phase, m.z0 - f0, W, S4, [span, ga]);
        const i1 = mesh.v(f.pt(b[0], b[1], m.z0), nrm, phase + len, m.z0 - f0, W, S4, [span, gb]);
        const i2 = mesh.v(f.pt(b[0], b[1], m.z1), nrm, phase + len, H, W, S4, [span, gb]);
        const i3 = mesh.v(f.pt(a[0], a[1], m.z1), nrm, phase, H, W, S4, [span, ga]);
        mesh.tri(i0, i1, i2); mesh.tri(i0, i2, i3);
      }
    }
    let tri = [];
    try { tri = Cesium.PolygonPipeline.triangulate(flat, holeStarts); } catch { tri = []; }
    const up = f.dir(0, 0, 1), RC = [...hex(m.roof), 0];
    const ids = flat.map(({ x, y }) => mesh.v(f.pt(x, y, m.z1 - (m.parapet ?? 0.9)), up, x, y, RC, [4, 4, 0, 1], [0, 0]));
    for (let k = 0; k < tri.length; k += 3) mesh.tri(ids[tri[k]], ids[tri[k + 1]], ids[tri[k + 2]]);
  }
  for (const p of pm.prims) {
    const G = new Local(mesh, f, p.ax, p.off);
    G.fh = p.fh; G.bw = p.bw;
    const col = hex(p.col);
    if (p.t === "box") {
      const faces = {};
      for (const [k, v] of Object.entries(p.faces ?? {})) faces[k] = v;
      G.box({ s0: p.s0, s1: p.s1, t0: p.t0, t1: p.t1, z0: p.z0, z1: p.z1,
        col, sty: p.sty, faces, top: p.top !== false, bottom: p.bottom, zref: p.zref });
    } else if (p.t === "cyl") {
      G.cyl({ s: p.s, t: p.t_, z0: p.z0, z1: p.z1, r0: p.r0, r1: p.r1, seg: p.seg, col, sty: p.sty });
    } else if (p.t === "sphere") {
      G.sphere({ s: p.s, t: p.t_, z: p.z, r: p.r, sz: p.sz, jit: p.jit, col, sty: p.sty ?? STY.FOLIAGE, seg: 12 });
    } else if (p.t === "profile") {
      G.profile(p.points, p.t0, p.t1, col);
    } else if (p.t === "panel") {
      const [a, b, c, d] = p.points;
      const width = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const height = c[2] - b[2];
      G.quad(a, b, c, d, p.normal, [[0, 0], [width, 0], [width, height], [0, height]], col, p.sty, height, width);
    }
  }
  return { mesh, topEll: datum + pm.top_m };
}

/** Extrude a ring given in frame-local metres; styleFor(a, b, len) -> [sty, fh, bw, rgb]. */
function extrudeLocalRing(mesh, f, ring, z0, z1, styleFor, roofZ, roofCol) {
  const pts = ring.slice(0, -1);
  let area = 0;
  for (let k = 0; k < pts.length; k++) { const a = pts[k], b = pts[(k + 1) % pts.length]; area += a[0] * b[1] - b[0] * a[1]; }
  const ccw = area > 0;
  for (let k = 0; k < pts.length; k++) {
    const a = pts[k], b = pts[(k + 1) % pts.length];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 0.05) continue;
    const nrm = f.dir((b[1] - a[1]) / len * (ccw ? 1 : -1), -(b[0] - a[0]) / len * (ccw ? 1 : -1), 0);
    const [sty, fh, bw, col] = styleFor(a, b, len);
    const W = [...col, 1], S4 = [fh, bw, sty, z1];
    const i0 = mesh.v(f.pt(a[0], a[1], z0), nrm, 0, z0, W, S4, [len, 0]);
    const i1 = mesh.v(f.pt(b[0], b[1], z0), nrm, len, z0, W, S4, [len, 0]);
    const i2 = mesh.v(f.pt(b[0], b[1], z1), nrm, len, z1, W, S4, [len, 0]);
    const i3 = mesh.v(f.pt(a[0], a[1], z1), nrm, 0, z1, W, S4, [len, 0]);
    mesh.tri(i0, i1, i2); mesh.tri(i0, i2, i3);
  }
  const tri = Cesium.PolygonPipeline.triangulate(pts.map(([e, n]) => new Cesium.Cartesian2(e, n)), []);
  const up = f.dir(0, 0, 1);
  const ids = pts.map(([e, n]) => mesh.v(f.pt(e, n, roofZ), up, e, n, [...roofCol, 0], [4, 4, 0, 1], [0, 0]));
  for (let k = 0; k < tri.length; k += 3) mesh.tri(ids[tri[k]], ids[tri[k + 1]], ids[tri[k + 2]]);
}

/**
 * 예술·디자인대학관 (College of Art & Design): white neoclassical complex modelled from photographs -
 * colonnaded two-storey base on the OSM footprint, central temple portico (4 giant columns, pediment with
 * medallion) and grand stairs, ~8-storey main block framed by two corner towers with tall arched windows,
 * open loggia along the top. Front side and footprint: OSM-derived.
 */
export function buildArtDesign(ad, rec, dem) {
  const [lon, lat] = ad.origin;
  const N = dem.geoidN(lon, lat);
  const f = new Frame(lon, lat, ad.front_ground_m[0] + N);
  const mesh = new Mesh();
  let dir = ad.front_dir, p0 = ad.front_p0_m;
  if ((-dir[1]) * ad.front_out[0] + dir[0] * ad.front_out[1] > 0) {       // make +t point inward
    p0 = [p0[0] + dir[0] * ad.front_len_m, p0[1] + dir[1] * ad.front_len_m];
    dir = [-dir[0], -dir[1]];
  }
  const G = new Local(mesh, f, dir, p0);
  const WH = hex("#f2f0ea"), TRIM = hex("#f8f7f3"), ROOF = hex("#b9bcbc"), DARKW = hex("#3d3f42");
  const len = ad.front_len_m, dep = ad.depth_m, c = len / 2;
  const groundZ = (rec.props.ground_min_m + rec.N) - f.h;
  const HB = 10.5;
  // two-storey base on the real footprint
  extrudeLocalRing(mesh, f, ad.ring_m, groundZ - 1.5, HB, () => [STY.GRANITE, 4.6, 4.4, WH], HB - 0.6, ROOF);
  // front colonnade (Ionic) + entablature + balustrade, either side of the portico
  for (let s = 3; s < len - 3; s += 4.4) {
    if (Math.abs(s - c) < 12.5) continue;
    G.box({ s0: s - 0.6, s1: s + 0.6, t0: -1.6, t1: -0.4, z0: 0, z1: 0.9, col: TRIM, sty: STY.STATUE });
    G.cyl({ s, t: -1.0, z0: 0.9, z1: 9.2, r0: 0.46, r1: 0.41, seg: 14, col: TRIM });
  }
  G.box({ s0: 0, s1: len, t0: -1.8, t1: 0.3, z0: 9.2, z1: 10.6, col: WH, sty: STY.CORNICE, bottom: true });
  G.box({ s0: 0, s1: len, t0: -1.6, t1: -1.3, z0: 10.6, z1: 11.5, col: TRIM, sty: STY.BALUSTRADE });
  // central temple portico with pediment + medallion
  G.box({ s0: c - 11, s1: c + 11, t0: -3.0, t1: 0.5, z0: 0, z1: 13.2, col: WH, sty: STY.GRANITE, faces: { front: STY.GRANITE } });
  for (const ds of [-9.9, -3.3, 3.3, 9.9]) {
    G.box({ s0: c + ds - 1.0, s1: c + ds + 1.0, t0: -5.2, t1: -3.2, z0: 0, z1: 1.6, col: TRIM, sty: STY.ASHLAR });
    G.cyl({ s: c + ds, t: -4.2, z0: 1.6, z1: 13.2, r0: 0.78, r1: 0.68, seg: 18, col: TRIM });
  }
  G.box({ s0: c - 11.6, s1: c + 11.6, t0: -5.4, t1: 0.5, z0: 13.2, z1: 14.6, col: WH, sty: STY.CORNICE, bottom: true });
  const ped = [[c - 11.6, 14.6], [c + 11.6, 14.6], [c, 18.2]];
  G.sFace(ped, -5.4, -1, WH, STY.ASHLAR, 14.6);
  G.sFace(ped, 0.5, 1, WH, STY.ASHLAR, 14.6);
  const sl = Math.atan2(3.6, 11.6);
  G.quad([c - 11.6, -5.4, 14.6], [c, -5.4, 18.2], [c, 0.5, 18.2], [c - 11.6, 0.5, 14.6], [-Math.sin(sl), 0, Math.cos(sl)], [[0, 0], [12, 0], [12, 6], [0, 6]], ROOF, STY.ASHLAR, 4, 12);
  G.quad([c, -5.4, 18.2], [c + 11.6, -5.4, 14.6], [c + 11.6, 0.5, 14.6], [c, 0.5, 18.2], [Math.sin(sl), 0, Math.cos(sl)], [[0, 0], [12, 0], [12, 6], [0, 6]], ROOF, STY.ASHLAR, 4, 12);
  G.cylBetween([c, -5.45, 16.0], [c, -5.7, 16.0], 0.85, DARKW, STY.BRONZE, 18);
  // grand stairs
  const nSt = 6;
  for (let k = 0; k < nSt; k++) G.box({ s0: c - 15, s1: c + 15, t0: -5.4 - (nSt - k) * 0.5, t1: -5.0, z0: -0.8, z1: (k + 1) * 0.27, col: TRIM, sty: STY.ASHLAR });
  // main block + corner towers + loggia
  const s0 = len * 0.16, s1 = len * 0.84, t0 = dep * 0.3, t1 = Math.min(dep - 4, t0 + 26);
  G.fh = 3.4; G.bw = 3.1;   // ~8 storeys of arched windows
  G.box({ s0, s1, t0, t1, z0: HB - 0.6, z1: 36, col: WH, sty: STY.GRANITE, top: false });
  G.fh = undefined; G.bw = undefined;
  G.box({ s0: s0 + 0.2, s1: s1 - 0.2, t0: t0 + 0.2, t1: t1 - 0.2, z0: 35.3, z1: 35.4, col: ROOF, sty: STY.ASHLAR });
  for (const [a, b] of [[s0 - 1, s0 + 9], [s1 - 9, s1 + 1]]) {
    G.box({ s0: a, s1: b, t0: t0 - 1.2, t1: t0 + 10, z0: HB - 0.6, z1: 41, col: WH, sty: STY.PAVILION, zref: HB - 0.6 });
    G.box({ s0: a - 0.4, s1: b + 0.4, t0: t0 - 1.6, t1: t0 + 10.4, z0: 41, z1: 41.8, col: TRIM, sty: STY.CORNICE, bottom: true });
    G.box({ s0: a + 1.2, s1: b - 1.2, t0: t0, t1: t0 + 8.8, z0: 41.8, z1: 43.2, col: WH, sty: STY.ASHLAR });
  }
  G.box({ s0: s0 + 9, s1: s1 - 9, t0, t1: t0 + 0.8, z0: 36, z1: 39, col: TRIM, sty: STY.BALUSTRADE });
  G.box({ s0: s0 + 9, s1: s1 - 9, t0: t0 - 0.2, t1: t0 + 1.0, z0: 39, z1: 39.5, col: TRIM, sty: STY.CORNICE });
  G.box({ s0: c - 9, s1: c + 9, t0: t0 + 6, t1: t1 - 6, z0: 36, z1: 39.5, col: WH, sty: STY.ASHLAR });
  return { mesh, topEll: f.h + 43.2 };
}
