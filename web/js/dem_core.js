// DEM sampling core with no Cesium dependency, shared by the page (terrain.js) and the terrain tile
// workers (terrain_worker.js): FABDEM V1-2 bare-earth DTM (EGM2008 orthometric) as a uint16 grid,
// plus the estimated local grades of terrain_mods.json and the EGM2008 geoid grid.
export class DemGrid {
  constructor(meta, buffer) {
    this.meta = meta;
    this.rows = meta.rows;
    this.cols = meta.cols;
    this.west = meta.west; this.north = meta.north;
    this.east = meta.east; this.south = meta.south;
    this.dlon = meta.dlon; this.dlat = meta.dlat;
    const q = new Uint16Array(buffer);
    if (q.length !== this.rows * this.cols) throw new Error("DEM size mismatch");
    this.h = new Float32Array(q.length);
    for (let i = 0; i < q.length; i++) this.h[i] = q[i] * meta.scale + meta.offset;
    const g = meta.geoid;
    this.geoid = { ...g, N: g.N_m.flat(), gdx: (g.east - g.west) / (g.nx - 1), gdy: (g.north - g.south) / (g.ny - 1) };
    // edge mean, used to fade terrain smoothly to a constant outside the data window
    let s = 0, n = 0;
    for (let c = 0; c < this.cols; c++) { s += this.h[c] + this.h[(this.rows - 1) * this.cols + c]; n += 2; }
    for (let r = 0; r < this.rows; r++) { s += this.h[r * this.cols] + this.h[r * this.cols + this.cols - 1]; n += 2; }
    this.edgeMean = s / n;
  }

  contains(lon, lat) {
    return lon >= this.west && lon <= this.east && lat >= this.south && lat <= this.north;
  }

  /** Bilinear orthometric height (m, EGM2008). Outside the grid, fades to the edge mean over ~2 km. */
  heightOrtho(lon, lat, conditioned = true) {
    const fxRaw = (lon - this.west) / this.dlon;
    const fyRaw = (this.north - lat) / this.dlat;
    const fx = Math.min(Math.max(fxRaw, 0), this.cols - 1.000001);
    const fy = Math.min(Math.max(fyRaw, 0), this.rows - 1.000001);
    const x0 = Math.floor(fx), y0 = Math.floor(fy);
    const tx = fx - x0, ty = fy - y0;
    const i = y0 * this.cols + x0, h = this.h;
    const v = h[i] * (1 - tx) * (1 - ty) + h[i + 1] * tx * (1 - ty) +
      h[i + this.cols] * (1 - tx) * ty + h[i + this.cols + 1] * tx * ty;
    const ox = Math.max(0, -fxRaw, fxRaw - (this.cols - 1)) * this.meta.spacing_m.x;
    const oy = Math.max(0, -fyRaw, fyRaw - (this.rows - 1)) * this.meta.spacing_m.y;
    const out = Math.hypot(ox, oy);
    if (out <= 0) return conditioned && this.mods ? this.applyMods(lon, lat, v) : v;
    const t = Math.min(1, out / 2000);
    const s = t * t * (3 - 2 * t);
    return v * (1 - s) + this.edgeMean * s;
  }

