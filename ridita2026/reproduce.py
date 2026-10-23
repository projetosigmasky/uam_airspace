#!/usr/bin/env python3
"""Recompute the RIDITA 2026 results from the frozen scenario files and check them against the paper.

    RIDITA_INPUTS=<folder with scenarios/ and new_scenario/> python ridita2026/reproduce.py
    (optional) RIDITA_TRACKS=<tracks_sbgr_sbsp_2022-12.csv.gz from scripts/extract_tracks.R>

Steps (outputs in RIDITA_RESULTS, default ridita2026/results/):
  1. overlap_volume.py          volumetric overlap, height sweep, per-segment shares (Table 2, 3.1, 3.2)
  2. overlap_volume.py          the same against the stream envelopes (abstract, Table 2, 3.2 sensitivity)
  3. stream_attribution.py      the SBSP stream share by stream (3.2)
  4. centerline_exposure.py     centerline length inside the envelopes (Table 2, 3.2, abstract)
  5. shared_reh_check.py        REH reference and REH/REA inside the envelopes (2.4, 3.2)
  6. occupancy.py               Flightradar24 flights through each volume (needs RIDITA_TRACKS; licensed)
  7. verify_paper.py            every quantitative claim of the paper: OK or CHECK
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE / "scripts"
ENVELOPES = HERE.parent / "data" / "envelopes"
RESULTS = Path(os.environ.get("RIDITA_RESULTS", HERE / "results"))
INPUTS = Path(os.environ.get("RIDITA_INPUTS", HERE / "inputs"))
TRACKS = Path(os.environ.get("RIDITA_TRACKS", INPUTS / "tracks_sbgr_sbsp_2022-12.csv.gz"))


def run(script, *args, results=RESULTS, stdout=None, extra_env=None):
    env = {**os.environ, "RIDITA_INPUTS": str(INPUTS), "RIDITA_RESULTS": str(results), "RIDITA_TRACKS": str(TRACKS),
           "PYTHONIOENCODING": "utf-8", **(extra_env or {})}
    results.mkdir(parents=True, exist_ok=True)
    print(f"--- {script} {' '.join(args)}", flush=True)
    with open(stdout, "w", encoding="utf-8") if stdout else open(os.devnull, "w") as out:
        r = subprocess.run([sys.executable, str(SCRIPTS / script), *args], env=env, stdout=out if stdout else None)
    if r.returncode:
        sys.exit(f"{script} failed ({r.returncode})")


if not (INPUTS / "scenarios").is_dir() or not (INPUTS / "new_scenario").is_dir():
    sys.exit(f"Scenario files not found in {INPUTS}: set RIDITA_INPUTS (see ridita2026/README.md).")
run("overlap_volume.py", "--json", stdout=RESULTS / "overlap_volume.json")
run("overlap_volume.py", "--json", results=RESULTS / "stream", stdout=RESULTS / "stream" / "overlap_volume_stream.json",
    extra_env={"ENV_SBGR_CSV": str(ENVELOPES / "approach_surfaces_SBGR_stream.csv"),
               "ENV_SBSP_CSV": str(ENVELOPES / "approach_surfaces_SBSP_stream.csv")})
run("stream_attribution.py", results=RESULTS / "stream")
run("centerline_exposure.py")
run("shared_reh_check.py", stdout=RESULTS / "shared_reh_check.txt")
if TRACKS.exists():
    run("occupancy.py", str(TRACKS))
else:
    print(f"--- occupancy.py skipped: {TRACKS} not found (licensed Flightradar24 data; see README.md)")
run("verify_paper.py", stdout=RESULTS / "verify_paper.txt")
lines = (RESULTS / "verify_paper.txt").read_text(encoding="utf-8").splitlines()
print("\n".join(l for l in lines if l.rstrip().endswith("CHECK")) or "", lines[-1], sep="\n")
