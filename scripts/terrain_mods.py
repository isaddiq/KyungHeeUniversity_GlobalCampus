"""Estimated local grades for engineered surfaces that the 30 m FABDEM grid cannot resolve.

Applied in BOTH places so everything stays consistent:
  * Python: dem.load() samples the conditioned surface (building ground levels, trees, ground objects ...);
    dem.load(raw=True) returns the untouched FABDEM (used by validate.py for accuracy checks).
  * Browser: web/data/terrain/terrain_mods.json is applied by DemGrid.heightOrtho() in web/js/terrain.js
    (dtm.bin itself is unchanged).
Types
  bowl     : sunken stadium - inside the OSM outline, a retaining slope (ramp_m) then `steps` terraces of
             `rise_m` down to a level field (field_m).
  platform : a levelled site below the surrounding ground - inside the region, ground = level_m; outside, a
             cut slope rising at `slope` (m per m) until it meets the original DTM.
  grade    : a flat playing surface inside its mapped outline, with a smooth shoulder outside it.
  level    : a building apron that blends back to the DTM just inside its boundary.
  profile  : a centreline elevation profile with a fixed cross-section and blended shoulders.

Run as a pipeline step (after build_terrain.py, before build_features.py): writes terrain_mods.json.
"""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from common import FEATURE_BBOX, RAW, WEB_DATA, read_json, write_json

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
PLAYING_SURFACES = {
    "way/326869014": ("artificial turf field, reference folder 05", 7),
    "way/455725380": ("four hard tennis courts beside the artificial turf, KHU panoramas 4743 and 4680", 3),
    "way/801815068": ("southern sports ground, reference folder 27", 9),
    "way/326869011": ("west baseball field, reference folder 28", 8),
    "way/801815067": ("east baseball field, reference folder 28", 8),
}

TURF_STAIR = [[127.079666, 37.245925], [127.079771, 37.245920],
              [127.079803, 37.245981], [127.079936, 37.245981]]

# The straight stone flight is visible from Woojungwon's lot in panorama 4733.
WOOJUNGWON_STAIR = [[127.07792670, 37.24553020], [127.07794547, 37.24546401]]
WOOJUNGWON_STAIR_W = 3.0
WOOJUNGWON_WALK = [[127.07790524, 37.24557077], *WOOJUNGWON_STAIR,
                  [127.07798302, 37.24541490], [127.07805276, 37.24539782],
                  [127.07814127, 37.24537006], [127.07820833, 37.24532736],
                  [127.07824051, 37.24526971], [127.07831830, 37.24519712]]

OBSERVATORY_APRON = "way/1385686357"
OBSERVATORY_BAYS = ("way/829334053", "way/1385686355", "way/1385686356")
BASKETBALL_COURTS = ("way/585696427", "way/585696429")


