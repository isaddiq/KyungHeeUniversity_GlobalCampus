// Real terrain: FABDEM V1-2 bare-earth DTM (EGM2008 orthometric) served as a static uint16 grid,
// converted to WGS84 ellipsoidal heights with the EGM2008 geoid grid and fed to Cesium through a
// CustomHeightmapTerrainProvider. No smoothing, no vertical exaggeration.
import { DemGrid, sampleTile } from "./dem_core.js";
export { DemGrid };
const Cesium = window.Cesium;

export async function loadDem(base) {
  const [meta, buf, mods] = await Promise.all([
    fetch(`${base}/dtm.json`).then((r) => r.json()),
    fetch(`${base}/dtm.bin`).then((r) => r.arrayBuffer()),
    fetch(`${base}/terrain_mods.json`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
  ]);
  const dem = new DemGrid(meta, buf);
  if (mods) dem.setMods(mods.mods);
  dem.source = { meta, buffer: buf, mods: mods?.mods ?? [] };   // handed to the terrain tile workers
  return dem;
}

/**
 * Pool of module workers that compute heightmap tiles (terrain_worker.js). Heights come from the same
 * DemGrid code; this only moves ~1 s of per-tile sampling during camera moves off the main thread.
 */
function createTilePool(dem, size) {
  if (typeof Worker === "undefined" || !dem.source) return null;
  try {
    const url = new URL("./terrain_worker.js", import.meta.url);
    const workers = [], pending = new Map();
    let next = 0, seq = 0;
    for (let i = 0; i < size; i++) {
      const w = new Worker(url, { type: "module" });
      w.onmessage = (e) => { const p = pending.get(e.data.id); pending.delete(e.data.id); p?.resolve(e.data.out); };
      w.onerror = (e) => { console.warn("terrain worker failed; using the main thread", e.message); pool.broken = true; for (const p of pending.values()) p.fail(); pending.clear(); };
      w.postMessage({ init: true, meta: dem.source.meta, buffer: dem.source.buffer.slice(0), mods: dem.source.mods });
      workers.push(w);
    }
    const pool = {
      broken: false,
      run(job) {
        return new Promise((resolve, reject) => {
          const id = ++seq;
          pending.set(id, { resolve, fail: () => resolve(sampleTile(dem, job.w, job.s, job.e, job.n, job.W, job.H)) });
          workers[next++ % workers.length].postMessage({ id, ...job });
        });
      },
    };
    return pool;
  } catch (e) {
    console.warn("terrain workers unavailable", e);
    return null;
  }
}

export function createTerrainProvider(dem, { workers = 2 } = {}) {
  const tilingScheme = new Cesium.GeographicTilingScheme();
  const W = 65, H = 65;
  const pool = workers > 0 ? createTilePool(dem, workers) : null;
  return new Cesium.CustomHeightmapTerrainProvider({
    width: W,
    height: H,
    tilingScheme,
    credit: new Cesium.Credit("Terrain: FABDEM V1-2 (Univ. of Bristol, CC BY-NC-SA 4.0), derived from Copernicus DEM GLO-30 © DLR/Airbus"),
    callback: (x, y, level) => {
      const rect = tilingScheme.tileXYToRectangle(x, y, level);
      const w = Cesium.Math.toDegrees(rect.west), e = Cesium.Math.toDegrees(rect.east);
      const s = Cesium.Math.toDegrees(rect.south), n = Cesium.Math.toDegrees(rect.north);
      if (pool && !pool.broken) return pool.run({ w, s, e, n, W, H });
      return sampleTile(dem, w, s, e, n, W, H);
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
