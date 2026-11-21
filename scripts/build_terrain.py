"""Phase 3: terrain construction.

Inputs : data/raw/fabdem_v1-2_N37E127.tif   (bare-earth DTM, EGM2008)
         data/raw/copernicus_glo30_N37E127.tif (DSM, EGM2008, for cross-checks)
Outputs: web/data/terrain/dtm.bin        uint16 grid, row 0 = north, PixelIsPoint (see dtm.json)
         web/data/terrain/dtm.json       grid georeference, scale/offset, geoid grid, stats
         web/data/terrain/slope.jpg      slope in degrees, colour-ramped (overlay)
         web/data/terrain/hillshade.png  multi-directional hillshade, alpha-encoded (overlay)
         data/raw/dsm_crop.npy, dtm_crop.npy (+ json) for later validation steps

No smoothing, no vertical exaggeration. Heights are orthometric (EGM2008) in metres.
"""
from __future__ import annotations

import math

import numpy as np
import pyproj
import tifffile
from PIL import Image
from pyproj import Transformer

from common import RAW, TERRAIN_BBOX, WEB_DATA, write_json

ARCSEC = 1.0 / 3600.0
TILE_LON0, TILE_LAT0 = 127.0, 38.0  # PixelIsPoint: pixel (0,0) centre


def read_tile(path):
    with tifffile.TiffFile(path) as t:
        p = t.pages[0]
        tie = p.tags["ModelTiepointTag"].value
        scale = p.tags["ModelPixelScaleTag"].value
        gk = p.tags["GeoKeyDirectoryTag"].value
        assert abs(tie[3] - TILE_LON0) < 1e-9 and abs(tie[4] - TILE_LAT0) < 1e-9, tie
        assert abs(scale[0] - ARCSEC) < 1e-12 and abs(scale[1] - ARCSEC) < 1e-12, scale
        keys = {gk[i]: gk[i + 3] for i in range(4, len(gk), 4)}
        assert keys.get(1025) == 2, "expected PixelIsPoint raster type"
        assert keys.get(2048) == 4326, "expected WGS84 geographic CRS"
        return p.asarray().astype(np.float64)


def crop_window(bbox):
    c0 = int(math.floor((bbox["west"] - TILE_LON0) / ARCSEC))
    c1 = int(math.ceil((bbox["east"] - TILE_LON0) / ARCSEC))
    r0 = int(math.floor((TILE_LAT0 - bbox["north"]) / ARCSEC))
    r1 = int(math.ceil((TILE_LAT0 - bbox["south"]) / ARCSEC))
    return r0, r1, c0, c1


def geoid_grid(west, south, east, north, nx=9, ny=9):
    pyproj.network.set_network_enabled(True)
    t = Transformer.from_crs("EPSG:4326+3855", "EPSG:4979", always_xy=True)
    lons = np.linspace(west, east, nx)
    lats = np.linspace(north, south, ny)
    g = np.zeros((ny, nx))
    for j, la in enumerate(lats):
        for i, lo in enumerate(lons):
            g[j, i] = t.transform(lo, la, 0.0)[2]
    desc = t.description
    if not np.all(np.isfinite(g)) or np.ptp(g) == 0:
        raise SystemExit("geoid grid unavailable (PROJ network grid not reachable)")
    return g, desc


def slope_aspect(z, dx, dy):
    """Horn (1981) gradient on a metric grid. z row 0 = north."""
    zp = np.pad(z, 1, mode="edge")
    a, b, c = zp[:-2, :-2], zp[:-2, 1:-1], zp[:-2, 2:]
    d, f = zp[1:-1, :-2], zp[1:-1, 2:]
    g, h, i = zp[2:, :-2], zp[2:, 1:-1], zp[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * dy)  # positive = downhill to north
    return dzdx, dzdy


def bilinear_upsample(z, out_h, out_w):
    """Resample a PixelIsPoint grid onto a finer grid spanning the same outer pixel centres."""
    h, w = z.shape
    ys = np.linspace(0, h - 1, out_h)
    xs = np.linspace(0, w - 1, out_w)
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 2)
    x0 = np.clip(np.floor(xs).astype(int), 0, w - 2)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    z00 = z[y0][:, x0]
    z01 = z[y0][:, x0 + 1]
    z10 = z[y0 + 1][:, x0]
    z11 = z[y0 + 1][:, x0 + 1]
    return (z00 * (1 - fx) * (1 - fy) + z01 * fx * (1 - fy) + z10 * (1 - fx) * fy + z11 * fx * fy)


def slope_colour(deg):
    stops = [(0, (26, 152, 80)), (5, (145, 207, 96)), (10, (217, 239, 139)), (15, (254, 224, 139)),
             (20, (252, 141, 89)), (30, (215, 48, 39)), (45, (120, 0, 60))]
    out = np.zeros(deg.shape + (3,))
    xs = np.array([s[0] for s in stops], float)
    for ch in range(3):
        out[..., ch] = np.interp(deg, xs, [s[1][ch] for s in stops])
    return out.astype(np.uint8)