def _profile(oid, line, stations, half_width, shoulder, source, taper=(5, 5), crown=0):
    """Sample grade breakpoints and preserve every bend in the mapped horizontal alignment."""
    metric = _to_m(LineString(line))
    run = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.asarray(metric.coords), axis=0), axis=1))]
    chain, height = np.array(stations).T
    chain[-1] = run[-1]
    points = []
    for s in sorted(set(run) | set(chain)):
        p = metric.interpolate(s)
        points.append([round(p.x / MX + 127.08, 8), round(p.y / MY + LAT_C, 8), round(float(np.interp(s, chain, height)), 3)])
    return {"type": "profile", "id": oid, "points": points, "width_m": half_width, "ramp_m": shoulder,
            "taper_m": taper, "crown": crown, "status": "estimated", "source": source}


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
    first_playing = len(mods)
    for oid, (site, shoulder) in PLAYING_SURFACES.items():
        g = _poly(els[oid])
        w, s, e, n = g.bounds
        lon, lat = np.meshgrid(np.arange(w, e, 3 / MX), np.arange(s, n, 3 / MY))
        x, y = (lon - 127.08) * MX, (lat - LAT_C) * MY
        inside = shapely.contains_xy(_to_m(g).buffer(-12), x, y)
        height = round(float(np.median(dtm_raw.sample(lon[inside], lat[inside]))), 2)
        mods.append({"type": "grade", "id": oid, "ring": _rings(g)[0], "height_m": height,
                     "ramp_m": shoulder, "status": "estimated",
                     "source": f"OSM outline and photo evidence of a level {site}; height from the median of the FABDEM interior, at least 12 m from the edge"})
    turf_level = next(m["height_m"] for m in mods if m["id"] == "way/326869014")
    mods.insert(first_playing, {"type": "grade", "id": "sports-plaza", "height_m": turf_level - 0.13, "ramp_m": 3.0,
                 "ring": [[127.078859, 37.2459], [127.079644, 37.245906], [127.079681, 37.246078],
                          [127.078864, 37.246059], [127.078859, 37.2459]], "status": "estimated",
                 "source": "KHU aerial panorama 4680: near-level brick plaza between the artificial turf and the hard courts"})

    def road(oid):
        return [[p["lon"], p["lat"]] for p in els[oid]["geometry"]]

    apron = unary_union([_poly(els[oid]) for oid in (OBSERVATORY_APRON, *OBSERVATORY_BAYS)]).convex_hull
    w, s, e, n = apron.bounds
    lon, lat = np.meshgrid(np.linspace(w, e, 36), np.linspace(s, n, 36))
    inside = shapely.contains_xy(apron, lon, lat)
    lot_height = round(float(np.median(dtm_raw.sample(lon[inside], lat[inside]))), 2)
    entry = road("way/423471674")[1:7]
    length = _to_m(LineString(entry)).length
    mods.append(_profile("observatory-access", entry,
                         [(0, dtm_raw.sample(*entry[0])), (27, 86.0), (50, lot_height),
                          (length, lot_height)], 3.2, 5.0,
                         "Observatory access road approaching the level forecourt in KHU panorama 5226", taper=(12, 8)))
    mods.append({"type": "grade", "id": "observatory-parking", "ring": _rings(apron)[0],
                 "height_m": lot_height, "ramp_m": 11, "status": "estimated",
                 "source": "KHU panorama 5226 shows the concrete parking forecourt below the ramp; bounds from the OSM plaza and parking rows, elevation inferred from FABDEM"})

    courts_m = unary_union([_to_m(_poly(els[oid])) for oid in BASKETBALL_COURTS]).convex_hull.buffer(1.0, join_style=2)
    courts = shapely.transform(courts_m, lambda c: np.column_stack([c[:, 0] / MX + 127.08, c[:, 1] / MY + LAT_C]))
    mods.append({"type": "grade", "id": "turf-basketball-courts", "ring": _rings(courts)[0],
                 "height_m": round(dtm_raw.sample(courts.centroid.x, courts.centroid.y), 2),
                 "ramp_m": 2.0, "status": "estimated",
                 "source": "KHU overhead photograph shows two parallel courts on the same deck; elevation inferred from FABDEM"})

    main = road("way/764171420")    # OSM order is from the Foreign Languages junction towards the gate.
    mods.append(_profile("way/764171420", main,
                         [(0, dtm_raw.sample(*main[0])), (37, 68.94), (82, 68.99), (173, 69.15),
                          (260, 69.48), (303, dtm_raw.sample(*main[-1]))],
                         7.2, 6.5, "Gate approach panoramas 5147–5148; street-to-street elevation inferred from FABDEM",
                         taper=(12, 8), crown=0.013))
    spur = road("way/423471649")[:2]  # upper road junction to the edge of the lower Woojungwon drive
    current = Conditioner(mods)
    ends = [current(*pt, dtm_raw.sample(*pt)) for pt in spur]
    mods.append(_profile("woojungwon-junction", spur, [(0, ends[0]), (7, ends[0] - 0.03),
                         (26, ends[0] - 3.1), (49, ends[1] + 0.8), (60, ends[1])], 3.2, 5.0,
                         "Ramp between the boulevard and Woojungwon from the aerial panorama and parking approach photos",
                         taper=(7, 7), crown=0.012))
    ends = [current(*pt, dtm_raw.sample(*pt)) + lift for pt, lift in zip((TURF_STAIR[0], TURF_STAIR[-1]), (0.12, 0.04))]
    mods.append(_profile("turf-engineering-stair", TURF_STAIR, [(0, ends[0]), (29, ends[1])], 1.65, 3.0,
                         "Stair route registered to KHU aerial panorama 4680; rise estimated from adjoining terrain", taper=(2, 2)))
    stair_lower = current(*WOOJUNGWON_STAIR[0], dtm_raw.sample(*WOOJUNGWON_STAIR[0]))
    walk_m = _to_m(LineString(WOOJUNGWON_WALK))
    stations = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.asarray(walk_m.coords), axis=0), axis=1))]
    walk_z = [current(*p, dtm_raw.sample(*p)) for p in WOOJUNGWON_WALK]
    walk_z[1:3] = [stair_lower, stair_lower + 2.5]
    mods.append(_profile("woojungwon-foreign-languages-walk", WOOJUNGWON_WALK, list(zip(stations, walk_z)),
                         WOOJUNGWON_STAIR_W / 2, 2.5,
                         "Woojungwon lot stair in KHU panorama 4733 and the university barrier-free map; alignment and rise estimated",
                         taper=(2, 4)))
    return mods


