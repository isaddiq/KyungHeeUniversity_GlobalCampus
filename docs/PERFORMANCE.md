# Loading and rendering performance

This page records what was slow, what was changed, and the measurements before and after. Every number
here comes from `scripts/bench.py` or from Chrome CPU profiles taken with the same harness. Nothing is
estimated.

## How to reproduce

```bash
pip install playwright && python -m playwright install chromium
python scripts/bench.py --runs 3 --out docs/perf/after.json            # this checkout
git worktree add ../khu_before <commit>                                 # an older version to compare
python scripts/bench.py --runs 3 --web ../khu_before/web --out docs/perf/before.json
```

The harness:

- serves the site with gzip, like GitHub Pages;
- drives Chromium on the real GPU through ANGLE/D3D11;
- measures a cold load (empty cache) and a warm load (a new tab sharing the HTTP cache);
- flies the camera along a fixed 6 s path: an orbit around the campus, then a low pass over the main gate.

The **desktop** profile is a 1600×900 window. The **mobile-class** profile is a 390×844 touch viewport,
which takes the site's mobile code path, with 4× CPU throttling and a 12 Mbit/s, 80 ms network. It is an
approximation of a phone, not a real one. An older version needs the `khu:*` performance marks added to its
`main.js` (the four `mark(...)` lines) to report stage times.

Test machine: Windows 11, Intel UHD Graphics (integrated), Chromium from Playwright.

## What the profile showed

The bottlenecks were not the model sizes.

| Where | Cost (desktop) | Cause |
| --- | --- | --- |
| Camera movement | 4.3 s of main-thread time in a 6 s flight | Cesium 1.123 recomputes the rectangle of the campus clipping polygon (116 vertices) for **every terrain tile on every frame** (`ClippingPolygonCollection.computeIntersectionWithBoundingVolume` → `ClippingPolygon.computeRectangle`). |
| Camera movement | ~1.0 s in the same flight | Terrain heightmap tiles computed synchronously on the main thread. Half of it was the Woojungwon `platform` grade testing every ring edge for samples far outside its reach. |
| Every frame after any mouse move | one globe ray pick per frame, forever | The cursor read-out never cleared its pending mouse position. |
| Start-up | ~0.35 s (≈1.4 s at 4× CPU) | Procedural generation of the campus models (the main gate's sculpture alone was 0.2 s) and of the ground objects. |
| Start-up | 1 812 synchronous `PolygonGeometry.createGeometry` calls | A validity check on every ground polygon, on every page load. |
| Start-up | ~2.7 s | WebGL shader compile and link for the first frames (the large procedural facade shader and Cesium's own). This is unchanged; see *Not changed*. |

## What was changed

1. **Clipping rectangle cached** ([main.js](../web/js/main.js)). The campus rings never change, so each
   clipping polygon's rectangle is computed once. This was the largest single gain.
2. **Terrain tiles in Web Workers** ([terrain_worker.js](../web/js/terrain_worker.js),
   [dem_core.js](../web/js/dem_core.js)). The DEM sampler has no Cesium dependency and now runs in a
   small worker pool. `CustomHeightmapTerrainProvider` gets a promise per tile. Heights are identical: the
   old and new samplers were compared on 800 000 points, with a maximum difference of 0. An exact early-out
   was added to the platform grade: `min()` can only lower the ground, so samples whose cut slope cannot
   reach them are skipped.
3. **Cursor read-out** is updated only when the mouse or camera moved, at most every 100 ms.
4. **Request-render mode**. Frames are drawn when something changes (camera, tiles, data loading, UI
   input), not continuously while the view is still. The walk/fly camera tick moved to `preUpdate` so
   keyboard movement still works.
5. **Pre-baked geometry** ([scripts/bake_models.py](../scripts/bake_models.py), [tools/bake.js](../tools/bake.js),
   [baked.js](../web/js/baked.js)):
   - The 44 campus models and the 152 ground objects (including the cherry trees) are generated once,
     offline, by the site's own generator code in headless Chromium. The site downloads and decodes them
     instead of rebuilding them.
   - Each building stays its own instance, so picking, highlighting and metadata are unchanged.
   - The encoding:
     - positions as int16 per item (< 4 mm steps);
     - normals as int8;
     - facade coordinates as int16 per item (a few mm);
     - wall length and ground level in cm;
     - a shared (colour, style) table;
     - planar per-item deltas and zigzag-delta indices, so gzip can use the regularity of procedural meshes.
   - Each bake decodes its own output and fails if any vertex moved by more than half a quantisation step.
   - Files carry a content hash in their names. `--check` (run by the deploy workflow) fails when the code
     or data the bake depends on has changed. Unchanged groups are not re-baked.
   - `?procedural=1` keeps the original in-browser generation as a fallback.
6. **Ground polygons validated offline**. The baked copy of `ground.json` holds only polygons that produce
   geometry, so the per-polygon `createGeometry` check is skipped at load. The surfaces stay one
   GroundPrimitive per kind, because kinds overlap on purpose (turf stripes, court markings, road lines)
   and that keeps their drawing order. Merging them into one primitive was tried and broke the drawing
   order.
7. **Slim campus details**. The browser loads a 10 kB copy of `campus_details.json` (1.24 MB) without the
   modelling specifications, which only the generators need.

### Measured trade-offs (kept out on purpose)

| Option | Measured | Decision |
| --- | --- | --- |
| Bake the 2 598 trees | 4.0 MB gzipped to download, against 37 kB of tree positions | **Not baked.** Trees are generated in the browser in small chunks after the campus is visible. They are grouped into ~150 m cells so that whole chunks can be frustum-culled. |
| Plain float32 bake of the buildings | 4.6 MB gzipped | Replaced by the quantised, delta-coded format: **1.25 MB** gzipped (ground objects 0.31 MB). |
| Draco / Meshopt decoders | quantisation + gzip already gave the reduction above | Not added: no extra decoder dependency. |
| One GroundPrimitive for all surface kinds | wrong drawing order of overlapping surfaces (screenshot check) | Reverted. |
| Staged / LOD loading | implemented, then removed at the owner's request | The original single loading screen is kept. |
| 3D Tiles | the campus is ~45 models and one terrain; Cesium culls per primitive already | Not introduced. |

## Results

RESULTS_TABLE

## Not changed

- **Shader compilation (~2.7 s on this GPU at start-up)** is the largest remaining start-up cost. It
  comes from compiling the procedural facade shader and Cesium's own programs on first use. Cesium does
  not use `KHR_parallel_shader_compile`, and splitting the facade shader would change how it looks, so it
  was left as it is.
- Shadows, MSAA and the "light / full detail" switch work as before.
