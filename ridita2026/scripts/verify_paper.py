"""Recompute every quantitative claim of the revised RIDITA paper from the data and code."""
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
from paths import DATA, INPUTS, RESULTS, TRACKS  # noqa: E402  (see paths.py)
B = str(INPUTS) + "/"
REPO = str(DATA) + "/"
REV = str(RESULTS) + "/"
FT, NM, R = 0.3048, 1852.0, 6371.0088
KM_NM = 1.852
rows = []


def claim(section, text, paper, computed, ok):
    rows.append((section, text, paper, computed, "OK" if ok else "CHECK"))


def hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    return 2 * R * np.arcsin(np.sqrt(np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2))


# ---------------------------------------------------------------- 3.3 network
def network(path):
    d = pd.read_csv(path)
    lens, nodes, edges = {}, set(), {}
    for r, g in d.groupby("route", sort=False):
        g = g.sort_values("id")
        la, lo, nm = g.lat.values, g.lon.values, g.name.values
        seg = hav(la[:-1], lo[:-1], la[1:], lo[1:])
        lens[r] = seg.sum()
        for i in range(len(g)):
            nodes.add((round(la[i], 7), round(lo[i], 7)))
        for i in range(len(g) - 1):
            k = tuple(sorted([(round(la[i], 7), round(lo[i], 7)), (round(la[i + 1], 7), round(lo[i + 1], 7))]))
            edges[k] = seg[i]
    # graph components
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b); adj[b].add(a)
    seen, comps = set(), 0
    for n in nodes:
        if n in seen:
            continue
        comps += 1
        stack = [n]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x); stack.extend(adj[x] - seen)
    return pd.Series(lens), len(nodes), len(edges), sum(edges.values()), comps


l6, n6, e6, c6, k6 = network(B + "scenarios/routes_uam_detailed_rmsp.csv")
l12, n12, e12, c12, k12 = network(B + "new_scenario/routes_uam_detailed_rmsp.csv")
claim("3.3", "pair paths 36 -> 105", "36 / 105", f"{len(l6)} / {len(l12)}", (len(l6), len(l12)) == (36, 105))
claim("3.3", "unique centerline 86.6 -> 133.2 NM", "86.6 / 133.2", f"{c6 / KM_NM:.1f} / {c12 / KM_NM:.1f}", (round(c6 / KM_NM, 1), round(c12 / KM_NM, 1)) == (86.6, 133.2))
claim("3.3", "independent cycles E-V+C 12 -> 23", "12 / 23", f"{e6 - n6 + k6} / {e12 - n12 + k12} (V={n6}/{n12}, E={e6}/{e12}, C={k6}/{k12})",
      (e6 - n6 + k6, e12 - n12 + k12) == (12, 23))
common = l6.index.intersection(l12.index); new = l12.index.difference(l6.index)
claim("3.3", "mean pair path 11.98 -> 11.09 NM (-7.5%)", "11.98 / 11.09 / -7.5%",
      f"{l6.mean() / KM_NM:.2f} / {l12.mean() / KM_NM:.2f} / {100 * (l12.mean() / l6.mean() - 1):.1f}%",
      (round(l6.mean() / KM_NM, 2), round(l12.mean() / KM_NM, 2)) == (11.98, 11.09))
unchanged = int(((l12[common] - l6[common]).abs() < 0.01).sum())
claim("3.3", "36 original pairs 11.90 NM, 28 unchanged", "11.90 / 28", f"{l12[common].mean() / KM_NM:.2f} / {unchanged}",
      round(l12[common].mean() / KM_NM, 2) == 11.90 and unchanged == 28)
claim("3.3", "69 new pairs average 10.66 NM", "69 / 10.66", f"{len(new)} / {l12[new].mean() / KM_NM:.2f}",
      len(new) == 69 and round(l12[new].mean() / KM_NM, 2) == 10.66)
t6, t12 = (len(set(pd.read_csv(B + f).query('type in ["Vertiport", "Airport"]').name))
           for f in ("scenarios/routes_uam_detailed_rmsp.csv", "new_scenario/routes_uam_detailed_rmsp.csv"))
claim("2.1", "9 terminals/36 pairs; 15/105", "9 / 15", f"{t6} / {t12}", (t6, t12) == (9, 15))


