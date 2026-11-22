"""Detail inputs for the enhanced (stylised) Kyung Hee campus buildings.

Everything is derived from real data; only the *appearance* in the viewer is stylised.
  gate          : frame of the main gate (정문, OSM way/473963422) from its footprint's minimum
                  rotated rectangle; the drive-through opening = where the mapped entrance road
                  crosses the footprint.
  amphitheatre  : seating terraces of 평화노천극장 (way/474531805) = the footprint sliced by 0.9 m
                  bands of the real DTM, i.e. the seats follow the true hillside.
  observatory   : centre/radius of the circular 천문대 footprint (dome placement).
Output: web/data/campus_details.json
"""
from __future__ import annotations

import math

import numpy as np
from shapely import set_precision
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

from common import RAW, WEB_DATA, read_json, to_epsg5186, write_json
from dem import load

GATE, AMPHI, OBS = "way/473963422", "way/474531805", "way/474521125"
LIB, PLAZA = "way/474085534", "way/585696477"
LAT_C = 37.2424
MX = 111_320.0 * math.cos(math.radians(LAT_C))
MY = 110_950.0


def main():
    dtm, _ = load()
    osm_els = read_json(RAW / "osm_overpass.json")["elements"]
    B = {f["properties"]["id"]: f for f in read_json(WEB_DATA / "buildings.geojson")["features"]}
    R = read_json(WEB_DATA / "roads.geojson")["features"]
    out = {"note": "Derived from OSM footprints + FABDEM; used only for stylised detail geometry."}

    # ---------------- gate ----------------
    g = shape(B[GATE]["geometry"])
    c = g.centroid
    loc = lambda x, y: ((x - c.x) * MX, (y - c.y) * MY)  # local metres (E, N)
    from shapely.affinity import translate
    pts = [loc(x, y) for x, y in g.exterior.coords]
    from shapely.geometry import Polygon
    gl = Polygon(pts)
    rr = list(gl.minimum_rotated_rectangle.exterior.coords)
    e0 = (rr[1][0] - rr[0][0], rr[1][1] - rr[0][1])
    e1 = (rr[2][0] - rr[1][0], rr[2][1] - rr[1][1])
    long_e, short_e = (e0, e1) if math.hypot(*e0) >= math.hypot(*e1) else (e1, e0)
    L, D = math.hypot(*long_e), math.hypot(*short_e)
    ax = (long_e[0] / L, long_e[1] / L)
    # opening: where the mapped vehicle/pedestrian entrance ways cross the footprint
    spans = []
    for f in R:
        if f["properties"]["highway"] in ("service", "pedestrian", "tertiary", "residential", "unclassified") and f["geometry"]["type"] == "LineString":
            ln = shape(f["geometry"])
            if ln.intersects(g):
                ip = ln.intersection(g).centroid
                lx, ly = loc(ip.x, ip.y)
                s = lx * ax[0] + ly * ax[1]
                w = f["properties"]["width_m"]
                spans.append((s - w / 2, s + w / 2, f["properties"]["id"]))
    if spans:
        o0 = min(s[0] for s in spans) - 1.0
        o1 = max(s[1] for s in spans) + 1.0
    else:
        o0, o1 = -5.0, 5.0
    # prefer the mapped footprint structure: interior vertices on the long sides that bracket the road
    proj = sorted({round(x * ax[0] + y * ax[1], 2) for x, y in pts})
    inner = [v for v in proj if -L / 2 + 1 < v < L / 2 - 1]
    lo = [v for v in inner if v <= o0 + 1.0]
    hi = [v for v in inner if v >= o1 - 1.0]
    opening_src = "entrance road width + 1 m margins"
    if lo and hi:
        o0, o1, opening_src = max(lo), min(hi), "interior footprint vertices bracketing the mapped entrance road"
    gz = [float(dtm.sample(x, y)) for x, y in g.exterior.coords]
    out["gate"] = {
        "id": GATE, "center": [round(c.x, 7), round(c.y, 7)],
        "axis_bearing_deg": round(math.degrees(math.atan2(ax[0], ax[1])) % 180, 2),
        "axis_en": [round(ax[0], 6), round(ax[1], 6)], "length_m": round(L, 2), "depth_m": round(D, 2),
        "opening_m": [round(o0, 2), round(o1, 2)], "opening_from": [s[2] for s in spans], "opening_method": opening_src,
        "ground_min_m": round(min(gz), 2), "ground_center_m": round(float(dtm.sample(c.x, c.y)), 2),
        "height_status": "total height 22.5 m documented (guidebook); form and detail heights measured from photographs",
    }

    # ---------------- amphitheatre terraces ----------------
    a = shape(B[AMPHI]["geometry"])
    minx, miny, maxx, maxy = a.bounds
    step_m = 0.75
    xs = np.arange(minx, maxx, step_m / MX)
    ys = np.arange(miny, maxy, step_m / MY)
    gx, gy = np.meshgrid(xs, ys)
    z = dtm.sample(gx.ravel(), gy.ravel()).reshape(gx.shape)
    band = 0.9
    zq = np.floor(z / band) * band
    cells = {}
    hx, hy = step_m / MX / 2, step_m / MY / 2
    for j in range(gx.shape[0]):
        for i in range(gx.shape[1]):
            cells.setdefault(round(float(zq[j, i]), 2), []).append(box(gx[j, i] - hx, gy[j, i] - hy, gx[j, i] + hx, gy[j, i] + hy))
    tiers = []
    for lvl in sorted(cells):
        poly = unary_union(cells[lvl]).intersection(a)
        if poly.is_empty or poly.area * MX * MY < 4:
            continue
        # morphological smoothing removes the raster staircase; seats stay inside the footprint
        r = 1.2 / MX
        poly = poly.buffer(r, join_style=1).buffer(-2 * r, join_style=1).buffer(r, join_style=1).intersection(a)
        poly = poly.simplify(0.35 / MX)
        parts = [poly] if poly.geom_type == "Polygon" else [p for p in getattr(poly, "geoms", []) if p.geom_type == "Polygon"]
        for p in parts:
            if p.area * MX * MY < 4:
                continue
            m = mapping(p)
            tiers.append({"top_m": round(lvl + band, 2), "coords": [[[round(x, 7), round(y, 7)] for x, y in ring] for ring in m["coordinates"]]})
    out["amphitheatre"] = {"id": AMPHI, "band_m": band, "tiers": tiers,
                           "method": "footprint sliced into 0.9 m bands of the FABDEM surface (seats follow the real slope)"}

    # ---------------- observatory ----------------
    o = shape(B[OBS]["geometry"])
    oc = o.centroid
    r = math.sqrt(o.area * MX * MY / math.pi)
    out["observatory"] = {"id": OBS, "center": [round(oc.x, 7), round(oc.y, 7)], "footprint_radius_m": round(r, 2)}
    # ---------------- library: facade facing 사색의 광장, portico recess inside the footprint ----------------
    from shapely.geometry import Polygon as P2
    L_ = [f for f in read_json(WEB_DATA / "landcover.geojson")["features"] if f["properties"]["id"] == PLAZA]
    lib = shape(B[LIB]["geometry"])
    lc = lib.centroid
    to_l = lambda x, y: ((x - lc.x) * MX, (y - lc.y) * MY)
    to_g = lambda e, n: (lc.x + e / MX, lc.y + n / MY)
    ring = [to_l(x, y) for x, y in lib.exterior.coords]
    libm = P2(ring)
    target = shape(L_[0]["geometry"]).centroid if L_ else lc
    tx, ty = to_l(target.x, target.y)
    best = None
    ccw = libm.exterior.is_ccw
    # merge consecutive collinear edges (OSM often splits one straight facade into several edges)
    segs = []
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        if segs:
            (sx, sy), (ex, ey) = segs[-1]
            a1 = math.atan2(ey - sy, ex - sx); a2 = math.atan2(y1 - y0, x1 - x0)
            if abs((a1 - a2 + math.pi) % (2 * math.pi) - math.pi) < math.radians(3):
                segs[-1] = ((sx, sy), (x1, y1)); continue
        segs.append(((x0, y0), (x1, y1)))
    for (x0, y0), (x1, y1) in segs:
        ln = math.hypot(x1 - x0, y1 - y0)
        if ln < 30:
            continue
        dx, dy = (x1 - x0) / ln, (y1 - y0) / ln
        nx, ny = (dy, -dx) if ccw else (-dy, dx)  # outward normal
        mx_, my_ = (x0 + x1) / 2, (y0 + y1) / 2
        score = ((tx - mx_) * nx + (ty - my_) * ny) / max(1e-6, math.hypot(tx - mx_, ty - my_))
        if best is None or score > best[0]:
            best = (score, (x0, y0), (x1, y1), (dx, dy), (nx, ny), ln)
    _, a0, a1, d, nout, flen = best
    pav = round(0.115 * flen, 2)
    depth = 3.4
    q = lambda s_, t_: (a0[0] + d[0] * s_ - nout[0] * t_, a0[1] + d[1] * s_ - nout[1] * t_)
    portico = P2([q(pav, 0), q(flen - pav, 0), q(flen - pav, depth), q(pav, depth)])
    mass = libm.difference(portico.buffer(0.01, join_style=2))
    mass = max(mass.geoms, key=lambda g: g.area) if mass.geom_type == "MultiPolygon" else mass
    fg = [float(dtm.sample(*to_g(*q(s_, -2.0)))) for s_ in np.linspace(0, flen, 12)]
    foot = [float(dtm.sample(*to_g(*q(s_, -10.0)))) for s_ in np.linspace(flen * 0.3, flen * 0.7, 6)]
    out["library"] = {
        "id": LIB, "origin": [round(lc.x, 7), round(lc.y, 7)],
        "facade_p0_m": [round(a0[0], 3), round(a0[1], 3)], "facade_dir": [round(d[0], 6), round(d[1], 6)],
        "facade_out": [round(nout[0], 6), round(nout[1], 6)], "facade_len_m": round(flen, 2),
        "pavilion_len_m": pav, "portico_depth_m": depth,
        "mass_m": [[round(x, 3), round(y, 3)] for x, y in mass.exterior.coords],
        "facade_ground_m": [round(min(fg), 2), round(max(fg), 2)], "stair_foot_ground_m": round(min(foot), 2),
        "method": "facade = longest footprint edge facing 사색의 광장 (OSM way/585696477); portico recess and colonnade kept inside the OSM footprint",
    }

    # ---------------- 사색의 광장: obelisks (OSM man_made=tower) + fountain (OSM amenity=fountain) ----------------
    plaza_g = shape(L_[0]["geometry"]).buffer(0.0003) if L_ else None
    obel, fount = [], []
    for el in osm_els:
        t = el.get("tags", {})
        if el["type"] != "way" or len(el.get("geometry", [])) < 4:
            continue
        g = Polygon([(p_["lon"], p_["lat"]) for p_ in el["geometry"]])
        if plaza_g is None or not plaza_g.contains(g.centroid):
            continue
        if t.get("man_made") == "tower":
            cg = g.centroid
            obel.append({"id": f"way/{el['id']}", "center": [round(cg.x, 7), round(cg.y, 7)],
                         "base_radius_m": round(math.sqrt(g.area * MX * MY / math.pi), 2),
                         "ground_m": round(float(dtm.sample(cg.x, cg.y)), 2)})
        if t.get("amenity") == "fountain":
            zz = [float(dtm.sample(x, y)) for x, y in g.exterior.coords]
            fount.append({"id": f"way/{el['id']}", "coords": [[round(x, 7), round(y, 7)] for x, y in g.exterior.coords],
                          "ground_min_m": round(min(zz), 2), "ground_mean_m": round(float(np.mean(zz)), 2)})
    out["plaza"] = {"obelisks": obel, "fountains": fount,
                    "obelisk_height_m": 23.0,
                    "obelisk_height_source": "published guidebook (조명화, 캠퍼스투어008 경희대학교): obelisks 23 m; KHU archives: two obelisks stand in 사색의 광장"}
    # ---------------- 평화노천극장 (Greek-style theatre): stage axis points to the OSM pond ----------------
    POND = "way/326869038"
    pond_el = next((e for e in osm_els if e["type"] == "way" and e["id"] == int(POND.split("/")[1])), None)
    th = shape(B[AMPHI]["geometry"])
    tcx, tcy = th.centroid.x, th.centroid.y
    tl = lambda x, y: ((x - tcx) * MX, (y - tcy) * MY)
    tg = lambda e, n: (tcx + e / MX, tcy + n / MY)
    thm = Polygon([tl(x, y) for x, y in th.exterior.coords])
    pond = Polygon([(p_["lon"], p_["lat"]) for p_ in pond_el["geometry"]]) if pond_el else None
    pe, pn = tl(pond.centroid.x, pond.centroid.y) if pond else (1.0, 0.0)
    pl = math.hypot(pe, pn)
    ue, un = pe / pl, pn / pl                                  # stage -> pond direction
    # orchestra centre: 16 m inside the footprint edge on the pond side
    far = LineString([(0, 0), (ue * 300, un * 300)]).intersection(thm.exterior)
    bp = far if far.geom_type == "Point" else min(far.geoms, key=lambda g_: g_.distance(Point(ue * 300, un * 300)))
    bd = math.hypot(bp.x, bp.y)
    Oe, On = ue * (bd - 16.0), un * (bd - 16.0)
    # cavea radius limited by the footprint over the seating span (+-100 deg around the uphill axis)
    dists = []
    for k in range(41):
        a = math.radians(-100 + 5 * k)
        de = -ue * math.cos(a) - un * math.sin(a) * -1
        dn = -un * math.cos(a) + ue * math.sin(a) * -1
        ray = LineString([(Oe, On), (Oe + de * 300, On + dn * 300)])
        hit = ray.intersection(thm.exterior)
        pts_ = [hit] if hit.geom_type == "Point" else list(getattr(hit, "geoms", []))
        if pts_:
            dists.append(min(math.hypot(q_.x - Oe, q_.y - On) for q_ in pts_))
    Rmax = float(np.clip(np.percentile(dists, 40), 30, 60)) if dists else 40.0
    zO = float(dtm.sample(*tg(Oe, On)))
    R0, tread = 14.5, 0.85
    radii = np.arange(R0, Rmax, tread)
    ringmax = []
    for r_ in radii:
        zz = []
        for a in np.linspace(-1.6, 1.6, 17):
            de = -ue * math.cos(a) + un * math.sin(a)
            dn = -un * math.cos(a) - ue * math.sin(a)
            zz.append(float(dtm.sample(*tg(Oe + de * r_, On + dn * r_))))
        ringmax.append(max(zz) - zO)
    pz = [float(dtm.sample(x, y)) for x, y in pond.exterior.coords] if pond else [zO - 4]
    out["theatre"] = {
        "id": AMPHI, "origin": [round(tg(Oe, On)[0], 7), round(tg(Oe, On)[1], 7)],
        "to_pond_en": [round(ue, 6), round(un, 6)], "R0_m": R0, "Rmax_m": round(Rmax, 2), "tread_m": tread,
        "orchestra_ground_m": round(zO, 2), "ring_dtm_max_rel_m": [round(v, 2) for v in ringmax],
        "pond": {"id": POND, "coords": [[round(x, 7), round(y, 7)] for x, y in pond.exterior.coords] if pond else [],
                 "ground_min_m": round(min(pz), 2), "ground_mean_m": round(float(np.mean(pz)), 2)},
        "method": "stage axis = direction from the theatre footprint towards the OSM pond (natural=water); seat rows rise with the real DTM and never sit below it; outer radius limited by the OSM footprint",
    }

    # ---------------- 선승관 (photos supplied as "Peace Hall"): D-shaped brick arcade hall + clock tower ----------------
    PH = "way/585696506"
    phg = shape(B[PH]["geometry"])
    pcx, pcy = phg.centroid.x, phg.centroid.y
    pl_ = lambda x, y: ((x - pcx) * MX, (y - pcy) * MY)
    ring_ph = [pl_(x, y) for x, y in phg.exterior.coords]
    segs_ph = []
    for (x0, y0), (x1, y1) in zip(ring_ph, ring_ph[1:]):
        if segs_ph:
            (sx, sy), (ex, ey) = segs_ph[-1]
            a1 = math.atan2(ey - sy, ex - sx); a2 = math.atan2(y1 - y0, x1 - x0)
            if abs((a1 - a2 + math.pi) % (2 * math.pi) - math.pi) < math.radians(4):
                segs_ph[-1] = ((sx, sy), (x1, y1)); continue
        segs_ph.append(((x0, y0), (x1, y1)))
    # projecting entrance block = the edge whose neighbouring vertices are both re-entrant (concave);
    # the clock tower fills the re-entrant notch nearest a drivable road (position confirmed by the user)
    pts_ph = ring_ph[:-1]
    nph = len(pts_ph)
    area_ph = sum(pts_ph[i][0] * pts_ph[(i + 1) % nph][1] - pts_ph[(i + 1) % nph][0] * pts_ph[i][1] for i in range(nph))
    def concave(i):
        a_, b_, c_ = pts_ph[i - 1], pts_ph[i], pts_ph[(i + 1) % nph]
        cr = (b_[0] - a_[0]) * (c_[1] - b_[1]) - (b_[1] - a_[1]) * (c_[0] - b_[0])
        return cr < 0 if area_ph > 0 else cr > 0
    conc = [i for i in range(nph) if concave(i)]
    road_u = unary_union([LineString([pl_(x, y) for x, y in f_["geometry"]["coordinates"]]) for f_ in R
                          if f_["geometry"]["type"] == "LineString" and f_["properties"]["highway"] not in ("footway", "path", "steps", "pedestrian", "cycleway")])
    front = None
    for i in range(nph):
        if concave((i - 1) % nph) and concave((i + 2) % nph):
            front = (pts_ph[i], pts_ph[(i + 1) % nph])
    if front is None:
        front = max(segs_ph, key=lambda sg: math.dist(*sg))
    end_a, end_b = front
    vi = min(conc, key=lambda i: road_u.distance(Point(pts_ph[i]))) if conc else 0
    v = pts_ph[vi]; pv = pts_ph[vi - 1]; qv = pts_ph[(vi + 1) % nph]
    d1 = ((v[0] - pv[0]) / math.dist(v, pv), (v[1] - pv[1]) / math.dist(v, pv))
    d2 = ((qv[0] - v[0]) / math.dist(qv, v), (qv[1] - v[1]) / math.dist(qv, v))
    tc = (v[0] - d1[0] * 3.7 + d2[0] * 3.7, v[1] - d1[1] * 3.7 + d2[1] * 3.7)
    dx_, dy_, dl_ = d1[0], d1[1], 1.0
    phm = Polygon(ring_ph)
    upper = phm.buffer(-3.5, join_style=2)
    west, south, east, north = upper.bounds
    roof_x = (west + east) / 2
    out["peacehall"] = {
        "id": PH, "origin": [round(pcx, 7), round(pcy, 7)],
        "ring_m": [[round(x, 3), round(y, 3)] for x, y in ring_ph],
        "upper_m": [[round(x, 3), round(y, 3)] for x, y in upper.exterior.coords],
        "roof_ridge_m": [[round(roof_x, 3), round(south + 11.7, 3)], [round(roof_x, 3), round(north - 24.0, 3)]],
        "straight_end_m": [[round(end_a[0], 3), round(end_a[1], 3)], [round(end_b[0], 3), round(end_b[1], 3)]],
        "tower_notch_vertex_m": [round(v[0], 3), round(v[1], 3)],
        "tower_center_m": [round(tc[0], 3), round(tc[1], 3)], "tower_axis": [round(dx_ / dl_, 6), round(dy_ / dl_, 6)],
        "method": "footprint = OSM way/585696506 (D-shaped); arcade facade, inset metal upper storey and clock tower from user-supplied photographs; grand arches on the projecting entrance block; clock tower in the re-entrant notch beside it nearest a drivable road (position confirmed by the user)",
    }

    # ---------------- 예술·디자인대학관: front = footprint side facing the nearest parking lot / road ----------------
    AD = "way/474085536"
    adg = shape(B[AD]["geometry"])
    acx, acy = adg.centroid.x, adg.centroid.y
    al = lambda x, y: ((x - acx) * MX, (y - acy) * MY)
    adm = Polygon([al(x, y) for x, y in adg.exterior.coords])
    rr_ = list(adm.minimum_rotated_rectangle.exterior.coords)
    LC = read_json(WEB_DATA / "landcover.geojson")["features"]
    targets = [Polygon([al(x, y) for x, y in f_["geometry"]["coordinates"][0]]) for f_ in LC
               if f_["properties"]["class"] == "parking" and f_["properties"]["in_campus"]]
    targets += [LineString([al(x, y) for x, y in f_["geometry"]["coordinates"]]) for f_ in R
                if f_["geometry"]["type"] == "LineString" and f_["properties"]["highway"] in ("service", "tertiary", "residential")]
    tu = unary_union(targets)
    best = None
    for k in range(4):
        a_, b_ = rr_[k], rr_[k + 1]
        mid = ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)
        dd = tu.distance(Point(mid))
        if best is None or dd < best[0]:
            best = (dd, a_, b_)
    _, fa, fb = best
    flen_ = math.dist(fa, fb)
    fdir = ((fb[0] - fa[0]) / flen_, (fb[1] - fa[1]) / flen_)
    fout = (fdir[1], -fdir[0])
    if adm.contains(Point((fa[0] + fb[0]) / 2 + fout[0] * 3, (fa[1] + fb[1]) / 2 + fout[1] * 3)):
        fout = (-fout[0], -fout[1])
    other = [math.dist(rr_[k], rr_[k + 1]) for k in range(4)]
    depth_ = [x for x in other if abs(x - flen_) > 0.01][0] if len(set(round(x, 2) for x in other)) > 1 else flen_
    zz = [float(dtm.sample(*((acx + (fa[0] + (fb[0] - fa[0]) * t_) / MX), (acy + (fa[1] + (fb[1] - fa[1]) * t_) / MY)))) for t_ in np.linspace(0, 1, 9)]
    out["artdesign"] = {
        "id": AD, "origin": [round(acx, 7), round(acy, 7)],
        "ring_m": [[round(x, 3), round(y, 3)] for x, y in adm.exterior.coords],
        "front_p0_m": [round(fa[0], 3), round(fa[1], 3)], "front_dir": [round(fdir[0], 6), round(fdir[1], 6)],
        "front_out": [round(fout[0], 6), round(fout[1], 6)], "front_len_m": round(flen_, 2), "depth_m": round(depth_, 2),
        "front_ground_m": [round(min(zz), 2), round(max(zz), 2)],
        "method": "front = side of the footprint's minimum rotated rectangle nearest a parking lot / road (OSM); massing from user-supplied photographs",
    }

    # ---------------- photo-based building models (rendered generically by buildPhotoModel in khu_landmarks.js) ----------------
    out["photo_buildings"] = photo_buildings(B, R, dtm)

    # ---------------- crop outline: campus boundary + 30 m (terrain/feature clip) ----------------
    camp = shape(read_json(WEB_DATA / "boundary.geojson")["features"][0]["geometry"])
    cc = camp.centroid
    from shapely.affinity import affine_transform
    to_m = [MX, 0, 0, MY, -cc.x * MX, -cc.y * MY]
    to_d = [1 / MX, 0, 0, 1 / MY, cc.x, cc.y]
    buf = affine_transform(affine_transform(camp, to_m).buffer(30, join_style=1).simplify(2.0), to_d)
    parts = [buf] if buf.geom_type == "Polygon" else list(buf.geoms)
    out["clip"] = {"margin_m": 30, "rings": [[[round(x, 7), round(y, 7)] for x, y in p_.exterior.coords] for p_ in parts],
                   "bbox": [round(v, 7) for v in buf.bounds],
                   "source": "OSM campus boundary relation 11246784 buffered by 30 m"}
    write_json(WEB_DATA / "campus_details.json", out, compact=True)
    print("theatre Rmax", out["theatre"]["Rmax_m"], "rows", len(out["theatre"]["ring_dtm_max_rel_m"]), "orchestra", out["theatre"]["orchestra_ground_m"], "pond ground", out["theatre"]["pond"]["ground_min_m"], "top rel", out["theatre"]["ring_dtm_max_rel_m"][-1])
    print("clip parts", len(parts), "vertices", sum(len(p_.exterior.coords) for p_ in parts))
    print("library facade", round(flen, 1), "m, pavilions", pav, "obelisks", len(obel), "fountains", len(fount))
    print("gate", out["gate"])
    print("amphitheatre tiers", len(tiers), "observatory r", round(r, 1))


