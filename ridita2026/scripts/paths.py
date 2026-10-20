"""Paths of the RIDITA 2026 analysis scripts.

DATA     this repository's data/ folder (REH/REA routes, airport-flow envelopes).
INPUTS   RIDITA_INPUTS: folder with the frozen scenario files, laid out as scenarios/ (six
         vertiports) and new_scenario/ (twelve vertiports); not in this repository (see ../README.md).
RESULTS  RIDITA_RESULTS: where outputs are written and read back (default ridita2026/results/).
TRACKS   RIDITA_TRACKS: Flightradar24 track extract written by extract_tracks.R (licensed; local only).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
INPUTS = Path(os.environ.get("RIDITA_INPUTS", ROOT / "ridita2026" / "inputs"))
RESULTS = Path(os.environ.get("RIDITA_RESULTS", ROOT / "ridita2026" / "results"))
TRACKS = Path(os.environ.get("RIDITA_TRACKS", INPUTS / "tracks_sbgr_sbsp_2022-12.csv.gz"))
RESULTS.mkdir(parents=True, exist_ok=True)
