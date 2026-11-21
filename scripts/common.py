"""Shared configuration and geodesy helpers for the KHU Global Campus digital-twin pipeline.

All geographic coordinates are WGS84 (EPSG:4326) longitude/latitude in degrees.
Metric work (areas, distances, local coordinates) uses Korea 2000 / Central Belt 2010
(EPSG:5186, Transverse Mercator on GRS80) implemented here with Kruger series
(Karney 2011), accurate to well below 1 mm inside Korea.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
WEB_DATA = ROOT / "web" / "data"
RAW.mkdir(parents=True, exist_ok=True)
WEB_DATA.mkdir(parents=True, exist_ok=True)

USER_AGENT = "khu-global-campus-digital-twin/1.0 (static research pipeline)"

# OSM relation of the campus (amenity=university, name=경희대학교 국제캠퍼스)
CAMPUS_RELATION_ID = 11246784

# Campus bounding box as reported by OSM/Nominatim for relation 11246784
CAMPUS_BBOX = {"south": 37.2366366, "north": 37.2498042, "west": 127.0759682, "east": 127.0876156}

# Feature context: campus bbox + ~600 m on every side (spec asks for ~500 m)
FEATURE_PAD_M = 600.0
# Terrain context: a much wider, still lightweight window so the horizon is real terrain
TERRAIN_PAD_M = 6000.0


def pad_bbox(b: dict, pad_m: float) -> dict:
    lat_c = (b["south"] + b["north"]) / 2
    dlat = pad_m / 111_320.0
    dlon = pad_m / (111_320.0 * math.cos(math.radians(lat_c)))
    return {"south": b["south"] - dlat, "north": b["north"] + dlat,
            "west": b["west"] - dlon, "east": b["east"] + dlon}


FEATURE_BBOX = pad_bbox(CAMPUS_BBOX, FEATURE_PAD_M)
TERRAIN_BBOX = pad_bbox(CAMPUS_BBOX, TERRAIN_PAD_M)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http_get(url: str, data: bytes | None = None, headers: dict | None = None,
             retries: int = 4, timeout: int = 180) -> bytes:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"GET failed for {url}: {last}")


def write_json(path: Path, obj, compact: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Transverse Mercator (EPSG:5186) - Kruger series, Karney (2011)
# ---------------------------------------------------------------------------
_A = 6378137.0
_F = 1 / 298.257222101  # GRS80
_N = _F / (2 - _F)
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_ALPHA = [
    _N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16,
    13 * _N ** 2 / 48 - 3 * _N ** 3 / 5,
    61 * _N ** 3 / 240,
]
_E = math.sqrt(_F * (2 - _F))

EPSG5186 = {"lat0": 38.0, "lon0": 127.0, "k0": 1.0, "fe": 200000.0, "fn": 600000.0}


def _tm_raw(lon: float, lat: float, lon0: float):
    phi = math.radians(lat)
    lam = math.radians(lon - lon0)
    t = math.sinh(math.atanh(math.sin(phi)) - _E * math.atanh(_E * math.sin(phi)))
    xi_p = math.atan2(t, math.cos(lam))
    eta_p = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi, eta = xi_p, eta_p
    for j, a in enumerate(_ALPHA, start=1):
        xi += a * math.sin(2 * j * xi_p) * math.cosh(2 * j * eta_p)
        eta += a * math.cos(2 * j * xi_p) * math.sinh(2 * j * eta_p)
    return _AA * eta, _AA * xi  # easting-ish, northing-ish (unscaled, no offsets)


_, _Y0 = _tm_raw(EPSG5186["lon0"], EPSG5186["lat0"], EPSG5186["lon0"])


def to_epsg5186(lon: float, lat: float):
    """WGS84/GRS80 lon, lat (deg) -> EPSG:5186 (x=Easting, y=Northing) in metres."""
    x, y = _tm_raw(lon, lat, EPSG5186["lon0"])
    k0 = EPSG5186["k0"]
    return EPSG5186["fe"] + k0 * x, EPSG5186["fn"] + k0 * (y - _Y0)


def ring_area_m2(ring_lonlat) -> float:
    """Planar area of a lon/lat ring after projecting to EPSG:5186 (scale factor ~1.0000x here)."""
    pts = [to_epsg5186(lo, la) for lo, la in ring_lonlat]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def haversine_m(lon1, lat1, lon2, lat2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


if __name__ == "__main__":
    print("feature bbox", FEATURE_BBOX)
    print("terrain bbox", TERRAIN_BBOX)
    print("campus centre EPSG:5186", to_epsg5186(127.0813337, 37.2424001))
    print("env", os.name)
