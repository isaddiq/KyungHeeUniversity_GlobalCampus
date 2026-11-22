"""Reproducible load + rendering benchmark for the static site (Playwright / Chromium, real GPU via ANGLE).

    pip install playwright && python -m playwright install chromium
    python scripts/bench.py                       # desktop + mobile-class, cold + warm cache, 3 runs each
    python scripts/bench.py --runs 5 --out docs/bench_after.json
    python scripts/bench.py --profile             # also print the hottest JS functions during start-up

What is measured (all from the browser, nothing is estimated):
  * stage marks written by web/js/main.js (khu:viewer, khu:first-frame, khu:layers, khu:ready, ...)
  * long tasks (> 50 ms) and total blocking time between navigation and khu:ready
  * bytes transferred (encoded, i.e. after gzip/brotli) and request count, split by origin
  * JS heap after start-up
  * frame times during a fixed scripted camera flight (overview orbit + low pass over the gate), plus
    Cesium draw commands per frame - once per run, after the warm load
Each load runs in its own browser process; the warm load reuses the cold load's on-disk HTTP cache.
"mobile" = 390x844 touch viewport (the site's mobile code path) with 4x CPU throttling and a 12 Mbit/s,
80 ms network on the same GPU. It is a mobile-class approximation, not a phone. The local server gzips
like GitHub Pages, so transferred sizes match what the published site sends.
"""
from __future__ import annotations

import argparse
import functools
import gzip
import os
import shutil
import tempfile
import http.server
import json
import statistics
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parent.parent / "web"   # --web points elsewhere (e.g. a worktree of an older commit)
GPU_ARGS = ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu", "--disable-gpu-vsync",
            "--disable-frame-rate-limit"]

INIT = """
window.__lt = [];
try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([e.startTime, e.duration]); })
        .observe({ type: 'longtask', buffered: true }); } catch (e) {}
"""

COLLECT = """() => {
  const m = {}; for (const e of performance.getEntriesByType('mark')) if (e.name.startsWith('khu:')) m[e.name.slice(4)] = Math.round(e.startTime);
  const fcp = performance.getEntriesByName('first-contentful-paint')[0];
  const ready = m.ready ?? performance.now();
  const lt = window.__lt.filter(([s]) => s <= ready);
  return { marks: m, fcp: fcp ? Math.round(fcp.startTime) : null,
           longTasks: lt.length, longTaskMs: Math.round(lt.reduce((a, [, d]) => a + d, 0)),
           tbt: Math.round(lt.reduce((a, [, d]) => a + Math.max(0, d - 50), 0)),
           heapMB: performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null };
}"""

# fixed flight: 3 s orbit around the campus centre at 900 m range, then 3 s low pass towards the gate
FLIGHT = """async () => {
  const C = Cesium, v = viewer, s = v.scene, dem = window.__layers.dem;
  const ctr = C.Cartesian3.fromDegrees(127.0818, 37.2427, dem.heightEllipsoid(127.0818, 37.2427));
  const times = [], cmds = [];
  const frame = () => new Promise((r) => requestAnimationFrame(r));
  let last = performance.now();
  const step = () => { const t = performance.now(); times.push(t - last); last = t;
    cmds.push(s.frameState.commandList.length); };
  const T0 = performance.now();
  while (performance.now() - T0 < 3000) {
    const a = (performance.now() - T0) / 3000;
    v.camera.lookAt(ctr, new C.HeadingPitchRange(C.Math.toRadians(20 + 120 * a), C.Math.toRadians(-32), 900));
    s.requestRender(); await frame(); step();
  }
  v.camera.lookAtTransform(C.Matrix4.IDENTITY);
  const T1 = performance.now();
  while (performance.now() - T1 < 3000) {
    const a = (performance.now() - T1) / 3000;
    const lon = 127.0776 + 0.0007 * a, lat = 37.2481 - 0.0007 * a;
    v.camera.setView({ destination: C.Cartesian3.fromDegrees(lon, lat, dem.heightEllipsoid(lon, lat) + 40),
      orientation: { heading: C.Math.toRadians(135), pitch: C.Math.toRadians(-20), roll: 0 } });
    s.requestRender(); await frame(); step();
  }
  times.shift(); cmds.shift();
  const sorted = [...times].sort((a, b) => a - b);
  const mean = times.reduce((a, b) => a + b, 0) / times.length;
  return { frames: times.length, fps: +(1000 / mean).toFixed(1), meanMs: +mean.toFixed(1),
           p95Ms: +sorted[Math.floor(0.95 * (sorted.length - 1))].toFixed(1), maxMs: +sorted.at(-1).toFixed(1),
           drawCmds: Math.round(cmds.reduce((a, b) => a + b, 0) / cmds.length) };
}"""


