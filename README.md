# UAM Airspace Dashboard

## 3D Corridor Designer for Urban Air Mobility

A web-based interactive dashboard for designing and visualizing Urban Air Mobility (UAM) airspace corridors. This tool enables users to upload airspace data, visualize flight networks in 3D, and manage routes for autonomous aerial vehicle operations.

## Features

🌐 **Interactive 3D Visualization**
- Real-time 3D rendering of airspace corridors using Three.js
- Pan, zoom, and rotate to explore airspace design from multiple angles

🗺️ **Map Integration**
- Integrated Leaflet map for geographic reference
- View routes and nodes with geographic context

📁 **Data Import**
- Upload CSV files with network node and edge data
- Support for multiple data formats

📊 **Route Management**
- View and manage multiple flight routes
- Visual representation of network connections
- Interactive corridor analysis

📐 **Overlap Analysis**
- Measures how much of one route layer's volume (e.g. UAM corridors) lies inside other layers (e.g. REH, REA, airport-flow envelopes)
- Volumetric: the plan is divided into square cells (default 50 m) and, in each cell, the altitude ranges of each layer are merged, so lanes and routes that share a waypoint segment are counted once
- Per layer: overlap volume, share of the corridor volume, share of the overlap that runs parallel (within 30° by default) rather than crossing, and the number of segments with at least 1%, 10% and 50% of their own volume overlapping
- Parallel and crossing are exclusive classes that add up to the overlap: in each cell, the part of the overlap lying inside at least one segment–obstacle pair within 30° of each other is parallel, the rest is crossing
- Corridor-height sweep (1,000 ft down to a 1-m slab at the axis altitude), largest overlaps by segment, map markers for segments above a chosen share, and CSV export per segment. The 1-m slab spans the full corridor width, so it gives the share of the corridor *footprint* at the axis altitude that lies inside other volumes, not the length of the centerline inside them
- The 50-m cells are counted whole when their center lies in a footprint, so a single segment's volume can be off by up to one row of cells (for example +9% for an east–west 457-m corridor); over a network the errors average out (for the RIDITA 2026 scenarios, every overlap share changed by at most 0.1 percentage point between 25-m and 100-m cells)

## Usage

1. **Load Data**: Use the sidebar file uploader to load your airspace network data (CSV format)
2. **Visualize**: The dashboard automatically renders your corridors in 3D
3. **Explore**: Use the map and 3D viewport to analyze different aspects of your network
4. **Manage Routes**: Add, remove, or modify routes in the routes panel
5. **Generate Parallel Routes**: *Batch Operations → Parallel Routes* offsets every route sideways by the given distances in meters (positive: to the left of the direction of travel) and/or vertically. End waypoints stay fixed; each interior waypoint moves to the intersection of its two offset edges (or perpendicular to them where they are collinear) and keeps its name, type, altitude, width and height. A two-waypoint route gets one extra point, `<end name> offset`, before its fixed end.
6. **Check Overlaps**: Load the corridors and the airspace structures as separate files, then open *Batch Operations → Overlap Analysis*. Volumes are the boxes drawn in the 3D view (start-waypoint width and height, centered on the segment, altitude interpolated along it). A segment is the pair of waypoints it joins, with all lanes and routes on it; segments touching a vertiport or airport are approach segments and are reported apart. The share of a segment's volume that overlaps separates thin crossings from corridors running inside another volume.

## Data Format

Route files are CSV with one row per waypoint, in order along each route:

```
route,id,name,lat,lon,type,altitude,height,width
```

`altitude` (MSL), `height` and `width` are in meters; each segment is drawn as a box with the width and height of its start waypoint, centered on the segment. Missing or zero values take defaults (altitude 760 m at vertiports and airports, 1,219 m elsewhere; height 305 m; width 457 m). `type` values `Vertiport` and `Airport` also create terminal volumes. Fields are separated by commas and may be quoted; quotes inside a field are not supported.

Each loaded file becomes a layer that can be recolored, hidden and used in the overlap analysis. Route names only need to be unique within a file: two files may contain routes with the same name (an REH and an REA route, two versions of a scenario), and each stays in its own layer. Vertiports are shared by name across layers. *Export CSV* writes all routes to one file; if a route name is used in more than one layer, the layer name is appended to it, e.g. `R1 [scenario_b.csv]`, so that the routes do not merge when the file is loaded again.

## Repository Contents