# =====================================================================================================
# Photo-based building models
# -----------------------------------------------------------------------------------------------------
# Each model is a plain description rendered by buildPhotoModel() in web/js/khu_landmarks.js:
#   masses : extrusions of the OSM footprint (or of sub-polygons clipped from it) with a facade style
#   prims  : boxes, cylinders, spheres and extruded profiles in the frame of a footprint edge
# Positions, outlines, orientation and ground level come ONLY from the OSM footprint and the DTM. The
# photographs give storey counts, proportions, element counts, materials and colours (all "estimated").
# z values are metres above the footprint's lowest DTM ground (ground_min_m) = the render datum.
# =====================================================================================================
from pathlib import Path

OVR = read_json(Path(__file__).resolve().parent / "height_overrides.json")["buildings"]
# facade style ids (see STY in web/js/mesh.js); BANDED encodes windows-per-bay as 23 + n/10
GRANITE, MODERN, RESID, GLASS, PLAIN, BANDED, ENGINEERING_WING = 0, 1, 2, 3, 12, 23, 25
FOREIGN_LANGUAGES_WINDOWS = 26
ELECTRONICS_BRICK = 27
WOOJUNGWON_WINDOWS, WOOJUNGWON_GLASS = 28, 29
DORM_WINDOWS = 30


class Site:
    """An OSM footprint in local metres (origin = footprint centroid) with DTM helpers."""

    def __init__(self, oid, B, dtm):
        self.id, self.dtm = oid, dtm
        g = shape(B[oid]["geometry"])
        self.props = B[oid]["properties"]
        c = g.centroid
        self.c = (c.x, c.y)
        polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
        self.polys = [Polygon([self.l(x, y) for x, y in p.exterior.coords],
                              [[self.l(x, y) for x, y in r.coords] for r in p.interiors]) for p in polys]
        self.poly = unary_union(self.polys)
        self.gmin = self.props["ground_min_m"]
        self.H = OVR[oid]["height"] if oid in OVR else self.props["height_m"]

    def l(self, x, y):
        return ((x - self.c[0]) * MX, (y - self.c[1]) * MY)

    def ground(self, e, n):
        """DTM ground at local (e, n), relative to the datum (ground_min_m)."""
        return float(self.dtm.sample(self.c[0] + e / MX, self.c[1] + n / MY)) - self.gmin

    def edges(self, merge_deg=4.0):
        """Footprint edges with consecutive collinear pieces merged; outward normal + its compass bearing."""
        out = []
        for poly in self.polys:
            ring = list(poly.exterior.coords)
            segs = []
            for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
                if math.hypot(x1 - x0, y1 - y0) < 0.05:
                    continue
                if segs:
                    (sx, sy), (ex, ey) = segs[-1]
                    a1, a2 = math.atan2(ey - sy, ex - sx), math.atan2(y1 - y0, x1 - x0)
                    if abs((a1 - a2 + math.pi) % (2 * math.pi) - math.pi) < math.radians(merge_deg):
                        segs[-1] = ((sx, sy), (x1, y1))
                        continue
                segs.append(((x0, y0), (x1, y1)))
            ccw = poly.exterior.is_ccw
            for a, b in segs:
                L = math.dist(a, b)
                d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                o = (d[1], -d[0]) if ccw else (-d[1], d[0])
                out.append({"a": a, "b": b, "len": L, "dir": d, "out": o,
                            "bearing": math.degrees(math.atan2(o[0], o[1])) % 360})
        return out

    def face(self, bearing, tol=35.0, min_len=4.0, rank=0):
        """The rank-th longest edge whose outward normal points within tol degrees of the compass bearing."""
        c = [e for e in self.edges() if e["len"] >= min_len and abs((e["bearing"] - bearing + 180) % 360 - 180) <= tol]
        c.sort(key=lambda e: -e["len"])
        if len(c) <= rank:
            raise ValueError(f"{self.id}: no face towards {bearing}")
        return c[rank]


def edge_frame(e):
    """Local frame on a footprint edge: s along the edge (0..len), +t INTO the building, z up."""
    a, d, o = e["a"], e["dir"], e["out"]
    if (-d[1]) * o[0] + d[0] * o[1] > 0:              # left normal points outward -> walk the edge backwards
        a, d = e["b"], (-d[0], -d[1])
    return {"ax": [round(d[0], 6), round(d[1], 6)], "off": [round(a[0], 3), round(a[1], 3)], "len": round(e["len"], 3)}


def ring_of(ring):
    return [[round(x, 3), round(y, 3)] for x, y in ring.coords]


def site_rings(S, poly):
    return [[[round(S.c[0] + e / MX, 7), round(S.c[1] + n / MY, 7)]
             for e, n in ring.coords] for ring in (poly.exterior, *poly.interiors)]


def mass(poly, z0, z1, wall, roof, sty, fh=3.6, bw=3.6, floor0=0.0, parapet=0.9, edge_sty=None):
    """An extruded mass. floor0 = height of the ground floor above the datum (phase of the storey grid)."""
    polys = [poly] if poly.geom_type == "Polygon" else [p for p in poly.geoms if p.geom_type == "Polygon"]
    return [{"ring": ring_of(p.exterior), "z0": round(z0, 2), "z1": round(z1, 2), "wall": wall, "roof": roof, "sty": sty,
             "fh": fh, "bw": bw, "floor0": round(floor0, 2), "parapet": parapet,
             **({"holes": [ring_of(r) for r in p.interiors]} if p.interiors else {}),
             **({"edge_sty": edge_sty(p)} if edge_sty else {})} for p in polys if p.area > 1.0]


def pbox(F, s0, s1, t0, t1, z0, z1, col, sty=PLAIN, fh=3.6, bw=3.6,
         faces=None, top=True, floor0=None, bottom=False):
    d = {"t": "box", "ax": F["ax"], "off": F["off"], "s0": round(s0, 3), "s1": round(s1, 3), "t0": round(t0, 3), "t1": round(t1, 3),
         "z0": round(z0, 2), "z1": round(z1, 2), "col": col, "sty": sty, "fh": fh, "bw": bw, "top": top}
    if faces:
        d["faces"] = faces
    if floor0 is not None:
        d["zref"] = round(floor0, 2)
    if bottom:
        d["bottom"] = True
    return d


def pcyl(F, s, t, z0, z1, r0, col, r1=None, sty=7, seg=14):
    return {"t": "cyl", "ax": F["ax"], "off": F["off"], "s": round(s, 3), "t_": round(t, 3), "z0": round(z0, 2), "z1": round(z1, 2),
            "r0": r0, "r1": r1 if r1 is not None else r0, "seg": seg, "col": col, "sty": sty}


def pprofile(F, points, t0, t1, col):
    """Extrude a counterclockwise (s, z) profile through a short section of the facade."""
    if not Polygon(points).exterior.is_ccw:
        points = list(reversed(points))
    return {"t": "profile", "ax": F["ax"], "off": F["off"],
            "points": [[round(s, 3), round(z, 3)] for s, z in points],
            "t0": round(t0, 3), "t1": round(t1, 3), "col": col}


# ---------------------------------------------------------------- 02 애지원
def m_aejiwon(S):
    """5-storey white slab (ROTC 학군단): continuous floor bands, 4 bays x 2 windows, taupe end stair towers.
    Photos: south face of the south wing over the parking lot (OSM edge facing ~170 deg)."""
    WHITE, TAUPE, ROOF = "#ecebe6", "#b39d90", "#9c9e9b"
    F = edge_frame(S.face(170))
    mid = [F["off"][0] + F["ax"][0] * F["len"] / 2, F["off"][1] + F["ax"][1] * F["len"] / 2]
    f0 = S.ground(mid[0] - F["ax"][1] * -3, mid[1] + F["ax"][0] * -3)   # parking-lot level just outside the face
    H = S.H                                     # parapet, from height_overrides.json (5 storeys above f0)
    masses = mass(S.poly, -1.5, H, WHITE, ROOF, BANDED + 0.2, fh=3.3, bw=6.9, floor0=f0)
    L = F["len"]
    prims = [pbox(F, s0, s1, -0.45, 9.5, -1.5, H + 1.6, TAUPE, PLAIN) for s0, s1 in ((0.0, 3.3), (L - 3.3, L))]
    # ground-floor entrance (green-tinted glazing) in the first bay + sign band
    prims.append(pbox(F, 4.0, 9.2, -0.12, 0.2, f0 + 0.3, f0 + 2.9, "#5f8f7c", GLASS, fh=2.6, bw=1.3))
    prims.append(pbox(F, 3.6, 9.6, -0.5, 0.2, f0 + 2.9, f0 + 3.5, "#f1f0ec", PLAIN))
    return {"masses": masses, "prims": prims, "top_m": round(H + 1.6, 2), "floors": 5,
            "appearance": "white 5-storey slab modelled from 3 photographs: continuous floor bands with recessed windows (4 bays x 2 per floor on the south face), taupe end stair towers, green-glazed ROTC entrance; same facade applied to the unphotographed wings",
            "front_bearing": 170}