def main():
    out_dir = WEB_DATA / "terrain"
    out_dir.mkdir(parents=True, exist_ok=True)
    dtm_full = read_tile(RAW / "fabdem_v1-2_N37E127.tif")
    dsm_full = read_tile(RAW / "copernicus_glo30_N37E127.tif")
    r0, r1, c0, c1 = crop_window(TERRAIN_BBOX)
    dtm = dtm_full[r0:r1 + 1, c0:c1 + 1]
    dsm = dsm_full[r0:r1 + 1, c0:c1 + 1]
    assert np.all(dtm > -1000), "nodata inside crop"
    rows, cols = dtm.shape
    west = TILE_LON0 + c0 * ARCSEC
    north = TILE_LAT0 - r0 * ARCSEC
    east = west + (cols - 1) * ARCSEC
    south = north - (rows - 1) * ARCSEC
    print(f"crop {rows}x{cols}  lon {west:.6f}..{east:.6f}  lat {south:.6f}..{north:.6f}")
    print(f"DTM {dtm.min():.2f}..{dtm.max():.2f} m   DSM {dsm.min():.2f}..{dsm.max():.2f} m")

    hmin = math.floor(dtm.min()) - 1.0
    rng = dtm.max() - hmin
    scale = 0.01 if rng < 655 else 0.1  # cm precision when possible
    q = np.round((dtm - hmin) / scale).astype(np.uint16)
    q.astype("<u2").tofile(out_dir / "dtm.bin")
    qerr = np.abs(q * scale + hmin - dtm).max()

    lat_c = (north + south) / 2
    dx = ARCSEC * 111_320.0 * math.cos(math.radians(lat_c))  # approx metric spacing (info + slope)
    dy = ARCSEC * 110_950.0
    geoid, geoid_desc = geoid_grid(west, south, east, north)

    # ---- overlays (bilinear upsample, ~6 m/pixel; no smoothing of the source) ----
    up_w = 2048
    up_h = int(round(up_w * (rows - 1) * dy / ((cols - 1) * dx)))
    zu = bilinear_upsample(dtm, up_h, up_w)
    pdx = (cols - 1) * dx / (up_w - 1)
    pdy = (rows - 1) * dy / (up_h - 1)
    gx, gy = slope_aspect(zu, pdx, pdy)
    slope_deg = np.degrees(np.arctan(np.hypot(gx, gy)))
    Image.fromarray(slope_colour(slope_deg)).save(out_dir / "slope.jpg", quality=86, optimize=True)

    # Multi-directional hillshade (NW/W/N/NE weighted), encoded as black with alpha = shadow
    shade = np.zeros_like(zu)
    slope_r = np.arctan(np.hypot(gx, gy))
    aspect_r = np.arctan2(gy, -gx)
    alt = math.radians(45)
    for az, wgt in ((315, 0.5), (270, 0.2), (0, 0.2), (45, 0.1)):
        az_r = math.radians(360 - az + 90)
        shade += wgt * (math.sin(alt) * np.cos(slope_r) +
                        math.cos(alt) * np.sin(slope_r) * np.cos(az_r - aspect_r))
    shade = np.clip(shade, 0, 1)
    flat = math.sin(alt)
    dark = np.clip((flat - shade) / flat, 0, 1)  # 0 on flat ground
    light = np.clip((shade - flat) / (1 - flat), 0, 1)
    la = np.zeros(zu.shape + (2,), np.uint8)
    la[..., 0] = np.where(light > dark, 255, 0)
    alpha = np.maximum(dark * 230, light * 90)
    la[..., 1] = (np.clip(alpha, 0, 255) // 6 * 6).astype(np.uint8)  # coarse steps -> smaller PNG
    Image.fromarray(la, mode="LA").save(out_dir / "hillshade.png", optimize=True)

    # pixel centres of the overlay span exactly the DEM's outer pixel centres; extend by half a
    # pixel so the PNG rectangle (edge-referenced) is aligned correctly
    hx, hy = 0.5 * (east - west) / (up_w - 1), 0.5 * (north - south) / (up_h - 1)
    overlay_rect = [west - hx, south - hy, east + hx, north + hy]

    meta = {
        "description": "FABDEM V1-2 bare-earth DTM crop (orthometric, EGM2008), PixelIsPoint",
        "format": "uint16 little-endian, row-major, row 0 = north edge; height = value*scale + offset",
        "rows": rows, "cols": cols,
        "west": west, "south": south, "east": east, "north": north,
        "dlon": ARCSEC, "dlat": ARCSEC,
        "scale": scale, "offset": hmin, "quantisation_error_max_m": round(float(qerr), 4),
        "spacing_m": {"x": round(dx, 3), "y": round(dy, 3)},
        "stats": {"min": round(float(dtm.min()), 2), "max": round(float(dtm.max()), 2),
                  "mean": round(float(dtm.mean()), 2)},
        "vertical_datum": "EGM2008 geoid (EPSG:3855)",
        "geoid": {"model": "EGM2008 via PROJ (us_nga_egm08_25)", "pipeline": geoid_desc,
                  "nx": geoid.shape[1], "ny": geoid.shape[0],
                  "west": west, "south": south, "east": east, "north": north,
                  "row0": "north", "N_m": [[round(float(v), 3) for v in row] for row in geoid]},
        "overlays": {"rectangle_deg": overlay_rect, "width": up_w, "height": up_h,
                     "pixel_m": [round(pdx, 2), round(pdy, 2)],
                     "slope": "slope.jpg", "hillshade": "hillshade.png",
                     "slope_legend_deg": [0, 5, 10, 15, 20, 30, 45]},
    }
    write_json(out_dir / "dtm.json", meta)
    np.save(RAW / "dtm_crop.npy", dtm)
    np.save(RAW / "dsm_crop.npy", dsm)
    write_json(RAW / "crop_meta.json", {k: meta[k] for k in ("rows", "cols", "west", "south", "east", "north", "dlon", "dlat")})
    print("quantisation", scale, "max err", qerr, "geoid N", geoid.min(), geoid.max())
    print("overlay", up_w, up_h, "px", pdx, pdy, "m/px; max slope", slope_deg.max())


if __name__ == "__main__":
    main()