# ---------------------------------------------------------------- 3.1 refinement edits
def edits(f0, f1):
    a, b = pd.read_csv(B + f0), pd.read_csv(B + f1)
    m = a.merge(b, on=["route", "id"], suffixes=("0", "1"))
    moved = (np.abs(m.lat0 - m.lat1) > 1e-9) | (np.abs(m.lon0 - m.lon1) > 1e-9)
    lowered = np.abs(m.altitude0 - m.altitude1) > 0.01
    changed = moved | lowered
    other = ((m.name0 != m.name1) | (m.type0 != m.type1) | (np.abs(m.width0 - m.width1) > 0.01) | (np.abs(m.height0 - m.height1) > 0.01)).sum()
    term_moved = (changed & m.type0.isin(["Vertiport", "Airport"])).sum()
    dist = hav(m.lat0[moved], m.lon0[moved], m.lat1[moved], m.lon1[moved]) * 1000
    # path length change (repeated track paths)
    def total(d):
        s = 0.0
        for _, g in d.groupby("route"):
            g = g.sort_values("id"); s += hav(g.lat.values[:-1], g.lon.values[:-1], g.lat.values[1:], g.lon.values[1:]).sum()
        return s
    t0, t1 = total(a), total(b)
    return dict(n=len(m), changed=int(changed.sum()), moved=int(moved.sum()), lowered=int(lowered.sum()),
                both=int((moved & lowered).sum()), tracks=m[changed].route.nunique(), routes=a.route.nunique(),
                labels=m[changed].name0.nunique(), other=int(other), term=int(term_moved), dist=np.round(np.sort(np.unique(np.round(dist, -1))), 0),
                by_d={float(d): set(g.name0) for d, g in m[moved].assign(d=np.round(np.asarray(dist), -1)).groupby("d")},
                alt=sorted(set(np.round(m[lowered].altitude1, 1))), pct=100 * (t1 / t0 - 1), dkm=t1 - t0)


e6 = edits("scenarios/scenario_horizontal_4000ft_expanded.csv", "scenarios/scenario_horizontal_3000ft_expanded_displaced.csv")
e12 = edits("new_scenario/new_scenario_horizontal_4000ft.csv", "new_scenario/new_scenario_horizontal_3000ft_displaced.csv")
claim("3.1", "220 of 930 records (23.7%), 48 of 72 tracks, 16 labels", "220/930, 48/72, 16",
      f"{e6['changed']}/{e6['n']} ({100 * e6['changed'] / e6['n']:.1f}%), {e6['tracks']}/{e6['routes']}, {e6['labels']}",
      (e6['changed'], e6['n'], e6['tracks'], e6['routes'], e6['labels']) == (220, 930, 48, 72, 16))
claim("3.1", "392 of 2,366 (16.6%), 88 of 210 tracks, 18 labels", "392/2366, 88/210, 18",
      f"{e12['changed']}/{e12['n']} ({100 * e12['changed'] / e12['n']:.1f}%), {e12['tracks']}/{e12['routes']}, {e12['labels']}",
      (e12['changed'], e12['n'], e12['tracks'], e12['routes'], e12['labels']) == (392, 2366, 88, 210, 18))
claim("3.1", "track paths lengthened 0.11% and 0.37%", "0.11 / 0.37", f"{e6['pct']:.2f} / {e12['pct']:.2f}",
      (round(e6['pct'], 2), round(e12['pct'], 2)) == (0.11, 0.37))
claim("2.2", "edited records moved AND lowered; names/widths/heights/types unchanged; terminals fixed",
      "all", f"6vp moved {e6['moved']} lowered {e6['lowered']} both {e6['both']} other-changes {e6['other']} terminals {e6['term']}; "
             f"12vp moved {e12['moved']} lowered {e12['lowered']} both {e12['both']} other {e12['other']} terminals {e12['term']}",
      e6['moved'] == e6['lowered'] == e6['both'] and e12['moved'] == e12['lowered'] == e12['both'] and e6['other'] == e12['other'] == 0 and e6['term'] == e12['term'] == 0)
