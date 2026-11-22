// Terrain heightmap tiles computed off the main thread. Same DemGrid code and the same sample
// positions as the main-thread path in terrain.js, so heights are identical.
import { DemGrid, sampleTile } from "./dem_core.js";

let dem = null;
self.onmessage = (e) => {
  const d = e.data;
  if (d.init) {
    dem = new DemGrid(d.meta, d.buffer);
    dem.setMods(d.mods);
    return;
  }
  const out = sampleTile(dem, d.w, d.s, d.e, d.n, d.W, d.H);
  self.postMessage({ id: d.id, out }, [out.buffer]);
};