# ---------------------------------------------------------------- 06 공학관
def m_engineering(S):
    """West-facing five-storey block, courtyard wings, entrance canopy and clock fins."""
    front = S.face(268)
    F = edge_frame(front)
    L = F["len"]
    c = L / 2
    ax, ay = F["ax"]
    x0, y0 = F["off"]
    # White render as in the official annex renderings (KHU, 2026); the photographs show a dustier off-white.
    wall, trim, roof = "#ebeae4", "#eeede7", "#a9aeab"
    glass, frame, stone = "#344b48", "#232f30", "#c7c3b9"
    sign = "#a18142"

    def plan(s, t):
        return x0 + ax * s - ay * t, y0 + ay * s + ax * t

    def band(s0, s1, t0, t1):
        return Polygon([plan(s0, t0), plan(s1, t0), plan(s1, t1), plan(s0, t1)])

    grade = S.ground(*plan(c, -5))
    upper_base = grade + 3.85
    storey = (S.H - upper_base) / 4

    def wall_styles(poly):
        styles = []
        points = list(poly.exterior.coords)
        for a, b in zip(points, points[1:]):
            # The front receives its bands and windows as geometry below.
            on_front = (math.dist(a, b) > L * 0.95 and
                        max(abs((x - x0) * -ay + (y - y0) * ax) for x, y in (a, b)) < 0.03)
            styles.append([PLAIN, storey, 5.4, "#e6e5df"] if on_front
                          else [ENGINEERING_WING, storey, 5.4, wall])
        return styles

    center_block = S.poly.intersection(band(0, L, -120, 120))
    wings = S.poly.difference(center_block)
    end_blocks = wings.intersection(band(-120, L + 120, -120, -38))
    end_top = grade + 10.8
    masses = mass(center_block, -1.5, S.H, wall, roof, ENGINEERING_WING,
                  fh=storey, bw=5.4, floor0=grade, parapet=0.6, edge_sty=wall_styles)
    masses += mass(wings.difference(end_blocks), -1.5, S.H - storey, wall, roof,
                   ENGINEERING_WING, fh=storey, bw=5.4, floor0=grade, parapet=0.55)
    # The end blocks facing the turf are blank white boxes with one clerestory strip under the cornice
    # (official annex renderings, 2026).
    masses += mass(end_blocks, -1.5, end_top, wall, "#b9bbb6", PLAIN, fh=storey, bw=5.4, floor0=grade,
                   parapet=0.5, edge_sty=lambda p: [[PLAIN, storey, 5.4, wall]] * (len(p.exterior.coords) - 1))

    prims = []
    for block in getattr(end_blocks, "geoms", [end_blocks]):
        if block.geom_type != "Polygon":
            continue
        ring, ccw = list(block.exterior.coords), block.exterior.is_ccw
        for a, b in zip(ring, ring[1:]):
            n = math.dist(a, b)
            if n < 6:
                continue
            d = ((b[0] - a[0]) / n, (b[1] - a[1]) / n)
            E = edge_frame({"a": a, "b": b, "len": n, "dir": d, "out": (d[1], -d[0]) if ccw else (-d[1], d[0])})
            prims.append(pbox(E, 0.8, n - 0.8, -0.04, 0.12, end_top - 2.45, end_top - 1.4, "#3d4b4b", GLASS, fh=1.05, bw=1.7))
            for s in np.arange(0.8, n - 0.79, (n - 1.6) / max(1, round((n - 1.6) / 1.75))):
                prims.append(pbox(E, s - 0.09, s + 0.09, -0.12, 0.05, end_top - 2.45, end_top - 1.4, wall))
            prims.append(pbox(E, -0.25, n + 0.25, -0.4, 0.05, end_top - 1.4, end_top - 0.95, trim, bottom=True))

    def box_at(s0, s1, t0, t1, z0, z1, col, bottom=False):
        prims.append(pbox(F, s0, s1, t0, t1, grade + z0, grade + z1, col, bottom=bottom))

    def profile_at(points, t0, t1, col):
        prims.append(pprofile(F, [(s, grade + z) for s, z in points], t0, t1, col))

    def window(s0, s1, lo, hi, panes, bars=False):
        box_at(s0, s1, -0.025, 0.06, lo, hi, glass)
        rails = [s0 + (s1 - s0) * k / panes for k in range(panes + 1)]
        for s in rails:
            box_at(s - 0.028, s + 0.028, -0.09, -0.015, lo, hi, frame)
        for z in (lo, lo + (hi - lo) * 0.61, hi):
            box_at(s0, s1, -0.089, -0.014, z - 0.031, z + 0.031, frame)
        if bars:
            for s in np.linspace(s0 + 0.15, s1 - 0.15, 9):
                box_at(s - 0.012, s + 0.012, -0.16, -0.075, lo + 0.02, hi - 0.02, "#83877f")

    def stroke(a, b, width, t, col):
        s, z = a
        q, r = b
        k = width / (2 * math.hypot(q - s, r - z))
        ds, dz = -(r - z) * k, (q - s) * k
        profile_at([(s - ds, z - dz), (q - ds, r - dz), (q + ds, r + dz), (s + ds, z + dz)],
                   t - 0.035, t, col)

    # Four dark, mullioned window rows, each behind a continuous projecting concrete spandrel.
    facade_height = S.H - grade
    for row in range(4):
        lower = upper_base - grade + row * storey
        box_at(-0.32, L + 0.32, -0.83, 0.15, lower - 0.71, lower + 0.62, trim, bottom=True)
        for side in (-1, 1):
            for bay in range(6):
                s = c + side * (8.25 + bay * 5.58)
                window(s - 1.66, s + 1.66, lower + 0.74, lower + 2.22, 3)
        window(c - 2.75, c + 2.75, lower + 0.74, lower + 2.22, 5)
    box_at(-0.54, L + 0.54, -1.03, 0.18, facade_height - 1.19, facade_height, trim, bottom=True)

    # The taller ground-floor bays have barred windows and chamfered concrete heads.
    for first, last in ((0.2, c - 5.6), (c + 5.6, L - 0.2)):
        width = (last - first) / 10
        for k in range(10):
            s = first + (k + 0.5) * width
            left, right = s - width / 2, s + width / 2
            window(left + 0.43, right - 0.43, 0.18, 2.57, 2, bars=True)
            profile_at([(left, 2.12), (left + 0.45, 2.73), (right - 0.45, 2.73),
                        (right, 2.12), (right, 3.29), (left, 3.29)], -0.59, 0.08, trim)
            box_at(left - 0.04, left + 0.21, -0.58, 0.09, -0.32, 2.66, trim)
        box_at(last - 0.12, last + 0.12, -0.58, 0.09, -0.32, 2.66, trim)

    # Raise the landing clear of the terrain so the whole approach and the threshold are visible.
    landing = max(S.ground(*plan(s, t)) - grade for s in (c - 6.65, c, c + 6.65) for t in (-5.1, 0.03)) + 0.1
    stair_base = max(S.ground(*plan(s, -6.95)) - grade for s in (c - 6.6, c, c + 6.6))
    box_at(c - 4.65, c + 4.65, -0.012, 0.12, landing, 4.51, "#77776d")
    window(c - 3.95, c + 3.95, landing + 0.04, 4.2, 7)
    box_at(c - 6.65, c + 6.65, -5.1, 0.03, -0.8, landing, "#aaa89c")
    for k in range(5):
        tread = stair_base + (landing - stair_base) * (k + 1) / 5
        box_at(c - 6.6, c + 6.6, -7.0 + k * 0.38, -5.09, -0.8, tread, stone)
    for side in (-1, 1):
        near, far = c + side * 6.65, c + side * 13.2
        grade_at_edge = max(S.ground(*plan(far, t)) - grade for t in (-6.15, -3.95))
        profile_at([(near, -0.75), (far, min(-0.3, grade_at_edge - 0.6)),
                    (far, grade_at_edge + 0.06), (near, landing)], -6.15, -3.95, stone)

    # The thick canopy bellies out above a pair of sculpted, flared supports.
    profile_at([(c - 8.25, 4.52), (c + 8.25, 4.52), (c + 8.73, 4.76), (c + 9.04, 5.96),
                (c - 9.04, 5.96), (c - 8.73, 4.76)], -5.45, 0.25, trim)
    box_at(c - 8.1, c + 8.1, -5.28, 0.08, 4.48, 4.53, "#a8a69b", bottom=True)
    for side in (-1, 1):
        support = [(5.5, landing - 0.03), (6.28, landing - 0.03), (6.32, 3.95), (7.0, 4.64),
                   (4.15, 4.64), (4.9, 4.24), (5.35, 3.66)]
        profile_at([(c + side * s, z) for s, z in support], -4.93, -3.96, trim)
        s = c + side * 5.88
        box_at(s - 0.18, s + 0.18, -5.0, -4.92, landing + 0.28, 3.5, "#61513d")
    # Simplified strokes for the four raised characters visible on the canopy, 工科大學.
    glyphs = (
        (((.13, .82), (.86, .82)), ((.5, .82), (.5, .13)), ((.07, .13), (.93, .13))),
        (((.08, .82), (.43, .93)), ((.06, .63), (.45, .63)), ((.27, .89), (.27, .09)),
         ((.27, .63), (.05, .32)), ((.27, .57), (.46, .38)), ((.58, .8), (.72, .7)),
         ((.55, .53), (.68, .44)), ((.47, .35), (.92, .48)), ((.78, .92), (.78, .08))),
        (((.08, .57), (.92, .57)), ((.52, .95), (.47, .54)), ((.47, .54), (.3, .25)),
         ((.3, .25), (.07, .07)), ((.52, .53), (.69, .27)), ((.69, .27), (.93, .08))),
        (((.13, .9), (.13, .57)), ((.13, .9), (.33, .94)), ((.13, .77), (.33, .77)),
         ((.13, .61), (.84, .61)), ((.65, .92), (.83, .92)), ((.66, .77), (.83, .77)),
         ((.83, .92), (.83, .61)), ((.39, .9), (.59, .7)), ((.59, .9), (.39, .7)),
         ((.06, .43), (.06, .57)), ((.06, .57), (.93, .57)), ((.93, .57), (.93, .43)),
         ((.27, .4), (.72, .4)), ((.72, .4), (.5, .27)), ((.5, .27), (.5, .08)),
         ((.5, .08), (.4, .08)), ((.13, .21), (.87, .21))),
    )
    for i, strokes in enumerate(glyphs):
        center = c + (i - 1.5) * 1.12
        for a, b in strokes:
            stroke((center + (a[0] - 0.5) * 0.68, 4.95 + a[1] * 0.63),
                   (center + (b[0] - 0.5) * 0.68, 4.95 + b[1] * 0.63), 0.075, -5.46, sign)

    # Two thin fins continue above the roof around the inset, square clock panel.
    fin_top = facade_height + 4.9
    for side in (-1, 1):
        s = c + side * 4.2
        box_at(s - 0.24, s + 0.24, -1.19, 0.38, 5.8, fin_top, trim)
    clock_z = facade_height + 1.13
    box_at(c - 4.12, c + 4.12, -0.45, 0.8, facade_height - 0.25, facade_height + 1.97, wall)
    box_at(c - 0.66, c + 0.66, -0.58, -0.43, clock_z - 0.66, clock_z + 0.66, frame)
    dial = [(c + 0.53 * math.cos(a), clock_z + 0.53 * math.sin(a))
            for a in np.linspace(0, 2 * math.pi, 24, endpoint=False)]
    profile_at(dial, -0.63, -0.57, "#e6e6dc")
    for a in np.linspace(0, 2 * math.pi, 12, endpoint=False):
        direction = math.cos(a), math.sin(a)
        stroke((c + 0.36 * direction[0], clock_z + 0.36 * direction[1]),
               (c + 0.45 * direction[0], clock_z + 0.45 * direction[1]), 0.026, -0.635, frame)
    stroke((c, clock_z), (c + 0.05, clock_z + 0.35), 0.047, -0.64, frame)
    stroke((c, clock_z), (c - 0.27, clock_z + 0.12), 0.052, -0.64, frame)
    box_at(c - 6.7, c + 6.7, 6.8, 14.1, facade_height - 0.62, facade_height + 1.32, wall)

    return {
        "masses": masses, "prims": prims, "top_m": round(grade + fin_top, 2), "floors": 5,
        "name_en": "College of Engineering", "front_bearing": round(front["bearing"], 1),
        "focus_heading": round((front["bearing"] + 168) % 360, 1),
        "appearance": ("photo-based concrete courtyard building with stepped wings, five front levels, projecting window "
                       "bands, barred ground-floor bays, entrance steps and side ramps, signed canopy and twin clock fins"),
    }


PLANNED = {b["id"]: b for b in read_json(Path(__file__).resolve().parent / "planned_buildings.json")["buildings"]}
ANNEX = "planned/engineering-annex"
SIGN_STROKES = {  # letters in a 0.7 x 1 box, drawn as raised strokes
    "E": [((0, 0), (0, 1)), ((0, 1), (.7, 1)), ((0, .5), (.55, .5)), ((0, 0), (.7, 0))],
    "N": [((0, 0), (0, 1)), ((0, 1), (.7, 0)), ((.7, 0), (.7, 1))],
    "G": [((.7, .85), (.5, 1)), ((.5, 1), (.2, 1)), ((.2, 1), (0, .75)), ((0, .75), (0, .25)), ((0, .25), (.2, 0)),
          ((.2, 0), (.55, 0)), ((.55, 0), (.7, .2)), ((.7, .2), (.7, .45)), ((.7, .45), (.4, .45))],
    "I": [((.35, 0), (.35, 1))],
    "R": [((0, 0), (0, 1)), ((0, 1), (.5, 1)), ((.5, 1), (.7, .85)), ((.7, .85), (.7, .65)), ((.7, .65), (.5, .5)),
          ((.5, .5), (0, .5)), ((.35, .5), (.7, 0))],
    "A": [((0, 0), (.35, 1)), ((.35, 1), (.7, 0)), ((.13, .38), (.57, .38))],
    "X": [((0, 0), (.7, 1)), ((0, 1), (.7, 0))],
}


