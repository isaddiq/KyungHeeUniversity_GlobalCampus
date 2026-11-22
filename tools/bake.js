// Offline geometry bake, run in Chromium by scripts/bake_models.py (served from the repository root).
// It calls the SAME generator code the site uses (web/js/*), so baked and procedural geometry are identical,
// and encodes the result with web/js/baked.js. Nothing here runs on the published site.
import { loadDem } from "../web/js/terrain.js";
import { buildKhuItems, buildingRec } from "../web/js/khu_buildings.js";
import { groundObjectItems } from "../web/js/ground_objects.js";
import { encodeGroup, decodeGroup, itemArrays } from "../web/js/baked.js";

const Cesium = window.Cesium;
const DATA = "/web/data";
const json = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`); return r.json(); });

function toBase64(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}


/**
 * Round trip: decode what was encoded and compare with the generator output (positions within the
 * quantisation step, indices exact after removing duplicate vertices). Throws if anything is off.
 */
function verify(items, manifest, bytes) {
  const g = decodeGroup(manifest, bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  let maxPos = 0;
  manifest.items.forEach((r, k) => {
    const m = items[k].mesh, d = itemArrays(g, r);
    // every original triangle must map onto decoded vertices at the same place
    for (let t = 0; t < m.i.length; t++) {
      const src = m.i[t], dst = d.idx[t];
      for (let a = 0; a < 3; a++) maxPos = Math.max(maxPos, Math.abs(m.p[3 * src + a] - d.p[3 * dst + a]) / r.q);
    }
  });
  if (!(maxPos <= 0.5001)) throw new Error(`${manifest.group}: decoded positions off by ${maxPos} steps`);
  return maxPos;
}

/** groups: subset of ["buildings", "ground_objects", "ground"]. */
export async function bake(groups) {
  const dem = await loadDem(`${DATA}/terrain`);
  const details = await json(`${DATA}/campus_details.json`);
  const ground = await json(`${DATA}/ground.json`);
  const out = {};
  const t0 = performance.now();

  if (groups.includes("buildings")) {
    const fc = await json(`${DATA}/buildings_campus.geojson`).catch(() => json(`${DATA}/buildings.geojson`));
    const recs = fc.features.filter((f) => f.properties.in_campus).map((f) => buildingRec(f, dem));
    const items = buildKhuItems(dem, recs, details);
    const { manifest, bytes } = encodeGroup("buildings", items);
    verify(items, manifest, bytes);
    out.buildings = { manifest, b64: toBase64(bytes) };
  }

  if (groups.includes("ground_objects")) {
    // cherries are ground objects too (separate layer toggle on the site, told apart by kind)
    const items = [...groundObjectItems(dem, ground.objects), ...groundObjectItems(dem, ground.cherries)];
    const { manifest, bytes } = encodeGroup("ground_objects", items);
    verify(items, manifest, bytes);
    out.ground_objects = { manifest, b64: toBase64(bytes) };
  }

  if (groups.includes("ground")) {
    // Validate every surface polygon once, here, instead of on every page load: a polygon whose Cesium
    // geometry comes out empty would be dropped inside a batch and shift the colours of the ones after it.
    const fills = [];
    let dropped = 0;
    for (const f of ground.fills) {
      let ok = false;
      try {
        const g = new Cesium.PolygonGeometry({ polygonHierarchy: new Cesium.PolygonHierarchy(
          Cesium.Cartesian3.fromDegreesArray(f.c[0].slice(0, -1).flat()),
          f.c.slice(1).map((h) => new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(h.slice(0, -1).flat())))) });
        ok = !!Cesium.PolygonGeometry.createGeometry(g);
      } catch { ok = false; }
      if (ok) fills.push(f); else dropped++;
    }
    out.ground = {
      data: {
        note: ground.note + " [baked copy: polygons validated offline (" + dropped + " degenerate dropped); 3D objects are in the baked ground_objects group, only the fountains stay for their water surfaces]",
        fills, lines: ground.lines, objects: (ground.objects ?? []).filter((o) => o.k === "fountain"), cherries: ground.cherries,
      },
      dropped,
    };
  }
  out.ms = Math.round(performance.now() - t0);
  return out;
}