class Conditioner:
    """Vectorised application of the mods to DTM samples (orthometric heights)."""

    def __init__(self, mods):
        self.items = []
        for m in mods:
            if m["type"] in ("bowl", "grade", "level"):
                g = _to_m(Polygon(m["ring"]))
                reach = m["ramp_m"] if m["type"] == "grade" else 0
                w, s, e, n = g.bounds
                self.items.append((m, g, g.boundary, (w - reach, s - reach, e + reach, n + reach)))
            elif m["type"] == "platform":
                g = _to_m(unary_union([Polygon(r) for r in m["rings"]]))
                reach = 40.0 / max(m["slope"], 1e-3)          # the cut slope never needs to run further than this
                b = g.bounds
                self.items.append((m, g, g.boundary, (b[0] - reach, b[1] - reach, b[2] + reach, b[3] + reach)))
            elif m["type"] == "profile":
                g = _to_m(LineString([p[:2] for p in m["points"]]))
                w, s, e, n = g.bounds
                reach = m["width_m"] + m["ramp_m"]
                self.items.append((m, g, None, (w - reach, s - reach, e + reach, n + reach)))

    def __call__(self, lon, lat, z):
        lon = np.asarray(lon, float); lat = np.asarray(lat, float); z = np.array(z, float)
        shape_ = z.shape
        x = ((lon - 127.08) * MX).ravel(); y = ((lat - LAT_C) * MY).ravel(); zz = z.ravel()
        for m, g, bnd, (bx0, by0, bx1, by1) in self.items:
            sel = np.nonzero((x >= bx0) & (x <= bx1) & (y >= by0) & (y <= by1))[0]
            if not len(sel):
                continue
            px, py = x[sel], y[sel]
            if m["type"] == "profile":
                pts = shapely.points(px, py)
                station = shapely.line_locate_point(g, pts)
                along = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.asarray(g.coords), axis=0), axis=1))]
                d = shapely.distance(g, pts)
                left, right = m["taper_m"]
                t = np.clip(np.minimum.reduce([(m["width_m"] + m["ramp_m"] - d) / m["ramp_m"],
                                              station / left, (along[-1] - station) / right]), 0, 1)
                height = np.interp(station, along, [pt[2] for pt in m["points"]]) - np.minimum(d, m["width_m"]) * m["crown"]
                weight = t * t * (3 - 2 * t)
                zz[sel] += weight * (height - zz[sel])
                continue
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
            elif m["type"] == "platform":
                cap = np.where(ins, m["level_m"], m["level_m"] + m["slope"] * d)
                zz[sel] = np.minimum(v, cap)
            else:
                if m["type"] == "grade":
                    t = np.where(ins, 1, np.clip(1 - d / m["ramp_m"], 0, 1))
                else:
                    t = np.where(ins, np.clip(d / m["ramp_m"], 0, 1), 0)
                weight = t * t * (3 - 2 * t)
                zz[sel] = v + weight * (m["height_m"] - v)
        return zz.reshape(shape_) if shape_ else float(zz[0])


def load_conditioner():
    p = WEB_DATA / "terrain" / "terrain_mods.json"
    if not p.exists():
        return None
    mods = read_json(p).get("base", [])
    return Conditioner(mods) if mods else None


def write_surface(base, details=None):
    """Publish identical local grades and terrain overlays for the viewer."""
    from dem import load
    from build_terrain import write_overlays

    target = WEB_DATA / "terrain" / "terrain_mods.json"
    pads = [{**pad, "id": oid} for oid, model in (details or {}).get("photo_buildings", {}).items()
            for pad in model.get("terrain_mods", [])]
    mods = base + pads
    write_json(target, {
        "note": "Estimated local grades on top of FABDEM. Building geometry is anchored to the base grades; "
                "the viewer and overlays also include the photo-derived entrance aprons.",
        "base": base, "mods": mods}, compact=True)
    dtm_raw, _ = load(raw=True)
    w, s, e, n = (FEATURE_BBOX[k] for k in ("west", "south", "east", "north"))
    cols, rows = round((e - w) * MX / 2.5) + 1, round((n - s) * MY / 2.5) + 1
    x, y = np.meshgrid(np.linspace(w, e, cols), np.linspace(n, s, rows))
    z = Conditioner(mods)(x, y, dtm_raw.sample(x, y))
    meta_p = target.with_name("dtm.json")
    meta = read_json(meta_p)
    meta["overlays"] = write_overlays(z, w, s, e, n, (e - w) * MX / (cols - 1),
                                     (n - s) * MY / (rows - 1), target.parent, width=cols)
    meta["overlays"]["conditioned"] = True
    write_json(meta_p, meta)


def main():
    from dem import load
    dtm_raw, _ = load(raw=True)
    base = build(dtm_raw)
    write_surface(base)
    for mod in base:
        print("terrain grade", mod["type"], mod["id"], mod.get("height_m", mod.get("field_m", mod.get("level_m"))))


if __name__ == "__main__":
    main()
