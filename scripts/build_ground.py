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
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box, shape
from shapely.geometry.polygon import orient
from shapely.ops import substring, unary_union

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


# ---- photo-derived per-feature details (estimated; see docs/MODEL_PROGRESS.md) ----
PLAZA_SURFACE = {"way/1385685748": "brick"}     # 05: terracotta brick around the courts
BB_SCHEME = {"way/585696427": "green", "way/585696429": "green"}          # 05: mint courts, terracotta keys
ENGINEERING_TERRACE = "way/1385685749"
TERRACE_BEDS = {"way/1385685750", "way/1385685751", "way/1385685752"}
SOCCER_SPECS = {
    # 05 인조잔디구장: striped turf, centre logo, ball-stop nets and the Engineering-side terrace
    "way/326869014": {"stripes": 5.0, "logo": "KHU", "net_h": 6.0, "courts": "way/585696427",
                      "terrace": ENGINEERING_TERRACE},
}
STROKES = {  # letter strokes in a 0.9 x 1.6 box
    "K": [[(0, 0), (0, 1.6)], [(0.9, 1.6), (0, 0.75), (0.9, 0)]],
    "H": [[(0, 0), (0, 1.6)], [(0.9, 0), (0.9, 1.6)], [(0, 0.8), (0.9, 0.8)]],
    "U": [[(0, 1.6), (0, 0.4), (0.15, 0.1), (0.45, 0), (0.75, 0.1), (0.9, 0.4), (0.9, 1.6)]],
}
OBJ_EXTRA = []   # 3D ground objects produced while laying out surfaces (nets and terraces)
TERRAIN_MODS = []   # per-model "level" terrain mods (photo_buildings[...].terrain_mods), merged into terrain_mods.json
STADIUM_SPECS = {
    # 14 대운동장: concrete terrace steps all round the oval, sand running track, natural-grass field with a low
    # green fence, goals at both ends, railing along the rim (13 reference photos, 2017-2025). Draped on the
    # DTM (the 30 m DTM cannot hold a level field; 3D steps would float or bury).
    "way/455725379": {"track": 9.0, "fence_h": 1.2, "rail_h": 1.1, "goals": True},
}
from terrain_mods import BOWLS as _BOWLS   # stands/ramp/steps/rise: the same numbers carve the terrain
for _k, _v in _BOWLS.items():
    STADIUM_SPECS.setdefault(_k, {}).update(_v)


def _segments(ring_line, tol=1.5):
    """Straight pieces of a (simplified) ring, as [[x,y],[x,y]] pairs in metres."""
    pts = list(ring_line.simplify(tol).coords)
    return [LineString([pts[i], pts[i + 1]]) for i in range(len(pts) - 1) if math.dist(pts[i], pts[i + 1]) > 0.5]


def stadium(poly_m, src):
    sp = STADIUM_SPECS[src]
    inner = poly_m.buffer(-sp["stands"])
    field = poly_m.buffer(-(sp["stands"] + sp["track"]))
    add_fill(poly_m.difference(inner), "terrace", src)
    tread = (sp["stands"] - sp["ramp"]) / sp["steps"]
    for i in range(0, sp["steps"]):
        ring = poly_m.buffer(-(sp["ramp"] + i * tread))
        if not ring.is_empty and ring.geom_type == "Polygon":
            add_line(LineString(ring.exterior.coords), "tread", 0.1)
    add_fill(inner.difference(field), "sand", src)
    add_fill(field, "field", src)
    for seg in _segments(field.exterior):
        OBJ_EXTRA.append({"k": "net", "id": src, "c": coords(d(seg)), "h": sp["fence_h"]})
    for seg in _segments(poly_m.buffer(-sp["ramp"] + 0.3).exterior):
        OBJ_EXTRA.append({"k": "net", "id": src, "c": coords(d(seg)), "h": sp["rail_h"]})
    if sp["goals"]:
        c, ua, ub, L, W = rect_frame(field)
        for sg in (-1, 1):
            gx, gy = c[0] + ua[0] * sg * (L / 2 - 1.0), c[1] + ua[1] * sg * (L / 2 - 1.0)
            lon, lat = d(Point(gx, gy)).coords[0]
            OBJ_EXTRA.append({"k": "goal", "id": src, "p": [round(lon, 7), round(lat, 7)], "axis": [round(ub[0], 4), round(ub[1], 4)]})