| File | Description |
|------|-------------|
| `index.html` | The dashboard (single page, runs in the browser) |
| `convert_xml_to_csv.py` | Converts DECEA GeoAISWEB XML (REH/REA) into dashboard CSV files |
| `generate_approach_surfaces_fr24.R` | Builds empirical approach/departure envelopes from Flightradar24 tracks |
| `data/nodes_edges_reh.csv`, `data/nodes_edges_rea.csv` | Helicopter (REH) and aircraft (REA) special routes for São Paulo |
| `data/approach_surfaces_SBGR.csv`, `data/approach_surfaces_SBSP.csv` | Airport-flow envelopes for Guarulhos and Congonhas (radial method), ready to load in the dashboard |
| `data/approach_surfaces_stations.csv`, `data/approach_surfaces_summary.csv` | Per-station statistics and per-side summary of the radial envelopes |
| `data/approach_surfaces_*_stream.csv` | The same four files for the stream (direction-resolved) envelopes: one route per traffic stream |
| `data/xml/` | Source GeoAISWEB XML files |
| `tests/` | Browser tests, envelope-script tests, fixtures and a synthetic track generator (see Tests) |
| `ridita2026/` | Scripts and instructions to recompute the RIDITA 2026 paper results (scenario files not included; see its README) |
| `CITATION.cff` | How to cite this software |

## Airport-Flow Envelopes (Flightradar24)

`generate_approach_surfaces_fr24.R` turns observed arrival and departure tracks at Guarulhos (SBGR) and Congonhas (SBSP) into 3D envelopes that can be loaded as route files and used in the overlap analysis:

```
Rscript generate_approach_surfaces_fr24.R <folder with daily .Rda files> [output folder, default data/]
                                          [--stations=radial|stream]
```

- **Input**: one `.Rda` file per day with a data frame `df` of track samples (flight id, time, phase, position, barometric altitude in ft, heading, planned origin and destination); the expected columns are listed in the script header. Requires R with `dplyr`.
- **Method**: final-approach, initial-climb and ground samples within 0.3° of each airport; runway direction from the touchdown or lift-off heading (parallel runways grouped); stations every 0.1 NM up to 10 NM on each side of the airport reference point, keeping each flight's nearest sample; smoothed 5th/95th altitude percentiles as lower/upper limits and twice the smoothed 95th percentile of the lateral deviation from the extended runway axis as width.
- **Published output** (`data/`): December 2022, 20,328 SBGR and 13,064 SBSP flights; four sides × 101 stations. Each side is one route; altitude is the mid-point of the 5th–95th percentile band and height its thickness, because the dashboard centers volumes on the stored altitude. Running the script without options reproduces these files byte for byte.
- **Two methods**, both provided in `data/`:
  - *Radial* (default, the published envelopes): a sample's station is its radial distance from the airport reference point, all samples in the half-plane on that side are pooled, and each cross-section is centered on the extended runway axis and twice the 95th percentile of the absolute lateral deviation wide. Turning, base and departure-turn traffic widens the cross-sections (up to 16–20 NM at 10 NM), while the lowest, near-axis traffic sets the floor across that whole width, so the envelope is a conservative fan.
  - *Stream* (direction-resolved; `--stations=stream`, files with the suffix `_stream`): each flight's last pass through the 10-NM circle (arrivals up to touchdown, departures from lift-off) is resampled along its length, and per flow and runway direction the paths are clustered with k-means into streams; the number of streams is the largest (up to 6) whose streams each carry at least 5% of the flights and whose mean paths are at least 1.5 NM apart on average (20 random starts, fixed seed). Each stream has stations every 0.1 NM along its mean path, from the runway outwards; each cross-section is bounded by the smoothed 5th/95th altitude percentiles of the stream's flights and spans the smoothed 5th–95th percentiles of their signed offset from the mean path (about one spline degree of freedom per NM, so turns and width changes are followed smoothly). The December 2022 data give 16 streams (9 at SBGR, 7 at SBSP) holding 33,374 of the 33,392 flights; at Congonhas, for example, a straight-in runway 17 final (3,335 arrivals), a circuit that joins it (766) and runway 17 and 35 departures turning each way. On synthetic straight-in, circuit, straight-out and turning streams it recovers each stream, its path, climb profile and lateral band (see Tests).
  - On the December 2022 data the two methods give similar lower limits on the Congonhas straight-in finals (within 50 ft up to 7 NM) but very different widths, so overlap *volume* shares differ widely. For the RIDITA 2026 corridors, 14.0% of the refined six-vertiport corridor volume lies in the radial SBSP envelope and 2.0% in the stream envelopes (almost all in departure streams), although about 130 Congonhas arrivals a day (December 2022) fly through one corridor segment on the runway 17 final: the stream envelope there is about 0.02 NM wide, and a thin, dense flow fills little volume. Volume shares should therefore be read with traffic counts.
  - Outputs of `--stations=stream` carry the suffix `_stream`, so the radial files are never overwritten.
  - Releases `ridita-2026` and `ridita-2026.1` also contain an along-axis variant (`--stations=axis --lateral=traffic --align=30`, files with the suffix `_axis_traffic_align30`). It was removed because it pools every aligned sample on one side of the airport, so traffic streams that share a side (a straight-in final and a circuit joining it, departures turning each way) are mixed in one cross-section, giving irregular envelopes.