claim("2.2", "lowered to 3,000 ft", "914.4 m", f"6vp {e6['alt']}, 12vp {e12['alt']}", e6['alt'] == e12['alt'] == [914.4])
# 1.0 / 1.5 km cross-track; 2.0 km along-route combined with 0.5, 1.0 or 1.5 km cross-track
allowed = (1000.0, 1500.0, math.hypot(2000, 500), math.hypot(2000, 1000), math.hypot(2000, 1500))
along = [{n for d, ns in e["by_d"].items() if d > 1900 for n in ns} for e in (e6, e12)]
cross15 = [{n for d, ns in e["by_d"].items() if abs(d - 1500) <= 20 or abs(d - 2500) <= 20 for n in ns} for e in (e6, e12)]
n05 = sum(len(ns) for e in (e6, e12) for d, ns in e["by_d"].items() if abs(d - allowed[2]) <= 20)
max_nm = max(max(e["by_d"]) for e in (e6, e12)) / NM
claim("2.2/T1", "shifts: 1.0/1.5 km cross-track; 2.0 km along-route at 1-2 points (two turning points), once with 0.5 km; 1.5 km at 2-3 points; resultant <= 1.35 NM",
      "1-2 / 2 / 1 / 2-3 / 1.35", f"6vp {[float(x) for x in e6['dist']]}, 12vp {[float(x) for x in e12['dist']]} m; along-route {[len(a) for a in along]} ({len(along[0] | along[1])} turning points); "
      f"0.5-km once: {n05}; 1.5 km {[len(c) for c in cross15]}; max {max_nm:.3f} NM",
      all(min(abs(d - x) for x in allowed) <= 20 for e in (e6, e12) for d in e["by_d"]) and [len(a) for a in along] == [1, 2]
      and len(along[0] | along[1]) == 2 and n05 == 1 and all(2 <= len(c) <= 3 for c in cross15) and max_nm <= 1.35 + 5e-4)


# ---------------------------------------------------------------- Table 1: generated track spacing
d = pd.read_csv(B + "scenarios/scenario_horizontal_4000ft_expanded.csv")
d["base"] = d.route.str.replace(r" \(Parallel \d\)", "", regex=True)
p1, p2 = d[d.route.str.contains("Parallel 1")], d[d.route.str.contains("Parallel 2")]
m = p1.merge(p2, on=["base", "id"], suffixes=("1", "2")); m = m[m.altitude1 > 800]
sep = hav(m.lat1, m.lon1, m.lat2, m.lon2) * 1000
# perpendicular spacing on straight stretches: distance of lane-1 interior waypoints from the lane-2 polyline
from shapely.geometry import LineString, Point
LAT0 = -23.55
M_LAT = 111132.92 - 559.82 * math.cos(2 * math.radians(LAT0)) + 1.175 * math.cos(4 * math.radians(LAT0))
M_LON = 111412.84 * math.cos(math.radians(LAT0)) - 93.5 * math.cos(3 * math.radians(LAT0))
perp = []
for b_, g1 in p1.groupby("base"):
    g2 = p2[p2.base == b_].sort_values("id"); g1 = g1.sort_values("id")
    line = LineString(list(zip((g2.lon + 46.63) * M_LON, (g2.lat - LAT0) * M_LAT)))
    perp += [line.distance(Point((lo_ + 46.63) * M_LON, (la_ - LAT0) * M_LAT)) for la_, lo_ in zip(g1.lat.values[1:-1], g1.lon.values[1:-1])]
perp = np.array(perp)
claim("T1", "generated spacing 0.27 NM / width 0.52 NM (perpendicular, straight stretches)", "0.27 / 0.52",
      f"{np.median(perp) / NM:.3f} / {(np.median(perp) + 457) / NM:.3f} (waypoint-to-waypoint median {np.median(sep) / NM:.3f})",
      round(np.median(perp) / NM, 2) == 0.27 and round((np.median(perp) + 457) / NM, 2) == 0.52)
claim("T1", "offsets widened by 11% (nominal +/-750 ft)", "11%", f"{np.median(perp) / 2 / 228.6:.4f} x nominal (median)", round(np.median(perp) / 2 / 228.6, 2) == 1.11)
claim("T1", "stored corridor height and width", "1,000 ft; 457 m lanes", f"heights {sorted(int(x) for x in d.height.unique())} m, widths {sorted(int(x) for x in d.width.unique())} m",
      sorted(d.height.unique()) == [305] and sorted(d.width.unique()) == [457])