def m_engineering_annex(S):
    """공과대학 별관 (under construction, completion planned for December 2027), from the official renderings.

    Two glazed floors under a broad roof terrace face the turf. The roof edge is a fluted white fascia that
    thins towards both ends. Clusters of three slim columns carry it, a planted stair drops from the north
    balcony, and a floor-3 pavilion stands on the north end of the roof. Behind, a raised stone court
    (inspired by the Jongmyo woldae) meets floor 2. A sunken garden in it lights the ground floor, and
    broad steps rise to the old entrance. Levels: ground floor and court from planned_buildings.json.
    """
    pb = PLANNED[S.id]
    front = S.face(268)
    F = edge_frame(front)
    L = F["len"]
    ax, ay = F["ax"]
    x0, y0 = F["off"]
    g0 = pb["ground_floor_m"] - S.gmin                        # ground floor, above the render datum
    p = pb["platform_m"] - S.gmin                             # floor 2 = raised court
    r = g0 + pb["roof_above_ground_floor_m"]                  # roof terrace
    white, soffit, wood = "#efeee9", "#c9a274", "#cdb595"
    pane, rail = "#9fb4b6", "#d3e0e0"

    def plan(s, t):
        return x0 + ax * s - ay * t, y0 + ay * s + ax * t

    def local(pt):
        e, n = pt[0] - x0, pt[1] - y0
        return e * ax + n * ay, -e * ay + n * ax

    def band(s0, s1, t0, t1):
        return Polygon([plan(s0, t0), plan(s1, t0), plan(s1, t1), plan(s0, t1)])

    def by_side(styles):
        """Per-edge facade styles chosen by the side of the rectangle each edge lies on."""
        def pick(poly):
            out = []
            sc, tc = local(poly.centroid.coords[0])
            pts = list(poly.exterior.coords)
            for a, b in zip(pts, pts[1:]):
                (sa, ta), (sb, tb) = local(a), local(b)
                if abs(sa - sb) < 0.1:
                    side = "north" if sa < sc else "south"
                else:
                    side = "front" if ta < tc else "back"
                out.append(styles[side])
            return out
        return pick

    prims = []

    def box(s0, s1, t0, t1, z0, z1, col, sty=PLAIN, **kw):
        prims.append(pbox(F, s0, s1, t0, t1, z0, z1, col, sty, **kw))

    def tree(s, t, z, h=6.0, leaf="#5d7e3c"):
        prims.append(pcyl(F, s, t, z - 0.1, z + h * 0.5, 0.16, "#6a5444", r1=0.1, sty=PLAIN, seg=7))
        for ds, dt, dz, k in ((-0.6, 0.2, 0.62, 0.26), (0.65, 0.3, 0.7, 0.27), (0, -0.5, 0.82, 0.25)):
            prims.append({"t": "sphere", "ax": F["ax"], "off": F["off"], "s": round(s + ds, 3), "t_": round(t + dt, 3),
                          "z": round(z + h * dz, 2), "r": round(h * k, 2), "sz": 0.75, "jit": 0.15, "col": leaf, "sty": 21})

    def shrub(s, t, z, rad, col="#5f8a3e"):
        prims.append({"t": "sphere", "ax": F["ax"], "off": F["off"], "s": round(s, 3), "t_": round(t, 3),
                      "z": round(z, 2), "r": rad, "sz": 0.6, "jit": 0.2, "col": col, "sty": 21})

    # ---- glazed floors -------------------------------------------------------------------------------
    glazed = {"front": [GLASS, p - 0.55 - g0, 1.6, pane], "back": [GLASS, p - 0.55 - g0, 1.6, pane],
              "north": [GLASS, p - 0.55 - g0, 1.6, pane], "south": [PLAIN, p - 0.55 - g0, 1.6, wood]}
    masses = mass(band(0.7, L - 0.7, 1.8, 26), -1.5, p - 0.55, pane, white, GLASS,
                  fh=p - 0.55 - g0, bw=1.6, floor0=g0, parapet=0, edge_sty=by_side(glazed))
    upper = {**glazed, "south": [PLAIN, r - 1.6 - p, 1.6, "#e4e2dc"]}
    upper = {k: [v[0], r - 1.6 - p, v[2], v[3]] for k, v in upper.items()}
    masses += mass(band(1.2, L - 1.2, 2.6, 26), p - 0.6, r - 1.6, pane, white, GLASS,
                   fh=r - 1.6 - p, bw=1.6, floor0=p, parapet=0, edge_sty=by_side(upper))
    box(-0.4, L + 0.4, 0.9, 26, p - 0.55, p, white, bottom=True)                      # floor-2 slab edge
    box(-0.4, 25.0, -2.5, 0.9, p - 0.45, p, white, bottom=True)                      # north balcony
    box(-0.3, 25.0, -2.5, -2.4, p, p + 1.1, rail, GLASS, fh=1.1, bw=1.6)
    box(-0.3, 25.0, -2.56, -2.36, p + 1.06, p + 1.14, "#dcdcd6")
    box(36.0, 40.4, 1.7, 1.82, g0, g0 + 3.1, "#3f4d4f", GLASS, fh=3.1, bw=1.1)       # entrance doors
    box(L - 0.75, L - 0.6, 3.0, 23.0, g0 + 0.2, p - 0.8, wood, fh=1.2, bw=1.2)     # solid south panels

    # ---- roof plate: thick at the middle, thinning towards both ends; fluted white fascia ----------
    prims.append(pprofile(F, [(-2.2, r - 0.5), (3.5, r - 1.6), (L - 3.5, r - 1.6), (L + 2.2, r - 0.5),
                              (L + 2.2, r), (-2.2, r)], -2.6, 28.0, white))
    box(3.5, L - 3.5, -2.5, 27.9, r - 1.67, r - 1.6, soffit, top=False, bottom=True)
    for s in np.arange(3.7, L - 3.6, 0.45):
        box(s - 0.07, s + 0.07, -2.69, -2.6, r - 1.6, r - 0.05, "#e5e3dd")
    for k in range(8):                                     # clusters of three slim columns
        s = 3.0 + k * (L - 6.0) / 7
        if 24.0 < s < 35.0:
            continue                                       # the planted stair takes this bay
        for ds in (-0.3, 0.0, 0.3):
            prims.append(pcyl(F, s + ds, -1.6, g0 - 0.2, r - 1.6, 0.1, white, sty=PLAIN, seg=8))

    # ---- planted stair from the north balcony down to the forecourt ------------------------------
    n_steps = 28
    rise, run = (p - g0) / n_steps, 9.0 / n_steps
    for k in range(n_steps):
        s0 = 25.0 + k * run
        box(s0, s0 + run, -2.4, -0.4, g0 - 0.3, p - k * rise, "#e8e6df")
    prims.append(pprofile(F, [(24.6, g0 - 0.3), (34.4, g0 - 0.3), (34.4, g0 + 0.9), (24.6, p + 0.9)], -2.75, -2.4, white))
    prims.append(pprofile(F, [(24.6, p + 0.9), (34.4, g0 + 0.9), (34.4, g0 + 1.25), (24.6, p + 1.25)], -2.75, -2.4, "#5f8a3e"))

    # ---- sign on the fascia near the south-west corner, and the corner sculpture --------------------
    text, size, s = "ENGINEERING ANNEX", 0.55, L - 15.2
    for ch in text:
        for (a, b) in SIGN_STROKES.get(ch, []):
            sa, za = s + a[0] * size, r - 1.12 + a[1] * size
            sb, zb = s + b[0] * size, r - 1.12 + b[1] * size
            k = 0.06 / max(1e-6, math.hypot(sb - sa, zb - za))
            ds, dz = -(zb - za) * k, (sb - sa) * k
            prims.append(pprofile(F, [(sa - ds, za - dz), (sb - ds, zb - dz), (sb + ds, zb + dz), (sa + ds, za + dz)],
                                  -2.74, -2.69, "#5a6878"))
        s += size * 0.7 + 0.2 if ch != " " else size * 0.9
    box(L - 2.0, L - 0.8, -5.2, -4.0, g0 - 0.2, g0 + 0.45, "#e2e0d9")
    prims.append(pcyl(F, L - 1.4, -4.6, g0 + 0.45, g0 + 1.75, 0.2, "#f4f3ef", r1=0.15, sty=12, seg=10))
    prims.append({"t": "sphere", "ax": F["ax"], "off": F["off"], "s": round(L - 1.4, 3), "t_": -4.6,
                  "z": round(g0 + 1.98, 2), "r": 0.17, "col": "#f4f3ef", "sty": 12})

    # ---- roof terrace -----------------------------------------------------------------------------
    box(0.4, L - 0.4, -1.9, 27.5, r, r + 0.05, "#9a9b97")
    for s0, s1, t0, t1 in ((-1.0, L + 1.0, -2.0, -1.9), (-1.0, L + 1.0, 27.5, 27.6),
                           (-1.0, -0.9, -2.0, 27.6), (L + 0.9, L + 1.0, -2.0, 27.6)):
        box(s0, s1, t0, t1, r, r + 1.1, rail, GLASS, fh=1.1, bw=1.6)
    for s0, s1, t0, t1 in ((25.0, 47.0, 0.4, 1.6), (26.0, 34.0, 24.4, 26.6), (48.0, 64.0, 24.6, 26.6)):
        box(s0, s1, t0, t1, r, r + 0.55, "#e9e8e2")
        box(s0 + 0.1, s1 - 0.1, t0 + 0.1, t1 - 0.1, r + 0.55, r + 0.8, "#62873f", 21)
    for k in range(3):                                     # stepped seating at the south end of the roof
        box(51.0, 62.0, 17.0 + k * 2.2, 23.5, r, r + 0.3 * (k + 1), "#cfcfc9")
    for s, t, h in ((40.0, 19.0, 4.2), (46.5, 7.5, 3.8), (60.5, 6.0, 4.0), (30.0, 13.0, 3.6)):
        box(s - 0.9, s + 0.9, t - 0.9, t + 0.9, r, r + 0.5, "#e9e8e2")
        tree(s, t, r + 0.5, h)
    for s, t, col in ((51, 25.6, "#8c3b3b"), (55, 25.4, "#6f8f4c"), (59, 25.7, "#a24f5d"), (29, 25.5, "#6f8f4c")):
        shrub(s, t, r + 0.85, 0.8, col)

    # ---- floor-3 pavilion: glazed to the west and south, timber-clad behind; broad white roof ---------
    pav = {"front": [GLASS, 4.1, 1.4, pane], "south": [GLASS, 4.1, 1.4, pane],
           "north": [PLAIN, 4.1, 1.4, wood], "back": [PLAIN, 4.1, 1.4, wood]}
    masses += mass(band(2.5, 22.0, 5.0, 25.0), r, r + 4.1, pane, white, GLASS, fh=4.1, bw=1.4, floor0=r,
                   parapet=0, edge_sty=by_side(pav))
    box(1.3, 23.2, 3.8, 26.2, r + 4.1, r + 4.5, white, bottom=True)
    box(8.0, 16.5, 8.0, 22.0, r + 4.5, r + 5.7, wood)
    box(10.5, 14.0, 10.0, 20.0, r + 5.7, r + 5.75, "#7d9496", GLASS, fh=1, bw=1.3)
    for s in np.arange(3.6, 21.5, 2.4):
        box(s - 0.06, s + 0.06, 4.75, 5.0, r, r + 4.1, white)

    # ---- raised court (woldae) behind, with a sunken garden against the annex ----------------------
    gs0, gs1, gt0, gt1 = 36.0, 54.0, 26.0, 34.0
    box(gs0, gs1, gt0, gt1, g0 - 0.3, g0, "#6f8f4c", 21)
    for k in range(9):
        shrub(gs0 + 1.5 + (k * 7.3) % 15.0, gt0 + 1.2 + (k * 2.9) % 5.6, g0 + 0.25, 0.75 + 0.1 * (k % 3))
    tree(45.0, 30.0, g0, 5.5)
    for s0, s1, t0, t1 in ((gs0, gs1, gt1 - 0.3, gt1), (gs0 - 0.3, gs0, gt0, gt1), (gs1, gs1 + 0.3, gt0, gt1)):
        box(s0, s1, t0, t1, g0 - 0.3, p + 0.05, "#d8d6cf")
        box(s0, s1, t0, t1, p + 0.05, p + 1.1, rail, GLASS, fh=1.05, bw=1.6)
    for s in (39.0, 45.0, 51.0):                           # light frames over the garden
        box(s - 0.13, s + 0.13, gt1 - 0.3, gt1 - 0.04, p, p + 3.3, white)
        box(s - 0.12, s + 0.12, gt0, gt1 - 0.04, p + 3.05, p + 3.3, white, bottom=True)
    box(gs0, gs1, gt1 - 0.32, gt1 - 0.02, p + 3.05, p + 3.3, white, bottom=True)
    for k, (s, t) in enumerate(((4, 31), (12, 36), (20, 31), (28, 36.5), (60, 31), (66, 36), (58, 37.5), (8, 37.5))):
        if k % 2:                                          # granite benches and planted beds as in the renderings
            box(s - 1.3, s + 1.3, t - 0.35, t + 0.35, p - 0.1, p + 0.45, "#cfccc4")
        else:
            box(s - 1.6, s + 1.6, t - 0.8, t + 0.8, p - 0.1, p + 0.4, "#cfccc4")
            for ds in (-0.9, 0.0, 0.9):
                shrub(s + ds, t, p + 0.5, 0.55, "#d9708a" if ds == 0 else "#62873f")
    # broad steps from the court up to the existing entrance level, following the ground in 4 m pieces
    for s0 in np.arange(-6.0, L + 6.0, 4.0):
        top = S.ground(*plan(s0 + 2.0, 43.3))
        if top - p < 0.15:
            continue
        n = math.ceil((top - p) / 0.17)
        for k in range(n):
            box(s0, s0 + 4.0, 39.5 + 3.5 * k / n, 43.0, p - 0.4, p + (top - p) * (k + 1) / n, "#bdb9b0")
    # low granite parapet where the court stands above the side ramps
    for s0, s1 in ((-4.0, 0.7), (L - 0.7, L + 4.0)):
        box(s0, s1, 25.7, 26.0, p - 1.5, p + 0.5, "#cfccc4")
    for s in (-4.0, L + 4.0):
        box(s - 0.15, s + 0.15, 26.0, 39.5, p - 1.5, p + 0.5, "#cfccc4")

    # ---- forecourt trees in front of the glass ---------------------------------------------------
    for s in (1.0, 15.0, 47.0, 59.0):
        tree(s, -4.6, g0, 6.2)

    def fill(poly, kind):
        return {"kind": kind, "rings": site_rings(S, poly)}

    def level(poly, z, ramp, why):
        return {"type": "level", "ring": site_rings(S, poly)[0], "height_m": round(S.gmin + z, 2), "ramp_m": ramp,
                "status": "estimated", "source": why}

    garden = band(gs0, gs1, gt0, gt1)
    court = band(-4.0, L + 4.0, 26.0, 39.5).difference(garden)
    return {
        "masses": masses, "prims": prims, "top_m": round(r + 5.75, 2), "floors": 3,
        "front_bearing": round(front["bearing"], 1), "focus_heading": round((front["bearing"] + 150) % 360, 1),
        "focus_pitch": -18,
        "pavement": [fill(band(-15.0, L + 15.0, -12.0, 26.0), "paving"), fill(band(-15.0, -4.0, 26.0, 43.0), "paving"),
                     fill(band(L + 4.0, L + 15.0, 26.0, 43.0), "paving"), fill(court, "plaza"), fill(garden, "garden")],
        "terrain_mods": [
            level(band(-6.0, L + 6.0, -8.0, 26.0), g0, 3.0, "annex forecourt at the ground-floor level of the renderings"),
            level(band(-4.0, L + 4.0, 26.0, 43.0), p, 0.6, "raised court at floor-2 level behind the annex (renderings)"),
            level(garden, g0, 0.3, "sunken garden at ground-floor level (renderings)"),
        ],
        "name_en": pb["name_en"],
        "appearance": ("under construction (completion planned Dec 2027), modelled from the official renderings: two glazed "
                       "floors under a roof terrace with a fluted white fascia, triple slim columns, planted balcony stair, "
                       "timber-clad floor-3 pavilion, raised stone court with a sunken garden and broad steps to the 1984 building"),
    }


def m_foreign_languages(S):
    """Two rounded wings flanking a stepped, four-level classroom block."""
    front = S.face(97, min_len=18)
    F = edge_frame(front)
    ax, ay = F["ax"]
    x0, y0 = F["off"]
    wall, trim, roof = "#dedfd9", "#e9e8df", "#a3a7a1"
    stone, glass, frame = "#adada6", "#527278", "#3e4f4b"

    def plan(s, t):
        return x0 + ax * s - ay * t, y0 + ay * s + ax * t

    def facade(p):
        e, n = p[0] - x0, p[1] - y0
        return e * ax + n * ay, -e * ay + n * ax

    def band(s0, s1, t0, t1):
        return Polygon([plan(s0, t0), plan(s1, t0), plan(s1, t1), plan(s0, t1)])

    footprint_edge = S.poly.boundary.buffer(0.015)

    def exterior(a, b):
        return footprint_edge.covers(LineString([a, b]))

    def wing_styles(poly):
        # Continue a glazing bay around each rounded end without a seam at every OSM vertex.
        pts = list(poly.exterior.coords)
        span = poly.exterior.length
        phase = 0.0
        styles = []
        for a, b in zip(pts, pts[1:]):
            style = FOREIGN_LANGUAGES_WINDOWS if exterior(a, b) else PLAIN
            styles.append([style, 3.45, 5.8, wall, round(phase, 3), round(span, 3)])
            phase += math.dist(a, b)
        return styles

    def block_styles(poly):
        pts = list(poly.exterior.coords)
        sign = 1 if poly.exterior.is_ccw else -1
        styles = []
        for a, b in zip(pts, pts[1:]):
            length = math.dist(a, b)
            faces_gate = length >= 5 and -(b[0] - a[0]) * sign / length > 0.6
            classroom = faces_gate or min(facade(a)[1], facade(b)[1]) >= 16.65
            styles.append([FOREIGN_LANGUAGES_WINDOWS if classroom and exterior(a, b) else PLAIN, 3.45, 4.15, wall])
        return styles

    # Compute shared edges at the same precision used when exporting the mesh.
    footprint = set_precision(S.poly, 0.001)
    east_wing = footprint.intersection(set_precision(band(-70, 0, -35, 21), 0.001))
    west_wing = footprint.intersection(set_precision(band(-70, 33, 81, 120), 0.001))
    tower = footprint.intersection(set_precision(band(9.8, 17.5, -2, 13.7), 0.001))
    core = footprint.difference(unary_union([east_wing, west_wing, tower]))
    wing_roof = 14.75
    masses = []
    for wing in (east_wing, west_wing):
        masses += mass(wing, -0.85, wing_roof, wall, roof, FOREIGN_LANGUAGES_WINDOWS,
                       floor0=7.1, parapet=0.16, edge_sty=wing_styles)
    masses += mass(core, -0.85, S.H - 1.45, wall, roof, FOREIGN_LANGUAGES_WINDOWS,
                   floor0=5.4, parapet=0.45, edge_sty=block_styles)
    masses += mass(tower, -0.85, S.H, wall, roof, PLAIN, parapet=0.4)

    prims = []

    def add_box(s0, s1, t0, t1, z0, z1, col, **kwargs):
        prims.append(pbox(F, s0, s1, t0, t1, z0, z1, col, **kwargs))

    # Entrance plaza, broad stair and landing under the projecting concrete canopy.
    foot_t, landing_t = -14.6, -8.1
    toe = max(S.ground(*plan(s, t)) for s in (4, 11.6, 19.2) for t in (-17, foot_t)) + 0.035
    landing = toe + 2.89
    add_box(0.6, 21.7, -17.0, foot_t + 0.02, toe - 0.48, toe, "#bbb4a6")
    add_box(3.95, 19.25, landing_t, 0.05, toe - 0.4, landing, stone)
    for i in range(17):
        t0 = foot_t + i * (landing_t - foot_t) / 17
        t1 = foot_t + (i + 1) * (landing_t - foot_t) / 17
        z = toe + (i + 1) * 0.17
        add_box(4.0, 19.2, t0, t1, toe - 0.4, z, stone)
        add_box(4.0, 19.2, t0 - 0.035, t0, z - 0.047, z, "#c7c5bd")

    for s0, s1 in ((1.5, 4.0), (19.2, 21.7)):
        mid = (s0 + s1) / 2
        for i in range(5):
            t0 = foot_t + i * 1.3
            z = toe + (i + 1) * 0.55
            add_box(s0, s1, t0, t0 + 1.3, toe - 0.42, z, trim)
            add_box(s0 + 0.16, s1 - 0.16, t0 + 0.12, t0 + 1.18, z, z + 0.04, "#666951")
            prims.append({"t": "sphere", "ax": F["ax"], "off": F["off"], "s": mid,
                          "t_": t0 + 0.66, "z": round(z + 0.15, 2), "r": 0.88, "sz": 0.58,
                          "jit": 0.09, "col": ("#51642f", "#647238", "#536632")[i % 3]})
        add_box(s0, s1, landing_t, -4.0, toe - 0.42, landing + 0.04, trim)

    # Piers and the glazed vestibule sit back behind the deep fascia.
    canopy = landing + 3.35
    add_box(0.25, 22.15, -8.5, 0.12, canopy, canopy + 1.33, trim, bottom=True)
    for s in (4.2, 19.0):
        add_box(s - 0.46, s + 0.46, -6.85, -5.79, landing, canopy, trim)
    for s in (5.25, 17.95):
        add_box(s - 0.41, s + 0.41, -1.1, -0.13, landing, canopy, trim)
    add_box(5.75, 17.45, -1.27, -0.02, landing + 0.04, canopy - 0.19, "#345152")
    for s in np.linspace(5.75, 17.45, 13):
        add_box(s - 0.035, s + 0.035, -1.33, -1.24, landing + 0.04, canopy - 0.18, frame)
    for z in (landing + 0.12, landing + 2.13, canopy - 0.19):
        add_box(5.75, 17.45, -1.34, -1.24, z - 0.035, z + 0.035, "#8b9189")

    # The left-hand approach remains open under its smaller landing.
    add_box(-2.9, 1.5, -6.2, 0.04, landing - 0.72, landing, trim, bottom=True)
    add_box(-2.9, -2.18, -6.15, -5.32, toe - 0.42, landing - 0.7, trim)
    add_box(-0.96, 1.5, -0.018, 0.06, toe, landing - 0.73, "#343937")
    for i in range(7):
        t = -5.8 + i * 0.34
        add_box(-0.87, 1.48, t, t + 0.34, toe - 0.4, toe + (i + 1) * 0.155, stone)
    add_box(-0.87, 1.48, -3.42, 0.0, toe - 0.4, toe + 1.085, stone)
    add_box(1.05, 6.0, -4.3, 0.1, canopy + 3.12, canopy + 3.6, trim, bottom=True)
    add_box(1.12, 1.72, -3.67, -2.97, canopy + 1.25, canopy + 3.12, wall)

    for z in (canopy + 1.72, canopy + 4.43, canopy + 7.08):
        add_box(11.9, 14.15, -0.035, 0.04, z, z + 1.29, glass)
        add_box(12.96, 13.03, -0.077, -0.024, z, z + 1.29, frame)
        add_box(11.78, 14.27, -0.20, 0.02, z - 0.09, z, trim)

    # The garden-facing walk has rounded openings over a small white balustrade.
    for edge in S.edges():
        sa, ta = facade(edge["a"])
        sb, tb = facade(edge["b"])
        if not (edge["len"] > 12 and 1 < (sa + sb) / 2 < 14 and 23 < (ta + tb) / 2 < 73):
            continue
        E = edge_frame(edge)
        a, b = edge["a"], edge["b"]
        z = max(S.ground(*p) for p in (a, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), b)) + 0.15
        length = edge["len"]
        prims.append(pbox(E, 0, length, -0.75, 0.1, z - 0.26, z, trim))
        bays = 4
        for i in range(bays):
            left, right = i * length / bays, (i + 1) * length / bays
            lo, hi, radius = left + 0.27, right - 0.27, 0.4
            head = [(lo, z + 2.3), (lo + 0.08, z + 2.54), (lo + radius, z + 2.72),
                    (hi - radius, z + 2.72), (hi - 0.08, z + 2.54), (hi, z + 2.3)]
            prims.append(pprofile(E, [(left, z + 2.3), *head, (right, z + 2.3),
                                      (right, z + 3.02), (left, z + 3.02)], -0.72, 0.06, trim))
            prims.append(pbox(E, left, lo, -0.72, 0.06, z, z + 2.3, trim))
            prims.append(pbox(E, hi, right, -0.72, 0.06, z, z + 2.3, trim))
            prims.append(pbox(E, lo, hi, -0.048, 0.02, z + 0.15, z + 2.73, glass))
            for s in np.linspace(lo + 0.48, hi - 0.48, 4):
                prims.append(pbox(E, s - 0.026, s + 0.026, -0.073, -0.042, z + 0.16, z + 2.71, frame))
            prims.append(pbox(E, lo, hi, -0.66, -0.33, z + 0.71, z + 0.88, trim))
            for s in np.linspace(lo + 0.22, hi - 0.22, 8):
                prims.append(pbox(E, s - 0.057, s + 0.057, -0.62, -0.39, z, z + 0.71, trim))

    # Raised letters on the canopy spell 외국어대학관.
    glyphs = (
        ("2,11 4,12 6,11 6,9 4,8 2,9 2,11;4,8 4,4;1,4 8,4;11,13 11,1"),
        ("2,12 10,12 10,10;1,8 12,8;6,8 6,6;2,5 10,5 10,1"),
        ("2,10 4,12 6,10 6,5 4,3 2,5 2,10;6,8 10,8;11,13 11,1"),
        ("6,11 2,11 2,4 6,4;8,13 8,1;8,7 11,7;11,13 11,1"),
        ("4,13 8,13;1,11 11,11;3,8 5,10 8,9 9,7 7,6 4,6 3,8;11,12 11,6;11,9 13,9;2,4 11,4 11,1"),
        ("1,12 7,12 7,10;4,10 4,7;1,7 8,7;10,13 10,5;10,9 13,9;3,5 3,2 11,2"),
    )
    for i, glyph in enumerate(glyphs):
        for path in glyph.split(";"):
            points = [tuple(map(int, point.split(","))) for point in path.split()]
            for (u, v), (q, r) in zip(points, points[1:]):
                s, z = 13.3 + (i - 2.5) * 0.91 + (u - 7) * 0.058, canopy + 1.33 + v * 0.054
                s1, z1 = s + (q - u) * 0.058, z + (r - v) * 0.054
                k = 0.024 / math.hypot(s1 - s, z1 - z)
                ds, dz = -(z1 - z) * k, (s1 - s) * k
                prims.append(pprofile(F, [(s - ds, z - dz), (s1 - ds, z1 - dz),
                                          (s1 + ds, z1 + dz), (s + ds, z + dz)],
                                      -8.46, -8.38, "#a27d3c"))

    # White open balustrades follow the winding roofline; the short interior cuts have solid walls.
    for wing in (east_wing, west_wing):
        pts = list(wing.exterior.coords)
        for a, b in zip(pts, pts[1:]):
            length = math.dist(a, b)
            if length < 0.2 or not exterior(a, b):
                continue
            dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            out = (dy, -dx) if wing.exterior.is_ccw else (-dy, dx)
            E = edge_frame({"a": a, "b": b, "dir": (dx, dy), "out": out, "len": length})
            prims.append(pbox(E, 0, length, -0.14, 0.26, wing_roof + 0.72, wing_roof + 0.94, trim, bottom=True))
            for s in np.linspace(0, length, max(2, round(length / 0.69) + 1))[:-1]:
                prims.append(pbox(E, s - 0.117, s + 0.117, -0.06, 0.2, wing_roof - 0.03, wing_roof + 0.72, trim))

    forecourt = Polygon([plan(s, t) for s, t in
                         ((-0.7, -8), (22, -8), (24, -15), (23, -26), (19, -31),
                          (8, -34), (-1, -31), (-7.5, -22), (-6.1, -15))])
    garden_walk = LineString([plan(s, t) for s, t in
                              ((7.8, 18), (7.1, 31), (0.5, 34), (-0.25, 36), (0, 52.5),
                               (0.45, 56.6), (8.6, 57.2), (8.6, 73), (0.4, 79), (-0.4, 81.4))]).buffer(0.95)
    pavement = []
    for surface in (forecourt, garden_walk):
        open_ground = surface.difference(S.poly)
        parts = [open_ground] if open_ground.geom_type == "Polygon" else open_ground.geoms
        for p in parts:
            if p.area < 0.5:
                continue
            pavement.append({"kind": "plaza", "rings": site_rings(S, p)})

    return {
        "masses": masses, "prims": prims, "pavement": pavement, "top_m": S.H, "floors": 4,
        "front_bearing": round(front["bearing"], 1),
        "focus_heading": round((front["bearing"] + 167) % 360, 1),
        "appearance": ("photo-based model with rounded window bays, open roof balustrades, "
                       "gate-facing classroom windows, a signed entrance canopy, broad stairs, tiered planters and a sheltered side passage"),
    }


