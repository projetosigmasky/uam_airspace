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
- Checks the 3D volumes of one route layer (e.g. UAM corridors) against other layers (e.g. REH, REA, airport-flow envelopes)
- Reports, per layer, the cruise segments with overlap, split into *parallel* (segments within a set angle, default 30°) and *crossing only*, plus overlapping approach segments and segments whose axis lies inside another volume
- Height sweep (1,000 to 200 ft) and the smallest axis-to-volume gap, i.e. the corridor height that would clear the remaining overlaps
- Optional markers on the 2D map (red square: parallel, amber diamond: crossing, grey circle: approach) and CSV export of every overlapping pair

## Usage

1. **Load Data**: Use the sidebar file uploader to load your airspace network data (CSV format)
2. **Visualize**: The dashboard automatically renders your corridors in 3D
3. **Explore**: Use the map and 3D viewport to analyze different aspects of your network
4. **Manage Routes**: Add, remove, or modify routes in the routes panel
5. **Check Overlaps**: Load the corridors and the airspace structures as separate files, then open *Batch Operations → Overlap Analysis*. Segments are the boxes drawn in the 3D view (start-waypoint width and height, centred on the segment); a pair counts when the plan overlap exceeds 1,000 m² and the vertical overlap exceeds 5 ft (both adjustable). Segments touching a vertiport or airport are approach segments.

## Data Format

Route files are CSV with one row per waypoint, in order along each route:

```
route,id,name,lat,lon,type,altitude,height,width
```

`altitude` (MSL), `height` and `width` are in metres; each segment is drawn as a box with the width and height of its start waypoint, centred on the segment. `type` values `Vertiport` and `Airport` also create terminal volumes. Each loaded file becomes a layer that can be recoloured, hidden and used in the overlap analysis.

## Repository Contents

| File | Description |
|------|-------------|
| `index.html` | The dashboard (single page, runs in the browser) |
| `convert_xml_to_csv.py` | Converts DECEA GeoAISWEB XML (REH/REA) into dashboard CSV files |
| `generate_approach_surfaces_fr24.R` | Builds empirical approach/departure envelopes from Flightradar24 tracks |
| `data/nodes_edges_reh.csv`, `data/nodes_edges_rea.csv` | Helicopter (REH) and aircraft (REA) special routes for São Paulo |
| `data/approach_surfaces_SBGR.csv`, `data/approach_surfaces_SBSP.csv` | Airport-flow envelopes for Guarulhos and Congonhas, ready to load in the dashboard |
| `data/approach_surfaces_stations.csv`, `data/approach_surfaces_summary.csv` | Per-station statistics and per-side summary of the envelopes |
| `data/xml/` | Source GeoAISWEB XML files |

## Airport-Flow Envelopes (Flightradar24)

`generate_approach_surfaces_fr24.R` turns observed arrival and departure tracks at Guarulhos (SBGR) and Congonhas (SBSP) into 3D envelopes that can be loaded as route files and used in the overlap analysis:

```
Rscript generate_approach_surfaces_fr24.R <folder with daily .Rda files> [output folder, default data/]
```

- **Input**: one `.Rda` file per day with a data frame `df` of track samples (flight id, time, phase, position, barometric altitude in ft, heading, planned origin and destination); the expected columns are listed in the script header. Requires R with `dplyr`.
- **Method**: final-approach, initial-climb and ground samples within 0.3° of each airport; runway direction from the touchdown or lift-off heading (parallel runways grouped); stations every 0.1 NM up to 10 NM on each side of the airport reference point, keeping each flight's nearest sample; smoothed 5th/95th altitude percentiles as lower/upper limits and twice the smoothed 95th percentile of the lateral deviation from the extended runway axis as width.
- **Published output** (`data/`): December 2022, 20,328 SBGR and 13,064 SBSP flights; four sides × 101 stations. Each side is one route; altitude is the mid-point of the 5th–95th percentile band and height its thickness, because the dashboard centres volumes on the stored altitude.
- **Data licence**: raw Flightradar24 records are licensed and are not distributed here; only the derived envelopes are.
- The envelopes describe observed traffic, not protected procedure surfaces.

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
