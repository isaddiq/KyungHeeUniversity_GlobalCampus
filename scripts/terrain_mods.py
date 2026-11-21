"""Local terrain conditioning on top of the FABDEM DTM (estimated; the 30 m DTM smooths these engineered forms away).

Applied in BOTH places so everything stays consistent:
  * Python: dem.load() samples the conditioned surface (building ground levels, trees, ground objects ...);
    dem.load(raw=True) returns the untouched FABDEM (used by validate.py for accuracy checks).
  * Browser: web/data/terrain/terrain_mods.json is applied by DemGrid.heightOrtho() in web/js/terrain.js
    (dtm.bin itself is unchanged).
Conditioning only ever LOWERS the DTM.

Types
  bowl     : sunken stadium - inside the OSM outline, a retaining slope (ramp_m) then `steps` terraces of
             `rise_m` down to a level field (field_m).
  platform : a levelled site below the surrounding ground - inside the region, ground = level_m; outside, a
             cut slope rising at `slope` (m per m) until it meets the original DTM.

Run as a pipeline step (after build_terrain.py, before build_features.py): writes terrain_mods.json.
"""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from common import RAW, WEB_DATA, read_json, write_json

LAT_C = 37.2424
MX = 111_320.0 * math.cos(math.radians(LAT_C))
MY = 110_950.0

# 14 대운동장: sunken stadium (13 photos + user confirmation: the grey ring is steps going down; the stadium lies
# below the surrounding road). Field level = lowest rim (10th percentile of DTM on the outline) - steps x rise.
BOWLS = {"way/455725379": {"stands": 12.0, "ramp": 3.0, "steps": 10, "rise": 0.4}}
# 04 우정원: the dormitory and its parking lots sit on one level below the main road, reached by a slope down
# from the road (user report + photo "front from across the road"). Level = 10th percentile of the DTM over
# the region; cut slope 1:4 back up to the original ground.
PLATFORMS = {"woojungwon": {"members": ["relation/8269760", "way/829334051", "way/1365659109"], "pad": 3.0, "slope": 0.25,
                            "source": "user report (lower than the main road, slope down from the road) + photo 'front from across the road'"}}


def _raw_els():
    return {f"{e['type']}/{e['id']}": e for e in read_json(RAW / "osm_overpass.json")["elements"]}


def _poly(el):
    from build_features import element_polygon   # import here: build_features imports dem, which imports us
    return element_polygon(el)


def _to_m(g):
    return shapely.transform(g, lambda c: np.column_stack([(c[:, 0] - 127.08) * MX, (c[:, 1] - LAT_C) * MY]))


def _rings(g):
    gs = [g] if g.geom_type == "Polygon" else list(g.geoms)
    return [[[round(x, 7), round(y, 7)] for x, y in p.exterior.coords] for p in gs]


def build(dtm_raw):
    els = _raw_els()
    mods = []
    for oid, sp in BOWLS.items():
        g = _poly(els[oid])
        rim = sorted(float(v) for v in dtm_raw.sample(*np.array(g.exterior.coords).T))
        zr = rim[max(0, int(0.1 * len(rim)) - 1)]
        mods.append({"type": "bowl", "id": oid, "ring": _rings(g)[0], "field_m": round(zr - sp["steps"] * sp["rise"], 2),
                     "stands_m": sp["stands"], "ramp_m": sp["ramp"], "steps": sp["steps"], "rise_m": sp["rise"], "status": "estimated",
                     "source": "OSM stadium outline; bowl from 13 reference photos + user confirmation; field = lowest rim DTM (10th pct) - steps x rise"})
    for name, sp in PLATFORMS.items():
        parts = [_poly(els[m]) for m in sp["members"] if m in els]
        reg_m = unary_union([_to_m(p).buffer(sp["pad"], join_style=2) for p in parts if p is not None])
        reg = shapely.transform(reg_m, lambda c: np.column_stack([c[:, 0] / MX + 127.08, c[:, 1] / MY + LAT_C]))
        x0, y0, x1, y1 = reg.bounds
        xs, ys = np.meshgrid(np.linspace(x0, x1, 60), np.linspace(y0, y1, 60))
        inside = shapely.contains_xy(reg, xs.ravel(), ys.ravel())
        z = dtm_raw.sample(xs.ravel()[inside], ys.ravel()[inside])
        level = round(float(np.percentile(z, 10)), 2)
        mods.append({"type": "platform", "id": name, "members": sp["members"], "rings": _rings(reg), "level_m": level, "slope": sp["slope"],
                     "status": "estimated", "source": sp["source"] + f"; level = 10th percentile of the DTM over the region ({level} m)"})
    return mods