def engineering_terrace(land, oid, field_c, ua, ub, field_width):
    """Terraced stairs from the mapped square and planters on the Engineering side of the pitch."""
    # s runs south along the pitch, t runs uphill from its east edge towards Engineering.
    origin = F(field_c, ua, ub)(0, -field_width / 2)
    ax, ay = -ua[0], -ua[1]
    to_local = [ax, ay, -ay, ax, -(ax * origin[0] + ay * origin[1]), ay * origin[0] - ax * origin[1]]
    allow = TERRACE_BEDS | {oid}
    mapped = {f["properties"]["id"]: affine_transform(m(shape(f["geometry"])), to_local)
              for f in land if f["properties"]["id"] in allow}
    if oid not in mapped:
        return
    stairs = mapped[oid]
    gardens = [g for key, g in mapped.items() if key in TERRACE_BEDS]
    pockets = list(stairs.convex_hull.difference(stairs).geoms)
    left, toe, right, crest = stairs.bounds
    surfaces, trees = [], []

    def surface(kind, polygon, sample, lift):
        # Subdivide long treads along the contour so they follow the DTM crossfall.
        if polygon.is_empty:
            return
        xmin, ymin, xmax, ymax = polygon.bounds
        span = math.ceil((xmax - xmin) / 6.0)
        for i in range(span):
            a, b = xmin + (xmax - xmin) * i / span, xmin + (xmax - xmin) * (i + 1) / span
            section = polygon.intersection(box(a, ymin - 1, b, ymax + 1))
            for piece in ([section] if section.geom_type == "Polygon" else section.geoms):
                if piece.geom_type != "Polygon" or piece.area < 0.015:
                    continue
                piece = orient(piece)
                surfaces.append({"k": kind, "t": round(sample, 3) if sample is not None else None, "lift": lift,
                                 "c": [coords(r, 3) for r in (piece.exterior, *piece.interiors)]})

    def inset(polygon, kind, sample, lift, border=0.26):
        inside = polygon.buffer(-border, join_style=2)
        surface("rim", polygon.difference(inside), sample, lift)
        surface(kind, inside, sample, lift - 0.07)

    # Thin pitch-side landing and two low planted inserts visible near the tapered ends.
    foot = Polygon([(-23.6, 0.72), (24.7, 0.72), (26.6, toe + 0.2), (-24.6, toe + 0.2)]).difference(stairs)
    lower_beds = [Polygon([(s - 2.1, 1.05), (s + 2.1, 1.05), (s + 3.45, toe - 0.23),
                           (s - 3.45, toe - 0.23)]) for s in (-20.5, 21.5)]
    surface("landing", foot.difference(unary_union(lower_beds)), toe + 0.15, 0.09)
    for bed in lower_beds:
        inset(bed, "grass", toe + 0.15, 0.25)

    # Paired small triangular stone inserts alternate with the three mapped planted diamonds.
    accents = [Polygon([(s - 2.9, toe + 1.8), (s + 2.9, toe + 1.8), (s, toe + 5.05)])
               for s in (-10.25, 10.5)]
    outline = list(stairs.convex_hull.exterior.coords)
    side_edges = [LineString([a, b]).buffer(0.27, cap_style=2)
                  for a, b in zip(outline, outline[1:]) if abs(a[1] - b[1]) > 2]
    edging = stairs.intersection(unary_union(side_edges))
    surface("rim", edging, None, 0.49)
    stepped = stairs.difference(unary_union([*gardens, *accents, edging]))
    rows = 9
    for i in range(rows):
        down = toe + (crest - toe) * i / rows
        up = toe + (crest - toe) * (i + 1) / rows
        nose = down + 0.12
        surface("nosing", stepped.intersection(box(left, down, right, nose)), up, 0.12)
        surface("tread", stepped.intersection(box(left, nose, right, up)), up, 0.12)
    for bed in gardens:
        inset(bed, "grass", bed.bounds[3] + 0.3, 0.24)
    for accent in accents:
        inset(accent, "stone", accent.bounds[3], 0.22)

    # The upper outline has three triangular notches. Their raised walls hold tree pockets.
    for pocket in pockets:
        sample = pocket.bounds[3]
        inset(pocket, "soil", sample, 0.28, border=0.35)
        p = pocket.centroid
        trees.append({"p": [round(p.x, 3), round(p.y, 3)], "t": round(sample, 3)})
    upper_walk = box(left + 0.6, crest - 1.7, right - 0.6, crest + 3.55).difference(stairs.convex_hull)
    surface("brick", upper_walk, None, 0.13)

    OBJ_EXTRA.append({"k": "terrace", "id": oid, "p": coords(d(Point(origin)))[0],
                      "axis": [round(ax, 8), round(ay, 8)], "surfaces": surfaces, "trees": trees,
                      "source": "OSM terrace and three planter outlines. Treads, additional inserts and landings estimated from KHU aerial and ground photographs."})


