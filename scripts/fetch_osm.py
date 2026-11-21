"""Phase 1/2: download OpenStreetMap features for the campus and a ~600 m context buffer.

Source: OpenStreetMap contributors via the Overpass API (ODbL 1.0).
Output: data/raw/osm_overpass.json (raw Overpass JSON with full geometry)
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

from common import CAMPUS_RELATION_ID, FEATURE_BBOX, RAW, http_get, write_json

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def build_query() -> str:
    b = FEATURE_BBOX
    bb = f"{b['south']:.6f},{b['west']:.6f},{b['north']:.6f},{b['east']:.6f}"
    return f"""
[out:json][timeout:180];
(
  relation({CAMPUS_RELATION_ID});
  way["amenity"="university"]({bb});
  relation["amenity"="university"]({bb});
  way["building"]({bb});
  relation["building"]({bb});
  way["building:part"]({bb});
  way["highway"]({bb});
  way["area:highway"]({bb});
  way["landuse"]({bb});
  relation["landuse"]({bb});
  way["leisure"]({bb});
  relation["leisure"]({bb});
  way["natural"]({bb});
  relation["natural"]({bb});
  node["natural"~"^(tree|peak)$"]({bb});
  way["amenity"~"^(parking|school|kindergarten|place_of_worship|hospital|fountain)$"]({bb});
  relation["amenity"="parking"]({bb});
  way["barrier"~"^(retaining_wall|wall|fence)$"]({bb});
  way["man_made"]({bb});
  way["waterway"]({bb});
  way["water"]({bb});
  way["place"~"^(square)$"]({bb});
  node["entrance"]({bb});
  node["highway"~"^(bus_stop|traffic_signals|crossing|steps)$"]({bb});
);
out body geom;
"""


def main():
    q = build_query()
    data = None
    for ep in ENDPOINTS:
        try:
            raw = http_get(ep, data=("data=" + urllib.parse.quote(q)).encode(),
                           headers={"Content-Type": "application/x-www-form-urlencoded"})
            data = json.loads(raw)
            data["_endpoint"] = ep
            break
        except Exception as e:  # noqa: BLE001
            print("endpoint failed", ep, e)
    if data is None:
        raise SystemExit("All Overpass endpoints failed")
    data["_retrieved_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["_bbox"] = FEATURE_BBOX
    write_json(RAW / "osm_overpass.json", data, compact=True)
    kinds = {}
    for el in data["elements"]:
        kinds[el["type"]] = kinds.get(el["type"], 0) + 1
    print("elements:", kinds, "osm_base:", data.get("osm3s", {}).get("timestamp_osm_base"))


if __name__ == "__main__":
    main()
