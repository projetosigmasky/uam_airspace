"""Empirical traffic occupancy: SBGR/SBSP flights (December 2022) whose tracks pass through each volume.

Independent of how airport-flow envelopes are drawn: each flight's track (as selected by
tools/generate_approach_surfaces_fr24.R) is densified to <= 50 m and tested against the dashboard boxes
(start-node width and height, centered, altitude interpolated). Volumes: cruise segments of the UAM
networks (segments touching a vertiport or airport excluded), the REH reference (shared_reh_<stage>.csv),
the same REH-reference pieces with one corridor lane's box at the REH altitude or at 4,000 ft, and the
REH and REA routes in the network area.
Counting unit: distinct flights (airport and Flightradar24 flight id), each counted once per volume set
(and once per segment) however many of its boxes it crosses, if its first point inside falls on
1-31 December 2022, local time (America/Sao_Paulo). The 31 daily files overlap in time and also hold
some flights of 30 November and 1 January; per-day values divide the December flights by 31.
Usage: Rscript extract_tracks.R <fr24 folder> <tracks.csv.gz>   (licensed data: keep the extract local)
       python occupancy.py [tracks.csv.gz]   (default: data/FR24/derived/tracks_sbgr_sbsp_2022-12.csv.gz)
Outputs next to this script (derived counts only): occupancy_summary.csv, occupancy_segments_<case>.csv.
"""
import math
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import shapely
from shapely.strtree import STRtree

sys.stdout.reconfigure(encoding="utf-8")
from paths import AIRSPACE, ENVELOPES, INPUTS, RESULTS, TRACKS  # noqa: E402  (see paths.py)
B = str(INPUTS) + "/"
AIR = str(AIRSPACE) + "/"
ENV_DIR = str(ENVELOPES) + "/"
REV = str(RESULTS) + "/"
TRACKS = sys.argv[1] if len(sys.argv) > 1 else str(TRACKS)
HERE = os.path.join(REV, "occupancy")
os.makedirs(HERE, exist_ok=True)
STEP = 50.0          # densification step (m)
MAX_GAP = 3704.0     # do not interpolate across gaps longer than 2 NM
TERMINALS = {"Vertiport", "Airport"}
LAT0, LON0 = -23.55, -46.63
phi = math.radians(LAT0)
M_LAT = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
M_LON = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
to_xy = lambda lat, lon: ((np.asarray(lon) - LON0) * M_LON, (np.asarray(lat) - LAT0) * M_LAT)

CASES = {"6vp_initial": "scenarios/scenario_horizontal_4000ft_expanded.csv",
         "6vp_refined": "scenarios/scenario_horizontal_3000ft_expanded_displaced.csv",
         "12vp_initial": "new_scenario/new_scenario_horizontal_4000ft.csv",
         "12vp_refined": "new_scenario/new_scenario_horizontal_3000ft_displaced.csv"}


def boxes(df, cruise_only):
    out = []
    for _, g in df.groupby("route", sort=False):
        g = g.sort_values("id").reset_index(drop=True)
        x, y = to_xy(g.lat.values, g.lon.values)
        for i in range(len(g) - 1):
            if cruise_only and (g.type[i] in TERMINALS or g.type[i + 1] in TERMINALS):
                continue
            dx, dy = x[i + 1] - x[i], y[i + 1] - y[i]
            L = math.hypot(dx, dy)
            if L == 0:
                continue
            a0 = g.altitude[i] if g.altitude[i] > 0 else 760.0
            a1 = g.altitude[i + 1] if g.altitude[i + 1] > 0 else 760.0
            hw = (g.width[i] if g.width[i] > 0 else 457.0) / 2
            half = (g.height[i] if g.height[i] > 0 else 305.0) / 2
            key = " – ".join(sorted([str(g.name[i]), str(g.name[i + 1])]))
            out.append(dict(key=key, x0=x[i], y0=y[i], ux=dx / L, uy=dy / L, L=L, hw=hw, half=half, a0=a0, a1=a1))
    return out


