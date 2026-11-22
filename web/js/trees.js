// Vegetation instances (VISUAL APPROXIMATION - positions are synthetic, see data/trees.json).
// Mix of Korean red pine (layered conifer crowns) and broadleaf trees (irregular lobed crowns),
// per-tree colour/size variation, rendered with the shared material shader (foliage style).
import { Mesh, Frame, Local, STY } from "./mesh.js";
const Cesium = window.Cesium;

/**
 * Builds the trees in chunks of ~250 into `coll` (a PrimitiveCollection), yielding to the browser between
 * chunks so the page stays responsive while vegetation fills in. Resolves with the number of trees.
 */
export async function buildTrees(viewer, dem, meta, arr, inClip, mobile, coll) {
  const stride = 4, count = arr.length / stride, keep = mobile ? 3 : 1;
  const f = new Frame(127.0818, 37.2427, 0);
  let mesh = new Mesh(), inChunk = 0, total = 0;
  const flush = async () => {
    if (!mesh.empty) coll.add(new Cesium.Primitive({
      geometryInstances: new Cesium.GeometryInstance({ id: { kind: "trees" }, geometry: mesh.geometry(), attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(new Cesium.Color(1, 1, 1, 0)) } }),
      appearance: createTreeAppearance(), asynchronous: false, compressVertices: false,
      shadows: mobile ? Cesium.ShadowMode.DISABLED : Cesium.ShadowMode.ENABLED,
    }));
    mesh = new Mesh(); inChunk = 0;
    await new Promise((r) => setTimeout(r, 0));
  };
  for (let i = 0; i < count; i += keep) {
    const lon = meta.origin_lon + arr[i * stride], lat = meta.origin_lat + arr[i * stride + 1];
    if (!inClip(lon, lat)) continue;
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
    total++;
    if (++inChunk >= 250) await flush();
  }
  await flush();
  return total;
}

// trees share the facade material shader (style 21 = foliage)
import { createFacadeAppearance } from "./mesh.js";
function createTreeAppearance() { return createFacadeAppearance(); }