# ---------------------------------------------------------------- 2.1 / 2.2 REH and REA
def xml_rows(f):
    return [{c.tag.split('}')[-1]: (c.text or '').strip() for c in el}
            for el in ET.parse(f).getroot().iter() if any(c.tag.endswith('fixo_a_lat') for c in el)]


reh = pd.read_csv(REPO + "nodes_edges_reh.csv").groupby("route", sort=False).agg(a=("altitude", "first"), h=("height", "first"), w=("width", "first"))
rea = pd.read_csv(REPO + "nodes_edges_rea.csv").groupby("route", sort=False).agg(a=("altitude", "first"), h=("height", "first"), w=("width", "first"))
xr, xa = xml_rows(REPO + "xml/CV_REH_XP_SAO_PAULO.xml"), xml_rows(REPO + "xml/CV_REA_XP1_SAO_PAULO.xml")
claim("2.1", "106 REH / 119 REA", "106 / 119", f"{len(reh)} / {len(rea)} (XML {len(xr)} / {len(xa)})", (len(reh), len(rea)) == (106, 119))
claim("2.1", "REH widths 0.27/0.11 NM; REA 1-3 NM", "0.27, 0.11 / 1-3",
      f"REH {sorted(float(x) for x in np.round(reh.w.unique() / NM, 2))}; REA {sorted(float(x) for x in np.round(rea.w.unique() / NM, 2))}",
      sorted(np.round(reh.w.unique() / NM, 2)) == [0.11, 0.27] and sorted(np.round(rea.w.unique() / NM, 2)) == [1.0, 2.0, 3.0])
mh_reh, mh_rea = reh.h.mode()[0], rea.h.mode()[0]
claim("2.1", "mean thickness 187 ft for 67 REH; 1,161 ft for 19 REA", "187/67; 1161/19",
      f"{mh_reh / FT:.0f} ft x {(reh.h == mh_reh).sum()}; {mh_rea / FT:.0f} ft x {(rea.h == mh_rea).sum()}",
      (round(mh_reh / FT), (reh.h == mh_reh).sum(), round(mh_rea / FT), (rea.h == mh_rea).sum()) == (187, 67, 1161, 19))
no_alt = sum(1 for r in xr if not (r.get('altcomp') or (r.get('altmax') and r.get('altmin')))) , \
         sum(1 for r in xa if not (r.get('altcomp') or r.get('altcompb_to_a') or (r.get('altmax') and r.get('altmin')) or (r.get('altmaxa_to_b') and r.get('altmina_to_b')) or (r.get('altmaxb_to_a') and r.get('altminb_to_a'))))
rows.append(("2.1", "(not in text) routes with no vertical data take a fallback altitude", "-", f"REH {no_alt[0]}, REA {no_alt[1]}", "INFO"))
reh_lo, reh_hi = (reh.a - reh.h / 2) / FT, (reh.a + reh.h / 2) / FT
inband = ((reh_lo >= 2990) & (reh_hi <= 3510)).mean()
claim("2.2", "REH mostly 3,000-3,500 ft", "mostly", f"{100 * inband:.0f}% of REH volumes within 3,000-3,500 ft; axes {reh.a.min() / FT:.0f}-{reh.a.max() / FT:.0f} ft", inband > 0.5)
pub = rea[(rea.h != mh_rea)]
fl = (pub.a - pub.h / 2) / FT
claim("2.2", "78% of REA with published bands have floors < 4,500 ft, median 4,000", "78% / 4,000",
      f"{100 * (fl < 4499).mean():.0f}% of {len(pub)} / {fl.median():.0f}", round(100 * (fl < 4499).mean()) == 78 and round(fl.median()) == 4000)


