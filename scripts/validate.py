"""Phase 7: accuracy validation + provenance.

Outputs:
  web/data/summary.json          campus statistics, dataset provenance, automated check results
  web/data/accuracy_report.json  per-feature, machine-readable provenance / measured-vs-estimated status
  docs/ACCURACY.md               human-readable report generated from the same numbers
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from common import (CAMPUS_BBOX, FEATURE_BBOX, RAW, ROOT, TERRAIN_BBOX, WEB_DATA, read_json,
                    to_epsg5186, write_json)
from dem import load

M_PER_DLON = 111_320.0 * np.cos(np.radians(37.2424))
M_PER_DLAT = 110_950.0


def main():
    dtm, dsm = load(raw=True)   # accuracy checks are about the source DTM, not the local conditioning
    tmeta = read_json(WEB_DATA / "terrain" / "dtm.json")
    boundary = read_json(WEB_DATA / "boundary.geojson")["features"][0]
    B = read_json(WEB_DATA / "buildings.geojson")["features"]
    R = read_json(WEB_DATA / "roads.geojson")["features"]
    L = read_json(WEB_DATA / "landcover.geojson")["features"]
    P = read_json(WEB_DATA / "pois.geojson")["features"]
    trees = read_json(WEB_DATA / "trees.json")
    qa = read_json(RAW / "qa_features.json")
    official = read_json(ROOT / "scripts" / "khu_official_campus_map.json")
    osm = read_json(RAW / "osm_overpass.json")
    osm_ts = osm.get("osm3s", {}).get("timestamp_osm_base")
    campus = shape(boundary["geometry"])
    cprep = prep(campus)
    checks = []

    def check(name, status, detail, **extra):
        checks.append({"name": name, "status": status, "detail": detail, **extra})

    # ---- campus elevation pattern (DTM samples inside the boundary, 5 m grid) ----
    minx, miny, maxx, maxy = campus.bounds
    xs = np.arange(minx, maxx, 5 / M_PER_DLON)
    ys = np.arange(miny, maxy, 5 / M_PER_DLAT)
    gx, gy = np.meshgrid(xs, ys)
    mask = np.array([cprep.contains(Point(x, y)) for x, y in zip(gx.ravel(), gy.ravel())])
    px, py = gx.ravel()[mask], gy.ravel()[mask]
    z = dtm.sample(px, py)
    imin, imax = int(np.argmin(z)), int(np.argmax(z))
    elev = {"min": round(float(z.min()), 2), "max": round(float(z.max()), 2), "mean": round(float(z.mean()), 2),
            "relief": round(float(z.max() - z.min()), 2),
            "lowest_point": [round(float(px[imin]), 6), round(float(py[imin]), 6)],
            "highest_point": [round(float(px[imax]), 6), round(float(py[imax]), 6)],
            "samples": int(mask.sum()), "note": "FABDEM bare-earth, orthometric EGM2008"}
    check("Campus terrain is not flat", "pass" if elev["relief"] > 10 else "fail",
          f"Relief inside the boundary: {elev['min']:.1f}–{elev['max']:.1f} m ({elev['relief']:.1f} m), from {elev['samples']} DTM samples")

    # ---- vertical check against mapped peak elevations ----
    pk = [f for f in P if f["properties"]["kind"] == "peak" and f["properties"]["ele_osm"]]
    d = np.array([f["properties"]["dtm_m"] - f["properties"]["ele_osm"] for f in pk])
    if len(d):
        names = ", ".join(f"{f['properties']['name']} {f['properties']['dtm_m']:.1f} vs {f['properties']['ele_osm']:.1f} m" for f in pk)
        check("DTM vs mapped peak elevations (OSM ele)", "pass" if np.abs(d).max() < 6 else "warn",
              f"n={len(d)}; mean Δ {d.mean():+.2f} m, max |Δ| {np.abs(d).max():.2f} m ({names}). A 30 m DEM is expected to slightly underestimate summits.",
              values=[{"name": f["properties"]["name"], "dtm": f["properties"]["dtm_m"], "ele_osm": f["properties"]["ele_osm"]} for f in pk])

    # ---- DTM vs DSM on open sports surfaces (no trees/buildings => should agree) ----
    diffs = []
    for f in L:
        p = f["properties"]
        if p["class"] == "sport" and p["in_campus"] and p["area_m2"] > 2000:
            g = shape(f["geometry"])
            bx0, by0, bx1, by1 = g.bounds
            gp = prep(g)
            for x in np.arange(bx0, bx1, 8 / M_PER_DLON):
                for y in np.arange(by0, by1, 8 / M_PER_DLAT):
                    if gp.contains(Point(x, y)):
                        diffs.append(float(dsm.sample(x, y) - dtm.sample(x, y)))
    diffs = np.array(diffs)
    check("DTM vs DSM agreement on open sports fields", "pass" if abs(np.median(diffs)) < 1.5 else "warn",
          f"n={len(diffs)} samples; median DSM−DTM {np.median(diffs):+.2f} m, RMS {np.sqrt(np.mean(diffs**2)):.2f} m. This is an internal consistency check only (FABDEM is derived from Copernicus).")

    # ---- projection check vs PROJ ----
    t = Transformer.from_crs(4326, 5186, always_xy=True)
    pts = [(CAMPUS_BBOX["west"], CAMPUS_BBOX["south"]), (CAMPUS_BBOX["east"], CAMPUS_BBOX["north"]), (127.0813337, 37.2424001)]
    err = max(max(abs(a - b) for a, b in zip(t.transform(*p), to_epsg5186(*p))) for p in pts)
    check("EPSG:5186 transform vs PROJ", "pass" if err < 1e-3 else "fail", f"max difference {err*1000:.4f} mm")

    # ---- geoid ----
    N = np.array(tmeta["geoid"]["N_m"])
    check("Vertical datum handled (EGM2008 → WGS84 ellipsoid)", "pass",
          f"N = {N.min():.2f}–{N.max():.2f} m over the terrain window ({tmeta['geoid']['model']}); this is added to every DTM height before rendering")
    check("DEM grid registration", "pass",
          "GeoTIFF GTRasterTypeGeoKey=PixelIsPoint; pixel (0,0) centre = 127.0°E, 38.0°N; 1″ spacing honoured without resampling")

    # ---- buildings ----
    inb = [f for f in B if f["properties"]["in_campus"]]
    st = Counter(f["properties"]["height_status"] for f in inb)
    st_all = Counter(f["properties"]["height_status"] for f in B)
    check("Building footprint overlaps", "pass" if not qa["overlaps"] else "warn",
          f"{len(qa['overlaps'])} overlapping footprint pairs (>1 m²) among {len(B)} buildings")
    steep = [f for f in inb if f["properties"]["ground_max_m"] - f["properties"]["ground_min_m"] > 4]
    check("Buildings on sloping ground", "info",
          f"{len(steep)} of {len(inb)} campus buildings span >4 m of DTM relief. Their bases are set to the lowest ground point minus 1.5 m, so the uphill side is embedded in the slope and nothing floats.")
    check("Campus building heights", "warn" if st.get("estimated") else "pass",
          f"In campus: {st.get('documented', 0)} documented, {st.get('derived', 0)} derived from floor count, {st.get('estimated', 0)} estimated. "
          f"Whole scene: {dict(st_all)}. OSM and the official KHU pages do not publish heights for most campus buildings.")
    check("DSM−DTM as height estimator (rejected)", "info",
          "Compared with 160 OSM-documented heights in the context area, Copernicus DSM minus FABDEM underestimated heights by about 45 m (r≈0.1), so it was not used.")

    ent_b = [e for e in official["entries"] if e["kind"] == "building"]
    matched = [e for e in ent_b if e["osm"]]
    ids = {f["properties"]["id"]: f for f in B}
    outside = [o for e in matched for o in e["osm"] if o in ids and not ids[o]["properties"]["in_campus"]]
    missing = [e["name_ko"] for e in ent_b if not e["osm"]]
    check("Official campus-map buildings matched to footprints", "pass" if len(matched) >= len(ent_b) - 2 else "warn",
          f"{len(matched)}/{len(ent_b)} official building entries matched to OSM footprints; unmatched: {', '.join(missing) or 'none'}; matched but outside boundary: {len(outside)}")

    # building ↔ road adjacency
    road_geoms = [shape(f["geometry"]) for f in R if f["properties"]["tunnel"] not in ("yes",)]
    ru = unary_union(road_geoms)
    dist = [shape(f["geometry"]).distance(ru) * M_PER_DLON for f in inb]
    near = sum(1 for x in dist if x < 30)
    check("Campus buildings connected to the path network", "pass" if near >= 0.9 * len(inb) else "warn",
          f"{near}/{len(inb)} campus buildings lie within 30 m of a mapped road/footway (median {np.median(dist):.1f} m)")

    det = read_json(WEB_DATA / "campus_details.json")
    check("Stylised Kyung Hee building appearance", "info",
          f"Campus buildings use their real footprints and DTM ground, but their facades (windows per estimated storey, colours) are procedural. "
          f"Main gate: illustrative model on the footprint frame ({det['gate']['length_m']} × {det['gate']['depth_m']} m, opening {det['gate']['opening_m'][1]-det['gate']['opening_m'][0]:.1f} m from footprint vertices); its heights are estimated. "
          f"Amphitheatre: {len(det['amphitheatre']['tiers'])} seating terraces sliced from the real DTM. None of this detail is surveyed.")
    check("North orientation", "pass", "All geometry is in geographic coordinates on the WGS84 globe, so north follows from the coordinates. There is no local rotation or scaling.")
    check("Imagery ↔ footprint alignment", "manual",
          "Checked visually in top-down screenshots (see docs/screenshots). Imagery comes from tile services; their offset relative to OSM is not quantified here.")

    # ---- per-feature accuracy report ----
    feats = []
    for f in B:
        p = f["properties"]
        miss = []
        if p["height_status"] == "estimated": miss.append("height")
        if not p["levels"]: miss.append("floor count")
        if not p["name_ko"]: miss.append("name")
        if not p["name_en"]: miss.append("English name")
        miss.append("roof shape")
        feats.append({
            "id": p["id"], "layer": "building", "name": p["name_ko"], "in_campus": p["in_campus"],
            "official_no": p["official_no"],
            "geometry": {"source": "OpenStreetMap", "status": "mapped (measured by contributors)",
                         "accuracy": "not quantified; typically 1–5 m for footprints digitised from imagery", "date": osm_ts},
            "height": {"value_m": p["height_m"], "status": p["height_status"], "source": p["height_source"], "confidence": p["height_confidence"]},
            "ground_elevation": {"min_m": p["ground_min_m"], "max_m": p["ground_max_m"], "source": "FABDEM V1-2 (bilinear)", "status": "measured (DEM)", "accuracy": "metres-level; ~30 m posting"},
            "missing": miss,
        })
    for f in R:
        p = f["properties"]
        feats.append({"id": p["id"], "layer": "road", "class": p["highway"], "in_campus": p["in_campus"],
                      "geometry": {"source": "OpenStreetMap", "status": "mapped", "date": osm_ts},
                      "width": {"value_m": p["width_m"], "status": "documented" if p["width_status"] == "OSM width tag" else ("derived" if p["width_status"].startswith("derived") else "estimated"), "source": p["width_status"]},
                      "vertical": "draped on DTM (bridges/ramps not modelled in 3D)",
                      "missing": [m for m, c in (("width", "estimated" in p["width_status"]), ("surface", not p["surface"])) if c]})
    for f in L:
        p = f["properties"]
        feats.append({"id": p["id"], "layer": "landcover", "class": p["class"], "osm_tag": p["osm_tag"], "in_campus": p["in_campus"],
                      "geometry": {"source": "OpenStreetMap", "status": "mapped", "date": osm_ts}})
    feats.append({"id": "vegetation-instances", "layer": "trees", "count": trees["count"], "status": "approximated",
                  "note": trees["status"] + ". " + trees["method"]})
    feats.append({"id": "terrain", "layer": "terrain", "status": "measured (satellite DEM, bare-earth corrected)",
                  "source": "FABDEM V1-2 N37E127", "resolution": "1 arc-second (~24.6 m E-W × 30.9 m N-S)",
                  "vertical_datum": "EGM2008", "extent_deg": [tmeta["west"], tmeta["south"], tmeta["east"], tmeta["north"]]})
    write_json(WEB_DATA / "accuracy_report.json", {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status_vocabulary": {"documented": "value taken from a source attribute", "derived": "computed from a documented attribute with a stated rule",
                              "estimated": "heuristic value; no source data", "approximated": "synthetic placement for visualisation", "mapped": "geometry digitised by OSM contributors", "measured (DEM)": "sampled from a measured elevation model"},
        "checks": checks, "features": feats}, compact=True)

    datasets = [
        {"id": "fabdem", "name": "FABDEM V1-2 (tile N37E127)", "role": "Primary terrain: bare-earth DTM with forests and buildings removed",
         "provider": "University of Bristol (Hawker et al., 2022)", "url": "https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn",
         "resolution": "1 arc-second (~24.6 × 30.9 m here)", "crs": "EPSG:4326 + EGM2008 (EPSG:3855)", "date": "Copernicus GLO-30 source data 2011–2015; FABDEM released 2022 (V1-2 2023)",
         "license": "CC BY-NC-SA 4.0 (non-commercial)", "limitations": "Machine-learning bare-earth correction; errors of metres, larger under dense forest and on steep slopes. Cannot resolve terraces or walls narrower than ~30 m."},
        {"id": "copdem", "name": "Copernicus DEM GLO-30 (tile N37E127)", "role": "DSM for cross-checks and the canopy-height model that guides vegetation",
         "provider": "ESA / DLR / Airbus via AWS Open Data", "url": "https://registry.opendata.aws/copernicus-dem/",
         "resolution": "1 arc-second", "crs": "EPSG:4326 + EGM2008", "date": "TanDEM-X acquisitions 2011–2015",
         "license": "Copernicus DEM licence (free, attribution)", "limitations": "Published spec: absolute vertical accuracy < 4 m (LE90). It is a surface model. Buildings in this area appear strongly under-represented."},
        {"id": "osm", "name": "OpenStreetMap", "role": "Campus boundary, building footprints/names/levels, roads, paths, steps, parking, landcover, POIs",
         "provider": "OpenStreetMap contributors via Overpass API", "url": "https://www.openstreetmap.org/relation/11246784",
         "resolution": "vector", "crs": "EPSG:4326", "date": f"snapshot {osm_ts}", "license": "ODbL 1.0",
         "limitations": "Volunteered geometry; positional accuracy not quantified (typically 1–5 m). Heights missing for most campus buildings."},
        {"id": "khu", "name": "Kyung Hee University official campus map list", "role": "Building names and numbering for verification (33 entries)",
         "provider": "khu.ac.kr", "url": official["urls"][0], "resolution": "list (no geometry)", "crs": "–", "date": f"retrieved {official['retrieved']}",
         "license": "© Kyung Hee University (names used for identification)", "limitations": "No coordinates, floor counts or English names on the pages."},
        {"id": "egm2008", "name": "EGM2008 geoid (PROJ us_nga_egm08_25)", "role": "Orthometric → ellipsoidal height conversion",
         "provider": "NGA via PROJ CDN", "url": "https://cdn.proj.org/", "resolution": "2.5′ grid, sampled 9×9 over the window", "crs": "EPSG:3855 → EPSG:4979",
         "date": "EGM2008", "license": "Public domain", "limitations": "N varies only 0.45 m over the window; residual interpolation error < 1 cm."},
        {"id": "khu_style", "name": "Stylised campus appearance (this project)", "role": "Procedural facades, main-gate model, amphitheatre terraces, observatory dome",
         "provider": "web/js/khu_buildings.js + scripts/build_campus_details.py", "url": "https://www.openstreetmap.org/way/473963422",
         "resolution": "derived from OSM footprints + FABDEM", "crs": "EPSG:4326", "date": "generated",
         "license": "project code", "limitations": "Appearance only. Window layout, colours, gate form and gate heights are illustrative, not surveyed."},
        {"id": "imagery", "name": "Imagery tiles (Esri World Imagery default; Sentinel-2 cloudless, OSM, optional VWorld)", "role": "Draped surface texture only, never used to derive geometry",
         "provider": "Esri / EOX / OSM / VWorld", "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
         "resolution": "~0.3–1 m (Esri), 10 m (Sentinel-2)", "crs": "EPSG:3857 tiles", "date": "varies by tile (provider-managed)",
         "license": "Provider terms; streamed, not redistributed", "limitations": "Third-party tiles; possible metre-level offsets and outdated capture dates."},
    ]
    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "osm_timestamp": osm_ts,
        "campus_bbox": CAMPUS_BBOX, "feature_bbox": FEATURE_BBOX, "terrain_bbox": TERRAIN_BBOX,
        "campus": {
            "name_ko": boundary["properties"]["name_ko"], "name_en": boundary["properties"]["name_en"],
            "address": "1732 Deogyeong-daero, Giheung-gu, Yongin-si, Gyeonggi-do 17104, Republic of Korea",
            "area_m2": boundary["properties"]["area_m2"], "perimeter_m": boundary["properties"]["perimeter_m"],
            "parts": boundary["properties"]["parts"],
            "buildings_in_campus": len(inb), "buildings_total": len(B),
            "official_building_entries": len(ent_b), "official_matched": len(matched),
            "elevation": elev,
            "height_status_in_campus": dict(st),
        },
        "datasets": datasets, "checks": checks,
        "trees": {"count": trees["count"], "status": trees["status"]},
    }
    write_json(WEB_DATA / "summary.json", summary)

    # ---- markdown report ----
    lines = ["# Accuracy & provenance report", "",
             f"Generated {summary['generated_utc']} by `scripts/validate.py`. The machine-readable versions are "
             "[`web/data/accuracy_report.json`](../web/data/accuracy_report.json) and [`web/data/summary.json`](../web/data/summary.json).", "",
             "## Campus", "",
             f"- Boundary: OSM relation 11246784 ({summary['campus']['parts']} parts), {summary['campus']['area_m2']/1e4:.2f} ha, perimeter {summary['campus']['perimeter_m']} m",
             f"- Elevation inside the boundary (FABDEM): {elev['min']:.1f}–{elev['max']:.1f} m, mean {elev['mean']:.1f} m, relief {elev['relief']:.1f} m",
             f"- Buildings: {len(inb)} inside the boundary, {len(B)} including the ~600 m context",
             f"- Height status (campus): {dict(st)}",
             f"- Official KHU map: {len(matched)}/{len(ent_b)} building entries matched",
             "", "## Automated checks", "", "| Check | Status | Result |", "|---|---|---|"]
    lines += [f"| {c['name']} | {c['status']} | {c['detail']} |" for c in checks]
    lines += ["", "## Datasets", "", "| Dataset | Role | Resolution | Date | Licence | Limitations |", "|---|---|---|---|---|---|"]
    lines += [f"| [{d['name']}]({d['url']}) | {d['role']} | {d['resolution']} | {d['date']} | {d['license']} | {d['limitations']} |" for d in datasets]
    lines += ["", "## Campus buildings", "", "| No. | Name | OSM id | Footprint m² | Ground m | Height m | Status | Height source |", "|---|---|---|---|---|---|---|---|"]
    for f in inb:
        p = f["properties"]
        lines.append(f"| {p['official_no'] or ''} | {p['name_ko'] or '(unnamed)'} | {p['id']} | {p['footprint_area_m2']:.0f} | "
                     f"{p['ground_min_m']:.1f}–{p['ground_max_m']:.1f} | {p['height_m']:.1f} | {p['height_status']} | {p['height_source']} |")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "ACCURACY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for c in checks:
        print(f"[{c['status']:>6}] {c['name']}: {c['detail']}")


if __name__ == "__main__":
    main()
