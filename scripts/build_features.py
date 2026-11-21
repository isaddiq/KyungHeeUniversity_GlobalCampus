"""Phases 4-5: buildings, circulation network, landcover and vegetation.

Inputs : data/raw/osm_overpass.json, DTM/DSM crops, khu_official_campus_map.json, height_overrides.json
Outputs (web/data/):
  boundary.geojson   campus boundary (OSM relation 11246784)
  buildings.geojson  every OSM building in the campus + ~600 m context, with height provenance
  roads.geojson      highway network (lines) + pedestrian areas, widths with provenance
  landcover.geojson  landuse / leisure / natural / parking polygons
  pois.geojson       entrances, bus stops, mapped peaks, mapped individual trees
  trees.bin/.json    visual vegetation instances (NOT surveyed positions)
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import polygonize, unary_union
from shapely.prepared import prep

from common import (CAMPUS_RELATION_ID, FEATURE_BBOX, RAW, WEB_DATA, haversine_m, read_json,
                    ring_area_m2, write_json)
from dem import load

ROOT_SCRIPTS = __import__("pathlib").Path(__file__).resolve().parent
LAT_C = 37.2424
M_PER_DLAT = 110_950.0
M_PER_DLON = 111_320.0 * math.cos(math.radians(LAT_C))
FLOOR_H_RES = 2.87   # m/floor: median height/levels of 160 OSM-documented buildings in this area
FLOOR_H_INST = 3.8   # m/floor: typical institutional storey height (assumption, labelled estimated)

ROAD_WIDTH_DEFAULT = {  # metres, carriageway/pavement width defaults by OSM class (estimated)
    "motorway": 24, "trunk": 20, "trunk_link": 8, "primary": 16, "primary_link": 7,
    "secondary": 12, "secondary_link": 7, "tertiary": 9, "tertiary_link": 6,
    "unclassified": 6, "residential": 6, "living_street": 5, "service": 4.5,
    "pedestrian": 5, "footway": 2.5, "cycleway": 2.5, "path": 1.5, "steps": 2.5,
    "track": 3, "corridor": 2.5,
}

LANDCOVER = {
    ("natural", "wood"): "forest", ("landuse", "forest"): "forest", ("natural", "scrub"): "forest",
    ("natural", "heath"): "scrub", ("natural", "grassland"): "grass", ("landuse", "grass"): "grass",
    ("landuse", "flowerbed"): "garden", ("leisure", "garden"): "garden", ("man_made", "planter"): "garden",
    ("leisure", "park"): "park", ("leisure", "playground"): "park", ("leisure", "golf_course"): "golf",
    ("leisure", "pitch"): "sport", ("leisure", "stadium"): "sport", ("leisure", "track"): "sport",
    ("amenity", "parking"): "parking", ("natural", "water"): "water", ("water", "pond"): "water",
    ("landuse", "residential"): "residential", ("landuse", "industrial"): "industrial",
    ("landuse", "construction"): "construction", ("landuse", "cemetery"): "cemetery",
    ("landuse", "farmland"): "farmland", ("amenity", "school"): "school",
    ("amenity", "kindergarten"): "school", ("place", "square"): "plaza", ("area:highway", "yes"): "plaza",
}


# ---------------------------------------------------------------------------
def way_coords(el):
    return [(p["lon"], p["lat"]) for p in el.get("geometry", []) if p]


def relation_polygon(el):
    outers, inners = [], []
    for m in el.get("members", []):
        if m.get("type") != "way" or "geometry" not in m:
            continue
        coords = [(p["lon"], p["lat"]) for p in m["geometry"] if p]
        if len(coords) < 2:
            continue
        (inners if m.get("role") == "inner" else outers).append(LineString(coords))
    if not outers:
        return None
    outer = unary_union(list(polygonize(unary_union(outers))))
    if inners:
        inner = unary_union(list(polygonize(unary_union(inners))))
        outer = outer.difference(inner)
    return outer if not outer.is_empty else None


def element_polygon(el):
    if el["type"] == "way":
        c = way_coords(el)
        if len(c) >= 4 and c[0] == c[-1]:
            p = Polygon(c)
            return p if p.is_valid else p.buffer(0)
        return None
    if el["type"] == "relation":
        return relation_polygon(el)
    return None


def polys_of(g):
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [x for x in getattr(g, "geoms", []) if isinstance(x, Polygon)]


def geom_area_m2(g):
    a = 0.0
    for p in polys_of(g):
        a += ring_area_m2(list(p.exterior.coords)[:-1])
        for r in p.interiors:
            a -= ring_area_m2(list(r.coords)[:-1])
    return a


def line_length_m(ls):
    c = list(ls.coords)
    return sum(haversine_m(*a, *b) for a, b in zip(c, c[1:]))


def rnd(g, nd=7):
    """GeoJSON mapping with rounded coordinates (1e-7 deg ~ 1 cm)."""
    def r(c):
        if isinstance(c[0], (float, int)):
            return [round(c[0], nd), round(c[1], nd)]
        return [r(x) for x in c]
    m = mapping(g)
    return {"type": m["type"], "coordinates": r(m["coordinates"])}


def interior_samples(g, step_m=5.0):
    pts = []
    for p in polys_of(g):
        pts.extend(p.exterior.coords[:-1])
        minx, miny, maxx, maxy = p.bounds
        pp = prep(p)
        for x in np.arange(minx, maxx, step_m / M_PER_DLON):
            for y in np.arange(miny, maxy, step_m / M_PER_DLAT):
                if pp.contains(Point(x, y)):
                    pts.append((x, y))
    return np.array(pts)


def hash01(*vals):
    h = hashlib.blake2b(repr(vals).encode(), digest_size=8).digest()
    return int.from_bytes(h, "little") / 2 ** 64


def parse_num(v):
    if v is None:
        return None
    try:
        return float(str(v).replace("m", "").replace(",", ".").strip().split(";")[0])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
def main():
    osm = read_json(RAW / "osm_overpass.json")
    official = read_json(ROOT_SCRIPTS / "khu_official_campus_map.json")
    overrides = read_json(ROOT_SCRIPTS / "height_overrides.json")["buildings"]
    osm_date = osm.get("osm3s", {}).get("timestamp_osm_base")
    retrieved = osm.get("_retrieved_utc")
    dtm, dsm = load()
    els = osm["elements"]
    clip = box(FEATURE_BBOX["west"], FEATURE_BBOX["south"], FEATURE_BBOX["east"], FEATURE_BBOX["north"])

    # ---------------- campus boundary ----------------
    camp_el = next(e for e in els if e["type"] == "relation" and e["id"] == CAMPUS_RELATION_ID)
    campus = relation_polygon(camp_el)
    campus_prep = prep(campus)
    camp_area = geom_area_m2(campus)
    perim = sum(line_length_m(LineString(p.exterior.coords)) for p in polys_of(campus))
    boundary_fc = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": rnd(campus),
        "properties": {"id": f"relation/{CAMPUS_RELATION_ID}", "name_ko": camp_el["tags"].get("name:ko"),
                       "name_en": camp_el["tags"].get("name:en"), "area_m2": round(camp_area),
                       "perimeter_m": round(perim), "parts": len(polys_of(campus)),
                       "source": "OpenStreetMap relation 11246784 (amenity=university)",
                       "osm_data_timestamp": osm_date}}]}
    write_json(WEB_DATA / "boundary.geojson", boundary_fc, compact=True)
    print(f"campus: {len(polys_of(campus))} parts, {camp_area/1e4:.2f} ha, perimeter {perim:.0f} m")

    # official crosswalk
    xwalk = {}
    for ent in official["entries"]:
        for oid in ent["osm"]:
            xwalk.setdefault(oid, []).append(ent)

    # ---------------- buildings ----------------
    bfeats, bgeoms = [], []
    status_count = Counter()
    for el in els:
        t = el.get("tags", {})
        if "building" not in t or el["type"] not in ("way", "relation"):
            continue
        g = element_polygon(el)
        if g is None or g.is_empty or not g.intersects(clip):
            continue
        oid = f"{el['type']}/{el['id']}"
        area = geom_area_m2(g)
        rp = g.representative_point()
        in_campus = campus_prep.contains(rp)
        pts = interior_samples(g, 4.0 if area < 3000 else 6.0)
        gz = dtm.sample(pts[:, 0], pts[:, 1])
        gmin, gmax, gmean = float(gz.min()), float(gz.max()), float(gz.mean())

        levels = parse_num(t.get("building:levels"))
        h_tag = parse_num(t.get("height"))
        btype = t.get("building", "yes")
        name_ko = t.get("name:ko") or t.get("name")
        ov = overrides.get(oid)
        if ov and ov.get("height"):
            h_status = ov.get("status", "documented")
            height, h_src = float(ov["height"]), ov["source"]
            conf = "high" if h_status == "documented" else "low-medium"
            levels = ov.get("levels", levels)
        elif h_tag:
            height, h_status, h_src, conf = h_tag, "documented", "OSM height tag", "medium"
        elif levels:
            fh = FLOOR_H_INST if btype in ("college", "university", "school", "dormitory", "commercial", "office") else FLOOR_H_RES
            height = levels * fh + (1.0 if fh == FLOOR_H_INST else 0.0)
            h_status, conf = "derived", "medium-low"
            h_src = f"OSM building:levels={levels:g} x {fh} m/floor"
        else:
            nm = name_ko or ""
            if "노천극장" in nm:
                height, est_lv = 2.0, None
                h_src = "estimated: open-air amphitheatre, rendered as low seating mass"
            elif btype in ("roof", "carport", "shelter") or t.get("amenity") == "shelter":
                height, est_lv = 4.0, None
                h_src = "estimated: open roof/shelter default 4 m"
            elif btype == "greenhouse" or "온실" in nm:
                height, est_lv = 5.0, None
                h_src = "estimated: greenhouse default 5 m"
            else:
                inst = in_campus or btype in ("college", "university", "school", "dormitory", "church", "commercial")
                est_lv = 1 if area < 150 else 2 if area < 500 else 3 if area < 1500 else 4
                fh = FLOOR_H_INST if inst else FLOOR_H_RES
                height = est_lv * fh + (1.0 if inst else 0.5)
                h_src = (f"estimated: footprint-size heuristic ({est_lv} floor(s) x {fh} m); "
                         "no documented height or floor count available")
            h_status, conf = "estimated", "low"
        status_count[h_status] += 1

        offi = xwalk.get(oid, [])
        props = {
            "id": oid,
            "official_no": offi[0]["no"] if offi else None,
            "official_name_ko": offi[0]["name_ko"] if offi else None,
            "name_ko": name_ko,
            "name_en": t.get("name:en"),
            "building_type": btype,
            "in_campus": in_campus,
            "centroid": [round(rp.x, 7), round(rp.y, 7)],
            "footprint_area_m2": round(area, 1),
            "ground_min_m": round(gmin, 2), "ground_max_m": round(gmax, 2), "ground_mean_m": round(gmean, 2),
            "height_m": round(height, 1), "height_status": h_status, "height_source": h_src,
            "height_confidence": conf,
            "levels": levels, "levels_status": ("documented" if levels and (t.get("building:levels") or (ov and ov.get("levels"))) else None),
            "roof_shape": t.get("roof:shape") or "flat (not mapped; LOD1)",
            "start_date": t.get("start_date"),
            "footprint_source": "OpenStreetMap (" + oid + ")" + (f", source={t['source']}" if t.get("source") else ""),
        }
        bfeats.append({"type": "Feature", "geometry": rnd(g), "properties": props})
        bgeoms.append(g)

    # overlap QA between building footprints
    overlaps = []
    from shapely.strtree import STRtree
    tree = STRtree(bgeoms)
    for i, g in enumerate(bgeoms):
        for j in tree.query(g):
            if j <= i:
                continue
            inter = g.intersection(bgeoms[j])
            if not inter.is_empty and inter.area > 0:
                a = geom_area_m2(inter)
                if a > 1.0:
                    overlaps.append({"a": bfeats[i]["properties"]["id"], "b": bfeats[int(j)]["properties"]["id"], "area_m2": round(a, 1)})
    bfeats.sort(key=lambda f: (not f["properties"]["in_campus"], f["properties"]["official_no"] or 999,
                               f["properties"]["name_ko"] is None, f["properties"]["name_ko"] or "", f["properties"]["id"]))
    write_json(WEB_DATA / "buildings.geojson", {"type": "FeatureCollection", "features": bfeats}, compact=True)
    n_campus = sum(f["properties"]["in_campus"] for f in bfeats)
    print(f"buildings: {len(bfeats)} total, {n_campus} in campus; height status {dict(status_count)}; overlaps {len(overlaps)}")

    # ---------------- roads ----------------
    rfeats, road_buffers = [], []
    for el in els:
        t = el.get("tags", {})
        if el["type"] != "way" or "highway" not in t:
            continue
        hw = t["highway"]
        if hw in ("bus_stop", "crossing", "traffic_signals", "construction", "proposed", "platform"):
            continue
        c = way_coords(el)
        if len(c) < 2:
            continue
        oid = f"way/{el['id']}"
        is_area = t.get("area") == "yes" and c[0] == c[-1] and len(c) >= 4
        if is_area:
            g = Polygon(c).intersection(clip)
        else:
            g = LineString(c).intersection(clip)
        if g.is_empty:
            continue
        w_tag = parse_num(t.get("width"))
        lanes = parse_num(t.get("lanes"))
        if w_tag:
            width, w_status = w_tag, "OSM width tag"
        elif lanes and hw not in ("footway", "path", "steps", "pedestrian"):
            width, w_status = lanes * 3.3, f"derived: lanes={lanes:g} x 3.3 m"
        else:
            width, w_status = ROAD_WIDTH_DEFAULT.get(hw, 3.0), "estimated: default width for highway class"
        props = {"id": oid, "highway": hw, "name": t.get("name"), "name_en": t.get("name:en"),
                 "width_m": round(width, 1), "width_status": w_status, "surface": t.get("surface"),
                 "layer": t.get("layer"), "bridge": t.get("bridge"), "tunnel": t.get("tunnel"),
                 "oneway": t.get("oneway"), "area": is_area,
                 "in_campus": campus_prep.intersects(g),
                 "length_m": None if is_area else round(sum(line_length_m(x) for x in getattr(g, "geoms", [g])), 1)}
        geoms = list(getattr(g, "geoms", [g]))
        for k, part in enumerate(geoms):
            if part.geom_type not in ("LineString", "Polygon") or part.is_empty:
                continue
            rfeats.append({"type": "Feature", "geometry": rnd(part), "properties": dict(props)})
            if t.get("tunnel") not in ("yes", "building_passage"):
                road_buffers.append(part.buffer((width / 2 + 1.0) / M_PER_DLON))
    write_json(WEB_DATA / "roads.geojson", {"type": "FeatureCollection", "features": rfeats}, compact=True)
    print("roads:", len(rfeats), Counter(f["properties"]["highway"] for f in rfeats).most_common(8))

    # ---------------- landcover ----------------
    lfeats, veg_polys, no_tree_polys = [], [], []
    for el in els:
        t = el.get("tags", {})
        if "building" in t or el["type"] not in ("way", "relation"):
            continue
        cls, key = None, None
        for (k, v), c in LANDCOVER.items():
            if t.get(k) == v:
                cls, key = c, f"{k}={v}"
                break
        if cls is None:
            continue
        g = element_polygon(el)
        if g is None or g.is_empty:
            continue
        g = g.intersection(clip)
        if g.is_empty:
            continue
        oid = f"{el['type']}/{el['id']}"
        rp = g.representative_point()
        props = {"id": oid, "class": cls, "osm_tag": key, "name": t.get("name"), "sport": t.get("sport"),
                 "in_campus": campus_prep.contains(rp), "area_m2": round(geom_area_m2(g), 1),
                 "official_no": (xwalk.get(oid) or [{}])[0].get("no"),
                 "official_name_ko": (xwalk.get(oid) or [{}])[0].get("name_ko"),
                 "source": "OpenStreetMap"}
        for part in polys_of(g):
            lfeats.append({"type": "Feature", "geometry": rnd(part), "properties": dict(props)})
        if cls == "forest":
            veg_polys.append(g)
        elif cls in ("sport", "parking", "water", "plaza", "construction", "cemetery", "farmland", "golf"):
            no_tree_polys.append(g)
    # draw order: large areas first
    order = {"residential": 0, "industrial": 0, "school": 0, "farmland": 1, "cemetery": 1, "golf": 1,
             "construction": 1, "park": 2, "forest": 3, "scrub": 3, "grass": 4, "garden": 5, "sport": 6,
             "parking": 6, "plaza": 6, "water": 7}
    lfeats.sort(key=lambda f: order.get(f["properties"]["class"], 5))
    write_json(WEB_DATA / "landcover.geojson", {"type": "FeatureCollection", "features": lfeats}, compact=True)
    print("landcover:", len(lfeats), Counter(f["properties"]["class"] for f in lfeats).most_common())

    # ---------------- POIs ----------------
    pfeats = []
    for el in els:
        if el["type"] != "node":
            continue
        t = el.get("tags", {})
        kind = ("entrance" if "entrance" in t else "bus_stop" if t.get("highway") == "bus_stop" else
                "peak" if t.get("natural") == "peak" else "tree" if t.get("natural") == "tree" else None)
        if kind is None:
            continue
        lon, lat = el["lon"], el["lat"]
        g_dtm = float(dtm.sample(lon, lat))
        pfeats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
                       "properties": {"id": f"node/{el['id']}", "kind": kind, "name": t.get("name"),
                                      "ele_osm": parse_num(t.get("ele")), "dtm_m": round(g_dtm, 2),
                                      "in_campus": campus_prep.contains(Point(lon, lat))}})
    write_json(WEB_DATA / "pois.geojson", {"type": "FeatureCollection", "features": pfeats}, compact=True)

    # ---------------- vegetation (visual approximation) ----------------
    bld_union = unary_union([g.buffer(5 / M_PER_DLON) for g in bgeoms])
    bld_far = prep(unary_union([g.buffer(22 / M_PER_DLON) for g in bgeoms]))
    bld_near = prep(bld_union)
    roads_u = prep(unary_union(road_buffers)) if road_buffers else None
    veg_u = prep(unary_union(veg_polys)) if veg_polys else None
    notree_u = prep(unary_union(no_tree_polys)) if no_tree_polys else None
    spacing = 10.0
    dx, dy = spacing / M_PER_DLON, spacing / M_PER_DLAT
    trees = []
    src_counter = Counter()
    west, south, east, north = FEATURE_BBOX["west"], FEATURE_BBOX["south"], FEATURE_BBOX["east"], FEATURE_BBOX["north"]
    xs = np.arange(west, east, dx)
    ys = np.arange(south, north, dy)
    for iy, y in enumerate(ys):
        for ix, x in enumerate(xs):
            jx = x + (hash01(ix, iy, 1) - 0.5) * dx * 0.9
            jy = y + (hash01(ix, iy, 2) - 0.5) * dy * 0.9
            ground = float(dtm.sample(jx, jy))
            chm = float(dsm.sample(jx, jy)) - ground
            p = Point(jx, jy)
            in_veg = veg_u is not None and veg_u.contains(p)
            if not in_veg and chm < 3.5:
                continue
            if notree_u is not None and notree_u.contains(p):
                continue
            if roads_u is not None and roads_u.contains(p):
                continue
            if bld_near.contains(p):
                continue
            if not in_veg and bld_far.contains(p):
                continue  # DSM-DTM near buildings is contaminated by the buildings themselves
            keep = 0.85 if in_veg else (0.55 if chm < 6 else 0.8)
            if hash01(ix, iy, 3) > keep:
                continue
            th = float(np.clip(chm * 1.4 + 5.0, 6.0, 19.0)) * (0.8 + 0.4 * hash01(ix, iy, 4))
            trees.append((jx - west, jy - south, ground, th, 1 if in_veg else 0))
            src_counter["osm_wood" if in_veg else "chm"] += 1
    arr = np.array([t[:4] for t in trees], dtype="<f4")
    arr.tofile(WEB_DATA / "trees.bin")
    write_json(WEB_DATA / "trees.json", {
        "count": len(trees), "origin_lon": west, "origin_lat": south,
        "layout": "float32 LE x4 per tree: dlon_deg, dlat_deg (from origin), ground_orthometric_m, tree_height_m",
        "status": "VISUAL APPROXIMATION - not surveyed tree positions",
        "method": ("Jittered 10 m grid. A grid point becomes a tree when it lies in an OSM natural=wood/"
                   "landuse=forest polygon, or where canopy height (Copernicus DSM - FABDEM DTM) >= 3.5 m; "
                   "excluded within 5 m of buildings (22 m for canopy-derived points), on roads, pitches, "
                   "parking and water. Heights are scaled from canopy height and randomised for display."),
        "by_source": dict(src_counter)})
    print("trees:", len(trees), dict(src_counter))

    write_json(RAW / "qa_features.json", {"overlaps": overlaps, "height_status": dict(status_count),
                                          "osm_timestamp": osm_date, "retrieved": retrieved,
                                          "campus_area_m2": camp_area, "campus_perimeter_m": perim})


if __name__ == "__main__":
    main()