  /**
   * Local terrain conditioning (terrain_mods.json, estimated): "bowl" shapes a stadium below the DTM.
   * "level" blends a building apron inside its outline. "grade" keeps a playing surface level
   * to the mapped edge and blends it into the surrounding ground outside the outline.
   */
  setMods(mods) {
    const mx = 111320 * Math.cos(37.2424 * Math.PI / 180), my = 110950; // terrain_mods.py matching metric frame
    this.mods = (mods ?? []).filter((m) => ["bowl", "platform", "level", "grade", "profile"].includes(m.type)).map((m) => {
      if (m.type === "profile") {
        const xs = m.points.map((p) => p[0]), ys = m.points.map((p) => p[1]);
        const reach = m.width_m + m.ramp_m;
        let total = 0;
        const segments = m.points.slice(1).map(([lon, lat, height], i) => {
          const [x, y, z] = m.points[i];
          const dx = (lon - x) * mx, dy = (lat - y) * my, len = Math.hypot(dx, dy);
          const seg = { x, y, z, dx, dy, len, start: total, rise: height - z };
          total += len;
          return seg;
        }).filter((seg) => seg.len > 0);
        return { ...m, segments, total, mx, my,
          bbox: [Math.min(...xs) - reach / mx, Math.min(...ys) - reach / my, Math.max(...xs) + reach / mx, Math.max(...ys) + reach / my] };
      }
      if (m.type === "platform") {   // levelled site (several rings) + cut slope back up to the DTM
        const points = m.rings.flat();
        const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]), reach = 40 / Math.max(m.slope, 1e-3);
        return { ...m, mx, my, rbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)],
          bbox: [Math.min(...xs) - reach / mx, Math.min(...ys) - reach / my, Math.max(...xs) + reach / mx, Math.max(...ys) + reach / my] };
      }
      const xs = m.ring.map((p) => p[0]), ys = m.ring.map((p) => p[1]);
      const reach = m.type === "grade" ? m.ramp_m : 0;
      return { ...m, mx, my, bbox: [Math.min(...xs) - reach / mx, Math.min(...ys) - reach / my, Math.max(...xs) + reach / mx, Math.max(...ys) + reach / my] };
    });
    if (!this.mods.length) this.mods = null;
  }

  applyMods(lon, lat, v) {
    for (const m of this.mods) {
      const b = m.bbox;
      if (lon < b[0] || lon > b[2] || lat < b[1] || lat > b[3]) continue;
      if (m.type === "platform") { v = this.platformHeight(m, lon, lat, v); continue; }
      if (m.type === "profile") { v = this.profileHeight(m, lon, lat, v); continue; }
      const r = m.ring;
      let inside = false, dmin = Infinity;
      for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
        const [xi, yi] = r[i], [xj, yj] = r[j];
        if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
        const ax = (xj - xi) * m.mx, ay = (yj - yi) * m.my, px = (lon - xi) * m.mx, py = (lat - yi) * m.my;
        const t = Math.max(0, Math.min(1, (px * ax + py * ay) / (ax * ax + ay * ay || 1)));
        dmin = Math.min(dmin, Math.hypot(px - ax * t, py - ay * t));
      }
      if (m.type === "grade") {
        const t = inside ? 1 : Math.max(0, 1 - dmin / m.ramp_m);
        v += t * t * (3 - 2 * t) * (m.height_m - v);
        continue;
      }
      if (!inside) continue;
      if (m.type === "level") {
        const t = Math.min(1, dmin / m.ramp_m), s = t * t * (3 - 2 * t);
        v += s * (m.height_m - v);
        continue;
      }
      // retaining slope over the first ramp_m inside the outline (no cliff exactly on the outline, which
      // rendered as saw-teeth), then steps of equal tread down to the level field
      const ramp = m.ramp_m ?? 0, tread = (m.stands_m - ramp) / m.steps;
      const k = Math.floor(Math.max(0, dmin - ramp) / tread);    // 0 = top step
      const above = k >= m.steps ? 0 : (m.steps - k) * m.rise_m;
      const h = Math.max(m.field_m, Math.min(v, m.field_m + above));
      const t = Math.min(1, dmin / ramp), s = t * t * (3 - 2 * t);
      v += s * (h - v);
    }
    return v;
  }

  /** Interpolate along the mapped path and blend across the shoulders. */
  profileHeight(m, lon, lat, v) {
    let nearest = Infinity, station = 0, height = v;
    for (const { x, y, z, dx, dy, len, start, rise } of m.segments) {
      const px = (lon - x) * m.mx, py = (lat - y) * m.my;
      const u = Math.max(0, Math.min(1, (px * dx + py * dy) / (len * len)));
      const distance = Math.hypot(px - u * dx, py - u * dy);
      if (distance < nearest) {
        nearest = distance;
        station = start + u * len;
        height = z + u * rise;
      }
    }
    const t = Math.max(0, Math.min(1, (m.width_m + m.ramp_m - nearest) / m.ramp_m,
      station / m.taper_m[0], (m.total - station) / m.taper_m[1]));
    return v + t * t * (3 - 2 * t) * (height - Math.min(nearest, m.width_m) * m.crown - v);
  }

  /** "platform": ground = level_m inside the rings; outside, a cut slope rising at m.slope back to the DTM (only lowers). */
  platformHeight(m, lon, lat, v) {
    // exact early-outs: the result is min(v, cap) with cap >= level + slope * (distance to the rings' bbox)
    if (v <= m.level_m) return v;
    const rb = m.rbox, dx = Math.max(rb[0] - lon, 0, lon - rb[2]) * m.mx, dy = Math.max(rb[1] - lat, 0, lat - rb[3]) * m.my;
    if (m.level_m + m.slope * Math.hypot(dx, dy) >= v) return v;
    let inside = false, dmin = Infinity;
    for (const r of m.rings) {
      let inR = false;
      for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
        const [xi, yi] = r[i], [xj, yj] = r[j];
        if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inR = !inR;
        const ax = (xj - xi) * m.mx, ay = (yj - yi) * m.my, px = (lon - xi) * m.mx, py = (lat - yi) * m.my;
        const t = Math.max(0, Math.min(1, (px * ax + py * ay) / (ax * ax + ay * ay || 1)));
        dmin = Math.min(dmin, Math.hypot(px - ax * t, py - ay * t));
      }
      inside = inside || inR;
    }
    return Math.min(v, inside ? m.level_m : m.level_m + m.slope * dmin);
  }

  /** EGM2008 geoid undulation N (m), bilinear on the 9x9 PROJ-derived grid (clamped). */
  geoidN(lon, lat) {
    const g = this.geoid;
    const fx = Math.min(Math.max((lon - g.west) / g.gdx, 0), g.nx - 1.000001);
    const fy = Math.min(Math.max((g.north - lat) / g.gdy, 0), g.ny - 1.000001);
    const x0 = Math.floor(fx), y0 = Math.floor(fy), tx = fx - x0, ty = fy - y0;
    const i = y0 * g.nx + x0, N = g.N;
    return N[i] * (1 - tx) * (1 - ty) + N[i + 1] * tx * (1 - ty) + N[i + g.nx] * (1 - tx) * ty + N[i + g.nx + 1] * tx * ty;
  }

  /** WGS84 ellipsoidal height of the bare-earth surface: h = H + N */
  heightEllipsoid(lon, lat) {
    return this.heightOrtho(lon, lat) + this.geoidN(lon, lat);
  }

  orthoToEllipsoid(lon, lat, H) { return H + this.geoidN(lon, lat); }

  statsInRect(w, s, e, n) {
    let mn = Infinity, mx = -Infinity;
    for (let r = 0; r < this.rows; r++) {
      const lat = this.north - r * this.dlat;
      if (lat < s || lat > n) continue;
      for (let c = 0; c < this.cols; c++) {
        const lon = this.west + c * this.dlon;
        if (lon < w || lon > e) continue;
        const v = this.heightOrtho(lon, lat);
        if (v < mn) mn = v; if (v > mx) mx = v;
      }
    }
    return { min: mn, max: mx };
  }
}

/** Ellipsoidal heights of a W x H heightmap tile (row 0 = north), exactly as the terrain provider needs. */
export function sampleTile(dem, w, s, e, n, W, H) {
  const out = new Float32Array(W * H);
  for (let r = 0; r < H; r++) {
    const lat = n - (r / (H - 1)) * (n - s);
    for (let c = 0; c < W; c++) {
      const lon = w + (c / (W - 1)) * (e - w);
      out[r * W + c] = dem.heightEllipsoid(lon, lat);
    }
  }
  return out;
}