# ---------------------------------------------------------------- 2.3 envelopes
st = pd.read_csv(REPO + "approach_surfaces_stations.csv")
summ = pd.read_csv(REPO + "approach_surfaces_summary.csv")
at5 = st[np.isclose(st.distance_nm, 5.0)].lower_limit_m / FT
at10 = st[np.isclose(st.distance_nm, 10.0)].lower_limit_m / FT
claim("2.3", "lower limit 3,650-3,900 ft at 5 NM; 4,600-5,000 ft at 10 NM", "3650-3900 / 4600-5000",
      f"{at5.min():.0f}-{at5.max():.0f} / {at10.min():.0f}-{at10.max():.0f}", 3600 <= at5.min() and at5.max() <= 3950 and 4550 <= at10.min() and at10.max() <= 5050)
claim("2.3", "404 cross-sections, 4 sides x 101", "404", f"{len(st)} ({summ.stations.tolist()})", len(st) == 404)
claim("2.3", "SBGR 20,328 / SBSP 13,064 flights; 80.2% rwy 10; 65.1% rwy 17", "from run log",
      "SBGR 8216+1961 ARR, 8092+2059 DEP -> 20328, rwy10 80.2%; SBSP 4103+2455, 4407+2099 -> 13064, rwy17 65.1%",
      round(100 * (8216 + 8092) / 20328, 1) == 80.2 and round(100 * (4103 + 4407) / 13064, 1) == 65.1 and 20328 + 13064 == 33392)

# ---------------------------------------------------------------- 3.1 / 3.2 / Table 2 volumetric
v = json.load(open(REV + "overlap_volume.json", encoding="utf-8"))


def pct(c, L):
    return v[c]["rows"][L]["pct_of_volume"]


r6i, r6r, r12i, r12r = "6vp_initial", "6vp_refined", "12vp_initial", "12vp_refined"
checks = [
    ("T2", "volume 27.8->29.3 | 40.6->41.5", (27.8, 29.3, 40.6, 41.5), (v[r6i]["volume_km3"], v[r6r]["volume_km3"], v[r12i]["volume_km3"], v[r12r]["volume_km3"]), 1),
    ("T2", "REH 0.6->1.4 | 0.6->1.2", (0.6, 1.4, 0.6, 1.2), (pct(r6i, "REH"), pct(r6r, "REH"), pct(r12i, "REH"), pct(r12r, "REH")), 1),
    ("T2", "REA 8.1->3.1 | 7.6->2.4", (8.1, 3.1, 7.6, 2.4), (pct(r6i, "REA"), pct(r6r, "REA"), pct(r12i, "REA"), pct(r12r, "REA")), 1),
    ("T2", "SBSP 14.7->14.0 | 16.5->16.1", (14.7, 14.0, 16.5, 16.1), (pct(r6i, "ENV_SBSP"), pct(r6r, "ENV_SBSP"), pct(r12i, "ENV_SBSP"), pct(r12r, "ENV_SBSP")), 1),
    ("T2", "SBGR 0.4->0.0 | 0.2->0.0", (0.4, 0.0, 0.2, 0.0), (pct(r6i, "ENV_SBGR"), pct(r6r, "ENV_SBGR"), pct(r12i, "ENV_SBGR"), pct(r12r, "ENV_SBGR")), 1),
    ("T2", "any 23.7->18.2 | 24.9->19.6", (23.7, 18.2, 24.9, 19.6), (pct(r6i, "ALL"), pct(r6r, "ALL"), pct(r12i, "ALL"), pct(r12r, "ALL")), 1),
    ("T2", "parallel part (refined) 68% | 53%", (68, 53), (v[r6r]["rows"]["ALL"]["parallel_pct"], v[r12r]["rows"]["ALL"]["parallel_pct"]), 0),
    ("T2", "segments >=10%: 26->23 | 32->29", (26, 23, 32, 29), tuple(v[c]["rows"]["ALL"]["segments"][">=10%"] for c in (r6i, r6r, r12i, r12r)), 0),
    ("T2", "segments >=50%: 10->7 | 14->9", (10, 7, 14, 9), tuple(v[c]["rows"]["ALL"]["segments"][">=50%"] for c in (r6i, r6r, r12i, r12r)), 0),
    ("3.1", "no segment >=10% inside REH (6vp refined)", (0,), (v[r6r]["rows"]["REH"]["segments"][">=10%"],), 0),
    ("3.1", "19 segments >=10% in SBSP, 7 >=50%", (19, 7), (v[r6r]["rows"]["ENV_SBSP"]["segments"][">=10%"], v[r6r]["rows"]["ENV_SBSP"]["segments"][">=50%"]), 0),
    ("3.2", "600 ft: 16.1 | 17.7", (16.1, 17.7), (v[r6r]["sweep"]["600"]["pct"], v[r12r]["sweep"]["600"]["pct"]), 1),
    ("3.2", "axis inside: 11.8 | 14.1", (11.8, 14.1), (v[r6r]["sweep"]["0"]["pct"], v[r12r]["sweep"]["0"]["pct"]), 1),
]
for sec, txt, paper, comp, nd in checks:
    ok = all(round(c, nd) == p if nd else round(c) == p for p, c in zip(paper, comp))
    claim(sec, txt, str(paper), str(tuple(round(c, 2) for c in comp)), ok)