def soccer(poly_m, src, land=None):
    c, ua, ub, L, W = rect_frame(poly_m)
    spec = SOCCER_SPECS.get(src)
    if spec and land is not None:
        cg = next((m(shape(f["geometry"])).centroid for f in land if f["properties"]["id"] == spec["courts"]), None)
        if cg is not None and ((cg.x - c[0]) * ub[0] + (cg.y - c[1]) * ub[1]) < 0:
            ub = (-ub[0], -ub[1])                              # +y (short axis) points to the courts
        if ua[0] * ub[1] - ua[1] * ub[0] < 0:
            ua = (-ua[0], -ua[1])                              # right-handed: logo letters must not be mirrored
    P = F(c, ua, ub)
    if spec:
        k = 0
        x = -L / 2
        while x < L / 2:
            if k % 2:
                add_fill(Polygon([P(x, -W / 2), P(x + spec["stripes"], -W / 2), P(x + spec["stripes"], W / 2), P(x, W / 2)]).intersection(poly_m), "turf2", src)
            x += spec["stripes"]; k += 1
        # logo: letters upright for a viewer on the stand side (-y), text along the long axis
        sc, gap = 4.5, 1.3      # letters ~7.2 m tall, text ~15 m: fills the 18.3 m centre circle as in the aerial photo
        tw = len(spec["logo"]) * 0.9 * sc + (len(spec["logo"]) - 1) * gap
        for i, ch in enumerate(spec["logo"]):
            x0 = -tw / 2 + i * (0.9 * sc + gap)
            for stroke in STROKES[ch]:
                add_line(LineString([P(x0 + u * sc, -0.8 * sc + v * sc) for u, v in stroke]), "paint", 0.55)
        # Nets on the two ends and the courts-side long edge.
        hl, hw = L / 2 - 0.3, W / 2 - 0.3
        for seg in ([P(-hl, -hw), P(-hl, hw)], [P(-hl, hw), P(hl, hw)], [P(hl, hw), P(hl, -hw)]):
            OBJ_EXTRA.append({"k": "net", "id": src, "c": coords(d(LineString(seg))), "h": spec["net_h"]})
        if land is not None:
            engineering_terrace(land, spec["terrace"], c, ua, ub, W)
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
    green = BB_SCHEME.get(src) == "green"
    add_fill(Polygon([P(-hl, -hw), P(hl, -hw), P(hl, hw), P(-hl, hw)]), "court_bbg" if green else "court_bb", src)
    if green:   # terracotta keys and centre circle (photographs)
        add_fill(Point(P(0, 0)).buffer(1.8 * s, 24), "court_key", src)
        for sg in (-1, 1):
            x = sg * hl
            add_fill(Polygon([P(x, -2.45 * s), P(x - sg * 5.8 * s, -2.45 * s), P(x - sg * 5.8 * s, 2.45 * s), P(x, 2.45 * s)]).union(
                Point(P(x - sg * 5.8 * s, 0)).buffer(1.8 * s, 24)), "court_key", src)
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
    details = read_json(WEB_DATA / "campus_details.json")
    clip = details["clip"]
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
                add_fill(g, "turf", src); soccer(g, src, land)
            elif "tennis" in sport:
                add_fill(g, "court_surround", src); tennis(g, src)
            elif "basketball" in sport:
                add_fill(g, "court_surround", src); basketball(g, src)
            elif src in STADIUM_SPECS:
                stadium(g, src)
            elif "baseball" in sport:
                add_fill(g, "dirt", src)
            else:
                add_fill(g, "dirt", src)
        elif k == "parking":
            parking(g, src)
        elif k in ("plaza",):
            add_fill(g, PLAZA_SURFACE.get(src, "plaza"), src)
        elif k in ("grass", "park", "golf"):
            add_fill(g, "grass", src)
        elif k in ("garden",):
            add_fill(g, "garden", src)
        elif k == "water":
            add_fill(g, "water", src)
        elif k in ("forest", "scrub"):
            add_fill(g, "forest", src)   # forest floor, shown in the rendered (no-imagery) mode
        else:
            continue
        counts[k] = counts.get(k, 0) + 1
    unmarked_areas = []
    for oid, model in details.get("photo_buildings", {}).items():
        for surface in model.get("pavement", []):
            outer, *holes = surface["rings"]
            g = m(Polygon(outer, holes)).intersection(clip_m)
            add_fill(g, surface["kind"], oid)
            if surface.get("unmarked"):
                unmarked_areas.append(g)
        TERRAIN_MODS.extend({**mod, "id": oid} for mod in model.get("terrain_mods", []))
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
            elif hw_ == "service" and w >= 6 and p.get("service") != "parking_aisle" and p.get("oneway") != "yes":
                for off in (-0.14, 0.14):          # double yellow centre line (campus road photos)
                    cl = ln.offset_curve(off)
                    if not cl.is_empty:
                        add_line(cl, "centre_yellow", 0.12)
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
    sidewalks_and_crossings(roads, land, clip_m)
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
    # Lines -> metre-width polygons. (Cesium GroundPolylineGeometry widths are in screen PIXELS, so roads were
    # hairlines at every zoom and 0.14 m paint was invisible.) Roads keep their OSM/class width.
    LINE_KIND = {"road_asphalt": "asphalt", "road_paving": "paving", "road_gravel": "gravel", "road_path": "path",
                 "road_steps": "steps", "road_asphalt_red": "asphalt_red", "centre_yellow": "line_yellow",
                 "centre_white": "line_white", "paint": "line_white", "net": "line_dark", "stall": "line_white", "tread": "tread"}
    unmarked = unary_union(unmarked_areas)
    for l in lines:
        k2 = LINE_KIND.get(l["k"])
        if not k2 or len(l["c"]) < 2:
            continue
        road = l["k"].startswith("road_")
        g = m(LineString(l["c"])).buffer(l["w"] / 2, cap_style=1 if road else 2, join_style=1 if road else 2)
        if k2 == "line_yellow":
            g = g.difference(unmarked)
        if not g.is_empty:
            add_fill(g, k2, l.get("src") or "marking")
    lines.clear()
    # Overlapping ground fills inside one GroundPrimitive have no defined draw order (a park polygon could
    # hide the plaza and flowerbeds inside it), so make them disjoint: every fill minus all higher-priority fills.
    prio = {"forest": 0, "grass": 1, "plaza": 2, "brick": 2, "paving": 3, "parking": 3, "dirt": 4, "turf": 4, "court_surround": 4,
            "terrace": 4.2, "sand": 4.3, "field": 4.4, "turf2": 4.5, "garden": 5.45, "court_out": 6, "court_in": 7, "court_bb": 7, "court_bbg": 7, "court_key": 7.5, "water": 8,
            "path": 5.2, "gravel": 5.3, "sidewalk": 5.35, "kerb": 5.36, "paving": 5.4, "asphalt": 5.5, "asphalt_red": 5.6, "steps": 5.7,
            "tread": 9, "line_dark": 9.1, "line_yellow": 9.2, "line_white": 9.3}
    fills.sort(key=lambda e: -prio.get(e["k"], 2))
    taken, disjoint = None, []
    for e in fills:
        g = m(Polygon(e["c"][0], e["c"][1:])).buffer(0)
        part = g if taken is None else g.difference(taken)
        taken = g if taken is None else taken.union(g)
        for q in ([part] if part.geom_type == "Polygon" else [x for x in getattr(part, "geoms", []) if x.geom_type == "Polygon"]):
            q = q.simplify(0.01)
            if q.area >= 0.5:
                dq = d(q)
                disjoint.append({**e, "c": [coords(dq.exterior)] + [coords(r) for r in dq.interiors]})
    fills[:] = sorted(disjoint, key=lambda e: prio.get(e["k"], 2))
    objects = ground_objects(land) + OBJ_EXTRA + pin_landmarks(roads)
    # terrain_mods.json: base mods from terrain_mods.py (sunken stadium, levelled sites) + per-model level mods
    tm_path = WEB_DATA / "terrain" / "terrain_mods.json"
    tm = read_json(tm_path) if tm_path.exists() else {}
    write_json(tm_path, {**tm, "mods": list(tm.get("base", [])) + TERRAIN_MODS}, compact=True)
    write_json(WEB_DATA / "ground.json", {
        "note": "Surfaces on OSM geometry (campus only), made disjoint by priority. Sports markings and parking stall lines are standard-dimension layouts fitted to each mapped outline - illustrative, not surveyed paint. 'objects' are 3D ground details (fountains, hedges, planters) on OSM outlines; their heights and forms are estimated from reference photographs.",
        "fills": fills, "lines": lines, "objects": objects}, compact=True)
    print("fills", len(fills), "lines", len(lines), "objects", len(objects), counts)


