"""Grid convergence of the overlap with the stream SBSP envelope (Section 3.2 sensitivity).

On the Congonhas straight-in finals the stream envelope is only about 0.01-0.02 NM (20-35 m) wide,
below the 50-m raster, so its overlap with the corridors could be aliased. The overlap volume
between the refined corridors (cruise segments) and that envelope is recomputed at 50, 25, 10 and
5-m cells in two independent ways, which must converge to the same volume:
  A  corridors rasterised (as in the paper), restricted to the corridor segments whose footprint
     touches an envelope footprint (the overlap comes only from those);
  B  envelope rasterised, with those corridor cruise segments as the obstacle layer.
Shares are relative to the corridor cruise volume at 50 m (Table 2).
Usage: python thin_envelope_convergence.py [cell sizes...]   (default 50 25 10 5)
ENV_SBSP_CSV overrides the envelope (default data/approach_surfaces_SBSP_stream.csv; the along-axis
envelope, data/approach_surfaces_SBSP_axis_traffic_align30.csv, was checked the same way).
Writes thin_envelope_convergence.csv in RIDITA_RESULTS.
"""
import importlib.util
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from paths import DATA, INPUTS, RESULTS

sys.stdout.reconfigure(encoding="utf-8")
CELLS = [float(c) for c in sys.argv[1:]] or [50.0, 25.0, 10.0, 5.0]
TERMINALS = {"Vertiport", "Airport"}
CASES = {"6vp_refined": "scenarios/scenario_horizontal_3000ft_expanded_displaced.csv",
         "12vp_refined": "new_scenario/new_scenario_horizontal_3000ft_displaced.csv"}
ENV = Path(os.environ.get("ENV_SBSP_CSV", DATA / "approach_surfaces_SBSP_stream.csv"))
LAT0 = -23.6261
M_LAT = 111132.92 - 559.82 * math.cos(2 * math.radians(LAT0)) + 1.175 * math.cos(4 * math.radians(LAT0))
M_LON = 111412.84 * math.cos(math.radians(LAT0)) - 93.5 * math.cos(3 * math.radians(LAT0))


def load(cell):
    os.environ["CELL_M"] = str(cell)
    spec = importlib.util.spec_from_file_location(f"ov_{cell:g}", Path(__file__).with_name("overlap_volume.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pieces(df, cruise_only):
    """Each segment as its own two-waypoint route, with its footprint polygon (local metres)."""
    rows, polys = [], []
    for r, g in df.groupby("route", sort=False):
        g = g.sort_values("id").reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            if cruise_only and (a.type in TERMINALS or b.type in TERMINALS):
                continue
            x0, y0 = (a.lon + 46.6564) * M_LON, (a.lat - LAT0) * M_LAT
            x1, y1 = (b.lon + 46.6564) * M_LON, (b.lat - LAT0) * M_LAT
            L = math.hypot(x1 - x0, y1 - y0)
            if L == 0:
                continue
            hw = (a.width if a.width > 0 else 457.0) / 2
            nx, ny = -(y1 - y0) / L * hw, (x1 - x0) / L * hw
            polys.append(Polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]))
            key = f"{r}#{i}"
            rows += [dict(a, route=key, id=1), dict(b, route=key, id=2)]
    return pd.DataFrame(rows), polys


env = pd.read_csv(ENV)
env_rows, env_polys = pieces(env, cruise_only=False)
tree = STRtree(env_polys)
out = []
for case, f in CASES.items():
    uam = pd.read_csv(INPUTS / f)
    seg_rows, seg_polys = pieces(uam, cruise_only=True)
    hit = {i for i, p in enumerate(seg_polys) if len(tree.query(p, predicate="intersects"))}
    # keep the corridor pieces whose footprint touches the envelope (polygons are in piece order)
    order = list(dict.fromkeys(seg_rows.route))
    near = seg_rows[seg_rows.route.isin([order[i] for i in sorted(hit)])]
    ov50 = load(50.0)
    vol50 = ov50.evaluate(ov50.run_case(uam, {}), [])["volume_km3"]
    print(f"\n{case}: {len(order)} corridor cruise pieces, {len(hit)} touch the SBSP envelope ({ENV.name}); corridor cruise volume at 50 m {vol50:.2f} km3")
    for cell in CELLS:
        ov = load(cell)
        t0 = time.time()
        st = ov.run_case(near, {"ENV_SBSP": env})
        a = ov.evaluate(st, ["ENV_SBSP"])["rows"]["ENV_SBSP"]["overlap_km3"]
        ta = time.time() - t0
        t0 = time.time()
        st = ov.run_case(env, {"UAM": near})
        b = ov.evaluate(st, ["UAM"])["rows"]["UAM"]["overlap_km3"]
        tb = time.time() - t0
        row = dict(case=case, cell_m=cell, overlap_A_km3=a, overlap_B_km3=b, share_A_pct=100 * a / vol50, share_B_pct=100 * b / vol50,
                   seconds_A=round(ta, 1), seconds_B=round(tb, 1))
        out.append(row)
        print(f"  {cell:4g} m: A {a * 1e3:8.4f} hm3 ({row['share_A_pct']:.4f}%)  B {b * 1e3:8.4f} hm3 ({row['share_B_pct']:.4f}%)  [{ta:.0f} s / {tb:.0f} s]", flush=True)
pd.DataFrame(out).to_csv(RESULTS / "thin_envelope_convergence.csv", index=False)
