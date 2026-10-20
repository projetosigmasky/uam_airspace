"""How much do the airport-flow envelopes overlap the existing REH/REA, and would a shared-REH UAM
network (eVTOLs flying inside the REH they follow) overlap them less than the dedicated corridors?

Uses the volumetric machinery of overlap_volume.py (same rasterisation, 50-m cells)."""
import importlib.util
import json
from pathlib import Path
import math
import sys

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from pyproj import Transformer

sys.stdout.reconfigure(encoding="utf-8")
from paths import DATA, INPUTS, RESULTS, TRACKS  # noqa: E402  (see paths.py)
B = str(INPUTS) + "/"
REPO = str(DATA) + "/"
REV = str(RESULTS) + "/"
spec = importlib.util.spec_from_file_location("ov", str(Path(__file__).with_name("overlap_volume.py")))
ov = importlib.util.module_from_spec(spec); spec.loader.exec_module(ov)
FT = 0.3048
ARP = {"SBSP": (-23.6261, -46.6564), "SBGR": (-23.4356, -46.4731)}

reh = pd.read_csv(REPO + "nodes_edges_reh.csv")
rea = pd.read_csv(REPO + "nodes_edges_rea.csv")
env = {"ENV_SBGR": pd.read_csv(REPO + "approach_surfaces_SBGR.csv"),
       "ENV_SBSP": pd.read_csv(REPO + "approach_surfaces_SBSP.csv")}
tr = Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)


def nm_from(lat, lon, ap):
    la, lo = ARP[ap]
    return math.hypot((lon - lo) * math.cos(math.radians(la)) * 60, (lat - la) * 60)


def layer_vs_env(df, name, radius_nm=None):
    """Share of a layer's volume inside the envelopes; optionally only segments whose midpoint lies
    within radius_nm of either airport (each segment is its own route, so per-segment shares)."""
    rows = []
    for r, g in df.groupby("route", sort=False):
        g = g.sort_values("id").reset_index(drop=True)
        for i in range(len(g) - 1):
            mid_lat, mid_lon = (g.lat[i] + g.lat[i + 1]) / 2, (g.lon[i] + g.lon[i + 1]) / 2
            dmin = min(nm_from(mid_lat, mid_lon, a) for a in ARP)
            if radius_nm is not None and dmin > radius_nm:
                continue
            seg = g.iloc[[i, i + 1]].copy()
            seg["route"] = f"{r}#{i}"
            seg["id"] = [1, 2]
            seg["type"] = "Node"
            rows.append(seg)
    sub = pd.concat(rows)
    st = ov.run_case(sub, env)
    res = ov.evaluate(st, env.keys())
    axis = ov.evaluate(st, env.keys(), half_override=0.5)
    return dict(layer=name, radius=radius_nm, segments=sub.route.nunique(), volume_km3=res["volume_km3"],
                pct_SBSP=res["rows"]["ENV_SBSP"]["pct_of_volume"], pct_SBGR=res["rows"]["ENV_SBGR"]["pct_of_volume"],
                pct_all=res["rows"]["ALL"]["pct_of_volume"], seg10=res["rows"]["ALL"]["segments"][">=10%"],
                seg50=res["rows"]["ALL"]["segments"][">=50%"], axis_all=axis["rows"]["ALL"]["pct_of_volume"],
                axis_SBSP=axis["rows"]["ENV_SBSP"]["pct_of_volume"])


# ---------------------------------------------------------------- shared-REH counterfactual
reh_lines, reh_attr = [], []
for r, g in reh.groupby("route", sort=False):
    g = g.sort_values("id")
    x, y = tr.transform(g.lon.values, g.lat.values)
    for i in range(len(g) - 1):
        reh_lines.append(LineString([(x[i], y[i]), (x[i + 1], y[i + 1])]))
        reh_attr.append((g.altitude.values[i], g.height.values[i], g.width.values[i], r))
tree = STRtree(reh_lines)