# ---------------------------------------------------------------- sidewalks, kerbs, zebra crossings
SIDEWALK_W, KERB_W = 2.5, 0.2   # estimated from the campus road photos (red-brown walks behind a granite kerb)


def _lines(g):
    return [g] if g.geom_type == "LineString" else [x for x in getattr(g, "geoms", []) if x.geom_type == "LineString"]


def sidewalks_and_crossings(roads, land, clip_m):
    """Sidewalks on both sides of campus through-roads (OSM maps almost none), skipped where a mapped
    footway already runs alongside; clipped off buildings, pitches, water and parking. Zebra crossings at
    OSM highway=crossing nodes. Illustrative layout on OSM centre lines (widths estimated)."""
    import json as _json
    from shapely.ops import unary_union as _uu
    B = read_json(WEB_DATA / "buildings.geojson")["features"]
    walk_ways, walk_lines, drive, drive_polys = [], [], [], []
    for f in roads:
        p = f["properties"]
        if not p["in_campus"] or p.get("tunnel") in ("yes", "building_passage"):
            continue
        g = m(shape(f["geometry"])).intersection(clip_m)
        if g.is_empty:
            continue
        if f["geometry"]["type"] == "Polygon":
            walk_ways.append(g.boundary)              # pedestrian areas count as existing walks
        elif p["highway"] in ("footway", "pedestrian", "path", "steps", "cycleway"):
            walk_ways.append(g)
            walk_lines.extend(_lines(g))
        elif p["highway"] in ("service", "tertiary", "secondary", "residential", "unclassified"):
            drive.append((p, g))
            drive_polys.append(g.buffer(p["width_m"] / 2, cap_style=2))
    walk_u = _uu(walk_ways).buffer(3.5) if walk_ways else None
    blocked = _uu([m(shape(f["geometry"])).buffer(0.3) for f in B if f["properties"]["in_campus"]] +
                  [m(shape(f["geometry"])) for f in land if f["properties"]["in_campus"] and f["properties"]["class"] in ("sport", "water", "parking")])
    roads_u = _uu(drive_polys)
    n_sw = 0
    for p, g in drive:
        if p.get("service") in ("parking_aisle", "driveway"):
            continue
        w = p["width_m"]
        own = g.buffer(w / 2 + 0.05, cap_style=2)
        others = roads_u.difference(own).buffer(0.3)
        for ln in _lines(g):
            if ln.length < 20:
                continue
            for side in (-1, 1):
                edge = ln.offset_curve(side * (w / 2 + KERB_W / 2))
                mid = ln.offset_curve(side * (w / 2 + KERB_W + SIDEWALK_W / 2))
                if edge.is_empty or mid.is_empty:
                    continue
                if walk_u is not None and mid.intersection(walk_u).length > 0.4 * mid.length:
                    continue                                  # a mapped footway already runs along this side
                sw = mid.buffer(SIDEWALK_W / 2, cap_style=2, join_style=2).difference(blocked).difference(roads_u)
                if sw.area < 5:
                    continue
                add_fill(sw, "sidewalk", p["id"])
                kerb = edge.difference(blocked).difference(others)
                if not kerb.is_empty:   # draped strip: 3D kerbs floated where rendered terrain differs from the DTM
                    add_fill(kerb.buffer(KERB_W / 2, cap_style=2, join_style=2), "kerb", p["id"])
                n_sw += 1
    # zebra crossings: OSM highway=crossing nodes + every point where a mapped footway/path crosses a campus
    # road (OSM has no crossing nodes inside the campus; the photos show zebras at these walk/road junctions)
    raw = _json.load(open(WEB_DATA.parent.parent / "data" / "raw" / "osm_overpass.json", encoding="utf-8"))["elements"]
    xpts = [m(Point(el["lon"], el["lat"])) for el in raw if el["type"] == "node" and el.get("tags", {}).get("highway") == "crossing"]
    for wl in walk_lines:
        for p, g in drive:
            if p.get("service") in ("parking_aisle", "driveway"):
                continue
            x = wl.intersection(g)
            xpts += [q for q in getattr(x, "geoms", [x]) if q.geom_type == "Point"]
    uniq = []
    for q in xpts:
        if all(q.distance(u) > 6 for u in uniq):
            uniq.append(q)
    n_x = 0
    for pt in uniq:
        cands = [(ln.distance(pt), p, ln) for p, g in drive for ln in _lines(g)]
        best = min(cands, key=lambda q: q[0], default=None)
        if best is None or best[0] > 1.5:
            continue
        _, p, ln = best
        s0 = ln.project(pt)
        a, b = ln.interpolate(max(0, s0 - 1)), ln.interpolate(min(ln.length, s0 + 1))
        L = math.hypot(b.x - a.x, b.y - a.y) or 1
        ux, uy = (b.x - a.x) / L, (b.y - a.y) / L          # along the road
        vx, vy = -uy, ux                                   # across the road
        hw = p["width_m"] / 2 - 0.3
        k = -hw
        while k < hw - 0.3:
            c0, c1 = k, min(hw, k + 0.5)
            add_fill(Polygon([(pt.x + vx * c0 - ux * 1.6, pt.y + vy * c0 - uy * 1.6), (pt.x + vx * c1 - ux * 1.6, pt.y + vy * c1 - uy * 1.6),
                              (pt.x + vx * c1 + ux * 1.6, pt.y + vy * c1 + uy * 1.6), (pt.x + vx * c0 + ux * 1.6, pt.y + vy * c0 + uy * 1.6)]), "line_white", "crossing")
            k += 1.0
        n_x += 1
    print("sidewalk sides", n_sw, "zebra crossings", n_x)