def polygon(b):
    px, py = -b["uy"] * b["hw"], b["ux"] * b["hw"]
    ex, ey = b["x0"] + b["ux"] * b["L"], b["y0"] + b["uy"] * b["L"]
    return shapely.Polygon([(b["x0"] + px, b["y0"] + py), (ex + px, ey + py), (ex - px, ey - py), (b["x0"] - px, b["y0"] - py)])


def densify(tr):
    """Track samples -> points every <= STEP m (x, y, z, time) with the flight index of each point."""
    xs, ys, zs, ts, fs = [], [], [], [], []
    for fid, g in tr.groupby("fid", sort=False):
        x, y, z, tt = g.x.values, g.y.values, g.alt_msl_m.values, g.time.values.astype(float)
        xs.append(x[:1]); ys.append(y[:1]); zs.append(z[:1]); ts.append(tt[:1]); fs.append(np.full(1, fid))
        seg = np.hypot(np.diff(x), np.diff(y))
        for i, d in enumerate(seg):
            n = 1 if d > MAX_GAP else max(1, math.ceil(d / STEP))
            t = np.arange(1, n + 1) / n
            xs.append(x[i] + (x[i + 1] - x[i]) * t); ys.append(y[i] + (y[i + 1] - y[i]) * t)
            zs.append(z[i] + (z[i + 1] - z[i]) * t); ts.append(tt[i] + (tt[i + 1] - tt[i]) * t); fs.append(np.full(n, fid))
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(ts), np.concatenate(fs)


def in_december(seconds):
    t = pd.to_datetime(np.asarray(seconds, dtype=float), unit="s", utc=True).tz_convert("America/Sao_Paulo")
    return (t.year == 2022) & (t.month == 12)


def flights_through(bx, X, Y, Z, T, F):
    """For each box: {flight id: time of its first point inside the box volume}."""
    tree = STRtree([polygon(b) for b in bx])
    pi, bi = tree.query(shapely.points(X, Y), predicate="intersects")
    hit = defaultdict(dict)
    if len(pi) == 0:
        return hit
    b = pd.DataFrame(bx)
    x0, y0, ux, uy, L = (b[c].values[bi] for c in ("x0", "y0", "ux", "uy", "L"))
    t = np.clip(((X[pi] - x0) * ux + (Y[pi] - y0) * uy) / L, 0, 1)
    alt = b.a0.values[bi] + (b.a1.values[bi] - b.a0.values[bi]) * t
    ok = np.abs(Z[pi] - alt) <= b.half.values[bi]
    for k, f, tt in zip(bi[ok], F[pi[ok]], T[pi[ok]]):
        if tt < hit[k].get(f, np.inf):
            hit[k][f] = tt
    return hit


def december_flights(hits):
    """Flights whose first point inside any of the given boxes falls in December 2022 (local time)."""
    first = {}
    for h in hits:
        for f, tt in h.items():
            first[f] = min(first.get(f, np.inf), tt)
    if not first:
        return set(), 0
    ids = np.array(list(first)); ok = in_december(list(first.values()))
    return set(ids[ok].tolist()), len(first)


tr = pd.read_csv(TRACKS)
tr = tr.sort_values(["icao", "indicat", "time"]).reset_index(drop=True)
tr["fid"] = tr.groupby(["icao", "indicat"], sort=False).ngroup()
tr["x"], tr["y"] = to_xy(tr.lat.values, tr.lon.values)
fl = tr.groupby("fid").agg(icao=("icao", "first"), flow=("flow", "first"))
n_days = 31   # December 2022
print(f"flights: {fl.icao.value_counts().to_dict()}; samples {len(tr):,}; "
      f"median sample spacing {np.nanmedian(np.hypot(tr.x.diff(), tr.y.diff())[tr.fid.diff() == 0]):.0f} m")

