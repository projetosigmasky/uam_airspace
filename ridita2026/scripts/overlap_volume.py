"""Volumetric overlap between the UAM corridor network and REH, REA and airport-flow envelopes.

Reference implementation of the dashboard's Overlap Analysis (index.html, OverlapAnalysis block).
Volumes are the boxes drawn in the 3D view: each segment has the width and height of its start
waypoint (zero values fall back to 457 m / 305 m, as on import), is centred on the segment and its
altitude is interpolated along it.

The plan is rasterised into square cells (CELL m) of a local metric plane centred on the UAM layer.
In each cell covered by a UAM segment (cell centre inside the footprint), the occupied altitude
intervals are merged, so lanes and routes that share a waypoint segment are counted once:
  - corridor volume V      = sum over cells of |union of UAM intervals| x cell area
  - overlap with layer L   = sum over cells of |UAM union  intersect  L union| x cell area
A segment (unordered pair of waypoint names; both lanes together) gets the same quantities from
its own intervals, so its overlap share is the fraction of its volume inside other volumes. The
parallel overlap is the part of the overlap shared by at least one UAM/obstacle pair within
PARALLEL_DEG; the rest is crossing (PARALLEL_RULE=cell reproduces the earlier, cell-level rule).
Segments touching a vertiport or airport (climb and descent) are reported separately.
CELL_M overrides the raster cell size (default 50 m).

Usage: python overlap_volume.py [--json]   (REH_CSV / REA_CSV / ENV_SBGR_CSV / ENV_SBSP_CSV override the input files)
Writes segments_volume_<case>.csv (per-segment shares and overlap centroid) for each scenario.
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
from paths import DATA, INPUTS, RESULTS, TRACKS  # noqa: E402  (see paths.py)
B = str(INPUTS) + "/"
REPO = str(DATA) + "/"
REV = str(RESULTS) + "/"
FT = 0.3048
CELL = float(os.environ.get("CELL_M", 50.0))
PARALLEL_RULE = os.environ.get("PARALLEL_RULE", "pair")
PARALLEL_DEG = 30.0
SWEEP = [1000, 800, 600, 400, 200]
THRESHOLDS = [0.01, 0.10, 0.50]
TERMINALS = {"Vertiport", "Airport"}
CASES = {"6vp_initial": "scenarios/scenario_horizontal_4000ft_expanded.csv",
         "6vp_refined": "scenarios/scenario_horizontal_3000ft_expanded_displaced.csv",
         "6vp_lateral": "scenarios/scenario_horizontal_4000ft_expanded_displaced.csv",
         "12vp_initial": "new_scenario/new_scenario_horizontal_4000ft.csv",
         "12vp_refined": "new_scenario/new_scenario_horizontal_3000ft_displaced.csv",
         "12vp_lateral": "new_scenario/new_scenario_horizontal_4000ft_displaced.csv"}
LAYERS = {"REH": os.environ.get("REH_CSV", REPO + "nodes_edges_reh.csv"),
          "REA": os.environ.get("REA_CSV", REPO + "nodes_edges_rea.csv"),
          "ENV_SBGR": os.environ.get("ENV_SBGR_CSV", REPO + "approach_surfaces_SBGR.csv"),
          "ENV_SBSP": os.environ.get("ENV_SBSP_CSV", REPO + "approach_surfaces_SBSP.csv")}


def projection(df):
    lat0 = (df.lat.min() + df.lat.max()) / 2
    lon0 = (df.lon.min() + df.lon.max()) / 2
    phi = math.radians(lat0)
    m_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    m_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
    to_xy = lambda lat, lon: ((np.asarray(lon) - lon0) * m_lon, (np.asarray(lat) - lat0) * m_lat)
    to_ll = lambda x, y: (lat0 + y / m_lat, lon0 + x / m_lon)
    return to_xy, to_ll


def segments(df, to_xy):
    out = []
    for _, g in df.groupby("route", sort=False):
        g = g.sort_values("id")
        x, y = to_xy(g.lat.values, g.lon.values)
        a = np.where(g.altitude.values > 0, g.altitude.values, 760.0)
        h = np.where(g.height.values > 0, g.height.values, 305.0)
        w = np.where(g.width.values > 0, g.width.values, 457.0)
        nm, ty = g.name.astype(str).values, g.type.values
        for i in range(len(g) - 1):
            dx, dy = x[i + 1] - x[i], y[i + 1] - y[i]
            L = math.hypot(dx, dy)
            if L == 0:
                continue
            out.append(dict(x0=x[i], y0=y[i], ux=dx / L, uy=dy / L, L=L, hw=w[i] / 2, a0=a[i], a1=a[i + 1],
                            half=h[i] / 2, key=" – ".join(sorted([nm[i], nm[i + 1]])),
                            terminal=(ty[i] in TERMINALS or ty[i + 1] in TERMINALS)))
    return out


def cover(s):
    """Cells whose centre lies inside the footprint of segment s, and the axis parameter t there."""
    xs = [s["x0"] + s["L"] * s["ux"] * k + s["hw"] * s["uy"] * m for k in (0, 1) for m in (-1, 1)]
    ys = [s["y0"] + s["L"] * s["uy"] * k - s["hw"] * s["ux"] * m for k in (0, 1) for m in (-1, 1)]
    i0, i1 = math.floor(min(xs) / CELL), math.floor(max(xs) / CELL)
    j0, j1 = math.floor(min(ys) / CELL), math.floor(max(ys) / CELL)
    I, J = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
    cx, cy = (I + 0.5) * CELL - s["x0"], (J + 0.5) * CELL - s["y0"]
    along = cx * s["ux"] + cy * s["uy"]
    across = -cx * s["uy"] + cy * s["ux"]
    m = (along >= 0) & (along <= s["L"]) & (np.abs(across) <= s["hw"])
    return I[m], J[m], along[m] / s["L"]


def union(iv):
    iv = sorted(iv)
    out = []
    for lo, hi in iv:
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def inter_len(a, b):
    i = j = 0
    tot = 0.0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            tot += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return tot


def run_case(uam_df, layer_dfs):
    to_xy, to_ll = projection(uam_df)
    uam = segments(uam_df, to_xy)
    keys = sorted({s["key"] for s in uam})
    kid = {k: n for n, k in enumerate(keys)}
    terminal_key = {s["key"]: s["terminal"] for s in uam}
    cells = defaultdict(dict)   # (i, j) -> {(key, alt_rounded): (alt, half, ux, uy, terminal)}
    for s in uam:
        I, J, t = cover(s)
        alt = s["a0"] + (s["a1"] - s["a0"]) * t
        for i, j, a in zip(I.tolist(), J.tolist(), alt.tolist()):
            cells[(i, j)].setdefault((kid[s["key"]], round(a, 1)), (a, s["half"], s["ux"], s["uy"], s["terminal"]))
    obst = defaultdict(list)    # (i, j) -> [(layer, lo, hi, ux, uy)]
    for name, df in layer_dfs.items():
        for s in segments(df, to_xy):
            I, J, t = cover(s)
            alt = s["a0"] + (s["a1"] - s["a0"]) * t
            for i, j, a in zip(I.tolist(), J.tolist(), alt.tolist()):
                if (i, j) in cells:
                    obst[(i, j)].append((name, a - s["half"], a + s["half"], s["ux"], s["uy"]))
    return dict(cells=cells, obst=obst, keys=keys, terminal_key=terminal_key, to_ll=to_ll)


def evaluate(st, layer_names, half_override=None):
    area = CELL * CELL
    cosp = math.cos(math.radians(PARALLEL_DEG))
    V = defaultdict(float)                     # 'cruise' / 'approach'
    ov = defaultdict(float)                    # (group, layer) incl. 'ALL'
    ovp = defaultdict(float)                   # parallel overlap (cruise), per layer incl. 'ALL'
    kV, kov = defaultdict(float), defaultdict(float)
    kovL = defaultdict(float)
    kpar, kx, ky = defaultdict(float), defaultdict(float), defaultdict(float)
    for c, entries in st["cells"].items():
        obs = st["obst"].get(c, [])
        byL = defaultdict(list)
        for o in obs:
            byL[o[0]].append((o[1], o[2]))
        O = {L: union(v) for L, v in byL.items()}
        Oall = union([iv for v in byL.values() for iv in v])
        for group, want in (("cruise", False), ("approach", True)):
            ents = [(k, e) for k, e in entries.items() if e[4] == want]
            if not ents:
                continue
            ivs = [(e[0] - (half_override or e[1]), e[0] + (half_override or e[1])) for _, e in ents]
            U = union(ivs)
            V[group] += sum(hi - lo for lo, hi in U) * area
            if not obs:
                if group == "cruise":
                    for kk in {k[0] for k, _ in ents}:
                        kV[kk] += sum(hi - lo for lo, hi in union([iv for (k, _), iv in zip(ents, ivs) if k[0] == kk])) * area
                continue
            for L, OL in O.items():
                ov[(group, L)] += inter_len(U, OL) * area
            ov[(group, "ALL")] += inter_len(U, Oall) * area
            if group != "cruise":
                continue
            # parallel share. "pair" (default): the parallel volume is the altitude range shared by
            # at least one UAM/obstacle pair within PARALLEL_DEG; the rest of the overlap is crossing
            # (exclusive classes; parallel takes precedence where both occur). "cell": the previous
            # rule, which counted the whole cell overlap as parallel if any overlapping pair was.
            par_by_L = defaultdict(list)
            for (_, e), iv in zip(ents, ivs):
                for o in obs:
                    lo, hi = max(iv[0], o[1]), min(iv[1], o[2])
                    if hi > lo and abs(e[2] * o[3] + e[3] * o[4]) >= cosp:
                        par_by_L[o[0]].append((lo, hi))
            if PARALLEL_RULE == "pair":
                for L, v in par_by_L.items():
                    ovp[L] += sum(h - l for l, h in union(v)) * area
                allp = [iv for v in par_by_L.values() for iv in v]
                if allp:
                    ovp["ALL"] += sum(h - l for l, h in union(allp)) * area
            else:
                for L in par_by_L:
                    ovp[L] += inter_len(U, O[L]) * area
                if par_by_L:
                    ovp["ALL"] += inter_len(U, Oall) * area
            for kk in {k[0] for k, _ in ents}:
                own = [(e, iv) for (k, e), iv in zip(ents, ivs) if k[0] == kk]
                Uk = union([iv for _, iv in own])
                kV[kk] += sum(hi - lo for lo, hi in Uk) * area
                o_k = inter_len(Uk, Oall) * area
                kov[kk] += o_k
                kx[kk] += o_k * (c[0] + 0.5) * CELL
                ky[kk] += o_k * (c[1] + 0.5) * CELL
                kp = [(max(iv[0], o[1]), min(iv[1], o[2])) for e, iv in own for o in obs
                      if min(iv[1], o[2]) > max(iv[0], o[1]) and abs(e[2] * o[3] + e[3] * o[4]) >= cosp]
                if kp:
                    kpar[kk] += (sum(h - l for l, h in union(kp)) * area) if PARALLEL_RULE == "pair" else o_k
                for L, OL in O.items():
                    kovL[(kk, L)] += inter_len(Uk, OL) * area
    cruise_keys = [n for n, k in enumerate(st["keys"]) if not st["terminal_key"][k]]
    share = {kk: (kov[kk] / kV[kk] if kV[kk] else 0.0) for kk in cruise_keys}
    rows = {}
    for L in list(layer_names) + ["ALL"]:
        o = ov[("cruise", L)]
        sh = share if L == "ALL" else {kk: (kovL[(kk, L)] / kV[kk] if kV[kk] else 0.0) for kk in cruise_keys}
        rows[L] = dict(overlap_km3=o / 1e9, pct_of_volume=100 * o / V["cruise"] if V["cruise"] else 0.0,
                       parallel_pct=100 * ovp[L] / o if o else 0.0,
                       segments={f">={int(t * 100)}%": int(sum(v >= t for v in sh.values())) for t in THRESHOLDS},
                       segments_any=int(sum(v > 0 for v in sh.values())))
    top = sorted(((kov[kk], st["keys"][kk], share[kk]) for kk in cruise_keys), reverse=True)[:5]
    seg_rows = []
    for kk in cruise_keys:
        lat, lon = st["to_ll"](kx[kk] / kov[kk], ky[kk] / kov[kk]) if kov[kk] else (None, None)
        seg_rows.append(dict(segment=st["keys"][kk], volume_km3=kV[kk] / 1e9, overlap_km3=kov[kk] / 1e9,
                             share=share[kk], parallel_share=kpar[kk] / kov[kk] if kov[kk] else 0.0,
                             **{f"share_{L}": (kovL[(kk, L)] / kV[kk] if kV[kk] else 0.0) for L in layer_names},
                             lat=lat, lon=lon))
    return dict(volume_km3=V["cruise"] / 1e9, n_segments=len(cruise_keys), rows=rows, segments=seg_rows,
                approach_pct=100 * ov[("approach", "ALL")] / V["approach"] if V["approach"] else 0.0,
                top=[(k, round(v / 1e9, 3), round(100 * s, 1)) for v, k, s in top])


if __name__ == "__main__":
    layer_dfs = {k: pd.read_csv(v) for k, v in LAYERS.items()}
    out = {}
    for case, f in CASES.items():
        st = run_case(pd.read_csv(B + f), layer_dfs)
        res = evaluate(st, layer_dfs.keys())
        res["sweep"] = {}
        for h in SWEEP + [0]:
            # H = 0: a 1-m slab around the axis, i.e. the share of the track axis inside other volumes
            r = evaluate(st, layer_dfs.keys(), half_override=(h * FT / 2) if h else 0.5)
            res["sweep"][h] = dict(pct=round(r["rows"]["ALL"]["pct_of_volume"], 2),
                                   seg10=int(r["rows"]["ALL"]["segments"][">=10%"]),
                                   by_layer={L: round(v["pct_of_volume"], 3) for L, v in r["rows"].items()})
        pd.DataFrame(res.pop("segments")).to_csv(REV + f"segments_volume_{case}.csv", index=False)
        out[case] = res
        if "--json" not in sys.argv:
            print(f"\n{case}: corridor volume {res['volume_km3']:.1f} km3, {res['n_segments']} cruise segments")
            for L, r in res["rows"].items():
                print(f"  {L:9s} {r['overlap_km3']:7.3f} km3 {r['pct_of_volume']:6.2f}%  parallel {r['parallel_pct']:5.1f}%"
                      f"  segments any {r['segments_any']:3d}  {r['segments']}")
            print("  approach overlap % of approach volume:", round(res["approach_pct"], 1))
            print("  sweep:", res["sweep"])
            print("  top:", res["top"])
    if "--json" in sys.argv:
        print(json.dumps(out, indent=1, default=float))
