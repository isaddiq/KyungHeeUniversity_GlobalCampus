"""Phase 2: download real elevation data covering the campus (tile N37 E127).

1. FABDEM V1-2 (Hawker et al. 2022, Univ. of Bristol) - Copernicus GLO-30 with forests and
   buildings removed => bare-earth DTM, 1 arc-second, EGM2008 heights. CC BY-NC-SA 4.0.
   The 10x10 degree zip is 640 MB; we read ONLY the N37E127 member via HTTP range requests.
2. Copernicus DEM GLO-30 (ESA / Airbus, AWS open data) - surface model (DSM), 1 arc-second,
   EGM2008 heights. Used for DSM-DTM cross-checks of building heights and as provenance.
"""
from __future__ import annotations

import io
import urllib.request
import zipfile

from common import RAW, USER_AGENT, http_get

COP_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N37_00_E127_00_DEM/"
           "Copernicus_DSM_COG_10_N37_00_E127_00_DEM.tif")
FAB_ZIP_URL = "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/N30E120-N40E130_FABDEM_V1-2.zip"
FAB_MEMBER = "N37E127_FABDEM_V1-2.tif"


class HttpRangeFile(io.RawIOBase):
    """Minimal seekable read-only file over HTTP Range requests (enough for zipfile)."""

    def __init__(self, url: str):
        self.url = url
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Length"])
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n) - 1
        data = http_get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        self.pos += len(data)
        return data

    def readinto(self, b):
        d = self.read(len(b))
        b[: len(d)] = d
        return len(d)


def main():
    cop = RAW / "copernicus_glo30_N37E127.tif"
    if not cop.exists():
        print("downloading Copernicus GLO-30 tile ...")
        cop.write_bytes(http_get(COP_URL, timeout=600))
    print("copernicus", cop.stat().st_size, "bytes")

    fab = RAW / "fabdem_v1-2_N37E127.tif"
    if not fab.exists():
        print("reading FABDEM zip central directory via HTTP range ...")
        zf = zipfile.ZipFile(io.BufferedReader(HttpRangeFile(FAB_ZIP_URL), buffer_size=1 << 20))
        names = zf.namelist()
        member = next((n for n in names if n.endswith(FAB_MEMBER)), None)
        if member is None:
            raise SystemExit(f"{FAB_MEMBER} not in zip; members: {names[:10]}...")
        info = zf.getinfo(member)
        print("member", member, info.compress_size, "->", info.file_size)
        fab.write_bytes(zf.read(member))
    print("fabdem", fab.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