def m_electronics(S):
    """Five-storey brick wing around an open court, with a lower uphill annex."""
    front = S.face(1, min_len=66)
    F = edge_frame(front)
    ax, ay = F["ax"]
    e0, n0 = F["off"]
    length, center = F["len"], F["len"] / 2
    brick, roof, annex = "#b0a08a", "#a3a59c", "#ccc8bb"
    concrete, stone, metal = "#b3b1a9", "#a4a29b", "#555c5c"
    glass, frame = "#3f6069", "#39464a"

    def plan(s, t):
        return e0 + ax * s - ay * t, n0 + ay * s + ax * t

    def band(s0, s1, t0, t1):
        return Polygon([plan(s0, t0), plan(s1, t0), plan(s1, t1), plan(s0, t1)])

    def fill(poly, kind):
        return {"kind": kind, "rings": site_rings(S, poly)}

    # The aerial view shows three taller wings and a lower fourth side enclosing an open court.
    east, west, north, south = 23.8, 58.8, 19.2, 52.8
    footprint = set_precision(S.poly, 0.001)
    court = set_precision(band(east, west, north, south), 0.001)
    older = footprint.intersection(set_precision(band(-10, 90, -2, south), 0.001)).difference(court)
    newer = footprint.difference(unary_union([older, court]))
    main_grade = round(S.ground(*plan(center, -8.3)), 2)
    court_grade = round(S.ground(*plan((east + west) / 2, (north + south) / 2)), 2)
    landing = main_grade + 1.12

    def main_styles(poly):
        pts = list(poly.exterior.coords)
        original_edge = S.poly.boundary.buffer(0.018)
        court_edge = court.boundary.buffer(0.018)
        return [[ELECTRONICS_BRICK if any(edge.covers(LineString([a, b]))
                                        for edge in (original_edge, court_edge)) else PLAIN,
                 3.38, length / 19 if math.dist(a, b) > length - 0.1 else 4.1, brick]
                for a, b in zip(pts, pts[1:])]

    masses = mass(older, -1.3, S.H - 0.95, brick, roof, ELECTRONICS_BRICK,
                  fh=3.38, bw=4.1, floor0=landing, parapet=0.32, edge_sty=main_styles)
    annex_sections = [
        (newer.intersection(set_precision(band(-10, 90, -2, 71.7), 0.001)), 16.45),
        (newer.intersection(set_precision(band(-10, 90, 71.7, 85), 0.001)), 17.8),
        (newer.intersection(set_precision(band(-10, 90, 85, 110), 0.001)), 18.6),
    ]
    for section, height in annex_sections:
        masses += mass(section, -1.3, height, annex, "#a7aaa3", MODERN,
                       fh=3.25, bw=4.6, floor0=court_grade + 1.55, parapet=0.45)

    prims = []

    def add_box(s0, s1, t0, t1, z0, z1, col, **kwargs):
        prims.append(pbox(F, s0, s1, t0, t1, z0, z1, col, **kwargs))

    def shrub(E, s, t, z, r, col, squash=0.65):
        prims.append({"t": "sphere", "ax": E["ax"], "off": E["off"], "s": float(s),
                      "t_": t, "z": round(z, 2), "r": r, "sz": squash,
                      "jit": 0.1, "col": col})

    # Roof slab and small rooftop enclosures seen in the aerial image.
    masses += mass(older, S.H - 0.95, S.H, "#a89b8d", roof, PLAIN, parapet=0.18)
    add_box(-0.85, length + 0.85, -1.15, 0.08, S.H - 1.04, S.H, "#938477", bottom=True)
    for s0, s1, t0, t1 in ((12, 18.5, 9.0, 17.6), (63.8, 72.0, 17.8, 25.6)):
        add_box(s0, s1, t0, t1, S.H - 0.25, S.H + 1.2, "#a6a69e")
    for s in np.arange(2.3, 8.6, 1.43):
        for t in np.arange(11.5, 44.5, 3.2):
            add_box(s, s + 0.76, t, t + 2.28, S.H - 0.2, S.H + 0.04, "#848c89")
    for t in (74.4, 78.0):
        add_box(10.5, 56.0, t, t + 0.82, 17.47, 18.05, "#adbbb9")

    # Wide stairs, sloping stone cheek walls and the flared concrete entrance canopy.
    foot, top_step = -8.65, -4.35
    half = 7.05
    add_box(center - half - 0.25, center + half + 0.25, top_step, 0.07,
            main_grade - 1.8, landing, stone)
    for i in range(7):
        t0 = foot + (top_step - foot) * i / 7
        t1 = foot + (top_step - foot) * (i + 1) / 7
        z = main_grade + (i + 1) * 0.16
        add_box(center - half, center + half, t0, t1, main_grade - 1.8, z, stone)
        add_box(center - half, center + half, t0 - 0.034, t0, z - 0.046, z, "#c0bdb4")
    for sign in (-1, 1):
        edge = center + sign * half
        ramp_frame = {"ax": [-ay, ax], "off": plan(edge, 0)}
        lo, hi = sorted((0, -sign * 0.71))
        profile = [(foot - 0.5, main_grade - 0.08), (top_step + 0.15, main_grade - 0.08),
                   (top_step + 0.15, landing + 0.31), (foot - 0.5, main_grade + 0.21)]
        prims.append(pprofile(ramp_frame, profile, lo, hi, "#b8b7af"))
        s0, s1 = sorted((edge - sign * 0.12, edge + sign * 0.78))
        add_box(s0, s1, foot - 0.63, foot + 0.06, main_grade - 0.12, main_grade + 0.38, concrete)

        pier = center + sign * 7.05
        add_box(pier - 0.49, pier + 0.49, -4.99, -4.17, landing, landing + 3.65, concrete)
        for z in np.arange(landing + 0.68, landing + 3.6, 0.68):
            add_box(pier - 0.494, pier + 0.494, -4.996, -4.166, z, z + 0.023, "#8c8983")

        s0, s1 = sorted((center + sign * 8.0, center + sign * 32.5))
        add_box(s0, s1, -5.05, -2.6, main_grade - 0.55, main_grade + 0.64, concrete)
        add_box(s0 + 0.12, s1 - 0.12, -4.92, -2.72, main_grade + 0.64, main_grade + 0.68, "#645e49")
        for k, s in enumerate(np.arange(s0 + 1.8, s1 - 0.8, 2.65)):
            shrub(F, s, -3.72, main_grade + 0.78, 0.7 + (k % 2) * 0.15, "#4e5e3b")

    canopy_z = landing + 3.61
    prims.append(pprofile(F, [(center - 8.03, canopy_z), (center + 8.03, canopy_z),
                              (center + 9.66, canopy_z + 1.52), (center - 9.66, canopy_z + 1.52)],
                          -5.58, 0.08, "#9e9d97"))
    add_box(center - 7.99, center + 7.99, -5.45, 0.06, canopy_z - 0.035, canopy_z,
            "#797972", bottom=True)
    add_box(center - 6.56, center + 6.56, -0.055, 0.03, landing, canopy_z - 0.14, "#333e40")
    for s in np.linspace(center - 6.56, center + 6.56, 13):
        add_box(s - 0.027, s + 0.027, -0.105, -0.052, landing, canopy_z - 0.14, "#a39d83")
    for z in (landing + 0.12, landing + 2.24, canopy_z - 0.15):
        add_box(center - 6.56, center + 6.56, -0.11, -0.05, z, z + 0.054, "#a39d83")

    # Courtyard elevation. This frame faces south, with the glazed stair tower on the left.
    R = {"ax": [-ax, -ay], "off": plan(west, north)}

    def rear_box(s0, s1, t0, t1, z0, z1, col, **kwargs):
        prims.append(pbox(R, s0, s1, t0, t1, z0, z1, col, **kwargs))

    tower_top = S.H + 0.37
    rear_box(0.8, 5.5, -1.6, 0.09, court_grade, tower_top, glass)
    for s in np.linspace(0.8, 5.5, 7):
        rear_box(s - 0.032, s + 0.032, -1.64, -1.574, court_grade, tower_top, "#a6aeac")
    for z in np.arange(court_grade + 0.12, tower_top - 0.06, 1.48):
        rear_box(0.8, 5.5, -1.644, -1.57, z, z + 0.055, "#a6aeac")
    rear_box(0.65, 5.65, -1.75, 0.1, tower_top - 0.23, tower_top + 0.16, concrete)

    rear_box(17.3, 23.65, -0.16, 0.05, court_grade, S.H - 0.95, "#c0b9a9",
             sty=ELECTRONICS_BRICK, fh=3.38, bw=8, floor0=court_grade + 1.6)
    rear_box(17.6, 26.1, -3.23, 0.14, court_grade + 2.65, court_grade + 3.13, metal, bottom=True)
    rear_box(18.35, 24.7, -0.21, 0.025, court_grade + 0.05, court_grade + 2.57, "#364244")
    for s in (18.35, 19.9, 21.5, 23.1, 24.7):
        rear_box(s - 0.028, s + 0.028, -0.25, -0.205, court_grade + 0.05, court_grade + 2.57, "#ada595")
    for s in (18.1, 25.5):
        rear_box(s - 0.18, s + 0.18, -3.05, -2.66, court_grade - 0.12, court_grade + 2.65, metal)

    # Curved green hood, stone planters and small trees beside the rear doors.
    hood_start, hood_end = 6.7, 15.8
    hx, hy = R["ax"]
    re, rn = R["off"]
    Hf = {"ax": [-hy, hx], "off": [re + hx * hood_start, rn + hy * hood_start]}
    arc = [(-2.16 + u * 2.21, court_grade + 2.18 + 0.75 * math.sin(u * math.pi / 2))
           for u in np.linspace(0, 1, 9)]
    hood = arc + [(s, z - 0.075) for s, z in reversed(arc)]
    prims.append(pprofile(Hf, hood, -(hood_end - hood_start), 0, "#405755"))
    for s in np.linspace(0, hood_end - hood_start, 9):
        rib = [(t, z + 0.04) for t, z in arc] + [(t, z - 0.075) for t, z in reversed(arc)]
        prims.append(pprofile(Hf, rib, -s - 0.023, -s + 0.023, "#828d8b"))
    rear_box(6.55, 16.15, -4.4, -0.33, court_grade - 0.3, court_grade + 0.45, "#ada99b")
    rear_box(6.69, 16.01, -4.24, -0.45, court_grade + 0.45, court_grade + 0.485, "#4d5337")
    for k, s in enumerate((8.7, 12.9)):
        h = court_grade + 4.2 + k * 0.35
        prims.append(pcyl(R, s, -3.34, court_grade + 0.48, h, 0.1, "#7a6f5a", r1=0.047, sty=PLAIN, seg=8))
        for ds, z, r in ((-0.7, h - 0.48, 1.03), (0.62, h - 0.32, 1.16), (0, h + 0.28, 1.36)):
            shrub(R, s + ds, -3.34, z, r, "#53633c", 0.86)

    top = round(S.H + 1.2, 2)
    levels = [
        (band(-8, length + 9, -27, 13), main_grade, 7.0),
        (band(east - 5, west + 5, north - 6, south + 6), court_grade, 4.8),
    ]
    grades = [{"type": "level", "ring": site_rings(S, p)[0], "height_m": round(S.gmin + z, 2),
               "ramp_m": ramp, "status": "estimated"} for p, z, ramp in levels]
    apron = band(-0.3, length + 0.3, -19.8, 0.032)
    rear_landing = band(west - 26.6, west - 16.8, north, north + 4.55)
    return {
        "masses": masses, "prims": prims, "top_m": top, "floors": 5,
        "pavement": [{**fill(apron, "asphalt"), "unmarked": True},
                     fill(court, "brick"), fill(rear_landing, "paving")],
        "terrain_mods": grades,
        "open_courtyard": site_rings(S, court)[0],
        "name_en": "College of Electronics Information and Applied Science",
        "front_bearing": round(front["bearing"], 1), "focus_heading": round(front["bearing"] + 189, 1),
        "appearance": ("photo-based five-storey brick frontage with a broad entrance stair and flared canopy, "
                       "an open courtyard with a glazed stair tower, and stepped rear roofs"),
    }


