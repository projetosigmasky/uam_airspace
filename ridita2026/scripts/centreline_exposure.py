"""Centerline exposure: fraction of route centerline length lying inside obstacle volumes.

Unlike the volumetric overlap (overlap_volume.py), which measures how much of the corridor VOLUME
lies inside other volumes, this measures LINE length: each cruise segment's centerline is sampled
every STEP m at its interpolated altitude, and a sample counts when it lies inside an obstacle box
as the dashboard draws it (start-node width and height, centered on the segment, altitude
interpolated along it). Shared segments are counted once (unique geometry).

Paths evaluated (cruise segments only; segments touching a vertiport or airport excluded):
  lanes, initial / refined  the generated lane centerlines of the scenario files
  base path @ 4,000 ft      the original undisplaced pair paths at the 4,000-ft corridor axis
  base path @ REH (REH reference)  the same paths at the altitude of the nearest REH segment
Geometry uses the dashboard's local projection (centered on each path set). Writes centreline_exposure.json.
"""
import json
import math
import sys

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

sys.stdout.reconfigure(encoding="utf-8")
from paths import DATA, INPUTS, RESULTS, TRACKS  # noqa: E402  (see paths.py)
B = str(INPUTS) + "/"
REPO = str(DATA) + "/"
REV = str(RESULTS) + "/"
STEP = 10.0
TERMINALS = {"Vertiport", "Airport"}


def projection(df):
    """Local equirectangular plane centered on the bounding box of df (as the dashboard)."""
    lat0 = (df.lat.min() + df.lat.max()) / 2
    lon0 = (df.lon.min() + df.lon.max()) / 2
    phi = math.radians(lat0)
    m_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    m_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
    return lambda lon, lat: ((np.asarray(lon, dtype=float) - lon0) * m_lon, (np.asarray(lat, dtype=float) - lat0) * m_lat)


def obstacle_boxes(df, tr):
    out = []
    for _, g in df.groupby("route", sort=False):
        g = g.sort_values("id")
        x, y = tr(g.lon.values, g.lat.values)
        a = np.where(g.altitude.values > 0, g.altitude.values, 760.0)
        h = np.where(g.height.values > 0, g.height.values, 305.0)
        w = np.where(g.width.values > 0, g.width.values, 457.0)
        for i in range(len(g) - 1):
            dx, dy = x[i + 1] - x[i], y[i + 1] - y[i]
            L = math.hypot(dx, dy)
            if L == 0:
                continue
            out.append((x[i], y[i], dx / L, dy / L, L, w[i] / 2, a[i], a[i + 1], h[i] / 2))
    return np.array(out)


def unique_cruise_segments(df):
    seen, segs = set(), []
    for _, g in df.groupby("route", sort=False):
        g = g.sort_values("id").reset_index(drop=True)
        for i in range(len(g) - 1):
            if g.type[i] in TERMINALS or g.type[i + 1] in TERMINALS:
                continue
            p, q = (round(g.lat[i], 6), round(g.lon[i], 6)), (round(g.lat[i + 1], 6), round(g.lon[i + 1], 6))
            key = (min(p, q), max(p, q))
            if key in seen or p == q:
                continue
            seen.add(key)
            segs.append((g.lat[i], g.lon[i], g.lat[i + 1], g.lon[i + 1], g.altitude[i], g.altitude[i + 1]))
    return segs


def sample(segs, tr):
    xs, ys, zs, ws = [], [], [], []
    for la0, lo0, la1, lo1, a0, a1 in segs:
        (x0, x1), (y0, y1) = tr([lo0, lo1], [la0, la1])
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, math.ceil(L / STEP))
        t = (np.arange(n) + 0.5) / n
        xs.append(x0 + (x1 - x0) * t); ys.append(y0 + (y1 - y0) * t); zs.append(a0 + (a1 - a0) * t)
        ws.append(np.full(n, L / n))
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(ws)


def inside(xs, ys, zs, boxes):
    hit = np.zeros(len(xs), dtype=bool)
    for x0, y0, ux, uy, L, hw, a0, a1, half in boxes:
        bx = np.abs(ux) * L + hw * 2; by = np.abs(uy) * L + hw * 2
        cx, cy = x0 + ux * L / 2, y0 + uy * L / 2
        m = (np.abs(xs - cx) <= bx / 2 + hw) & (np.abs(ys - cy) <= by / 2 + hw) & ~hit
        if not m.any():
            continue
        idx = np.nonzero(m)[0]
        dx, dy = xs[idx] - x0, ys[idx] - y0
        along = dx * ux + dy * uy
        across = -dx * uy + dy * ux
        t = along / L
        ok = (along >= 0) & (along <= L) & (np.abs(across) <= hw)
        alt = a0 + (a1 - a0) * np.clip(t, 0, 1)
        ok &= np.abs(zs[idx] - alt) <= half
        hit[idx[ok]] = True
    return hit


