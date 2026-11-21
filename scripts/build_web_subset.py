"""Small browser copies of the feature layers (the viewer shows only the university grounds).

The full files (buildings/roads/landcover with the ~600 m context ring, trees over the whole terrain window)
stay the pipeline's source of truth for validation and model inputs; the site loads these subsets instead:
  buildings_campus.geojson, roads_campus.geojson, landcover_campus.geojson  - features with in_campus = true
  trees_campus.bin / trees_campus.json                                         - trees inside the campus crop
Output is byte-for-byte derived from the full files (no geometry changes).
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

from common import WEB_DATA, read_json, write_json


def main():
    sizes = {}
    for name in ("buildings", "roads", "landcover"):
        fc = read_json(WEB_DATA / f"{name}.geojson")
        sub = {"type": "FeatureCollection", "features": [f for f in fc["features"] if f["properties"].get("in_campus")]}
        write_json(WEB_DATA / f"{name}_campus.geojson", sub, compact=True)
        sizes[name] = (len(fc["features"]), len(sub["features"]))
    clip = read_json(WEB_DATA / "campus_details.json")["clip"]
    clip_p = prep(Polygon(clip["rings"][0]).union(*[Polygon(r) for r in clip["rings"][1:]]) if len(clip["rings"]) > 1 else Polygon(clip["rings"][0]))
    meta = read_json(WEB_DATA / "trees.json")
    arr = np.fromfile(WEB_DATA / "trees.bin", dtype="<f4").reshape(-1, 4)
    keep = np.array([clip_p.contains(Point(meta["origin_lon"] + x, meta["origin_lat"] + y)) for x, y in arr[:, :2]])
    mapped = int(meta.get("mapped_count", 0))
    sub = arr[keep]
    arr[keep].astype("<f4").tofile(WEB_DATA / "trees_campus.bin")
    write_json(WEB_DATA / "trees_campus.json", {**meta, "count": int(keep.sum()), "mapped_count": int(keep[:mapped].sum()),
                                                "subset": "trees inside the campus crop (campus boundary + 30 m)"})
    print("web subsets", sizes, "trees", len(arr), "->", len(sub))


if __name__ == "__main__":
    main()