- **Data license**: raw Flightradar24 records are licensed and are not distributed here; only the derived envelopes are.
- The envelopes describe observed traffic, not protected procedure surfaces.

## Tests

`python tests/run_browser_tests.py` runs, in headless Chrome, Edge or Chromium (`pip install websocket-client`):

- `tests/core_tests.html`: unit tests of the pure functions in `index.html` (overlap volume and union, shared segments counted once, altitude interpolation, parallel/crossing split, approach segments, the axis-altitude slab, and parallel-route offsets for straight, turning, collinear, repeated-waypoint and two-waypoint routes). The page can also be opened from a local web server (`python -m http.server`, then `/tests/core_tests.html`).
- UI tests with `data/` and `tests/fixtures/`: loading files that reuse route names, export, names containing markup (shown as text), and batch parallel routes.

`Rscript tests/test_envelopes.R` (R with `dplyr`) tests `generate_approach_surfaces_fr24.R` without licensed data: the default (radial) output on synthetic tracks from `tests/make_synthetic_fr24.R` (straight-in finals at known lateral offsets after a downwind leg) must match `tests/expected/`, and the removed along-axis options must be rejected; and `--stations=stream` on synthetic streams from `tests/make_synthetic_streams.R` (straight-in and circuit arrivals, straight-out and turning departures, with an off-center lateral spread): each stream must be found with exactly its flights and must follow its known path and climb profile, span its 5th–95th lateral band on the correct side and be smooth.

Both suites run on GitHub Actions for every pull request and push to `main` (`.github/workflows/tests.yml`).

## Limitations

- Volumes are boxes per segment with the start waypoint's width and height; turns are not joined, and cells are counted whole (see Overlap Analysis).
- The airport-flow envelopes describe observed traffic in one month, not protected procedure surfaces, and depend on how stations and lateral extent are defined (see above).
- The overlap results describe geometry only; they do not model traffic density, time or separation minima.

## Changes Affecting Earlier Results

- Parallel routes: before this version, offsets were applied in a plane of 10⁻⁵-degree units, so one entered meter became 1.108 m (offsets toward north or south) to 1.114 m (toward east or west), and waypoints were matched to their names, types and altitudes by position, which shifted them for two-waypoint routes and collinear edges. Scenario files made with the earlier version, such as those of the RIDITA 2026 paper (±750 ft entered, ±253 m generated), keep their stored geometry; the overlap analysis always uses the loaded files.
- Overlap analysis: before this version, a cell's whole overlap was counted as parallel when any overlapping pair in it was parallel, which slightly overstated the parallel share (RIDITA 2026 refined networks: 69.4% instead of 68.2%, 53.4% instead of 52.7%). Overlap totals and segment counts are unchanged.
- Loader: before this version, a route whose name already existed in another layer was skipped without notice.

## Citing

Cite a tagged release (see *Releases* and `CITATION.cff`) rather than the live dashboard, which changes over time. The RIDITA 2026 paper results can be recomputed with `ridita2026/` (see its README).

## Technology Stack

- **Three.js**: 3D visualization and rendering
- **Leaflet**: Interactive mapping
- **HTML5/CSS3**: Modern web interface
- **JavaScript**: Interactive functionality

## Getting Started

1. Visit the [live dashboard](https://projetosigmasky.github.io/uam_airspace/)
2. Upload your airspace network data
3. Start exploring your corridors in 3D!

## Project Information

This project is part of research into Urban Air Mobility (UAM) airspace design and simulation using Bluesky air traffic simulator.

---
**Author**: Lucas Orbolato Carvalho
**Status**: Active Development 🚀
