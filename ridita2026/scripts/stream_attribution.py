"""Corridor volume share inside each SBSP stream envelope (Section 3.2).

Each stream of data/envelopes/approach_surfaces_SBSP_stream.csv is evaluated as its own layer (50-m cells, as
in Table 2), so shares can add up to more than the union where streams overlap; the ENV_SBSP entry is
the union of all streams. Writes stream_attribution.json in RIDITA_RESULTS.
Usage: python stream_attribution.py
"""
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from paths import ENVELOPES, INPUTS, RESULTS

sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("overlap_volume", Path(__file__).with_name("overlap_volume.py"))
ov = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ov)
env = pd.read_csv(ENVELOPES / "approach_surfaces_SBSP_stream.csv")
layers = {r: g for r, g in env.groupby("route", sort=False)}
layers["ENV_SBSP"] = env
out = {}
for case in ("6vp_initial", "6vp_refined", "12vp_initial", "12vp_refined"):
    st = ov.run_case(pd.read_csv(INPUTS / ov.CASES[case]), layers)
    rows = ov.evaluate(st, layers.keys())["rows"]
    out[case] = {L: round(rows[L]["pct_of_volume"], 3) for L in layers}
    print(case, json.dumps(out[case]), flush=True)
json.dump(out, open(RESULTS / "stream_attribution.json", "w", encoding="utf-8"), indent=1)
