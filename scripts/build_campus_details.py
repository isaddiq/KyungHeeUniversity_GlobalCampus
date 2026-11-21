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
    out["peacehall"] = {
        "id": PH, "origin": [round(pcx, 7), round(pcy, 7)],
        "ring_m": [[round(x, 3), round(y, 3)] for x, y in ring_ph],
        "upper_m": [[round(x, 3), round(y, 3)] for x, y in upper.exterior.coords],
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
    wall, trim, roof = "#e2dfd5", "#e2e0d7", "#9da4a1"
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
            styles.append([PLAIN, storey, 5.4, "#d9d7cf"] if on_front
                          else [ENGINEERING_WING, storey, 5.4, wall])
        return styles

    center_block = S.poly.intersection(band(0, L, -120, 120))
    wings = S.poly.difference(center_block)
    end_blocks = wings.intersection(band(-120, L + 120, -120, -38))
    masses = mass(center_block, -1.5, S.H, wall, roof, ENGINEERING_WING,
                  fh=storey, bw=5.4, floor0=grade, parapet=0.6, edge_sty=wall_styles)
    masses += mass(wings.difference(end_blocks), -1.5, S.H - storey, wall, roof,
                   ENGINEERING_WING, fh=storey, bw=5.4, floor0=grade, parapet=0.55)
    masses += mass(end_blocks, -1.5, grade + 10.8, wall, "#72796a",
                   ENGINEERING_WING, fh=storey, bw=5.4, floor0=grade, parapet=0.5)

    prims = []

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
        return [[FOREIGN_LANGUAGES_WINDOWS if exterior(a, b) and
                 min(facade(a)[1], facade(b)[1]) >= 16.65 else PLAIN, 3.45, 4.15, wall]
                for a, b in zip(pts, pts[1:])]

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
                       "a signed entrance canopy, broad stairs, tiered planters and a sheltered side passage"),
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
    cream, roof, jade = "#e5e1d5", "#b4b6ac", "#5a8078"
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
        pavement.append({"kind": "garden", "rings": site_rings(S, court.buffer(-2.7))})

    return {
        "masses": masses, "prims": prims, "pavement": pavement, "top_m": round(tower_top + 0.14, 2),
        "floors": 7, "name_en": "Woojungwon Dormitory", "front_bearing": round(front["bearing"], 1),
        "focus_heading": round((front["bearing"] + 170) % 360, 1),
        "appearance": ("photo-based seven-storey dormitory with twin curved glass towers, a signed teal canopy, "
                       "a pediment above the entrance, and two mapped courtyards"),
    }


PHOTO_SPECS = {
    "way/170482640": m_aejiwon,
    "way/455725718": m_engineering,
    "way/585696507": m_foreign_languages,
    "way/474085540": m_electronics,
    "relation/8269760": m_woojungwon,
}


def photo_buildings(B, R, dtm):
    out = {}
    for oid, fn in PHOTO_SPECS.items():
        S = Site(oid, B, dtm)
        d = fn(S)
        d.update({"id": oid, "origin": [round(S.c[0], 7), round(S.c[1], 7)]})
        out[oid] = d
        print("photo model", oid, S.props.get("name_ko"), "masses", len(d["masses"]), "prims", len(d["prims"]), "top", d["top_m"])
    return out


if __name__ == "__main__":
    main()
