"""Ground surfaces + markings for the university grounds (draped on the terrain in the viewer).

Everything is placed on real OSM geometry (campus only):
  roads/paths  : surface strips at their OSM (or class-default) width; centre lines on through roads
  steps        : OSM highway=steps drawn with tread stripes every 0.4 m
  sports       : leisure=pitch/stadium/track filled by surface type; soccer, tennis and basketball line
                 markings laid out to standard dimensions inside each pitch's minimum rotated rectangle
  parking      : amenity=parking asphalt + 2.5 m stall lines along the long edges
  plazas/grass : place=square, landuse=grass/flowerbed ...
Markings are standard-dimension layouts fitted to the mapped outline (illustrative, not surveyed paint).
Output: web/data/ground.json
"""
from __future__ import annotations

import math

from shapely.affinity import affine_transform
from shapely.geometry import LineString, MultiLineString, Point, Polygon, shape
from shapely.ops import substring

from common import WEB_DATA, read_json, write_json

LAT_C = 37.2424
MX = 111_320.0 * math.cos(math.radians(LAT_C))
MY = 110_950.0
O = (127.0818, 37.2427)
TO_M = [MX, 0, 0, MY, -O[0] * MX, -O[1] * MY]
TO_D = [1 / MX, 0, 0, 1 / MY, O[0], O[1]]


def m(g):
    return affine_transform(g, TO_M)


def d(g):
    return affine_transform(g, TO_D)


def coords(g, nd=7):
    return [[round(x, nd), round(y, nd)] for x, y in g.coords]


fills, lines = [], []


def add_fill(poly_m, kind, src):
    poly = d(poly_m)
    for p in ([poly] if poly.geom_type == "Polygon" else getattr(poly, "geoms", [])):
        if p.geom_type == "Polygon" and not p.is_empty:
            fills.append({"k": kind, "src": src, "c": [coords(p.exterior)] + [coords(r) for r in p.interiors]})


def add_line(line_m, kind, w, src=None):
    if line_m.is_empty:
        return
    parts = [line_m] if line_m.geom_type == "LineString" else [g for g in getattr(line_m, "geoms", []) if g.geom_type == "LineString"]
    for ln in parts:
        if ln.length < 0.05:
            continue
        e = {"k": kind, "w": round(w, 2), "c": coords(d(ln))}
        if src:
            e["src"] = src
        lines.append(e)


def rect_frame(poly_m):
    """centre, unit long axis, unit short axis, long length, short length of the min rotated rectangle."""
    r = list(poly_m.minimum_rotated_rectangle.exterior.coords)
    e0 = (r[1][0] - r[0][0], r[1][1] - r[0][1])
    e1 = (r[2][0] - r[1][0], r[2][1] - r[1][1])
    l0, l1 = math.hypot(*e0), math.hypot(*e1)
    if l0 < l1:
        e0, e1, l0, l1 = e1, e0, l1, l0
    c = poly_m.minimum_rotated_rectangle.centroid
    return (c.x, c.y), (e0[0] / l0, e0[1] / l0), (e1[0] / l1, e1[1] / l1), l0, l1


def F(c, ua, ub):
    """local field coords (x along long axis, y along short axis) -> metres"""
    return lambda x, y: (c[0] + ua[0] * x + ub[0] * y, c[1] + ua[1] * x + ub[1] * y)


def rect_line(P, x0, y0, x1, y1):
    return LineString([P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1), P(x0, y0)])


def arc_line(P, cx, cy, r, a0, a1, n=36):
    return LineString([P(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)])


def soccer(poly_m, src):
    c, ua, ub, L, W = rect_frame(poly_m)
    P = F(c, ua, ub)
    hl, hw = L / 2 - 1.5, W / 2 - 1.5
    s = min(1.0, (2 * hl) / 105.0, (2 * hw) / 68.0) if hl > 0 and hw > 0 else 1.0
    add_line(rect_line(P, -hl, -hw, hl, hw), "paint", 0.14, src)
    add_line(LineString([P(0, -hw), P(0, hw)]), "paint", 0.14)
    add_line(arc_line(P, 0, 0, 9.15 * s, 0, 2 * math.pi, 48), "paint", 0.14)
    for sg in (-1, 1):
        x = sg * hl
        add_line(LineString([P(x, -20.15 * s), P(x - sg * 16.5 * s, -20.15 * s), P(x - sg * 16.5 * s, 20.15 * s), P(x, 20.15 * s)]), "paint", 0.14)
        add_line(LineString([P(x, -9.16 * s), P(x - sg * 5.5 * s, -9.16 * s), P(x - sg * 5.5 * s, 9.16 * s), P(x, 9.16 * s)]), "paint", 0.14)
        a = math.acos(min(1.0, 5.5 / 9.15))
        add_line(arc_line(P, x - sg * 11 * s, 0, 9.15 * s, (math.pi if sg > 0 else 0) - a, (math.pi if sg > 0 else 0) + a, 16), "paint", 0.14)