def m_woojungwon(S):
    """Seven-storey dormitory with two courtyards and a glazed east entrance."""
    front = S.face(89, min_len=32)
    F = edge_frame(front)
    ax, ay = F["ax"]
    e0, n0 = F["off"]
    length = F["len"]
    center = length / 2
    cream, roof, jade = "#e5e1d5", "#a49d89", "#5a8078"
    teal, navy, blue = "#4a7980", "#274755", "#365c77"
    glass, mullion, gold = "#3c565a", "#a5afaa", "#bb9859"

    def plan(s, t):
        return e0 + ax * s - ay * t, n0 + ay * s + ax * t

    grade = S.ground(*plan(center, -4.0))
    landing = grade + 0.42
    canopy = grade + 4.23
    sills = grade + 3.72

    def facade_styles(poly):
        points = list(poly.exterior.coords)
        styles = []
        for a, b in zip(points, points[1:]):
            s0, s1 = sorted((p[0] - e0) * ax + (p[1] - n0) * ay for p in (a, b))
            depths = [-(p[0] - e0) * ay + (p[1] - n0) * ax for p in (a, b)]
            main_face = max(map(abs, depths)) < 0.045 and s1 - s0 > length - 0.08
            end_panel = all(6.8 < t < 7.8 for t in depths) and (s1 < -8.7 or s0 > 45.8)
            styles.append([PLAIN if end_panel else WOOJUNGWON_WINDOWS, 3.21,
                           length / 10 if main_face else 3.55, cream])
        return styles

    masses = mass(S.poly, -1.1, S.H - 0.34, cream, roof, WOOJUNGWON_WINDOWS,
                  fh=3.21, bw=3.55, floor0=sills, parapet=0.16, edge_sty=facade_styles)
    masses += mass(S.poly, S.H - 0.34, S.H, "#a5b8ac", roof, PLAIN, parapet=0.16)
    prims = []

    def add_box(s0, s1, t0, t1, z0, z1, col, **kwargs):
        prims.append(pbox(F, s0, s1, t0, t1, z0, z1, col, **kwargs))

    def profile(points, t0, t1, col):
        prims.append(pprofile(F, points, t0, t1, col))

    # Outside the room block, blue columns stand under the long signed canopy.
    add_box(-0.75, length + 0.75, -3.67, 0.09, canopy - 1.31, canopy, teal, bottom=True)
    for z, width in ((canopy - 1.30, 0.12), (canopy - 0.34, 0.08), (canopy - 0.09, 0.26)):
        add_box(-0.91, length + 0.91, -3.88, 0.14, z, z + width, navy, bottom=True)
    add_box(-0.86, length + 0.86, -3.79, 0.14, canopy + 0.17, canopy + 0.22, "#77918c")
    add_box(-0.2, length + 0.2, -0.10, 0.085, landing, canopy - 1.2, "#3b494a")
    for s in np.linspace(0.1, length - 0.1, 26):
        add_box(s - 0.023, s + 0.023, -0.146, -0.092, landing, canopy - 1.28, mullion)
    for z in (landing + 0.07, landing + 1.99, canopy - 1.28):
        add_box(-0.1, length + 0.1, -0.15, -0.091, z - 0.025, z + 0.025, mullion)
    for s in np.linspace(0.17, length - 0.17, 7):
        prims.append(pcyl(F, s, -2.95, landing, canopy - 1.3, 0.29, blue, sty=PLAIN, seg=16))
        prims.append(pcyl(F, s, -2.95, landing, landing + 0.13, 0.335, navy, sty=PLAIN, seg=16))
    add_box(-0.5, length + 0.5, -3.58, 0.07, grade - 0.3, landing, "#aaa9a3")
    for i in range(3):
        t = -4.81 + i * 0.41
        z = grade + (i + 1) * 0.14
        add_box(-0.5, length + 0.5, t, t + 0.41, grade - 0.3, z, "#adaba1")
        add_box(-0.5, length + 0.5, t - 0.035, t, z - 0.033, z, "#c4c0b6")

    # Sage-green pediment, white piers and tall mullioned window above the canopy.
    sill_z, glass_head = canopy + 0.12, grade + 9.84
    profile([(center - 8.16, sill_z), (center + 8.16, sill_z), (center + 8.16, glass_head + 0.47),
             (center, glass_head + 1.09), (center - 8.16, glass_head + 0.47)], -0.39, 0.06, "#92ab91")
    add_box(center - 6.35, center + 6.35, -0.56, -0.36, sill_z, glass_head, "#d6d9cb")
    add_box(center - 5.79, center + 5.79, -0.59, -0.52, sill_z + 0.12, glass_head - 0.34, "#435e68")
    for s in np.linspace(center - 5.76, center + 5.76, 21):
        add_box(s - 0.018, s + 0.018, -0.639, -0.579, sill_z + 0.08, glass_head - 0.34, "#a6b0ae")
    for z in np.linspace(sill_z + 0.06, glass_head - 0.34, 6):
        add_box(center - 5.82, center + 5.82, -0.64, -0.573, z - 0.022, z + 0.022, "#a6b0ae")
    for s in (center - 4.48, center + 4.48):
        add_box(s - 0.245, s + 0.245, -0.69, -0.554, sill_z, glass_head - 0.29, "#d2d5ca")

    def oval(s, z, rx, rz, t, col):
        loop = [(s + rx * math.cos(a), z + rz * math.sin(a))
                for a in np.linspace(0, 2 * math.pi, 20, endpoint=False)]
        profile(loop, t - 0.047, t, col)

    oval(center, glass_head + 0.88, 0.42, 0.49, -0.40, "#e4e4d6")

    # Teal trim surrounds the room facade. The end towers follow the two mapped projections.
    for s0, s1 in ((-0.09, 0.56), (length - 0.56, length + 0.09)):
        add_box(s0, s1, -0.28, 0.085, canopy + 0.02, S.H - 0.13, jade)
    add_box(-0.16, length + 0.16, -0.37, 0.095, S.H - 0.76, S.H + 0.14, jade, bottom=True)
    add_box(-0.19, length + 0.19, -0.41, 0.11, S.H + 0.14, S.H + 0.3, "#d2d6cc")
    tower_top = S.H + 2.65
    for s, t in ((-6.32, 2.97), (42.78, 5.26)):
        prims.append(pcyl(F, s, t + 0.14, grade, S.H - 0.31, 1.63, "#28444f",
                          sty=WOOJUNGWON_GLASS, seg=32))
        add_box(s - 2.61, s + 2.61, t - 1.97, t + 2.61, S.H - 0.35, S.H + 1.57, cream, bottom=True)
        add_box(s - 2.75, s + 2.75, t - 2.04, t + 2.69, S.H + 1.46, S.H + 1.77, jade)
        add_box(s - 2.7, s + 2.7, t + 2.38, t + 8.27, S.H - 0.41, tower_top, "#d9d7ca")
        add_box(s - 2.76, s + 2.76, t + 2.32, t + 8.33, tower_top - 0.11, tower_top + 0.14, "#a5b5a7")
        for offset in (-1.65, 0.55):
            add_box(s + offset, s + offset + 0.47, t - 1.99, t - 1.94,
                    S.H + 0.67, S.H + 1.1, "#4e5d5a")
    for s, t in ((-15.7, 7.1), (50.6, 7.42)):
        add_box(s - 0.22, s + 0.22, t - 0.23, t + 0.07, grade + 0.44, S.H - 0.19, jade)

    # The entrance name and the smaller vertical Hangul sign are raised from their mounting planes.
    glyphs = {
        "D": ".16,.06 .16,.92 .48,.92 .79,.78 .86,.51 .8,.23 .53,.06 .16,.06",
        "E": ".82,.92 .17,.92 .17,.06 .83,.06;.17,.51 .7,.51",
        "G": ".87,.82 .65,.94 .36,.94 .16,.75 .12,.43 .22,.16 .46,.05 .82,.16 .82,.46 .54,.46",
        "H": ".15,.06 .15,.93;.83,.06 .83,.93;.15,.49 .83,.49",
        "I": ".25,.93 .75,.93;.5,.93 .5,.06;.25,.06 .75,.06",
        "K": ".15,.06 .15,.93;.83,.93 .17,.44;.47,.64 .87,.06",
        "M": ".11,.06 .11,.93 .5,.38 .89,.93 .89,.06",
        "N": ".13,.06 .13,.93 .85,.06 .85,.93",
        "O": ".36,.93 .64,.93 .86,.75 .9,.49 .84,.23 .64,.06 .36,.06 .15,.24 .1,.49 .15,.75 .36,.93",
        "R": ".16,.06 .16,.93 .59,.93 .81,.8 .81,.62 .6,.48 .16,.48;.54,.48 .89,.06",
        "S": ".85,.83 .63,.94 .36,.93 .17,.8 .15,.64 .28,.53 .69,.43 .84,.29 .81,.17 .62,.06 .33,.06 .13,.17",
        "T": ".08,.93 .92,.93;.5,.93 .5,.06",
        "U": ".14,.93 .14,.29 .25,.1 .5,.05 .75,.1 .86,.3 .86,.93",
        "V": ".1,.93 .49,.06 .9,.93",
        "Y": ".08,.93 .5,.5 .92,.93;.5,.5 .5,.06",
        "우": ".31,.72 .34,.9 .65,.9 .7,.72 .62,.6 .38,.6 .31,.72;.11,.47 .89,.47;.5,.47 .5,.08",
        "정": ".1,.9 .53,.9;.32,.9 .32,.73 .09,.55;.32,.73 .52,.57;.53,.73 .78,.73;.79,.94 .79,.5;"
             ".39,.25 .46,.42 .7,.42 .8,.26 .74,.12 .5,.09 .39,.25",
        "원": ".15,.78 .22,.92 .44,.92 .51,.78 .44,.66 .21,.67 .15,.78;.08,.56 .59,.56;.34,.56 .34,.35;"
             ".81,.96 .81,.35;.58,.43 .81,.43;.26,.33 .26,.09 .84,.09",
    }

    def glyph(letter, s, z, width, height, t, col):
        for path in glyphs[letter].split(";"):
            points = [tuple(map(float, p.split(","))) for p in path.split()]
            for (u, v), (q, r) in zip(points, points[1:]):
                a = (s + u * width, z + v * height)
                b = (s + q * width, z + r * height)
                stroke = LineString([a, b]).buffer(height * 0.051, cap_style=2)
                profile(list(stroke.exterior.coords)[:-1], t - 0.031, t, col)

    name = "KYUNG HEE UNIVERSITY DORMITORY"
    for i, letter in enumerate(name):
        if letter != " ":
            glyph(letter, center + (i - len(name) / 2) * 0.56, canopy - 0.97, 0.5, 0.54, -3.68, gold)
    for i, letter in enumerate("우정원"):
        glyph(letter, 47.35, grade + 14.53 - i * 0.96, 0.82, 0.86, 7.355, "#3f3f3c")
    oval(47.77, grade + 16.28, 0.5, 0.5, 7.36, "#906c46")
    oval(47.77, grade + 16.28, 0.32, 0.32, 7.306, gold)

    # Small roof vents follow the long side wings without bridging the two courts.
    for s in (-10.7, 45.5):
        for t in np.arange(14.0, 90, 6.3):
            if S.poly.contains(Point(*plan(s, t)).buffer(0.92)):
                add_box(s - 0.46, s + 0.46, t - 0.43, t + 0.43, S.H - 0.17, S.H + 0.27, "#8e9a94")
                add_box(s - 0.37, s + 0.37, t - 0.32, t + 0.32, S.H + 0.27, S.H + 0.35, "#6c807e")

    pavement = []
    for ring in S.poly.interiors:
        court = Polygon(ring)
        pavement.append({"kind": "plaza", "rings": site_rings(S, court)})
        # The gate-side aerial shows paved courts with narrow planting strips.
        x, y = court.representative_point().coords[0]
        for offset in (-1.0, 2.5):
            planter = box(x + offset - 0.55, y - 4.2, x + offset + 0.55, y + 4.2)
            if court.buffer(-1.2).covers(planter):
                pavement.append({"kind": "garden", "rings": site_rings(S, planter)})

    return {
        "masses": masses, "prims": prims, "pavement": pavement, "top_m": round(tower_top + 0.14, 2),
        "floors": 7, "name_en": "Woojungwon Dormitory", "front_bearing": round(front["bearing"], 1),
        "focus_heading": round((front["bearing"] + 170) % 360, 1),
        "appearance": ("photo-based seven-storey dormitory with twin curved glass towers, a signed teal canopy, "
                       "a pediment above the entrance, and two paved courtyards with planting strips"),
    }


class Frontage:
    """Detail geometry along a mapped footprint edge."""

    def __init__(self, site, edge, prims):
        self.site, self.prims = site, prims
        self.frame = edge_frame(edge)
        self.length = self.frame["len"]

    def plan(self, s, t):
        ux, uy = self.frame["ax"]
        x, y = self.frame["off"]
        return x + s * ux - t * uy, y + s * uy + t * ux

    def box(self, s0, s1, t0, t1, z0, z1, color, **kwargs):
        self.prims.append(pbox(self.frame, s0, s1, t0, t1, z0, z1, color, **kwargs))

    def glass(self, s0, s1, t, z0, z1, panes, color="#436267", rows=1, trim="#647170"):
        self.box(s0, s1, t, t + 0.14, z0, z1, color, sty=GLASS)
        for s in np.linspace(s0, s1, panes + 1):
            self.box(s - 0.032, s + 0.032, t - 0.045, t + 0.025, z0, z1, trim)
        for z in np.linspace(z0, z1, rows + 1):
            self.box(s0, s1, t - 0.05, t + 0.03, z - 0.034, z + 0.034, trim)

    def steps(self, s0, s1, t0, t1, grade, rise, count):
        tread = (t1 - t0) / count
        for i in range(count):
            t = t0 + tread * i
            self.box(s0, s1, t, t + tread, grade - 0.36, grade + rise * (i + 1) / count, "#aaa7a0")

    def grade(self, reach):
        return float(np.median([self.site.ground(*self.plan(self.length / 2 + ds, -reach)) for ds in (-3, 0, 3)]))

    def apron(self, s0, s1, t0, t1, grade, ramp):
        poly = Polygon([self.plan(s, t) for s, t in ((s0, t0), (s1, t0), (s1, t1), (s0, t1))])
        return {"type": "level", "ring": site_rings(self.site, poly)[0], "height_m": round(self.site.gmin + grade, 2),
                "ramp_m": ramp, "status": "estimated", "source": "entrance grade estimated from the local DTM and photographs"}


def facade_model(masses, prims, front, top, floors, appearance):
    return {"masses": masses, "prims": prims, "top_m": round(top, 2), "floors": floors,
            "front_bearing": round(front["bearing"], 1), "focus_heading": round((front["bearing"] + 180) % 360, 1),
            "appearance": appearance}


def m_emart(S):
    """Hillside shop beside Renaissance Park, visible in the gate-side aerial."""
    front = S.face(222, min_len=10)
    prims = []
    F = Frontage(S, front, prims)
    length, grade = F.length, F.grade(2)
    wall, green, pale = "#deded5", "#679279", "#e7e7dd"
    roof = S.H - 0.56
    masses = mass(S.poly, -1.5, roof, wall, green, PLAIN, parapet=0.23)
    cap = S.poly.intersection(Polygon([F.plan(s, t) for s, t in ((0, 8.8), (length, 8.8), (length, 34), (0, 34))]))
    masses += mass(cap, roof - 0.28, S.H, pale, pale, PLAIN, parapet=0.16)
    for edge in (front, S.face(312, min_len=12), S.face(132, min_len=17)):
        side = Frontage(S, edge, prims)
        side.glass(0.9, side.length - 0.9, -0.14, grade + 4.0, grade + 5.84,
                   max(4, round(side.length / 1.5)), "#627776", trim="#b9beb2")
    F.glass(1.0, length - 1.05, -0.18, grade + 0.38, grade + 2.75, 8, rows=2)
    F.box(0.52, length - 0.5, -1.24, 0.04, grade + 3.18, grade + 3.59, "#444947", bottom=True)
    F.box(2.1, length - 2.15, -1.27, -1.22, grade + 3.28, grade + 3.48, "#d8ad3a")
    F.steps(1.0, length - 0.8, -1.92, 0, grade, 0.38, 3)
    return facade_model(masses, prims, front, S.H, 2,
                        "hillside shop with green and cream roof sections from the campus aerial and an estimated storefront facing Woojungwon")


def m_second_dormitory(S):
    """Shared façade materials with documented storey counts for A and B."""
    tower_b = S.id == "relation/6739958"
    floors = 13 if tower_b else 10
    front = S.face(41 if tower_b else 85, min_len=35)
    prims = []
    F = Frontage(S, front, prims)
    length, grade = F.length, F.grade(4.2)
    landing = grade + (0.72 if tower_b else 1.02)
    room_height = 2.91
    floor0 = landing + 3.14
    top = floor0 + (floors - 1) * room_height + 0.34
    wall, base, frame = "#a5a397", "#d3d1c5", "#b7b6a9"
    cap = "#926653" if tower_b else "#626b63"
    masses = mass(S.poly, -1.5, top - 0.31, wall, "#92938a", DORM_WINDOWS,
                  fh=room_height, bw=3.9, floor0=floor0, parapet=0.35)
    masses += mass(S.poly, top - 0.31, top, cap, "#92938a", PLAIN, parapet=0.05)
    for edge in (e for e in S.edges() if e["len"] >= 25):
        side = Frontage(S, edge, prims)
        for s in (0.62, side.length - 4.69):
            z0 = S.ground(*side.plan(s + 2.0, -0.5)) - 0.25
            side.box(s, s + 4.05, -0.52, 0.07, z0, top - 0.34, "#6b8b90", sty=GLASS)
            for pos in np.linspace(s, s + 4.05, 5):
                side.box(pos - 0.029, pos + 0.029, -0.57, -0.50, z0, top - 0.34, frame)
            for z in np.arange(floor0 - 2 * room_height, top - 0.48, room_height / 3):
                if z > z0:
                    side.box(s, s + 4.05, -0.58, -0.48, z, z + 0.06, "#919c99")
    s0, s1 = 5.15, length - 5.15
    F.box(s0, s1, -0.15, 0.06, landing, floor0 + 0.02, base)
    F.box(s0 - 1.55, s1 + 1.55, -3.35, 0.12, floor0 - 0.05, floor0 + 0.67, base, bottom=True)
    F.box(s0 - 1.68, s1 + 1.68, -3.48, 0.15, floor0 + 0.60, floor0 + 0.77, frame)
    width = (s1 - s0 - 1.3) / 6
    for pos in np.linspace(s0 + 0.65, s1 - 0.65, 7)[:-1]:
        F.glass(pos, pos + width - 0.31, -0.23, landing + 0.04, floor0 - 0.2, 4, rows=3, trim=frame)
    F.steps(s0 - 0.2, s1 + 0.2, -3.55, -1.18, grade, landing - grade, 5 if tower_b else 7)
    F.box(s0 - 0.2, s1 + 0.2, -1.18, 0.06, grade - 0.36, landing, base)
    model = facade_model(masses, prims, front, top, floors,
                         f"photo-based {floors}-storey residence with recessed room windows, glazed corners and a broad entrance canopy")
    model["terrain_mods"] = [F.apron(s0 - 3.1, s1 + 3.1, -7.0, 2.0, grade, 2.8)]
    return model


