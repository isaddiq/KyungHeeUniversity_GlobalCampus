"""Reproduce every derived dataset in web/data from the original sources.

    pip install -r requirements.txt
    python scripts/run_all.py            # full pipeline (downloads ~80 MB once)
    python scripts/run_all.py --offline  # reuse data/raw, rebuild everything else
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = [
    ("fetch_osm.py", True),        # Phase 1-2: OSM via Overpass (campus relation + 600 m context)
    ("fetch_dem.py", True),        # Phase 2: FABDEM + Copernicus GLO-30 tile N37E127
    ("build_terrain.py", False),   # Phase 3: DTM grid, geoid grid, slope/hillshade overlays
    ("build_features.py", False),  # Phase 4-5: buildings, roads, landcover, POIs, vegetation
    ("build_campus_details.py", False),  # landmark inputs: gate, library, theatre, peace hall, plaza, crop
    ("build_ground.py", False),    # sports fields, parking, roads, stairs and markings
    ("validate.py", False),        # Phase 7: checks, provenance, accuracy report
]


def main():
    offline = "--offline" in sys.argv
    for script, network in STEPS:
        if offline and network:
            print(f"-- skip {script} (offline)")
            continue
        print(f"== {script}")
        subprocess.run([sys.executable, str(HERE / script)], cwd=HERE, check=True)
    print("done. Serve with:  python -m http.server 8000 --directory web")


if __name__ == "__main__":
    main()