def shared_reh_network(base_csv, piece_m=100.0, max_dist=300.0):
    """Split base-path segments into pieces <= piece_m; each piece takes the volume of the nearest REH
    segment (altitude, height, width). Pieces farther than max_dist or touching a terminal are
    excluded from the cruise comparison (typed as Vertiport so they count as approach)."""
    b = pd.read_csv(base_csv)
    out, unmatched, total = [], 0, 0
    for r, g in b.groupby("route", sort=False):
        g = g.sort_values("id").reset_index(drop=True)
        for i in range(len(g) - 1):
            term = g.type[i] in ("Vertiport", "Airport") or g.type[i + 1] in ("Vertiport", "Airport")
            x0, y0 = tr.transform(g.lon[i], g.lat[i]); x1, y1 = tr.transform(g.lon[i + 1], g.lat[i + 1])
            L = math.hypot(x1 - x0, y1 - y0)
            n = max(1, math.ceil(L / piece_m))
            for k in range(n):
                xa, ya = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
                xb, yb = x0 + (x1 - x0) * (k + 1) / n, y0 + (y1 - y0) * (k + 1) / n
                mid = Point((xa + xb) / 2, (ya + yb) / 2)
                j = tree.nearest(mid)
                dist = reh_lines[j].distance(mid)
                alt, h, w, rr = reh_attr[j]
                total += 1
                bad = term or dist > max_dist
                unmatched += (dist > max_dist) and not term
                lo_a, la_a = tr.transform(xa, ya, direction="INVERSE")
                lo_b, la_b = tr.transform(xb, yb, direction="INVERSE")
                tp = "Vertiport" if bad else "Node"
                key = f"{r}|{i}|{k}"
                out.append(dict(route=key, id=1, name=f"{key}a", lat=la_a, lon=lo_a, type=tp, altitude=alt, height=h, width=w))
                out.append(dict(route=key, id=2, name=f"{key}b", lat=la_b, lon=lo_b, type=tp, altitude=alt, height=h, width=w))
    return pd.DataFrame(out), unmatched, total


results = []
for name, df in (("REH", reh), ("REA", rea)):
    results.append(layer_vs_env(df, name))
    results.append(layer_vs_env(df, name, radius_nm=10))
print(pd.DataFrame(results).round(2).to_string(index=False))

print("\nShared-REH counterfactual vs dedicated corridors (cruise only)")
ded = json.load(open(REV + "overlap_volume.json", encoding="utf-8"))
comp = []
for stage, base in (("6vp", "scenarios/routes_uam_detailed_rmsp.csv"), ("12vp", "new_scenario/routes_uam_detailed_rmsp.csv")):
    sdf, unm, tot = shared_reh_network(B + base)
    st = ov.run_case(sdf, env)
    res = ov.evaluate(st, env.keys())
    axis = ov.evaluate(st, env.keys(), half_override=0.5)
    comp.append(dict(network=f"{stage} shared-REH", unmatched_pieces=f"{unm}/{tot}",
                     vol_km3=round(res["volume_km3"], 2),
                     SBSP_pct=round(res["rows"]["ENV_SBSP"]["pct_of_volume"], 2),
                     all_pct=round(res["rows"]["ALL"]["pct_of_volume"], 2),
                     axis_SBSP=round(axis["rows"]["ENV_SBSP"]["pct_of_volume"], 2),
                     axis_all=round(axis["rows"]["ALL"]["pct_of_volume"], 2)))
    for case in (f"{stage}_initial", f"{stage}_refined"):
        v = ded[case]
        comp.append(dict(network=f"{case} dedicated", unmatched_pieces="", vol_km3=round(v["volume_km3"], 2),
                         SBSP_pct=round(v["rows"]["ENV_SBSP"]["pct_of_volume"], 2),
                         all_pct=round(v["rows"]["ENV_SBSP"]["pct_of_volume"] + v["rows"]["ENV_SBGR"]["pct_of_volume"], 2),
                         axis_SBSP=round(v["sweep"]["0"]["by_layer"]["ENV_SBSP"], 2),
                         axis_all=round(v["sweep"]["0"]["by_layer"]["ENV_SBSP"] + v["sweep"]["0"]["by_layer"]["ENV_SBGR"], 2)))
    sdf.to_csv(REV + f"shared_reh_{stage}.csv", index=False)
print(pd.DataFrame(comp).to_string(index=False))