def m_multimedia(S):
    front = S.face(86, min_len=65)
    prims = []
    F = Frontage(S, front, prims)
    length, grade = F.length, F.grade(5.4)
    c, landing = length / 2, grade + 1.19
    floor_height, floors = 3.34, 9
    wall, pier, roof = "#bfbab4", "#a8a5a4", "#96918a"
    top = S.H
    bays = 11

    def styles(poly):
        points = list(poly.exterior.coords)
        return [[PLAIN if math.dist(a, b) > 70 else ELECTRONICS_BRICK, floor_height, 6.4, wall]
                for a, b in zip(points, points[1:])]

    masses = mass(S.poly, -1.6, top, wall, roof, ELECTRONICS_BRICK,
                  fh=floor_height, bw=6.4, floor0=landing, parapet=1.0, edge_sty=styles)
    for s in np.linspace(1.1, length - 1.1, bays + 1):
        F.box(s - 0.30, s + 0.30, -0.31, 0.08, landing, landing + 7 * floor_height + 0.88, pier)
    bay = (length - 2.2) / bays
    for i in range(bays):
        s = 1.1 + bay * i
        for level in range(1, 7):
            z = landing + floor_height * level + 1.04
            F.glass(s + 0.56, s + bay - 0.56, -0.21, z, z + 1.26, 6, "#446e73", rows=2, trim="#526769")
        if abs(s + bay / 2 - c) > 12:
            F.glass(s + 0.66, s + bay - 0.65, -0.20, landing + 0.66, landing + 2.73, 5, rows=2)
    for z, high in ((landing + 7 * floor_height + 1.05, 1.34), (top - 3.05, 0.89)):
        F.glass(1.2, length - 1.2, -0.23, z, z + high, 52, "#48757b", rows=2)
    F.box(0, length, -0.35, 0.04, top - 1.25, top - 0.86, pier)
    F.glass(c - 9.8, c + 9.8, -0.30, landing, landing + 3.24, 15, rows=3, trim="#a6a79a")
    F.box(c - 12.1, c + 12.1, -3.45, 0.12, landing + 3.24, landing + 4.10, "#515852", bottom=True)
    for x, drift in ((c - 10.5, -0.78), (c + 10.5, 0.78)):
        prims.append(pprofile(F.frame, [(x - 0.32, landing), (x + 0.32, landing),
                                       (x + drift + 0.36, landing + 3.24), (x + drift - 0.36, landing + 3.24)],
                              -2.65, -1.97, pier))
    F.steps(c - 12.5, c + 12.5, -5.2, -0.15, grade, landing - grade, 7)
    model = facade_model(masses, prims, front, top, floors,
                         "photo-based tall stone facade with teal ribbon windows, a dark canopy, angled supports and broad steps")
    model["terrain_mods"] = [F.apron(c - 15.0, c + 15.0, -9.2, 1.5, grade, 2.7)]
    return model


def m_global_hall(S):
    front = S.face(176, min_len=23)
    prims = []
    F = Frontage(S, front, prims)
    c, grade = F.length * 0.69, F.grade(3.5)
    landing = grade + 0.91
    wall, roof = "#b7ad96", "#a09b8d"
    masses = mass(S.poly, -1.25, S.H, wall, roof, ENGINEERING_WING, fh=3.2, bw=4.2, floor0=grade, parapet=0.65)
    F.box(0.05, F.length - 0.05, -0.12, 0.04, landing + 3.35, S.H - 0.3, wall)
    F.glass(c - 2.55, c + 2.55, -0.18, landing, landing + 2.62, 6, rows=2, trim="#929a8c")
    F.box(c - 3.7, c + 3.7, -3.1, 0.05, landing + 2.7, landing + 3.27, "#50524a", bottom=True)
    F.steps(c - 3.5, c + 3.5, -3.78, -0.16, grade, landing - grade, 6)
    F.box(c + 3.5, c + 3.62, -3.8, -1.0, grade + 0.85, grade + 0.94, "#b5b7b1")
    for t in (-3.7, -2.6, -1.4):
        F.box(c + 3.52, c + 3.60, t, t + 0.06, grade + 0.18, grade + 0.87, "#b5b7b1")
    model = facade_model(masses, prims, front, S.H, 4,
                         "photo-based beige hall with a recessed entrance, dark canopy, glazed doors and steps beside the access lane")
    model["focus_heading"] = round((front["bearing"] + 157) % 360, 1)
    model["focus_pitch"] = -65  # a low approach is screened by the adjacent dormitory
    return model


def m_student_union(S):
    front = min((edge for edge in S.edges() if 160 <= edge["bearing"] <= 200 and edge["len"] >= 14),
                key=lambda edge: (edge["a"][1] + edge["b"][1]) / 2)
    prims = []
    F = Frontage(S, front, prims)
    c, grade = F.length / 2, F.grade(6.0)
    landing, wall, trim = grade + 1.42, "#ded7ca", "#bd9e8d"
    top = S.H
    masses = mass(S.poly, -1.55, top - 0.3, wall, "#a69e91", ENGINEERING_WING,
                  fh=3.55, bw=4.2, floor0=landing, parapet=0.55)
    masses += mass(S.poly, top - 0.30, top, trim, "#aaa296", PLAIN, parapet=0.6)
    for rank in (0, 2):
        side = Frontage(S, S.face(180, min_len=14, rank=rank), prims)
        side.box(0, side.length, -0.13, 0.07, landing - 0.4, top - 0.33, wall)
        side.glass(0.7, side.length - 0.7, -0.20, landing + 0.93, landing + 3.62, 12, rows=3)
        side.glass(0.7, side.length - 0.7, -0.20, top - 3.79, top - 2.27, 12, rows=2)
        side.box(0, 0.4, -0.24, 0.07, landing - 0.70, top, trim)
    F.glass(c - 7.0, c + 7.0, -0.19, landing, landing + 3.74, 11, rows=3, color="#405959")
    F.box(c - 9.2, c + 9.2, -1.43, 0.12, landing + 3.74, landing + 5.17, wall, bottom=True)
    F.box(c - 7.36, c + 7.36, -0.17, 0.04, landing + 5.16, top - 0.3, wall)
    for s in (c - 7.54, c + 7.54):
        F.box(s - 0.39, s + 0.39, -1.22, 0.07, landing, landing + 3.74, trim)
    F.steps(c - 9.7, c + 9.7, -4.35, -0.13, grade, landing - grade, 9)
    top_block = S.poly.intersection(Polygon([F.plan(s, t) for s, t in
                                      ((c - 5, 8), (c + 5, 8), (c + 5, 17), (c - 5, 17))]))
    masses += mass(top_block, top - 0.7, top + 1.85, trim, "#b2a99c", MODERN, fh=2.3, bw=7, floor0=top - 0.5, parapet=0.26)
    model = facade_model(masses, prims, front, top + 1.85, 3,
                         "photo-based brick front with two long window bands, a glazed central entrance and wide steps facing the plaza")
    approach = Polygon([F.plan(s, t) for s, t in
                        ((c - 10.3, -7.35), (c + 10.3, -7.35), (c + 10.3, 0.1), (c - 10.3, 0.1))]).difference(S.poly)
    model["pavement"] = [{"kind": "paving", "rings": site_rings(S, part)}
                          for part in (approach.geoms if approach.geom_type == "MultiPolygon" else [approach])]
    model["terrain_mods"] = [F.apron(c - 12.0, c + 12.0, -8.5, 2.0, grade, 2.8)]
    return model


def m_portal_hall(S):
    """Academic halls with matching deep brick entry frames."""
    business = S.id == "way/474085539"
    front = S.face(181 if business else 1, min_len=45)
    prims = []
    F = Frontage(S, front, prims)
    c, grade = F.length / 2, F.grade(3.75)
    landing = grade + 0.91
    brick, panel = "#a78575", "#d4c9b6"
    top = S.H
    run = 13.6 if business else 14.8
    masses = mass(S.poly, -1.45, top - 0.31, panel, "#a29a90", ENGINEERING_WING,
                  fh=3.52, bw=5.25, floor0=landing, parapet=0.56)
    for x in (c - run, c + run - 2.25):
        F.box(x, x + 2.25, -1.13, 0.12, landing - 0.30, top, brick)
    F.box(c - run, c + run, -1.15, 0.14, top - 1.82, top, brick, bottom=True)
    for offset in (0.21, 0.46, 0.69):
        for s in (c - run + 2.22 + offset, c + run - 2.22 - offset):
            F.box(s - 0.044, s + 0.044, -1.10 + offset, 0.03, landing, top - 1.85 + offset, "#a48b7c")
        F.box(c - run + 2.16, c + run - 2.16, -1.11 + offset, 0.04, top - 1.88 + offset, top - 1.79 + offset,
              "#a48b7c", bottom=True)
    lo, hi = c - run + 2.95, c + run - 2.95
    F.box(lo - 0.2, hi + 0.2, -0.10, 0.06, landing, top - 1.82, panel)
    for z, height in ((landing + 0.02, 2.55), (landing + 4.07, 1.53), (landing + 7.62, 1.54)):
        F.glass(lo, hi, -0.18, z, z + height, 16, rows=2, trim="#7c8176")
    F.steps(lo - 1.3, hi + 1.3, -3.35, -0.16, grade, landing - grade, 6)
    return facade_model(masses, prims, front, top, 3,
                        "photo-based stepped brick portal around horizontal window bands, glazed entrance and stone approach")


def m_physical_education(S):
    """West-facing stone colonnade, broad stairs and slightly lower side wings."""
    front = S.face(265, min_len=30)
    prims = []
    F = Frontage(S, front, prims)
    grade = F.grade(10)
    landing = grade + 2.03
    stone, trim, roof = "#dbd4c2", "#eee8d6", "#a99e85"
    top, wing_top = S.H, S.H - 1.8
    cornice = top - 3.25

    def styles(poly):
        points = list(poly.exterior.coords)
        sign = 1 if poly.exterior.is_ccw else -1
        return [[PLAIN if sign * (b[1] - a[1]) < -2 else ENGINEERING_WING, 3.8, 4.3, stone]
                for a, b in zip(points, points[1:])]

    masses = mass(S.poly, -1.55, wing_top, stone, roof, ENGINEERING_WING,
                  fh=3.8, bw=4.3, floor0=landing, parapet=0.35, edge_sty=styles)
    core = S.poly.intersection(Polygon([F.plan(s, t) for s, t in
                                        ((0, -0.2), (F.length, -0.2), (F.length, 67), (0, 67))]))
    masses += mass(core, wing_top - 0.45, top, stone, roof, PLAIN, parapet=0.32)
    for rank, count in enumerate((13, 8, 8)):
        colonnade = Frontage(S, S.face(265, min_len=30, rank=rank), prims)
        length = colonnade.length
        col_start = landing if rank == 0 else colonnade.grade(7.6) + 1.42
        entablature = cornice - (1.55 if rank else 0)
        eave = top if rank == 0 else wing_top
        for z, thickness, setback in ((entablature - 0.24, 0.24, 4.6), (entablature, 0.78, 4.48),
                                      (entablature + 0.78, 0.2, 4.82), (eave - 0.40, 0.38, 0.77)):
            colonnade.box(-0.31, length + 0.31, -setback, 0.12, z, z + thickness, trim, bottom=True)
        colonnade.box(0, length, -4.35, 0.08, entablature - 0.16, entablature, "#d5ccb8", bottom=True)
        for s in np.linspace(1.58, length - 1.58, count):
            colonnade.box(s - 0.64, s + 0.64, -4.04, -2.78, col_start - 0.19, col_start + 0.21, trim)
            prims.append(pcyl(colonnade.frame, s, -3.42, col_start + 0.21, entablature - 0.63, 0.47, trim, r1=0.39, seg=22))
            colonnade.box(s - 0.56, s + 0.56, -4.02, -2.84, entablature - 0.67, entablature, trim)
        bay = (length - 2.3) / count
        for i in range(count):
            s = 1.15 + bay * (i + 0.5)
            colonnade.glass(s - 0.79, s + 0.79, -0.12, col_start + 4.02, col_start + 6.16,
                            2, "#52676a", trim="#888e83")
            if rank or abs(s - length / 2) > 3:
                colonnade.glass(s - 0.7, s + 0.7, -0.13, col_start + 0.68, col_start + 2.98,
                                2, "#475e61", trim="#7d867e")
            arch = col_start + 8.75
            profile = [(s - 0.78, arch - 1.02), (s + 0.78, arch - 1.02)] + [
                (s + 0.78 * math.cos(a), arch + 0.67 * math.sin(a)) for a in np.linspace(0, math.pi, 13)]
            prims.append(pprofile(colonnade.frame, profile, -0.16, -0.05, "#44504d"))
            colonnade.glass(s - 0.72, s + 0.72, -0.14, eave - 2.02, eave - 0.91, 2, "#52696a", trim=stone)
        colonnade.box(-0.3, length + 0.3, -5.75 if not rank else -4.56, 0.13,
                      col_start - 1.82, col_start, stone)
    F.glass(F.length / 2 - 3.25, F.length / 2 + 3.25, -0.21, landing + 0.035, landing + 3.38,
            7, "#365a61", rows=2, trim="#97998a")
    F.steps(1.0, F.length - 1.0, -10.4, -5.75, grade, landing - grade, 13)
    for s in (1.31, F.length - 1.31):
        F.box(s - 0.7, s + 0.7, -9.9, -8.14, grade - 0.12, grade + 1.32, "#bdb7a9")
        F.box(s - 0.81, s + 0.81, -10.0, -8.04, grade + 1.27, grade + 1.46, stone)
        # The two facing stone lions in the entrance photographs.
        statue_base = grade + 1.45
        for offset in (-0.22, 0.22):
            prims.append(pcyl(F.frame, s + offset, -9.23, statue_base, statue_base + 0.62,
                              0.12, stone, r1=0.14, sty=PLAIN, seg=10))
        parts = [(0, 0.32, 0.36, 0.43, 0.84), (0, 0.07, 0.60, 0.36, 1.44),
                 (0, -0.13, 0.98, 0.37, 1.04), (0, -0.34, 1.14, 0.26, 0.9),
                 (0, -0.51, 1.07, 0.16, 0.67)]
        for side in (-1, 1):
            parts += [(side * 0.22, -0.38, 0.1, 0.16, 0.62),
                      (side * 0.19, -0.25, 1.29, 0.082, 1.23)]
        for ds, dt, z, r, sz in parts:
            prims.append({"t": "sphere", "ax": F.frame["ax"], "off": F.frame["off"], "s": round(s + ds, 3),
                          "t_": -9.0 + dt, "z": round(statue_base + z, 2), "r": r, "sz": sz,
                          "jit": 0.065, "col": stone, "sty": PLAIN})
    model = facade_model(masses, prims, front, top, 4,
                         "photo-based Classical stone colonnade, arched upper windows, broad entrance steps and stylised stone lions")
    model["terrain_mods"] = [F.apron(-3, F.length + 3, -13.3, -4.5, grade, 2.7)]
    forecourt = Polygon([F.plan(s, t) for s, t in ((-2, -15.8), (F.length + 2, -15.8),
                                                   (F.length + 2, -4.5), (-2, -4.5))])
    model["pavement"] = [{"kind": "paving", "rings": site_rings(S, forecourt)}]
    return model


def gabled_roof(F, depth, eave, ridge, color):
    """A low gable whose ridge follows the long edge of a rectangular building."""
    ax, ay = F.frame["ax"]
    across = {"ax": [-ay, ax], "off": F.plan(F.length, 0)}
    return pprofile(across, [(-0.30, eave - 0.15), (depth + 0.30, eave - 0.15),
                             (depth + 0.30, eave), (depth / 2, ridge), (-0.30, eave)],
                    -0.28, F.length + 0.28, color)


def depth_from(F, poly):
    x, y = F.frame["off"]
    ax, ay = F.frame["ax"]
    return max((px - x) * -ay + (py - y) * ax for px, py in poly.exterior.coords)


def m_ceramics(S):
    front = S.face(259, min_len=25)
    prims = []
    F = Frontage(S, front, prims)
    grade = F.grade(4.8)
    main = grade + 1.05
    brick, trim = "#a05b48", "#d6c9ad"
    top = S.H
    masses = mass(S.poly, -1.5, top - 0.55, brick, "#47545e", PLAIN, parapet=0.15)
    prims.append(gabled_roof(F, depth_from(F, S.poly), top - 0.48, top, "#41494f"))
    F.box(0, F.length, -0.13, 0.03, -0.45, main - 0.1, "#bab7aa", sty=ENGINEERING_WING, fh=3.1, bw=6)
    for i, s in enumerate(np.linspace(4.4, F.length - 4.4, 5)):
        F.box(s - 0.73, s + 0.73, -0.18, 0.08, main + 0.1, top - 1.11, trim)
        for row, z in enumerate(np.arange(main + 0.33, top - 1.30, 0.42)):
            # Small patterned ceramic insets on the five vertical façade panels.
            span = 0.39 if row % 2 else 0.52
            color = ("#6a7672", "#a48662", "#b1a894")[(i + row) % 3]
            prims.append(pprofile(F.frame, [(s - span, z), (s, z + 0.18), (s + span, z), (s, z - 0.18)],
                                  -0.205, -0.176, color))
    for s in np.linspace(1.9, F.length - 1.9, 6):
        for z in (main + 1.0, top - 3.44):
            F.glass(s - 1.25, s + 1.25, -0.12, z, z + 1.56, 3)
    c = F.length / 2
    F.glass(c - 1.45, c + 1.45, -0.22, main, main + 2.39, 3, rows=2)
    F.steps(c - 2.0, c + 2.0, -3.4, -0.12, grade, main - grade, 7)
    E = Frontage(S, S.face(169, min_len=15), prims)
    E.glass(2.1, 8.3, -0.19, E.grade(2.0) + 0.3, top - 1.4, 4, rows=7, trim="#a3a5a0")
    model = facade_model(masses, prims, front, top, 3,
                         "red-brick Ceramics Hall with ceramic panels, two rows of windows, a glazed end bay and hillside steps")
    apron = Polygon([F.plan(s, t) for s, t in ((-0.2, -6.5), (F.length + 0.2, -6.5),
                                               (F.length + 0.2, 0), (-0.2, 0))])
    model["pavement"] = [{"kind": "paving", "rings": site_rings(S, apron)}]
    return model