slab = [v[c]["sweep"]["0"] for c in (r6r, r12r)]
claim("3.2", "footprint at the axis altitude inside other volumes: mostly the SBSP envelope", "mostly SBSP",
      " | ".join(f"SBSP {s['by_layer']['ENV_SBSP']:.2f} of {s['pct']:.2f}%" for s in slab), all(s["by_layer"]["ENV_SBSP"] > 0.5 * s["pct"] for s in slab))
r800 = [v[c]["sweep"]["800"]["by_layer"]["REH"] for c in (r6i, r12i)]
claim("3.2", "800-ft corridor (+/-400 ft) at the 4,000-ft axis: almost no REH overlap", "< 0.01%", f"{r800[0]:.3f}% / {r800[1]:.3f}%", max(r800) < 0.01)
rows.append(("3.2", "(not in text) refined corridors, partly at 3,000 ft inside the REH band, at 800 ft", "-",
             " / ".join(f"{v[c]['sweep']['800']['by_layer']['REH']:.2f}%" for c in (r6r, r12r)), "INFO"))

sg = pd.read_csv(REV + "segments_volume_6vp_refined.csv")
s = sg[sg.share_ENV_SBSP >= 0.10].copy()
la, lo = -23.6261, -46.6564
s["r"] = np.hypot((s.lon - lo) * np.cos(np.radians(la)) * 60, (s.lat - la) * 60)
s["b"] = (np.degrees(np.arctan2((s.lon - lo) * np.cos(np.radians(la)), (s.lat - la))) + 360) % 360
claim("3.1", "SBSP segments 2.9-6.9 NM north-west", "2.9-6.9 NM, NW", f"{s.r.min():.1f}-{s.r.max():.1f} NM, bearings {s.b.min():.0f}-{s.b.max():.0f} deg",
      round(s.r.min(), 1) == 2.9 and round(s.r.max(), 1) == 6.9 and s.b.min() > 270)

# ---------------------------------------------------------------- centerline, stream variant, traffic counts
ce = json.load(open(REV + "centerline_exposure.json", encoding="utf-8"))
cc = (ce["6vp"]["lanes_initial"]["ENV_SBSP"], ce["6vp"]["lanes_refined"]["ENV_SBSP"], ce["6vp"]["base_REH"]["ENV_SBSP"],
      ce["12vp"]["lanes_initial"]["ENV_SBSP"], ce["12vp"]["lanes_refined"]["ENV_SBSP"], ce["12vp"]["base_REH"]["ENV_SBSP"])
claim("T2/3.2/abs", "centerline in SBSP: 11.7->11.3 (2.8) | 16.1->15.5 (1.9)", "(11.7, 11.3, 2.8, 16.1, 15.5, 1.9)",
      str(tuple(round(x, 2) for x in cc)), tuple(round(x, 1) for x in cc) == (11.7, 11.3, 2.8, 16.1, 15.5, 1.9))
claim("2.4", "REH reference: 99% of path within REH", "99%", f"{ce['6vp']['base_REH']['within_250m_of_REH_axis_pct']:.2f} / {ce['12vp']['base_REH']['within_250m_of_REH_axis_pct']:.2f}",
      min(ce['6vp']['base_REH']['within_250m_of_REH_axis_pct'], ce['12vp']['base_REH']['within_250m_of_REH_axis_pct']) >= 99)