class Conditioner:
    """Vectorised application of the mods to DTM samples (orthometric heights)."""

    def __init__(self, mods):
        self.items = []
        for m in mods:
            if m["type"] == "bowl":
                g = _to_m(Polygon(m["ring"]))
                self.items.append((m, g, g.boundary, g.bounds))
            elif m["type"] == "platform":
                g = _to_m(unary_union([Polygon(r) for r in m["rings"]]))
                reach = 40.0 / max(m["slope"], 1e-3)          # the cut slope never needs to run further than this
                b = g.bounds
                self.items.append((m, g, g.boundary, (b[0] - reach, b[1] - reach, b[2] + reach, b[3] + reach)))

    def __call__(self, lon, lat, z):
        lon = np.asarray(lon, float); lat = np.asarray(lat, float); z = np.array(z, float)
        shape_ = z.shape
        x = ((lon - 127.08) * MX).ravel(); y = ((lat - LAT_C) * MY).ravel(); zz = z.ravel()
        for m, g, bnd, (bx0, by0, bx1, by1) in self.items:
            sel = np.nonzero((x >= bx0) & (x <= bx1) & (y >= by0) & (y <= by1))[0]
            if not len(sel):
                continue
            px, py = x[sel], y[sel]
            ins = shapely.contains_xy(g, px, py)
            d = shapely.distance(bnd, shapely.points(px, py))
            v = zz[sel]
            if m["type"] == "bowl":
                tread = (m["stands_m"] - m["ramp_m"]) / m["steps"]
                k = np.floor(np.maximum(0, d - m["ramp_m"]) / tread)
                above = np.where(k >= m["steps"], 0.0, (m["steps"] - k) * m["rise_m"])
                h = np.maximum(m["field_m"], np.minimum(v, m["field_m"] + above))
                t = np.clip(d / m["ramp_m"], 0, 1); s = t * t * (3 - 2 * t)
                h = np.where(d < m["ramp_m"], v * (1 - s) + h * s, h)
                zz[sel] = np.where(ins, h, v)
            else:
                cap = np.where(ins, m["level_m"], m["level_m"] + m["slope"] * d)
                zz[sel] = np.minimum(v, cap)
        return zz.reshape(shape_) if shape_ else float(zz[0])


def load_conditioner():
    p = WEB_DATA / "terrain" / "terrain_mods.json"
    if not p.exists():
        return None
    mods = [m for m in read_json(p).get("base", []) if m["type"] in ("bowl", "platform")]
    return Conditioner(mods) if mods else None


def main():
    from dem import load
    dtm_raw, _ = load(raw=True)
    mods = build(dtm_raw)
    target = WEB_DATA / "terrain" / "terrain_mods.json"
    details_path = WEB_DATA / "campus_details.json"
    # Preserve photo-model pads when refreshing the base terrain by itself.
    details = read_json(details_path) if details_path.exists() else {}
    pads = [{**pad, "id": oid} for oid, model in details.get("photo_buildings", {}).items()
            for pad in model.get("terrain_mods", [])]
    write_json(target, {
        "note": "Estimated local terrain conditioning on top of FABDEM. Base mods lower the DTM in Python and in the "
                "viewer. Photo-model pads level the viewer's surface. See docs/MODEL_PROGRESS.md.",
        "base": mods, "mods": mods + pads}, compact=True)
    for m in mods:
        print("terrain mod", m["type"], m["id"], m.get("field_m", m.get("level_m")))
    # overlays (hillshade/slope) on the conditioned surface, so they match the 3D terrain
    from build_terrain import write_overlays
    meta_p = WEB_DATA / "terrain" / "dtm.json"
    meta = read_json(meta_p)
    ov = write_overlays(dtm_raw.z, meta["west"], meta["south"], meta["east"], meta["north"],
                        meta["spacing_m"]["x"], meta["spacing_m"]["y"], WEB_DATA / "terrain", cond=Conditioner(mods))
    meta["overlays"] = ov
    write_json(meta_p, meta)


if __name__ == "__main__":
    main()
