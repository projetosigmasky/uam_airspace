# UAM Airspace Dashboard

A browser-based tool for designing urban air mobility (UAM) corridors and checking them against existing airspace structures. It loads route networks from CSV files and shows them as 3D volumes and on a 2D map. You can edit them, generate parallel lanes, and measure by volume how much of one layer, such as the UAM corridors, lies inside others, such as the helicopter and aircraft special routes (REH, REA) or empirical airport-flow envelopes. It was developed in the SIGMA-Sky Project at the Instituto Tecnológico de Aeronáutica (ITA) for the São Paulo Metropolitan Region.

**Live dashboard:** https://projetosigmasky.github.io/uam_airspace/

## Quick start

1. Open the [live dashboard](https://projetosigmasky.github.io/uam_airspace/), or serve this folder locally (`python -m http.server`, then open `http://localhost:8000/`).
2. Load route files with *Load Routes from CSV*. Each file becomes a layer. For São Paulo, this repository provides:
   - `data/airspace/nodes_edges_reh.csv` and `nodes_edges_rea.csv`: helicopter (REH) and aircraft (REA) special routes;
   - `data/envelopes/approach_surfaces_SBGR.csv` and `approach_surfaces_SBSP.csv`: airport-flow envelopes for Guarulhos and Congonhas (radial method), and the `_stream` files (stream method).
3. Load your corridor network the same way, then use *Batch Operations → Generate Parallel Routes* or *Batch Operations → Overlap Analysis*.

## Features

- **3D view** (Three.js): corridors as boxes, vertiports and airports as cylinders; rotate, pan and zoom; grid, solid volumes and node display toggles; meters or feet.
- **Map view** (Leaflet): routes, nodes and corridor footprints on an OpenStreetMap (color) or CARTO (gray) basemap, plus flight trajectories loaded with *Load Trajectories* (2D map only).
- **Layers and editing**: per-file layers that can be recolored, hidden and used in the overlap analysis; vertiports, routes and waypoints can be added, edited and deleted; *Export CSV* writes all routes to one file.
- **Generate Parallel Routes**: offsets every route sideways by the given distances in meters (positive: to the left of the direction of travel) and/or vertically.
  - End waypoints stay fixed.
  - Each interior waypoint moves to the intersection of its two offset edges, or perpendicular to them where they are collinear, and keeps its name, type, altitude, width and height.
  - A two-waypoint route gets one extra point, `<end name> offset`, before its fixed end.
- **Overlap Analysis**: measures how much of one route layer's volume lies inside other layers.
  - *Volumes*: the boxes drawn in the 3D view (start-waypoint width and height, centered on the segment, altitude interpolated along it). A segment is the pair of waypoints it joins, with all lanes and routes on it; segments touching a vertiport or airport are approach segments and are reported apart.
  - *Method*: the plan is divided into square cells (default 50 m). In each cell, the altitude ranges of each layer are merged, so lanes and routes that share a waypoint segment are counted once.
  - *Results per layer*: overlap volume; share of the corridor volume; the share that runs parallel rather than crossing; and the number of segments with at least 1%, 10% and 50% of their own volume overlapping. A segment's overlap share separates thin crossings from corridors running inside another volume.
  - *Parallel vs crossing*: the two classes are exclusive and add up to the overlap. In each cell, the part of the overlap inside at least one segment–obstacle pair within 30° (default) of each other is parallel; the rest is crossing.
  - *Also*: a corridor-height sweep (1,000 ft down to a 1-m slab at the axis altitude), the largest overlaps by segment, map markers for segments above a chosen share, and CSV export per segment. The 1-m slab spans the full corridor width, so it gives the share of the corridor *footprint* at the axis altitude that lies inside other volumes, not the length of the centerline inside them.
  - *Grid effects*: cells are counted whole when their center lies in a footprint, so a single segment's volume can be off by up to one row of cells (for example +9% for an east–west 457-m corridor). Over a network the errors average out: for the RIDITA 2026 scenarios, every overlap share changed by at most 0.1 percentage point between 25-m and 100-m cells.

## Data format

Route files are CSV with one row per waypoint, in order along each route:

```
route,id,name,lat,lon,type,altitude,height,width
```

- **Units and drawing:** `altitude` (MSL), `height` and `width` are in meters. Each segment is drawn as a box with the width and height of its start waypoint, centered on the segment.
- **Defaults:** missing or zero values take altitude 760 m at vertiports and airports (1,219 m elsewhere), height 305 m and width 457 m.
- **Terminals:** `type` values `Vertiport` and `Airport` also create terminal volumes.
- **Parsing:** fields are separated by commas and may be quoted; quotes inside a field are not supported.

Route names only need to be unique within a file. Two files may contain routes with the same name (an REH and an REA route, two versions of a scenario), and each stays in its own layer. Vertiports are shared by name across layers. When *Export CSV* finds a route name used in more than one layer, it appends the layer name, e.g. `R1 [scenario_b.csv]`, so the routes do not merge when the file is loaded again.

## Repository layout

```
index.html                      the dashboard page (GitHub Pages entry point)
css/dashboard.css               dashboard styles
js/                             dashboard scripts (see Development)
  overlap-analysis.js           overlap engine (pure functions)
  route-geometry.js             parallel-route geometry (pure functions)
  state.js, common.js, scene3d.js, map2d.js, editor.js, io.js,
  batch-parallel.js, overlap-panel.js
  main.js                       event wiring and start-up
data/
  airspace/                     REH and REA route files, and their GeoAISWEB XML sources (xml/)
  envelopes/                    airport-flow envelopes for SBGR and SBSP (radial and _stream)
tools/
  convert_xml_to_csv.py         GeoAISWEB XML -> data/airspace CSV files
  generate_approach_surfaces_fr24.R   Flightradar24 tracks -> data/envelopes CSV files
tests/
  dashboard/                    browser tests (core functions and UI) and their fixtures
  envelopes/                    envelope-script tests, synthetic track generators, expected outputs
ridita2026/                     recomputing the RIDITA 2026 paper results (see its README)
CITATION.cff                    how to cite this software
```

## Data and tools

### Helicopter and aircraft special routes (REH, REA)

`data/airspace/nodes_edges_reh.csv` (106 routes) and `nodes_edges_rea.csv` (119 routes) come from the DECEA GeoAISWEB XML files in `data/airspace/xml/`. `python tools/convert_xml_to_csv.py` rebuilds them: it derives each route's centerline from its polygon sides and writes the route files, plus a combined file that is not kept in the repository.

### Airport-flow envelopes (Flightradar24)

`tools/generate_approach_surfaces_fr24.R` turns observed arrival and departure tracks at Guarulhos (SBGR) and Congonhas (SBSP) into 3D envelopes. They can be loaded as route files and used in the overlap analysis:

```
Rscript tools/generate_approach_surfaces_fr24.R <folder with daily .Rda files> [output folder, default data/envelopes/]
                                                [--stations=radial|stream]
```

- **Input**: one `.Rda` file per day with a data frame `df` of track samples (flight id, time, phase, position, barometric altitude in ft, heading, planned origin and destination). The expected columns are listed in the script header. Requires R with `dplyr`.
- **Common steps**: final-approach, initial-climb and ground samples within 0.3° of each airport are kept. The runway direction comes from the touchdown or lift-off heading, with parallel runways grouped. Lower and upper limits are the smoothed 5th and 95th altitude percentiles.
- **Stored geometry**: altitude is the mid-point of the 5th–95th percentile band and height its thickness, because the dashboard centers volumes on the stored altitude.
- **Radial method** (default; the published envelopes, `approach_surfaces_SBGR.csv`, `approach_surfaces_SBSP.csv` and the stations and summary files):
  - *Stations*: every 0.1 NM of radial distance from the airport reference point, up to 10 NM, on each side of the airport, keeping each flight's nearest sample.
  - *Cross-sections*: centered on the extended runway axis and twice the smoothed 95th percentile of the absolute lateral deviation wide.
  - *Behavior*: turning, base and departure-turn traffic widens the cross-sections (up to 16–20 NM at 10 NM), while the lowest, near-axis traffic sets the floor across that whole width, so the envelope is a conservative fan.
  - *December 2022*: 20,328 SBGR and 13,064 SBSP flights; four sides × 101 stations, one route per side.
- **Stream method** (`--stations=stream`; files with the suffix `_stream`, so the radial files are never overwritten):
  - *Paths*: each flight's last pass through the 10-NM circle (arrivals up to touchdown, departures from lift-off) is resampled along its length.
  - *Streams*: per flow and runway direction, the paths are clustered with k-means. The number of streams is the largest (up to 6) for which every stream carries at least 5% of the flights and the mean paths are at least 1.5 NM apart on average (20 random starts, fixed seed).
  - *Stations and cross-sections*: every 0.1 NM along each stream's mean path, from the runway outward. Each cross-section spans the smoothed 5th–95th percentiles of the flights' signed offset from the mean path, with about one spline degree of freedom per NM, so turns and width changes are followed smoothly.
  - *December 2022*: 16 streams (9 at SBGR, 7 at SBSP) holding 33,374 of the 33,392 flights. At Congonhas, for example: a straight-in runway 17 final (3,335 arrivals), a circuit that joins it (766), and runway 17 and 35 departures turning each way.
- **Comparing the methods**: on the December 2022 data they give similar lower limits on the Congonhas straight-in finals (within 50 ft up to 7 NM) but very different widths, so overlap *volume* shares differ widely.
  - For the RIDITA 2026 corridors, 14.0% of the refined six-vertiport corridor volume lies in the radial SBSP envelope and 2.0% in the stream envelopes, almost all of it in departure streams.
  - Yet about 130 Congonhas arrivals a day fly through one corridor segment on the runway 17 final. The stream envelope there is about 0.02 NM wide, and a thin, dense flow fills little volume.
  - Volume shares should therefore be read with traffic counts.
- **Reproducibility**: running the script on the December 2022 data reproduces the files in `data/envelopes/` byte for byte.
- **Data license**: raw Flightradar24 records are licensed and are not distributed here; only the derived envelopes are.

## Tests

`python tests/dashboard/run_browser_tests.py` runs in headless Chrome, Edge or Chromium (`pip install websocket-client`):
- `tests/dashboard/core_tests.html`: unit tests of `js/overlap-analysis.js` and `js/route-geometry.js`. They cover overlap volume and union, shared segments counted once, altitude interpolation, the parallel/crossing split, approach segments, the axis-altitude slab, and parallel-route offsets for straight, turning, collinear, repeated-waypoint and two-waypoint routes. The page can also be opened from a local web server at `/tests/dashboard/core_tests.html`.
- UI tests with `data/airspace/` and `tests/dashboard/fixtures/`: loading files that reuse route names, export, names containing markup (shown as text), and batch parallel routes.

`Rscript tests/envelopes/test_envelopes.R` (R with `dplyr`) tests the envelope script without licensed data:
- The default (radial) output on synthetic tracks from `make_synthetic_fr24.R` (straight-in finals at known lateral offsets after a downwind leg) must match `tests/envelopes/expected/`.
- `--stations=stream` runs on synthetic streams from `make_synthetic_streams.R` (straight-in and circuit arrivals, straight-out and turning departures, with an off-center lateral spread). Each stream must be found with exactly its flights, follow its known path and climb profile, span its 5th–95th lateral band on the correct side, and be smooth.

Both suites run on GitHub Actions for every pull request and push to `main` (`.github/workflows/tests.yml`).

## Development

The dashboard is a static site with no build step: `index.html`, `css/dashboard.css` and the scripts in `js/`.

The scripts are classic `<script>` files that share one global scope, loaded in the order listed at the end of `index.html`:
- the two pure engines, `overlap-analysis.js` and `route-geometry.js`, which have no DOM access and are unit-tested on their own;
- the application files, which only declare state and functions;
- `main.js` last, which wires the events and starts the app.

`ridita2026/scripts/overlap_volume.py` is a Python mirror of `overlap-analysis.js` and gives the same results.

## Reproducing the RIDITA 2026 paper

`ridita2026/` holds the scripts, settings and expected results for the RIDITA 2026 paper. See its README; the frozen scenario files are available on request, and the Flightradar24 tracks are licensed. The paper cites release `ridita-2026.2`. Later versions have the same methods and outputs, with different file locations (see below).

## Limitations

- Volumes are boxes per segment with the start waypoint's width and height; turns are not joined, and cells are counted whole (see Features).
- The airport-flow envelopes describe observed traffic in one month, not protected procedure surfaces, and depend on how stations and lateral extent are defined.
- The overlap results describe geometry only; they do not model traffic density, time or separation minima.

## Changes affecting earlier results

- **Parallel routes**:
  - Before release `ridita-2026`, offsets were applied in a plane of 10⁻⁵-degree units, so one entered meter became 1.108 m (offsets toward north or south) to 1.114 m (toward east or west).
  - Waypoints were also matched to their names, types and altitudes by position, which shifted them for two-waypoint routes and collinear edges.
  - Scenario files made with the earlier version, such as those of the RIDITA 2026 paper (±750 ft entered, ±253 m generated), keep their stored geometry; the overlap analysis always uses the loaded files.
- **Overlap analysis**: before release `ridita-2026`, a cell's whole overlap was counted as parallel when any overlapping pair in it was parallel. This slightly overstated the parallel share (RIDITA 2026 refined networks: 69.4% instead of 68.2%, 53.4% instead of 52.7%). Overlap totals and segment counts are unchanged.
- **Loader**: before release `ridita-2026`, a route whose name already existed in another layer was skipped without notice.
- **Envelopes**: releases `ridita-2026` and `ridita-2026.1` also contain an along-axis envelope variant (`--stations=axis --lateral=traffic --align=30`, files with the suffix `_axis_traffic_align30`). It was removed because it pools every aligned sample on one side of the airport, so traffic streams that share a side are mixed in one cross-section, giving irregular envelopes.
- **Repository layout (after `ridita-2026.3`)**: files moved and a few names changed to US spelling. Results are unchanged.

  | Before | Now |
  |---|---|
  | `index.html` (inline styles and scripts) | `index.html`, `css/dashboard.css`, `js/*.js` |
  | `data/nodes_edges_reh.csv`, `data/nodes_edges_rea.csv`, `data/xml/` | `data/airspace/` |
  | `data/approach_surfaces_*.csv` | `data/envelopes/` |
  | `convert_xml_to_csv.py`, `generate_approach_surfaces_fr24.R` | `tools/` |
  | `tests/core_tests.html`, `tests/run_browser_tests.py`, `tests/fixtures/` | `tests/dashboard/` |
  | `tests/test_envelopes.R`, `tests/make_synthetic_*.R`, `tests/expected/` | `tests/envelopes/` |
  | `ridita2026/scripts/centreline_exposure.py` (`centreline_exposure.json`) | `centerline_exposure.py` (`centerline_exposure.json`) |
  | column `centre_offset_nm` (stream stations file) | `center_offset_nm` |
  | `OverlapAnalysis.analyse()` | `OverlapAnalysis.analyze()` |

## Citing

Cite a tagged release (see *Releases* and `CITATION.cff`) rather than the live dashboard, which changes over time.

Author: Lucas Orbolato Carvalho (ITA), SIGMA-Sky Project.