def reh_altitude(xs, ys, reh, tr):
    lines, alts = [], []
    for _, g in reh.groupby("route", sort=False):
        g = g.sort_values("id")
        x, y = tr(g.lon.values, g.lat.values)
        for i in range(len(g) - 1):
            lines.append(LineString([(x[i], y[i]), (x[i + 1], y[i + 1])])); alts.append(g.altitude.values[i])
    tree = STRtree(lines)
    idx = tree.nearest([Point(a, b) for a, b in zip(xs, ys)])
    d = np.array([lines[j].distance(Point(a, b)) for j, a, b in zip(idx, xs, ys)])
    return np.array(alts)[idx], d


layers = {"REH": pd.read_csv(REPO + "nodes_edges_reh.csv"), "REA": pd.read_csv(REPO + "nodes_edges_rea.csv"),
          "ENV_SBGR": pd.read_csv(REPO + "approach_surfaces_SBGR.csv"), "ENV_SBSP": pd.read_csv(REPO + "approach_surfaces_SBSP.csv")}

if __name__ == "__main__":
    nets = {"6vp": ("scenarios/routes_uam_detailed_rmsp.csv", "scenarios/scenario_horizontal_4000ft_expanded.csv",
                    "scenarios/scenario_horizontal_3000ft_expanded_displaced.csv"),
            "12vp": ("new_scenario/routes_uam_detailed_rmsp.csv", "new_scenario/new_scenario_horizontal_4000ft.csv",
                     "new_scenario/new_scenario_horizontal_3000ft_displaced.csv")}
    out = {}
    for stage, (base_f, ini_f, ref_f) in nets.items():
        base = pd.read_csv(B + base_f)
        base["altitude"] = np.where(base.type.isin(list(TERMINALS)), 760.0, 1219.0)
        variants = {"lanes_initial": unique_cruise_segments(pd.read_csv(B + ini_f)),
                    "lanes_refined": unique_cruise_segments(pd.read_csv(B + ref_f)),
                    "base_4000ft": unique_cruise_segments(base)}
        frames = {"lanes_initial": pd.read_csv(B + ini_f), "lanes_refined": pd.read_csv(B + ref_f), "base_4000ft": base}
        res = {}
        for name, segs in variants.items():
            tr = projection(frames[name])
            boxes = {k: obstacle_boxes(v, tr) for k, v in layers.items()}
            xs, ys, zs, ws = sample(segs, tr)
            res[name] = {"length_nm": ws.sum() / 1852}
            hits = {}
            for k, b in boxes.items():
                hits[k] = inside(xs, ys, zs, b)
                res[name][k] = 100 * ws[hits[k]].sum() / ws.sum()
            res[name]["ALL"] = 100 * ws[np.logical_or.reduce(list(hits.values()))].sum() / ws.sum()
        # REH reference: base paths at the altitude of the nearest REH segment
        tr = projection(base)
        boxes = {k: obstacle_boxes(v, tr) for k, v in layers.items()}
        xs, ys, _, ws = sample(variants["base_4000ft"], tr)
        zs, dist = reh_altitude(xs, ys, layers["REH"], tr)
        res["base_REH"] = {"length_nm": ws.sum() / 1852, "within_250m_of_REH_axis_pct": 100 * ws[dist <= 250].sum() / ws.sum()}
        hits = {}
        for k, b in boxes.items():
            if k == "REH":
                continue   # flown inside the REH by construction
            hits[k] = inside(xs, ys, zs, b)
            res["base_REH"][k] = 100 * ws[hits[k]].sum() / ws.sum()
        res["base_REH"]["ALL_except_REH"] = 100 * ws[np.logical_or.reduce(list(hits.values()))].sum() / ws.sum()
        out[stage] = res
        print(f"\n{stage}: centerline length inside each layer (% of cruise centerline length)")
        print(pd.DataFrame(res).T.round(2).to_string())
    json.dump(out, open(REV + "centreline_exposure.json", "w"), indent=1)