volumes = {case: pd.read_csv(B + f) for case, f in CASES.items()}
# REH reference (base paths in 100-m pieces with the nearest REH's altitude, height and width), and
# the same pieces with one corridor lane's height and width, at the REH altitude or at 4,000 ft
for stage in ("6vp", "12vp"):
    ref = pd.read_csv(REV + f"shared_reh_{stage}.csv")
    volumes[f"REH_ref_{stage}"] = ref
    volumes[f"base_REHalt_lane_{stage}"] = ref.assign(height=305.0, width=457.0)
    volumes[f"base_4000ft_lane_{stage}"] = ref.assign(height=305.0, width=457.0, altitude=1219.0)
CASES_ALL = list(volumes)
layers = {"REH": pd.read_csv(AIR + "nodes_edges_reh.csv"), "REA": pd.read_csv(AIR + "nodes_edges_rea.csv")}
allbx = {case: boxes(df, True) for case, df in volumes.items()}
allbx.update({k: boxes(df, False) for k, df in layers.items()})

# keep points near the UAM networks only (the REH/REA results are then local to the network area)
ux = np.concatenate([[b["x0"] for b in allbx[c]] + [b["x0"] + b["ux"] * b["L"] for b in allbx[c]] for c in CASES])
uy = np.concatenate([[b["y0"] for b in allbx[c]] + [b["y0"] + b["uy"] * b["L"] for b in allbx[c]] for c in CASES])
xmin, xmax, ymin, ymax = ux.min() - 2000, ux.max() + 2000, uy.min() - 2000, uy.max() + 2000
X, Y, Z, T, F = densify(tr)
m = (X >= xmin) & (X <= xmax) & (Y >= ymin) & (Y <= ymax) & (Z < 2500)
X, Y, Z, T, F = X[m], Y[m], Z[m], T[m], F[m]
first_sample = tr.groupby("fid").time.min()
movements_dec = {icao: int(((fl.icao == icao) & in_december(first_sample.reindex(fl.index).values)).sum()) for icao in ("SBSP", "SBGR")}
print(f"densified points in the network area below 2,500 m: {len(X):,}")

summary = []
for name, bx in allbx.items():
    if name in layers:   # REH/REA: only the routes inside the network area
        bx = [b for b in bx if xmin <= b["x0"] <= xmax and ymin <= b["y0"] <= ymax]
    hit = flights_through(bx, X, Y, Z, T, F)
    every, n_all = december_flights(hit.values())
    row = dict(volume=name, boxes=len(bx), flights=len(every), flights_all_files=n_all)
    for icao in ("SBSP", "SBGR"):
        row[f"{icao}_flights"] = int((fl.loc[list(every), "icao"] == icao).sum()) if every else 0
        row[f"{icao}_per_day"] = round(row[f"{icao}_flights"] / n_days, 2)
        row[f"{icao}_share_of_movements"] = round(100 * row[f"{icao}_flights"] / movements_dec[icao], 2)
    summary.append(row)
    if name in CASES_ALL:
        by_key = defaultdict(list)
        for k, h in hit.items():
            by_key[bx[k]["key"]].append(h)
        keys = sorted({b["key"] for b in bx})
        seg = {k: december_flights(by_key.get(k, []))[0] for k in keys}
        pd.DataFrame([dict(segment=k, flights=len(seg[k]), per_day=round(len(seg[k]) / n_days, 2),
                           SBSP=sum(fl.icao[f] == "SBSP" for f in seg[k]),
                           SBGR=sum(fl.icao[f] == "SBGR" for f in seg[k])) for k in keys]) \
            .to_csv(f"{HERE}/occupancy_segments_{name}.csv", index=False)
pd.DataFrame(summary).to_csv(f"{HERE}/occupancy_summary.csv", index=False)
print(pd.DataFrame(summary).to_string(index=False))