def tennis(poly_m, src):
    c, ua, ub, L, W = rect_frame(poly_m)
    n = max(1, int((W + 3) // 17.0))
    pitch = W / n
    for k in range(n):
        yc = -W / 2 + pitch * (k + 0.5)
        P = F(c, ua, ub)
        Q = lambda x, y, yc=yc: P(x, y + yc)
        add_fill(Polygon([Q(-15.5, -8.0), Q(15.5, -8.0), Q(15.5, 8.0), Q(-15.5, 8.0)]).intersection(poly_m.buffer(0.5)), "court_out", src)
        add_fill(Polygon([Q(-11.885, -5.485), Q(11.885, -5.485), Q(11.885, 5.485), Q(-11.885, 5.485)]), "court_in", src)
        add_line(rect_line(Q, -11.885, -5.485, 11.885, 5.485), "paint", 0.08)
        for y in (-4.115, 4.115):
            add_line(LineString([Q(-11.885, y), Q(11.885, y)]), "paint", 0.08)
        for x in (-6.4, 6.4):
            add_line(LineString([Q(x, -4.115), Q(x, 4.115)]), "paint", 0.08)
        add_line(LineString([Q(-6.4, 0), Q(6.4, 0)]), "paint", 0.08)
        add_line(LineString([Q(0, -6.0), Q(0, 6.0)]), "net", 0.12)


def basketball(poly_m, src):
    c, ua, ub, L, W = rect_frame(poly_m)
    P = F(c, ua, ub)
    s = min(1.0, (L - 2) / 28.0, (W - 2) / 15.0)
    hl, hw = 14 * s, 7.5 * s
    add_fill(Polygon([P(-hl, -hw), P(hl, -hw), P(hl, hw), P(-hl, hw)]), "court_bb", src)
    add_line(rect_line(P, -hl, -hw, hl, hw), "paint", 0.08)
    add_line(LineString([P(0, -hw), P(0, hw)]), "paint", 0.08)
    add_line(arc_line(P, 0, 0, 1.8 * s, 0, 2 * math.pi, 24), "paint", 0.08)
    for sg in (-1, 1):
        x = sg * hl
        add_line(LineString([P(x, -2.45 * s), P(x - sg * 5.8 * s, -2.45 * s), P(x - sg * 5.8 * s, 2.45 * s), P(x, 2.45 * s)]), "paint", 0.08)
        add_line(arc_line(P, x - sg * 1.575 * s, 0, 6.75 * s, (math.pi if sg > 0 else 0) - 1.35, (math.pi if sg > 0 else 0) + 1.35, 24), "paint", 0.08)


def parking(poly_m, src):
    add_fill(poly_m, "parking", src)
    c, ua, ub, L, W = rect_frame(poly_m)
    if L < 8 or W < 4.5:
        return
    P = F(c, ua, ub)
    inner = poly_m.buffer(-0.3)
    rows = [(-W / 2, 1)] + ([(W / 2, -1)] if W >= 11 else [])
    for y0, sg in rows:
        x = -L / 2 + 1.0
        while x < L / 2 - 1.0:
            add_line(LineString([P(x, y0), P(x, y0 + sg * 5.0)]).intersection(inner), "stall", 0.1)
            x += 2.5
        add_line(LineString([P(-L / 2, y0 + sg * 5.0), P(L / 2, y0 + sg * 5.0)]).intersection(inner), "stall", 0.1)


def dashed(ln, dash, gap):
    out, s, L = [], 0.0, ln.length
    while s < L:
        out.append(substring(ln, s, min(L, s + dash)))
        s += dash + gap
    return MultiLineString(out) if out else ln


def main():
    roads = read_json(WEB_DATA / "roads.geojson")["features"]
    land = read_json(WEB_DATA / "landcover.geojson")["features"]
    clip = read_json(WEB_DATA / "campus_details.json")["clip"]
    clip_m = m(Polygon(clip["rings"][0]))
    surf = {"trunk": "asphalt", "primary": "asphalt", "secondary": "asphalt", "tertiary": "asphalt", "unclassified": "asphalt",
            "residential": "asphalt", "service": "asphalt", "living_street": "asphalt", "track": "gravel",
            "pedestrian": "paving", "footway": "paving", "cycleway": "asphalt_red", "path": "path", "steps": "steps"}
    counts = {}
    # ---- landcover-derived fills (campus only) ----
    for f in land:
        p = f["properties"]
        if not p["in_campus"]:
            continue
        g = m(shape(f["geometry"])).intersection(clip_m)
        if g.is_empty:
            continue
        k, src = p["class"], p["id"]
        sport = (p.get("sport") or "").lower()
        if k == "sport":
            if "soccer" in sport:
                add_fill(g, "turf", src); soccer(g, src)
            elif "tennis" in sport:
                add_fill(g, "court_surround", src); tennis(g, src)
            elif "basketball" in sport:
                add_fill(g, "court_surround", src); basketball(g, src)
            elif "baseball" in sport:
                add_fill(g, "dirt", src)
            else:
                add_fill(g, "dirt", src)
        elif k == "parking":
            parking(g, src)
        elif k in ("plaza",):
            add_fill(g, "plaza", src)
        elif k in ("grass", "park", "golf"):
            add_fill(g, "grass", src)
        elif k in ("garden",):
            add_fill(g, "garden", src)
        elif k in ("forest", "scrub"):
            add_fill(g, "forest", src)   # forest floor, shown in the rendered (no-imagery) mode
        else:
            continue
        counts[k] = counts.get(k, 0) + 1
    # ---- roads, paths, steps ----
    for f in roads:
        p = f["properties"]
        if not p["in_campus"] or p.get("tunnel") in ("yes", "building_passage"):
            continue
        g = m(shape(f["geometry"])).intersection(clip_m)
        if g.is_empty:
            continue
        hw_ = p["highway"]
        if f["geometry"]["type"] == "Polygon":
            add_fill(g, "paving", p["id"]); continue
        kind = surf.get(hw_, "paving")
        w = max(1.2, p["width_m"])
        add_line(g, "road_" + kind, w, p["id"])
        for ln in ([g] if g.geom_type == "LineString" else getattr(g, "geoms", [])):
            if ln.geom_type != "LineString":
                continue
            if hw_ in ("tertiary", "secondary", "primary", "unclassified", "residential"):
                add_line(ln, "centre_yellow", 0.15)
            elif hw_ == "service" and w >= 5:
                add_line(dashed(ln, 3.0, 4.0), "centre_white", 0.12)
            if hw_ == "steps":
                s = 0.2
                while s < ln.length:
                    a = ln.interpolate(s); b = ln.interpolate(min(ln.length, s + 0.05))
                    dx, dy = b.x - a.x, b.y - a.y
                    L = math.hypot(dx, dy) or 1
                    nx, ny = -dy / L * w / 2, dx / L * w / 2
                    add_line(LineString([(a.x - nx, a.y - ny), (a.x + nx, a.y + ny)]), "tread", 0.07)
                    s += 0.4
        counts["road:" + kind] = counts.get("road:" + kind, 0) + 1
    # forest floor from the canopy-height model (Copernicus DSM - FABDEM >= 3.5 m), 10 m cells, minus built/sport areas
    import numpy as np
    from shapely.geometry import box as _box
    from shapely.ops import unary_union as _uu
    from dem import load as _load
    dtm, dsm = _load()
    B = read_json(WEB_DATA / "buildings.geojson")["features"]
    blocked = _uu([m(shape(f["geometry"])).buffer(6) for f in B if f["properties"]["in_campus"]] +
                  [m(shape(f["geometry"])) for f in land if f["properties"]["in_campus"] and f["properties"]["class"] in ("sport", "parking", "plaza", "water")])
    x0, y0, x1, y1 = clip_m.bounds
    cells = []
    for x in np.arange(x0, x1, 10.0):
        for y in np.arange(y0, y1, 10.0):
            lon, lat = O[0] + (x + 5) / MX, O[1] + (y + 5) / MY
            if float(dsm.sample(lon, lat) - dtm.sample(lon, lat)) >= 3.5:
                cells.append(_box(x, y, x + 10, y + 10))
    canopy = _uu(cells).buffer(4).buffer(-4).simplify(2.0).intersection(clip_m).difference(blocked)
    add_fill(canopy, "forest", "Copernicus DSM - FABDEM canopy model")
    counts["canopy_ha"] = round(canopy.area / 1e4, 1)
    order = {"forest": -1, "grass": 0, "garden": 1, "plaza": 2, "paving": 2, "dirt": 3, "turf": 3, "court_surround": 3, "court_out": 4,
             "court_in": 5, "court_bb": 5, "parking": 3}
    fills.sort(key=lambda e: order.get(e["k"], 2))
    write_json(WEB_DATA / "ground.json", {
        "note": "Surfaces on OSM geometry (campus only). Sports markings and parking stall lines are standard-dimension layouts fitted to each mapped outline - illustrative, not surveyed paint.",
        "fills": fills, "lines": lines}, compact=True)
    print("fills", len(fills), "lines", len(lines), counts)


if __name__ == "__main__":
    main()
