# Reproducing the RIDITA 2026 results

Scripts used for the paper *A methodological procedure and supporting tool for dedicated urban air mobility corridor design in the São Paulo metropolitan region* (X Congreso Internacional de la RIDITA, 2026). They are Python mirrors of the dashboard's Overlap Analysis plus the paper-specific checks. The dashboard's own overlap engine (`js/overlap-analysis.js`) gives the same volumetric results (checked to 10⁻¹² on the six scenarios).

## What is and is not in this repository

| Input | Status |
|---|---|
| REH and REA volumes (`data/airspace/nodes_edges_reh.csv`, `data/airspace/nodes_edges_rea.csv`), from DECEA GeoAISWEB XML (`data/airspace/xml/`) | Public, in this repository |
| Airport-flow envelopes, radial method (`data/envelopes/approach_surfaces_*.csv`) and stream method (`data/envelopes/approach_surfaces_*_stream.csv`); the along-axis method, the alternative in release `ridita-2026`, is only in releases `ridita-2026` and `ridita-2026.1` | Public derived data, in this repository |
| Frozen UAM scenario files (below) | **Not in this repository.** Available on request from the authors |
| Flightradar24 tracks, December 2022 (31 daily `.Rda` files) | **Licensed; not distributed.** Needed only to rebuild the envelopes and for the traffic counts |
| SIGMA-Sky Product II report (demand scenarios) | Public, at https://sigma.ita.br/sky/produtos |

Without the scenario files, no corridor result of the paper can be recomputed from this repository alone. The tests in `../tests/` (`dashboard/`, `envelopes/`) check the code on public and synthetic data.

### Scenario files (`RIDITA_INPUTS`)

`RIDITA_INPUTS` must point to a folder laid out as follows (the authors' original names):

| File | Content |
|---|---|
| `scenarios/routes_uam_detailed_rmsp.csv` | Six-vertiport network: base (undisplaced) pair paths, waypoints only |
| `scenarios/scenario_horizontal_4000ft_expanded.csv` | Six vertiports, initial corridors: two lanes per path, 4,000 ft |
| `scenarios/scenario_horizontal_3000ft_expanded_displaced.csv` | Six vertiports, refined corridors (waypoints displaced and lowered to 3,000 ft) |
| `new_scenario/routes_uam_detailed_rmsp.csv` | Twelve-vertiport network, base pair paths |
| `new_scenario/new_scenario_horizontal_4000ft.csv` | Twelve vertiports, initial corridors |
| `new_scenario/new_scenario_horizontal_3000ft_displaced.csv` | Twelve vertiports, refined corridors |
| `scenarios/scenario_horizontal_4000ft_expanded_displaced.csv`, `new_scenario/new_scenario_horizontal_4000ft_displaced.csv` | Lateral-only displacement (used by `overlap_volume.py` as the `*_lateral` cases; not in the paper) |

The corridor lanes were generated with a dashboard version older than this repository's current one: its plane used 10⁻⁵-degree units, so the ±750-ft offsets became ±253 m (0.27 NM between tracks), and two-waypoint routes got an extra point. The stored files are the basis of the paper; **regenerating the lanes with the current dashboard gives different geometry**, so use the files as they are.

## Method settings

- Volumes as the dashboard draws them: one box per segment with the start waypoint's width and height, centered on the segment, altitude interpolated along it; zero width/height/altitude take 457 m / 305 m / 760 m.
- Subject layer: the scenario's cruise segments; segments touching a `Vertiport` or `Airport` (climb and descent) are reported apart and excluded from the paper's shares.
- Other layers, in this order: `REH`, `REA`, `ENV_SBGR`, `ENV_SBSP` (radial envelopes unless stated; the stream envelopes for the sensitivity, with `stream_attribution.py` splitting the SBSP share by stream).
- 50-m cells; per cell, altitude intervals are merged per layer; parallel part = overlap inside segment–obstacle pairs within 30°, intersected pair by pair.
- Height sweep 1,000 / 800 / 600 / 400 / 200 ft and a 1-m slab at the axis altitude (a footprint share, not a centerline length).
- Centerline exposure: centerline sampled every 10 m against the same boxes (`centerline_exposure.py`).
- REH reference: base paths cut into 100-m pieces, each with the altitude, height and width of the nearest REH segment (`shared_reh_check.py`).
- Traffic counts (`occupancy.py`): Flightradar24 tracks of the flights selected by `tools/generate_approach_surfaces_fr24.R`, densified to ≤ 50 m; a flight counts once for a volume set (and once for a segment) if a point lies inside a box and its first point inside falls on 1–31 December 2022, local time; per-day values divide by 31. These are geometric exposures of observed tracks, not conflicts or losses of separation.

## Running

```
pip install numpy pandas shapely
RIDITA_INPUTS=/path/to/scenario/folder python ridita2026/reproduce.py
```

Optional, with the licensed tracks: `Rscript ridita2026/scripts/extract_tracks.R <folder with the daily .Rda files> tracks.csv.gz`, then set `RIDITA_TRACKS=tracks.csv.gz` before `reproduce.py`. Results go to `ridita2026/results/` (or `RIDITA_RESULTS`); `verify_paper.txt` lists every quantitative claim of the paper with `OK`, `CHECK` or `SKIP` (traffic counts without the tracks). `scripts/thin_envelope_convergence.py` repeats the stream SBSP overlap at 50, 25, 10 and 5-m cells (`ENV_SBSP_CSV` selects another envelope).

## Expected results

`expected_results.csv` is `verify_paper.csv` from a full run (with the licensed tracks): each quantitative claim of the manuscript, the recomputed value and the status: `OK` for all 49 checked claims, plus two `INFO` lines that are not claims of the paper. The manuscript was amended on 20 October 2026 after the final checks: the traffic counts are 176 and 262 movements a day (130 on the busiest segment) counting only flights that pass through during December; and, from release `ridita-2026.1` on, its alternative envelope is the stream (direction-resolved) one instead of the along-axis one, which mixes the traffic streams that share a side of the airport. With the stream envelopes the SBSP share is 2.1 → 2.0% (six vertiports) and 2.5 → 2.5% (twelve), almost all in departure streams (arrival streams: 0.02%). `scripts/thin_envelope_convergence.py` confirms it at finer cells: 2.002% (six vertiports) and 2.497% (twelve) at 5 m in both raster orientations. (For the along-axis envelope, the alternative of release `ridita-2026`, the same check gave 0.0105% and 1.221%.)
