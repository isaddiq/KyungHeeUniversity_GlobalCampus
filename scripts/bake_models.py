"""Pre-bake the campus geometry into web/data/baked (run before deploying; the site stays static).

    python scripts/bake_models.py            # re-bake only the groups whose inputs changed
    python scripts/bake_models.py --force    # re-bake everything
    python scripts/bake_models.py --check    # CI: exit 1 if web/data/baked does not match its inputs

What it produces (all referenced from web/data/baked/manifest.json, file names carry a content hash):
  buildings.<h>.json/.bin       every campus building and landmark model (one item per building)
  ground_objects.<h>.json/.bin  fountains, hedges, terraces, nets, stairs, cherry trees ... (one item each)
  (trees are not baked: generating them in the browser is cheaper than downloading ~4 MB; see docs/PERFORMANCE.md)
  ground.<h>.json               ground.json with its surface polygons validated (and the baked objects removed)
  details.<h>.json              campus_details.json without the modelling specs (only needed to generate models)

The geometry is made by the site's own generator code (web/js/*) running in headless Chromium via
tools/bake.js, so baked and in-browser geometry are the same. Format: web/js/baked.js.
Needs: pip install playwright && python -m playwright install chromium, and network access for the Cesium
build from the CDN (the same URL as web/index.html). --check needs neither (only the standard library).
"""
from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import http.server
import json
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = WEB / "data" / "baked"
D = "web/data/"
J = "web/js/"
COMMON = [J + "mesh.js", J + "baked.js", J + "dem_core.js", J + "terrain.js", "tools/bake.js", "scripts/bake_models.py",
          D + "terrain/dtm.bin", D + "terrain/dtm.json", D + "terrain/terrain_mods.json"]
INPUTS = {
    "buildings": COMMON + [J + "khu_buildings.js", J + "khu_landmarks.js", J + "gate_sculpture.js",
                           D + "buildings_campus.geojson", D + "campus_details.json"],
    "ground_objects": COMMON + [J + "ground_objects.js", J + "khu_landmarks.js", J + "gate_sculpture.js", D + "ground.json"],
    "ground": ["tools/bake.js", "scripts/bake_models.py", D + "ground.json"],
    "details": ["scripts/bake_models.py", D + "campus_details.json"],
}
GEOMETRY = ("buildings", "ground_objects")   # trees: generated in the browser (2.6k trees bake to ~4 MB gz vs 37 kB source)
TEXT = (".js", ".json", ".geojson", ".py", ".html")


def file_digest(rel: str) -> str:
    data = (ROOT / rel).read_bytes()
    if rel.endswith(TEXT):          # line endings differ between Windows checkouts and CI: hash LF text
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def inputs_hash(group: str) -> str:
    h = hashlib.sha256()
    for rel in sorted(set(INPUTS[group])):
        h.update(rel.encode() + b"\0" + file_digest(rel).encode() + b"\n")
    return h.hexdigest()[:16]


def content_name(stem: str, data: bytes, ext: str) -> str:
    return f"{stem}.{hashlib.sha256(data).hexdigest()[:10]}{ext}"


def slim_details(details: dict) -> dict:
    """campus_details without what only the model generator reads (kept: ids, clip, pools, courtyards ...)."""
    out = dict(details)
    out["slim"] = True
    out["photo_buildings"] = {k: {kk: v[kk] for kk in ("open_courtyard", "name_en") if kk in v}
                              for k, v in details.get("photo_buildings", {}).items()}
    if "amphitheatre" in out and details.get("theatre"):
        out["amphitheatre"] = {k: v for k, v in details["amphitheatre"].items() if k != "tiers"}
    return out


def check(manifest: dict | None) -> list[str]:
    problems = []
    if not manifest:
        return ["web/data/baked/manifest.json is missing"]
    for g in GEOMETRY:
        e = manifest.get("groups", {}).get(g)
        if not e:
            problems.append(f"{g}: not baked")
            continue
        if e.get("inputs") != inputs_hash(g):
            problems.append(f"{g}: inputs changed since the bake")
        for f in (e["manifest"], e["bin"]):
            if not (OUT / f).exists():
                problems.append(f"{g}: {f} missing")
    for g, key in (("ground", "ground"), ("details", "details")):
        if manifest.get("inputs", {}).get(g) != inputs_hash(g):
            problems.append(f"{g}: inputs changed since the bake")
        if not manifest.get(key) or not (OUT / manifest[key]).exists():
            problems.append(f"{g}: file missing")
    return problems