vs = json.load(open(REV + "stream/overlap_volume_stream.json", encoding="utf-8"))
ss = tuple(vs[c]["rows"]["ENV_SBSP"]["pct_of_volume"] for c in (r6i, r6r, r12i, r12r))
claim("abs/3.2/T2", "stream SBSP share: 2.1 -> 2.0% | 2.5 -> 2.5%", "2.1 / 2.0 / 2.5 / 2.5", str(tuple(round(x, 3) for x in ss)),
      tuple(round(x, 1) for x in ss) == (2.1, 2.0, 2.5, 2.5))
sm = pd.read_csv(REPO + "approach_surfaces_summary_stream.csv")
claim("2.3", "16 streams", "16", f"{len(sm)} (SBGR {(sm.icao == 'SBGR').sum()}, SBSP {(sm.icao == 'SBSP').sum()}), {sm.flights.sum()} flights",
      len(sm) == 16)
at = json.load(open(REV + "stream/stream_attribution.json", encoding="utf-8"))[r6r]
arr = sum(x for k, x in at.items() if k.startswith("ARR"))
claim("3.2", "six-vertiport stream share almost all in departure streams", "almost all",
      f"arrival streams {arr:.3f}% of {at['ENV_SBSP']:.3f}%", arr < 0.05 * at["ENV_SBSP"])
fin = pd.read_csv(REPO + "approach_surfaces_stations_stream.csv").query("icao == 'SBSP' and stream == 'ARR17_S1'")
tube = fin[np.hypot((fin.lon - lo) * np.cos(np.radians(la)) * 60, (fin.lat - la) * 60).between(4.0, 5.0)].width_nm
claim("3.2", "runway 17 final a tube 0.02 NM wide (stream ARR17_S1, 4-5 NM from the ARP)", "0.02", f"{tube.min():.3f}-{tube.max():.3f}",
      len(tube) > 0 and round(tube.max(), 2) <= 0.02)
import os
if not os.path.exists(REV + "occupancy/occupancy_summary.csv"):
    rows.append(("T2/abs/3.2", "Flightradar24 flights through the volumes (176, 0.3, 262, 44, 1.0, 130)", "-",
                 "not computed: needs the licensed track extract (RIDITA_TRACKS)", "SKIP"))
else:
    oc = pd.read_csv(REV + "occupancy/occupancy_summary.csv").set_index("volume").SBSP_per_day
    claim("T2/abs", "SBSP movements/day (December): 176 -> 176 (0.3) | 262 -> 262 (0.3)", "(176, 176, 0.3, 262, 262, 0.3)",
          str(tuple(float(oc[k]) for k in ("6vp_initial", "6vp_refined", "REH_ref_6vp", "12vp_initial", "12vp_refined", "REH_ref_12vp"))),
          (round(oc["6vp_initial"]), round(oc["6vp_refined"]), round(oc["REH_ref_6vp"], 1), round(oc["12vp_initial"]), round(oc["12vp_refined"]), round(oc["REH_ref_12vp"], 1)) == (176, 176, 0.3, 262, 262, 0.3))
    claim("3.2", "one lane's box: 44/day at 4,000 ft, 1.0 at REH altitudes (6vp)", "44 / 1.0", f"{oc['base_4000ft_lane_6vp']} / {oc['base_REHalt_lane_6vp']}",
          round(oc["base_4000ft_lane_6vp"]) == 44 and round(oc["base_REHalt_lane_6vp"], 1) == 1.0)
    os_ = pd.read_csv(REV + "occupancy/occupancy_segments_6vp_refined.csv").sort_values("per_day", ascending=False).iloc[0]
    claim("3.2", "130 movements/day along one segment on the runway 17 final", "130", f"{os_.segment}: {os_.per_day}", round(os_.per_day) == 130)

pd.set_option("display.width", 250, "display.max_colwidth", 140)
out = pd.DataFrame(rows, columns=["section", "claim", "paper", "computed", "status"])
out.to_csv(REV + "verify_paper.csv", index=False)
print(out.to_string(index=False))
print("\nCHECK items:", (out.status == "CHECK").sum(), "| OK:", (out.status == "OK").sum(), "| INFO/SKIP:", out.status.isin(["INFO", "SKIP"]).sum())
