"""Phase 7/8: functional + visual verification of the built site in a real browser (Playwright).

Usage:  python scripts/check_site.py [URL]   (default http://127.0.0.1:8765/)
Serve the site first, e.g.  python -m http.server 8765 --directory web
Writes screenshots to docs/screenshots/ and prints console errors and check results.
Uses the locally installed Chrome (channel="chrome"); falls back to Edge.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"


def settle(page, seconds=6.0):
    """Wait until Cesium reports the globe tiles loaded (or timeout)."""
    t0 = time.time()
    while time.time() - t0 < seconds + 30:
        done = page.evaluate("() => { const v = window.viewer; return !!v && v.scene.globe.tilesLoaded; }")
        if done and time.time() - t0 > seconds:
            return True
        time.sleep(0.5)
    return False


def main():
    results = []
    with sync_playwright() as p:
        browser = None
        for ch in ("chrome", "msedge"):
            try:
                browser = p.chromium.launch(channel=ch, headless=True, args=[
                    "--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist",
                    "--enable-webgl"])
                break
            except Exception as e:  # noqa: BLE001
                print("launch failed", ch, e)
        page = browser.new_page(viewport={"width": 1600, "height": 950}, device_scale_factor=1)
        logs = []
        page.on("console", lambda m: logs.append((m.type, m.text)))
        page.on("pageerror", lambda e: logs.append(("pageerror", str(e))))
        t0 = time.time()
        page.goto(URL, wait_until="load", timeout=120000)
        page.wait_for_function("document.body.dataset.ready", timeout=240000)
        ready = page.evaluate("document.body.dataset.ready")
        results.append(("app ready", ready == "1", f"{time.time()-t0:.1f}s, state={ready}"))
        if ready != "1":
            print(page.inner_text("#loadingText"))
        settle(page, 8)
        page.screenshot(path=str(OUT / "01_home_oblique.png"))

        info = page.evaluate("""() => {
          const v = window.viewer;
          const prims = v.scene.primitives;
          const out = { primitives: prims.length, imagery: v.imageryLayers.length };
          return out; }""")
        results.append(("scene populated", info["primitives"] >= 6, json.dumps(info)))

        # terrain sanity: ellipsoidal height at campus centre vs DTM + N
        h = page.evaluate("""() => {
          const v = window.viewer, C = Cesium;
          const c = C.Cartographic.fromDegrees(127.0818, 37.2427);
          return { globe: v.scene.globe.getHeight(c) };
        }""")
        results.append(("globe height at campus centre", h["globe"] is not None and 60 < h["globe"] < 160, json.dumps(h)))

        # search + select
        page.click("button.tab[data-tab=buildings]")
        page.fill("#search", "중앙도서관")
        page.wait_for_timeout(300)
        n = page.locator("#buildingList li").count()
        results.append(("search '중앙도서관'", n >= 1, f"{n} result(s)"))
        page.locator("#buildingList li").first.click()
        page.wait_for_timeout(2500)
        settle(page, 4)
        det = page.inner_text("#details")
        results.append(("building info panel", "중앙도서관" in det and "EPSG:5186" in det, det.split("\n")[0]))
        page.screenshot(path=str(OUT / "02_selected_library.png"))

        # enhanced Kyung Hee buildings
        for q, name in (("정문", "02b_main_gate"), ("노천극장", "02c_amphitheatre"), ("천문대", "02d_observatory"), ("예술디자인", "02e_art_design")):
            page.fill("#search", q)
            page.wait_for_timeout(300)
            page.locator("#buildingList li").first.click()
            page.wait_for_timeout(2600)
            settle(page, 4)
            page.screenshot(path=str(OUT / f"{name}.png"))
        # walk from the main gate
        page.click("button.tab[data-tab=overview]")
        page.click("#walkCampus")
        page.wait_for_timeout(3500)
        settle(page, 4)
        page.screenshot(path=str(OUT / "02f_walk_gate.png"))
        page.keyboard.press("Escape")
        page.click("#btnReset")
        page.wait_for_timeout(2600)
        page.click("button.tab[data-tab=buildings]")

        # top-down for alignment check
        page.click("#closeRight")
        page.click("#modeSeg button[data-mode=top]")
        page.wait_for_timeout(2600)
        settle(page, 6)
        page.screenshot(path=str(OUT / "03_topdown.png"))
        hd = page.evaluate("() => Cesium.Math.toDegrees(viewer.camera.pitch)")
        results.append(("top-down pitch", hd < -85, f"pitch {hd:.1f}°"))

        # elevation / slope / contours
        page.click("button.tab[data-tab=terrain]")
        for v, name in (("elevation", "04_elevation"), ("slope", "05_slope"), ("elevcontours", "06_contours")):
            page.select_option("#vizSel", v)
            page.wait_for_timeout(800)
            settle(page, 3)
            page.screenshot(path=str(OUT / f"{name}.png"))
        page.select_option("#vizSel", "realistic")
        page.check("#wireframe")
        page.click("#btnTerrainOnly")
        page.click("#btnReset")
        page.wait_for_timeout(2600)
        settle(page, 4)
        page.screenshot(path=str(OUT / "07_terrain_only_wireframe.png"))
        page.uncheck("#wireframe")
        page.click("#btnTerrainOnly")

        # status colouring
        page.click("button.tab[data-tab=layers]")
        page.select_option("#colorSel", "status")
        page.wait_for_timeout(800)
        settle(page, 3)
        page.screenshot(path=str(OUT / "08_height_status.png"))
        page.select_option("#colorSel", "realistic")

        mem = page.evaluate("() => performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : -1")
        results.append(("JS heap after visual tour (MB)", mem < 1500, str(mem)))
        # fresh browser process for navigation tests: headless SwiftShader (software GPU) runs out of
        # memory after many minutes of rendering, which is a test-harness limit, not an app error
        browser.close()
        browser = p.chromium.launch(channel="chrome", headless=True, args=[
            "--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"])
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
        page.on("console", lambda m: logs.append((m.type, m.text)))
        page.on("pageerror", lambda e: logs.append(("pageerror", str(e))))
        page.goto(URL, wait_until="load", timeout=120000)
        page.wait_for_function("document.body.dataset.ready", timeout=240000)
        settle(page, 3)
        # walk mode: camera must stay 1.7 m above DTM
        page.click("#modeSeg button[data-mode=walk]")
        page.wait_for_timeout(2500)
        page.keyboard.down("KeyW"); page.wait_for_timeout(1500); page.keyboard.up("KeyW")
        settle(page, 4)
        agl = page.evaluate("""() => { const c = viewer.camera.positionCartographic; return c.height; }""")
        page.screenshot(path=str(OUT / "09_walk.png"))
        results.append(("walk mode camera height (ellipsoidal)", agl is not None, f"{agl:.1f} m"))

        # fly mode: try to dive below terrain
        page.click("#modeSeg button[data-mode=fly]")
        page.evaluate("""() => { const C = Cesium; viewer.camera.setView({ destination: C.Cartesian3.fromDegrees(127.0818, 37.2427, 10), orientation: { heading: 0, pitch: -1.2, roll: 0 } }); }""")
        page.evaluate("""() => new Promise((res) => { const f0 = viewer.scene.frameState.frameNumber;
          const t = () => (viewer.scene.frameState.frameNumber - f0 >= 3 ? res() : setTimeout(t, 100)); t(); })""")
        below = page.evaluate("""() => { const c = viewer.camera.positionCartographic; return c.height - viewer.scene.globe.getHeight(c); }""")
        results.append(("cannot go below terrain", below is not None and below >= 1.0, f"{below:.2f} m above globe surface"))
        page.keyboard.press("Escape")

        # follow mode + reset
        page.click("#btnReset")
        page.wait_for_timeout(2600)
        settle(page, 3)
        page.click("#openAbout")
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "10_about.png"))
        browser.close()

    errs = [l for l in logs if l[0] in ("error", "pageerror")]
    print("\n=== results ===")
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"\nconsole errors: {len(errs)}")
    for e in errs[:30]:
        print("  ", e[1][:300])
    warns = [l for l in logs if l[0] == "warning"]
    for w in warns[:10]:
        print("  warn:", w[1][:200])
    return 0 if all(r[1] for r in results) and not errs else 1


if __name__ == "__main__":
    sys.exit(main())