def cesium_url() -> str:
    m = re.search(r'<script src="(https://[^"]+/Cesium\.js)"', (WEB / "index.html").read_text(encoding="utf8"))
    if not m:
        sys.exit("could not find the Cesium script tag in web/index.html")
    return m.group(1)


def run_browser_bake(groups: list[str]) -> dict:
    from playwright.sync_api import sync_playwright

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("console", lambda m: m.type in ("warning", "error") and print("  [browser]", m.text))
            page.goto(f"http://127.0.0.1:{srv.server_address[1]}/tools/bake.html")
            page.add_script_tag(url=cesium_url())
            page.wait_for_function("!!window.Cesium", timeout=120_000)
            result = page.evaluate("(g) => import('/tools/bake.js').then((m) => m.bake(g))", groups)
            browser.close()
            return result
    finally:
        srv.shutdown()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    mpath = OUT / "manifest.json"
    old = json.loads(mpath.read_text()) if mpath.exists() else None
    if a.check:
        problems = check(old)
        if problems:
            print("baked geometry is out of date:\n  " + "\n  ".join(problems) + "\nrun: python scripts/bake_models.py")
            sys.exit(1)
        print("baked geometry matches its inputs")
        return

    OUT.mkdir(parents=True, exist_ok=True)
    manifest = old if old and not a.force else {"version": 1, "groups": {}, "inputs": {}}
    manifest.setdefault("groups", {}); manifest.setdefault("inputs", {})
    todo = [g for g in GEOMETRY if a.force or manifest["groups"].get(g, {}).get("inputs") != inputs_hash(g)
            or not all((OUT / manifest["groups"][g][k]).exists() for k in ("manifest", "bin"))]
    if a.force or manifest["inputs"].get("ground") != inputs_hash("ground") or not (OUT / str(manifest.get("ground"))).exists():
        todo.append("ground")
    keep = set()
    if todo:
        print("baking:", ", ".join(todo), flush=True)
        res = run_browser_bake(todo)
        print(f"  generated in {res['ms']} ms (browser)")
        for g in GEOMETRY:
            if g not in todo:
                continue
            data = base64.b64decode(res[g]["b64"])
            gm = res[g]["manifest"]
            bin_name = content_name(g, data, ".bin")
            gm["bin"] = bin_name
            meta = json.dumps(gm, separators=(",", ":"), ensure_ascii=False).encode()
            man_name = content_name(g, meta, ".json")
            (OUT / bin_name).write_bytes(data)
            (OUT / man_name).write_bytes(meta)
            manifest["groups"][g] = {"manifest": man_name, "bin": bin_name, "inputs": inputs_hash(g),
                                     "items": len(gm["items"]), "vertices": gm["vertices"], "triangles": gm["indices"] // 3,
                                     "bytes": len(data), "duplicate_vertices_removed": gm["duplicateVerticesRemoved"]}
            print(f"  {g}: {len(gm['items'])} items, {gm['vertices']} vertices, {gm['indices'] // 3} triangles, "
                  f"{len(data) / 1024:.0f} kB (+{len(meta) / 1024:.0f} kB index), {gm['duplicateVerticesRemoved']} duplicate vertices removed")
        if "ground" in todo:
            data = json.dumps(res["ground"]["data"], separators=(",", ":"), ensure_ascii=False).encode()
            manifest["ground"] = content_name("ground", data, ".json")
            (OUT / manifest["ground"]).write_bytes(data)
            manifest["inputs"]["ground"] = inputs_hash("ground")
            print(f"  ground: {len(res['ground']['data']['fills'])} surface polygons kept, {res['ground']['dropped']} degenerate dropped")
    else:
        print("geometry inputs unchanged: nothing to bake")
    details = json.loads((WEB / "data" / "campus_details.json").read_text(encoding="utf8"))
    data = json.dumps(slim_details(details), separators=(",", ":"), ensure_ascii=False).encode()
    manifest["details"] = content_name("details", data, ".json")
    (OUT / manifest["details"]).write_bytes(data)
    manifest["inputs"]["details"] = inputs_hash("details")
    manifest["version"] = 1
    manifest["note"] = "Generated by scripts/bake_models.py - do not edit. Geometry format: web/js/baked.js."
    # drop files of earlier bakes that the manifest no longer references
    keep = {manifest["ground"], manifest["details"], "manifest.json"}
    for e in manifest["groups"].values():
        keep |= {e["manifest"], e["bin"]}
    for f in OUT.iterdir():
        if f.name not in keep:
            f.unlink()
    mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf8")
    problems = check(manifest)
    if problems:
        sys.exit("bake incomplete: " + "; ".join(problems))
    print("wrote", mpath.relative_to(ROOT))


if __name__ == "__main__":
    main()
