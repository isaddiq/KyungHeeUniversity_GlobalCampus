"""Bilinear DEM sampler over the PixelIsPoint crops written by build_terrain.py."""
from __future__ import annotations

import numpy as np

from common import RAW, read_json


class Grid:
    def __init__(self, arr: np.ndarray, meta: dict):
        self.z = arr
        self.west, self.north = meta["west"], meta["north"]
        self.dlon, self.dlat = meta["dlon"], meta["dlat"]
        self.rows, self.cols = arr.shape

    def sample(self, lon, lat):
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        fx = np.clip((lon - self.west) / self.dlon, 0, self.cols - 1.000001)
        fy = np.clip((self.north - lat) / self.dlat, 0, self.rows - 1.000001)
        x0 = np.floor(fx).astype(int)
        y0 = np.floor(fy).astype(int)
        tx, ty = fx - x0, fy - y0
        z = self.z
        return (z[y0, x0] * (1 - tx) * (1 - ty) + z[y0, x0 + 1] * tx * (1 - ty)
                + z[y0 + 1, x0] * (1 - tx) * ty + z[y0 + 1, x0 + 1] * tx * ty)


def load():
    meta = read_json(RAW / "crop_meta.json")
    return Grid(np.load(RAW / "dtm_crop.npy"), meta), Grid(np.load(RAW / "dsm_crop.npy"), meta)