# ---------------------------------------------------------------- 3D ground objects (on OSM outlines)
# Photo-derived parameters per OSM feature (estimated; see docs/MODEL_PROGRESS.md)
FOUNTAIN_SPECS = {
    # 03 르네상스공원: round granite basin, blue-tiled pool, ring of jets, white obelisk inscribed 인간적인 인간사회
    # with a seated figure on the front of its pedestal (10 reference photos)
    "way/764320697": {"rim_h": 0.55, "rim_w": 0.55, "water": 0.35,
                      "centre": {"type": "obelisk", "h": 5.0, "base": 1.25, "figure": "seated", "face_towards": "way/1385683781"},
                      "jets_ring": True, "name": "르네상스공원 분수 · Renaissance Park fountain"},
}
# Point landmarks not mapped in OSM, placed at the official KHU campus-map pin (approximate position).
PIN_LANDMARKS = [
    # 11 경희공원: 7-tier stone pagoda ringed by clipped hedges (5 panoramas; its shadow sits on the pin in imagery).
    # Square hedge ring aligned with the adjacent campus road way/1224707679.
    {"k": "pagoda", "id": "khu-map-11-pagoda", "p": [127.076893925102, 37.2453837393951], "h": 5.4, "tiers": 7,
     "align_road": "way/1224707679", "hedge": 5.2, "name": "경희공원 석탑 · stone pagoda (Kyung Hee Park)",
     "source": "position: official KHU campus-map pin no. 11 (approximate); form and height estimated from 5 reference photos"},
]
# flowerbeds edged with clipped box hedges (scalloped) in the photographs
HEDGED_AREAS = ["way/455726192"]          # 03 르네상스공원 (park polygon)