def m_horticulture(S):
    front = S.face(181, min_len=12)
    prims = []
    F = Frontage(S, front, prims)
    stone, glass, trim = "#8e8d81", "#8ca8a8", "#ced6cc"
    top, deck = S.H, S.H - 3.0
    masses = mass(S.poly, -1.3, deck, stone, "#9b9a8f", 5, parapet=0.22)
    north = Frontage(S, S.face(2, min_len=35), prims)
    # Several shallow glazed pavilion bays on the masonry roof deck.
    for a, b in ((1.3, 12.1), (12.6, 24.7), (28.5, north.length - 1.25)):
        north.box(a, b, 0.80, 7.25, deck - 0.15, top - 1.25, glass, sty=GLASS)
        section = {"ax": [-north.frame["ax"][1], north.frame["ax"][0]], "off": north.plan(b, 0)}
        prims.append(pprofile(section, [(0.77, top - 1.25), (7.28, top - 1.25), (4.02, top)],
                              -0.04, b - a + 0.04, "#a9bcba"))
        for s in np.arange(a + 0.13, b, 1.42):
            north.box(s - 0.035, s + 0.035, 0.72, 0.82, deck, top - 1.14, trim)
            prims.append(pprofile(section, [(0.76, top - 1.22), (4.02, top + 0.07), (7.29, top - 1.22),
                                           (7.29, top - 1.33), (4.02, top - 0.06), (0.76, top - 1.33)],
                                  b - s - 0.035, b - s + 0.035, trim))
    g = F.grade(2.5)
    F.glass(3.1, min(F.length - 0.85, 10.4), -0.14, g + 0.76, g + 2.68, 7, rows=2, trim=trim)
    E = Frontage(S, S.face(91, min_len=15), prims)
    E.glass(E.length - 4.2, E.length - 2.1, -0.12, E.grade(2.0) + 0.3, deck - 0.65, 2, rows=3, trim=trim)
    return facade_model(masses, prims, front, top, 2,
                        "stepped grey masonry horticulture building with glazed greenhouses on its roof deck")


def m_life_sciences(S):
    front = S.face(2, min_len=40)
    prims = []
    F = Frontage(S, front, prims)
    grade = F.grade(5.5)
    landing = grade + 0.63
    cream, ochre, roof = "#d9d4c0", "#b5a078", "#c8c4b7"
    top = S.H
    north = Polygon([F.plan(s, t) for s, t in ((0, -0.2), (F.length, -0.2), (F.length, 28), (0, 28))])
    high = S.poly.intersection(north)
    low = S.poly.difference(high)
    masses = mass(high, -1.55, top, cream, roof, ENGINEERING_WING, fh=3.3, bw=6.1, floor0=landing, parapet=0.6)
    masses += mass(low, -1.55, top - 2.75, cream, roof, ENGINEERING_WING, fh=3.3, bw=6.1, floor0=landing, parapet=0.56)
    # Honey-coloured brick volumes flank the recessed north entrance.
    c = F.length * 0.63
    F.box(c + 3.8, min(F.length - 0.18, c + 16.2), -0.46, 0.12, landing - 0.7, top - 0.06, ochre)
    for z in (landing + 2.55, landing + 6.1, landing + 9.55):
        F.glass(c + 5.28, c + 6.27, -0.52, z, z + 1.5, 2, "#3e666c")
    F.glass(c - 4.6, c + 3.1, -0.53, landing + 0.02, landing + 2.92, 8, rows=3, trim="#7e8173")
    F.box(c - 5.6, c + 4.5, -2.6, 0.05, landing + 2.97, landing + 3.39, ochre, bottom=True)
    F.steps(c - 5.4, c + 4.2, -3.55, -0.16, grade, landing - grade, 4)
    W = Frontage(S, S.face(272, min_len=15, rank=1), prims)
    wc, wg = W.length / 2, W.grade(4.5)
    W.glass(wc - 4.5, wc + 4.5, -0.19, wg + 1.04, wg + 3.82, 8, rows=2)
    W.box(wc - 5.2, wc + 5.2, -1.25, 0.08, wg + 3.81, wg + 4.13, ochre, bottom=True)
    W.steps(wc - 5.3, wc + 5.3, -3.44, -0.12, wg, 1.04, 7)
    model = facade_model(masses, prims, front, top, 4,
                         "stepped cream and yellow-brick Life Sciences block with horizontal windows and two glazed entrances")
    apron = Polygon([F.plan(s, t) for s, t in ((0.5, -12.4), (F.length - 0.5, -12.4),
                                               (F.length - 0.5, -0.1), (0.5, -0.1))])
    model["pavement"] = [{"kind": "paving", "rings": site_rings(S, apron)}]
    return model


def m_reactor_center(S):
    front = S.face(268, min_len=14)
    prims = []
    F = Frontage(S, front, prims)
    grade = F.grade(1.4)
    white, roof = "#e5e4d9", "#afb3a7"
    top = S.H
    masses = mass(S.poly, -1.35, top, white, roof, PLAIN, parapet=0.26)
    s = F.length * 0.78
    F.glass(s - 0.95, s + 0.88, -0.37, grade + 0.43, grade + 3.06, 2, "#416560", rows=3)
    F.box(s - 1.08, s + 1.03, -0.63, 0.07, grade + 3.04, grade + 3.22, "#8e9991")
    F.glass(s - 5.3, s - 2.85, -0.15, grade + 0.91, grade + 2.56, 3, "#536760", rows=2)
    F.steps(s - 1.15, s + 1.08, -1.7, -0.15, grade, 0.43, 3)
    return facade_model(masses, prims, front, top, 1,
                        "low pale-concrete Reactor Center exterior with a green glazed entry and small hillside steps")


def m_engineering_laboratory(S):
    front = S.face(268, min_len=65)
    prims = []
    F = Frontage(S, front, prims)
    grade, top = F.grade(3.6), S.H
    eave = top - 2.45
    wall, beam, roof = "#d4cbb6", "#c4b99f", "#8098b4"
    masses = mass(S.poly, -1.7, eave, wall, roof, PLAIN, parapet=0.12)
    ax, ay = F.frame["ax"]
    across = {"ax": [-ay, ax], "off": F.plan(F.length - 0.45, 0)}
    depth = depth_from(F, S.poly)
    prims.append(pprofile(across, [(0, eave - 0.3), (depth, eave - 0.3), (depth, eave),
                                  (depth * .75, top), (depth / 2, eave + 0.1), (depth * .25, top), (0, eave)],
                          0, F.length - 0.45, roof))
    for k in range(9):
        s0 = 0.93 + (F.length - 1.8) * k / 9
        s1 = s0 + (F.length - 1.8) / 9
        F.box(s0 - 0.25, s0 + 0.28, -0.26, 0.08, grade - 0.2, eave + 0.04, beam)
        for z in (eave - 3.32, eave - 1.88):
            F.glass(s0 + 0.51, s1 - 0.55, -0.16, z, z + 0.92, 5, "#617470", trim="#b2ad95")
        if k in (0, 1, 5, 6, 8):
            F.box(s0 + 1.08, s1 - 1.26, -0.21, 0.03, grade + 0.19, grade + 4.12,
                  "#919991" if k in (1, 6) else "#d7d6c8")
            F.box(s0 + 0.99, s1 - 1.15, -0.26, -0.18, grade + 4.04, grade + 4.23, beam)
    E = Frontage(S, S.face(178, min_len=22), prims)
    c, g = E.length * 0.61, E.grade(3.0)
    E.glass(c - 3, c + 3, -0.19, g + 0.35, g + 2.87, 7, rows=2)
    E.steps(c - 3.55, c + 3.55, -2.65, -0.09, g, 0.35, 3)
    return facade_model(masses, prims, front, top, 2,
                        "engineering workshop with paired blue roof ridges, clerestory ribbons, concrete piers and service bays")


def m_research_block(S):
    main = S.id == "way/801815069"
    front = S.face(1 if main else 90, min_len=35)
    prims = []
    F = Frontage(S, front, prims)
    g, top = F.grade(3), S.H
    roof = "#b8b9b2" if main else "#6289a9"
    siding = "#9b9d97" if main else "#c0c5bc"
    eave = top - (0.15 if main else 1.3)
    masses = mass(S.poly, -1.35, eave, siding, roof, PLAIN, parapet=0.15)
    c = F.length * 0.57
    if not main:
        prims.append(gabled_roof(F, depth_from(F, S.poly), eave, top, roof))
    n = 9 if main else 10
    for i in range(n):
        a = F.length * i / n
        b = F.length * (i + 1) / n
        s = (a + b) / 2
        if main:
            F.box(a + 0.48, b - 0.48, -0.16, 0.08, g + 0.06, top - 0.33,
                  "#c3c5bd" if i % 2 == 0 else "#a8adab")
        if abs(s - c) > (2.5 if main else 3.7) and (not main or i < 7):
            for z in ([g + 0.92, g + 4.23] if main else [g + 1.23]):
                F.glass(s - 1.35, s + 1.35, -0.28, z, z + 1.4, 3, "#537076", trim="#a6afa7")
    F.glass(c - 2.25, c + 2.25, -0.31, g + 0.25, g + (6.9 if main else 2.65), 6, rows=5 if main else 2)
    if not main:
        F.box(c - 2.82, c + 2.82, -1.25, 0.13, g + 2.67, g + 2.94, "#7a8790", bottom=True)
    F.steps(c - 2.6, c + 2.6, -1.56, -0.14, g, 0.25, 2)
    return facade_model(masses, prims, front, top, 2 if main else 1,
                        "two-storey research block with alternating panel bays and a glazed entry" if main else
                        "single-storey research block with blue gable roof, strip windows and a sheltered entrance")


# Visible exterior forms for the small farm and research structures in the orthophoto.
# Bearings point towards the adjacent yards. Indistinct walls use quiet, unmarked finishes.
UTILITY_BUILDINGS = {
    "way/585696420": (335, "#a3b494", "#c6c9af", "Teaching Farm Building", True),
    "way/1370623062": (245, "#8ba3a4", "#b6b8af", "Teaching Farm outbuilding", True),
    "way/1370623063": (157, "#6e8586", "#b3b9a7", "Teaching Farm outbuilding", True),
    "way/778946320": (155, "#b7bcb1", "#c2c5bc", "Teaching Farm yard annex", True),
    "way/778946321": (156, "#597f9c", "#adbdb9", "Teaching Farm shed", True),
    "way/778946314": (65, "#6992af", "#bfc9bc", "Research courtyard annex", True),
    "way/778946315": (152, "#7299b4", "#c1c6bb", "Research courtyard annex", True),
    "way/778946316": (244, "#5e8aa9", "#bdc5ba", "Research courtyard annex", True),
    "way/778946317": (333, "#587891", "#abb9ae", "Research courtyard annex", True),
    "way/778946318": (138, "#a3b5b8", "#bdc7b9", "Research workshop", True),
    "way/778946319": (141, "#84a48c", "#b3bba6", "Research outbuilding", True),
    "way/170482643": (213, "#a7aba0", "#d4d2c7", "Aejiwon detached annex", False),
    "way/474521124": (259, "#888c7f", "#b1ab9d", "Ceramics Hall hillside outbuilding", False),
    "way/1385686358": (219, "#75837d", "#abb4a5", "Observatory approach structure", False),
}


def m_utility(S):
    bearing, roof, wall, name, gable = UTILITY_BUILDINGS[S.id]
    front = S.face(bearing, min_len=3.0)
    prims = []
    F = Frontage(S, front, prims)
    grade = F.grade(1.25)
    top = S.H
    eave = top - (1.05 if gable else 0)
    masses = mass(S.poly, -1.4, eave, wall, roof, PLAIN if F.length < 12 else 5, parapet=0.19)
    if gable:
        prims.append(gabled_roof(F, depth_from(F, S.poly), eave, top, roof))
    # Aircraft/aerial imagery resolves roofs much more clearly than these small façades.
    c = F.length / 2
    door = min(1.45, F.length * 0.14)
    if eave - grade > 1.7:
        F.box(c - door, c + door, -0.17, 0.05, grade + 0.08, min(grade + 2.62, eave - 0.35), "#687b73")
    if F.length >= 15 and eave - grade > 2.7:
        for t in (0.22, 0.80):
            F.glass(F.length * t - 0.76, F.length * t + 0.76, -0.14, grade + 1.22,
                    grade + 2.20, 2, "#637c7b", trim="#acb5a8")
    model = facade_model(masses, prims, front, top, S.props.get("levels"),
                         f"{name}, roof form and colour from aerial imagery, with simplified estimated exterior details")
    model["name_en"] = name
    model["reference_quality"] = "aerial estimate"
    return model


def m_observatory(S):
    bearing = 37  # hillside entry towards mapped steps way/1370636323
    theta = math.radians(bearing)
    radius = math.sqrt(S.poly.area / math.pi)
    ax, ay = -math.cos(theta), math.sin(theta)
    ox, oy = ay, -ax
    top = S.H
    floor = top - 12.5
    white, trim = "#e1e6e2", "#f0f0e7"
    C = {"ax": [1, 0], "off": [0, 0]}
    curves = [(-1.4, 1.0), (floor, 1.0), (floor + 2.65, 0.985), (floor + 4.86, 0.885),
              (floor + 7.75, 0.69), (floor + 8.47, 0.61), (floor + 8.70, 0.55),
              (floor + 9.55, 0.51), (floor + 9.95, 0.39), (floor + 10.55, 0.37),
              (floor + 11.37, 0.30), (floor + 12.10, 0.20), (top, 0.012)]
    prims = [pcyl(C, 0, 0, a, b, radius * r, "#c1cac7" if a >= floor + 9.95 else white,
                  r1=radius * s, sty=PLAIN, seg=64) for (a, r), (b, s) in zip(curves, curves[1:])]
    # Follow the sloped lower shell with short planar window panes. Leave the entrance sector open for the portal.
    for i in range(24):
        angle = theta + i * math.tau / 24
        if i in (0, 1, 23):
            continue
        for j in range(3):
            lo = angle - 0.094 + j * 0.063
            hi = lo + 0.056
            pts = [[round(math.sin(a) * radius * r, 3), round(math.cos(a) * radius * r, 3), round(z, 3)]
                   for a, r, z in ((hi, 0.981, floor + 3.00), (lo, 0.981, floor + 3.00),
                                   (lo, 0.915, floor + 4.48), (hi, 0.915, floor + 4.48))]
            prims.append({"t": "panel", "ax": C["ax"], "off": C["off"], "points": pts,
                          "normal": [math.sin(angle), math.cos(angle), 0.28], "col": "#597981", "sty": GLASS})
    # Set the entrance frame on the northeast side. Its broad masonry arch stands in front of the dome.
    frame = {"ax": [ax, ay], "off": [ox * radius * 0.96, oy * radius * 0.96]}
    out = lambda p: (ox * p, oy * p)
    toe = S.ground(*out(radius + 3.6)) + 0.05
    for i in range(15):
        t = -4.24 + 4.34 * i / 15
        half = 4.33 - 0.49 * i / 15
        prims.append(pbox(frame, -half, half, t, t + 4.34 / 15, toe - 0.47,
                          toe + (floor - toe) * (i + 1) / 15, "#bbbcb4"))
    spring = floor + 3.9

    def arch(w, r, z):
        return [(-w, floor), (w, floor)] + [(w * math.cos(a), z + r * math.sin(a))
                                             for a in np.linspace(0, math.pi, 26)]

    prims.append(pprofile(frame, arch(4.14, 3.83, spring), -0.54, 3.7, trim))
    prims.append(pprofile(frame, arch(3.43, 3.17, spring - 0.10), -0.60, -0.53, "#5a7b82"))
    for s in np.linspace(-2.69, 2.69, 7):
        prims.append(pbox(frame, s - 0.033, s + 0.033, -0.66, -0.589, floor + 0.06, spring, "#405b60"))
    prims.append(pbox(frame, -3.42, 3.42, -0.67, -0.587, spring - 0.09, spring + 0.02, "#405b60"))
    for a in np.linspace(0.29, math.pi - 0.29, 6):
        s, z = 3.42 * math.cos(a), spring - 0.09 + 3.11 * math.sin(a)
        prims.append(pprofile(frame, [(-0.04, spring), (0.04, spring), (s + 0.04, z), (s - 0.04, z)],
                              -0.67, -0.594, "#455f64"))
    return facade_model([], prims, {"bearing": bearing}, top, None,
                        "white domed observatory with sloping window bands, a smaller crown dome and a glazed arch above hillside steps")


PHOTO_SPECS = {
    "way/170482640": m_aejiwon,
    "way/455725718": m_engineering,
    ANNEX: m_engineering_annex,
    "way/455726113": m_physical_education,
    "way/585696507": m_foreign_languages,
    "way/474085540": m_electronics,
    "relation/8269760": m_woojungwon,
    "way/764320683": m_emart,
    "relation/6739964": m_second_dormitory,
    "relation/6739958": m_second_dormitory,
    "way/474085537": m_multimedia,
    "way/474085538": m_global_hall,
    "way/474085535": m_student_union,
    "way/474085539": m_portal_hall,
    "way/474085542": m_portal_hall,
    "way/474521123": m_ceramics,
    "way/474521122": m_horticulture,
    "way/474521121": m_life_sciences,
    "way/455728923": m_reactor_center,
    "way/455728922": m_engineering_laboratory,
    "way/778946313": m_research_block,
    "way/801815069": m_research_block,
    "way/474521125": m_observatory,
    **dict.fromkeys(UTILITY_BUILDINGS, m_utility),
}


MODEL_ROOFS = {
    ANNEX: "Roof terrace with a floor-3 pavilion (estimated from renderings)",
    "way/455728922": "Twin pitched metal roofs (estimated)",
    "way/474521123": "Low pitched roof (estimated)",
    "way/474521122": "Masonry deck with glazed roof pavilions (estimated)",
    "way/474521121": "Stepped flat roofs (estimated)",
    "way/778946313": "Pitched metal roof (estimated)",
    "way/474521125": "Broad dome with smaller crown dome (estimated)",
}


def photo_buildings(B, R, dtm):
    out = {}
    for oid, fn in PHOTO_SPECS.items():
        S = Site(oid, B, dtm)
        d = fn(S)
        if oid in MODEL_ROOFS:
            d["roof_shape"] = MODEL_ROOFS[oid]
        elif oid in UTILITY_BUILDINGS:
            d["roof_shape"] = "Pitched roof (estimated)" if UTILITY_BUILDINGS[oid][-1] else "Flat roof (estimated)"
        d.update({"id": oid, "origin": [round(S.c[0], 7), round(S.c[1], 7)]})
        out[oid] = d
        print("photo model", oid, S.props.get("name_ko"), "masses", len(d["masses"]), "prims", len(d["prims"]), "top", d["top_m"])
    return out


if __name__ == "__main__":
    main()