def serve(web=None):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        """Serves gzip-compressed responses like GitHub Pages (which gzips .json, .bin, .js, .png ...)."""
        cache = {}

        def log_message(self, *a):
            pass

        def do_GET(self):
            path = self.translate_path(self.path)
            if "gzip" not in self.headers.get("Accept-Encoding", "") or not os.path.isfile(path):
                return super().do_GET()
            st = os.stat(path)
            etag = f'"{st.st_mtime_ns:x}-{st.st_size:x}"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304); self.send_header("ETag", etag); self.end_headers(); return
            key = (path, st.st_mtime_ns)
            if key not in Quiet.cache:
                with open(path, "rb") as f:
                    Quiet.cache[key] = gzip.compress(f.read(), 6)
            body = Quiet.cache[key]
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=600")      # GitHub Pages default
            self.send_header("ETag", etag)
            self.end_headers()
            self.wfile.write(body)
    handler = functools.partial(Quiet, directory=str(web or WEB))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def one_run(pw, url, mobile, profile):
    # Every load gets its own browser process (headless Chromium can stall a later load behind an earlier
    # page's GPU work). cold = fresh profile; warm = relaunch on the same profile directory, so the HTTP
    # disk cache is shared but nothing else.
    user_dir = tempfile.mkdtemp(prefix="khu-bench-")
    results = {}
    for phase in ("cold", "warm"):
        ctx = pw.chromium.launch_persistent_context(
            user_dir, args=GPU_ARGS, viewport={"width": 390, "height": 844} if mobile else {"width": 1600, "height": 900},
            is_mobile=mobile, has_touch=mobile, device_scale_factor=2 if mobile else 1)
        ctx.add_init_script(INIT)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        cdp = ctx.new_cdp_session(page)
        cdp.send("Network.enable")
        if mobile:
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            # "fast 4G"-like link for every request (local files and the Cesium CDN alike)
            cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 80,
                     "downloadThroughput": 12_000_000 / 8, "uploadThroughput": 3_000_000 / 8})
        net = {"local": [0, 0], "cdn": [0, 0]}
        reqs = {}
        cdp.on("Network.requestWillBeSent", lambda e, reqs=reqs: reqs.__setitem__(e["requestId"], e["request"]["url"]))

        def done(e, net=net, reqs=reqs):
            u = reqs.get(e["requestId"], "")
            k = "local" if u.startswith(url.rsplit("/", 1)[0]) else "cdn"
            net[k][0] += 1
            net[k][1] += e["encodedDataLength"]
        cdp.on("Network.loadingFinished", done)
        if profile and phase == "cold":
            cdp.send("Profiler.enable")
            cdp.send("Profiler.setSamplingInterval", {"interval": 200})
            cdp.send("Profiler.start")
        print(f"  {'mobile' if mobile else 'desktop'} {phase}: loading", flush=True)
        page.goto(url, wait_until="commit")
        page.wait_for_function("document.body?.dataset.ready === '1'", timeout=300_000, polling=50)
        r = page.evaluate(COLLECT)
        if profile and phase == "cold":
            prof = cdp.send("Profiler.stop")["profile"]
            r["hot"] = hot_functions(prof)
        page.wait_for_timeout(1500)
        r["net"] = {k: {"requests": v[0], "kB": round(v[1] / 1024)} for k, v in net.items()}
        print(f"    ready at {r['marks'].get('ready')} ms", flush=True)
        if phase == "warm":
            r["flight"] = page.evaluate(FLIGHT)
        results[phase] = r
        ctx.close()
    shutil.rmtree(user_dir, ignore_errors=True)
    return results


def hot_functions(prof, n=25):
    nodes = {nd["id"]: nd for nd in prof["nodes"]}
    dt = {}
    samples, deltas = prof.get("samples", []), prof.get("timeDeltas", [])
    for sid, d in zip(samples, deltas):
        dt[sid] = dt.get(sid, 0) + d
    agg = {}
    for nid, us in dt.items():
        cf = nodes[nid]["callFrame"]
        key = f'{cf["functionName"] or "(anon)"} {cf["url"].rsplit("/", 1)[-1]}:{cf["lineNumber"] + 1}'
        agg[key] = agg.get(key, 0) + us
    return [(k, round(v / 1000)) for k, v in sorted(agg.items(), key=lambda kv: -kv[1])[:n]]


def summarise(runs):
    out = {}
    for phase in ("cold", "warm"):
        rs = [r[phase] for r in runs]
        med = lambda xs: statistics.median(xs) if xs else None
        keys = sorted({k for r in rs for k in r["marks"]})
        out[phase] = {
            "marks_ms": {k: med([r["marks"][k] for r in rs if k in r["marks"]]) for k in keys},
            "fcp_ms": med([r["fcp"] for r in rs if r["fcp"] is not None]),
            "long_tasks": med([r["longTasks"] for r in rs]), "long_task_ms": med([r["longTaskMs"] for r in rs]),
            "tbt_ms": med([r["tbt"] for r in rs]), "heap_MB": med([r["heapMB"] for r in rs if r["heapMB"]]),
            "net": rs[0]["net"],
            "flight": {k: med([r["flight"][k] for r in rs]) for k in rs[0]["flight"]} if "flight" in rs[0] else None,
        }
        if "hot" in rs[0]:
            out[phase]["hot"] = rs[0]["hot"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--only", choices=["desktop", "mobile"])
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--path", default="index.html", help="page to load, relative to web/")
    ap.add_argument("--out")
    ap.add_argument("--web", help="directory to serve instead of web/ (for an A/B against another checkout)")
    a = ap.parse_args()
    srv = serve(Path(a.web) if a.web else None)
    url = f"http://127.0.0.1:{srv.server_address[1]}/{a.path}"
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=GPU_ARGS)
        gpu = browser.new_page().evaluate("""() => { const c = document.createElement('canvas').getContext('webgl2');
            const e = c && c.getExtension('WEBGL_debug_renderer_info'); return e ? c.getParameter(e.UNMASKED_RENDERER_WEBGL) : '?'; }""")
        report["gpu"] = gpu
        browser.close()
        for name in ("desktop", "mobile"):
            if a.only and a.only != name:
                continue
            runs = [one_run(p, url, name == "mobile", a.profile and i == 0) for i in range(a.runs)]
            report[name] = summarise(runs)
            print(name, json.dumps(report[name], indent=1))
    srv.shutdown()
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