def pin_landmarks(roads):
    out = []
    for o in PIN_LANDMARKS:
        o = dict(o)
        r = next((f for f in roads if f["properties"]["id"] == o.pop("align_road", None)), None)
        if r is not None:
            ln = m(shape(r["geometry"]))
            pt = m(Point(*o["p"]))
            s0 = ln.project(pt)
            a, b = ln.interpolate(max(0, s0 - 5)), ln.interpolate(min(ln.length, s0 + 5))
            L = math.hypot(b.x - a.x, b.y - a.y) or 1
            o["axis"] = [round((b.x - a.x) / L, 4), round((b.y - a.y) / L, 4)]
        out.append(o)
    return out


def ground_objects(land):
    import json as _json
    from shapely.geometry import shape as _shape
    raw = _json.load(open(WEB_DATA.parent.parent / "data" / "raw" / "osm_overpass.json", encoding="utf-8"))["elements"]
    clip = read_json(WEB_DATA / "campus_details.json")["clip"]
    clip_g = Polygon(clip["rings"][0])
    areas = {f["properties"]["id"]: _shape(f["geometry"]) for f in land if f["properties"]["id"] in HEDGED_AREAS}
    hedge_zone = None
    for g in areas.values():
        hedge_zone = g if hedge_zone is None else hedge_zone.union(g)
    objs = []
    for el in raw:
        t = el.get("tags", {})
        if el["type"] != "way" or not el.get("geometry"):
            continue
        pts = [(q["lon"], q["lat"]) for q in el["geometry"]]
        if len(pts) < 4 or pts[0] != pts[-1]:
            continue
        g = Polygon(pts)
        if not clip_g.contains(g.representative_point()):
            continue
        oid = f"way/{el['id']}"
        area = m(g).area
        if oid in FOUNTAIN_SPECS:            # (사색의 광장 fountains and the theatre pond are drawn by the landmark code)
            spec = _json.loads(_json.dumps(FOUNTAIN_SPECS[oid]))
            tgt = (spec.get("centre") or {}).pop("face_towards", None)
            if tgt:                           # centrepiece figure faces the open side of the mapped plaza
                tg = next(_shape(f["geometry"]) for f in land if f["properties"]["id"] == tgt).centroid
                v = (m(tg).x - m(g.centroid).x, m(tg).y - m(g.centroid).y)
                L = math.hypot(*v)
                spec["centre"]["facing"] = [round(v[0] / L, 4), round(v[1] / L, 4)]
            objs.append({"k": "fountain", "id": oid, "c": coords(g.exterior), **spec})
        elif t.get("man_made") == "planter":
            c = g.centroid
            objs.append({"k": "planter", "id": oid, "p": [round(c.x, 7), round(c.y, 7)], "r": round(math.sqrt(area / math.pi), 2)})
        elif t.get("landuse") == "flowerbed" and hedge_zone is not None and hedge_zone.contains(g.representative_point()):
            objs.append({"k": "hedge", "id": oid, "c": coords(g.exterior), "h": 0.6, "w": 0.55})
    return objs


if __name__ == "__main__":
    main()
