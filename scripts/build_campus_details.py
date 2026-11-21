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
from shapely.geometry import LineString, Point, box, mapping, shape
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


if __name__ == "__main__":
    main()
