// Real terrain: FABDEM V1-2 bare-earth DTM (EGM2008 orthometric) served as a static uint16 grid,
// converted to WGS84 ellipsoidal heights with the EGM2008 geoid grid and fed to Cesium through a
// CustomHeightmapTerrainProvider. No smoothing, no vertical exaggeration.
const Cesium = window.Cesium;

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
        return { ...m, mx, my, bbox: [Math.min(...xs) - reach / mx, Math.min(...ys) - reach / my, Math.max(...xs) + reach / mx, Math.max(...ys) + reach / my] };
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

export async function loadDem(base) {
  const meta = await (await fetch(`${base}/dtm.json`)).json();
  const buf = await (await fetch(`${base}/dtm.bin`)).arrayBuffer();
  const dem = new DemGrid(meta, buf);
  try {
    const r = await fetch(`${base}/terrain_mods.json`);
    if (r.ok) dem.setMods((await r.json()).mods);
  } catch { /* no local conditioning */ }
  return dem;
}

export function createTerrainProvider(dem) {
  const tilingScheme = new Cesium.GeographicTilingScheme();
  const W = 65, H = 65;
  return new Cesium.CustomHeightmapTerrainProvider({
    width: W,
    height: H,
    tilingScheme,
    credit: new Cesium.Credit("Terrain: FABDEM V1-2 (Univ. of Bristol, CC BY-NC-SA 4.0), derived from Copernicus DEM GLO-30 © DLR/Airbus"),
    callback: (x, y, level) => {
      const rect = tilingScheme.tileXYToRectangle(x, y, level);
      const w = Cesium.Math.toDegrees(rect.west), e = Cesium.Math.toDegrees(rect.east);
      const s = Cesium.Math.toDegrees(rect.south), n = Cesium.Math.toDegrees(rect.north);
      const out = new Float32Array(W * H);
      for (let r = 0; r < H; r++) {
        const lat = n - (r / (H - 1)) * (n - s);
        for (let c = 0; c < W; c++) {
          const lon = w + (c / (W - 1)) * (e - w);
          out[r * W + c] = dem.heightEllipsoid(lon, lat);
        }
      }
      return out;
    },
  });
}

// Globe material: hypsometric tint + contour lines computed on orthometric height (h_ell - N).
export function createTerrainMaterial({ minH, maxH, geoidN }) {
  return new Cesium.Material({
    fabric: {
      type: "KhuTerrainViz",
      uniforms: {
        minH, maxH, geoidN,
        showRamp: 1.0, rampAlpha: 0.85,
        showContours: 0.0, spacing: 5.0, majorEvery: 5.0,
        contourColor: new Cesium.Color(0.08, 0.06, 0.04, 0.95),
      },
      source: `
        vec3 ramp(float t) {
          vec3 c0 = vec3(0.10, 0.36, 0.20);
          vec3 c1 = vec3(0.40, 0.62, 0.27);
          vec3 c2 = vec3(0.85, 0.84, 0.46);
          vec3 c3 = vec3(0.86, 0.60, 0.30);
          vec3 c4 = vec3(0.62, 0.36, 0.22);
          vec3 c5 = vec3(0.96, 0.94, 0.92);
          if (t < 0.2) return mix(c0, c1, t / 0.2);
          if (t < 0.4) return mix(c1, c2, (t - 0.2) / 0.2);
          if (t < 0.6) return mix(c2, c3, (t - 0.4) / 0.2);
          if (t < 0.8) return mix(c3, c4, (t - 0.6) / 0.2);
          return mix(c4, c5, (t - 0.8) / 0.2);
        }
        czm_material czm_getMaterial(czm_materialInput materialInput) {
          czm_material m = czm_getDefaultMaterial(materialInput);
          float h = materialInput.height - geoidN;
          vec3 col = vec3(0.0);
          float a = 0.0;
          if (showRamp > 0.5) {
            float t = clamp((h - minH) / max(maxH - minH, 1.0), 0.0, 1.0);
            col = ramp(t);
            a = rampAlpha;
          }
          if (showContours > 0.5) {
            float dh = max(abs(dFdx(h)), abs(dFdy(h)));
            float d = mod(h, spacing);
            d = min(d, spacing - d);
            float major = mod(h, spacing * majorEvery);
            major = min(major, spacing * majorEvery - major);
            float w = dh * czm_pixelRatio * 0.9;
            float wm = dh * czm_pixelRatio * 1.8;
            float line = 1.0 - smoothstep(0.0, w, d);
            float lineM = 1.0 - smoothstep(0.0, wm, major);
            float l = max(line * 0.75, lineM);
            col = mix(col, contourColor.rgb, l * (a > 0.0 ? 1.0 : 1.0));
            a = max(a, l * contourColor.a);
          }
          m.diffuse = col;
          m.alpha = a;
          return m;
        }`,
    },
    translucent: false,
  });
}
