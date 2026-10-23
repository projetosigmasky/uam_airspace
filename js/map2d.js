// UAM Airspace Dashboard: 2D map view (Leaflet): basemaps, route and overlap layers, and switching between views.
// Classic script sharing one global scope with the others; load order is set in index.html.

// CARTO basemap key (https://carto.com/basemaps), used by the gray 2D map
const CARTO_API_KEY = 'cb1_4qeg_1_378c20ca618436a5bc54e532';

// Initialize Leaflet map for 2D view
function initMap() {
    if (map2D) return;

    map2D = L.map(mapElement).setView([-23.55, -46.63], 11);

    // Default tile layer (color)
    map2D.colorTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
        maxNativeZoom: 18
    }).addTo(map2D);

    // Gray tile layer. CARTO basemaps need an API key (without one they serve
    // "API key required" tiles); the key is sent with every tile request, so it is
    // public by design and should be restricted to this site in the CARTO account.
    map2D.grayTileLayer = L.tileLayer('https://basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png?key=' + CARTO_API_KEY, {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19,
        maxNativeZoom: 18
    });

    map2D.currentTileLayer = 'color';

    // Store map layers for easy management
    map2D.routeMarkers = L.featureGroup().addTo(map2D);
    map2D.vertiportMarkers = L.featureGroup().addTo(map2D);
    map2D.routeLines = L.featureGroup().addTo(map2D);
    map2D.overlapMarkers = L.featureGroup().addTo(map2D);
    // Overlap markers are drawn above the waypoint and vertiport markers
    map2D.createPane('overlapPane');
    map2D.getPane('overlapPane').style.zIndex = 650;

    // Resize map when container changes
    setTimeout(() => map2D.invalidateSize(), 100);
}

// Toggle tile layers in 2D map
function switchMapTileLayer() {
    if (map2D.currentTileLayer === 'color') {
        map2D.removeLayer(map2D.colorTileLayer);
        map2D.addLayer(map2D.grayTileLayer);
        map2D.currentTileLayer = 'gray';
        document.getElementById('mapTileToggle').textContent = '🎨 Color Map (OpenStreetMap)';
    } else {
        map2D.removeLayer(map2D.grayTileLayer);
        map2D.addLayer(map2D.colorTileLayer);
        map2D.currentTileLayer = 'color';
        document.getElementById('mapTileToggle').textContent = '⬜ Gray Map (CartoDB)';
    }
}

// Helper function to convert degrees to kilometers
function degreesToKm(degrees) {
    return degrees * 111.32; // 1 degree ≈ 111.32 km
}

// Helper function to calculate bearing between two points
function calculateBearing(lat1, lon1, lat2, lon2) {
    const dLon = lon2 - lon1;
    const y = Math.sin(dLon * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180);
    const x = Math.cos(lat1 * Math.PI / 180) * Math.sin(lat2 * Math.PI / 180) -
              Math.sin(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.cos(dLon * Math.PI / 180);
    return Math.atan2(y, x) * 180 / Math.PI;
}

// Helper function to offset a point by distance and bearing
function offsetPoint(lat, lon, distanceKm, bearingDegrees) {
    const R = 6371; // Earth's radius in km
    const latRad = lat * Math.PI / 180;
    const lonRad = lon * Math.PI / 180;
    const bearingRad = bearingDegrees * Math.PI / 180;
    const distRad = distanceKm / R;

    const newLatRad = Math.asin(
        Math.sin(latRad) * Math.cos(distRad) +
        Math.cos(latRad) * Math.sin(distRad) * Math.cos(bearingRad)
    );
    const newLonRad = lonRad + Math.atan2(
        Math.sin(bearingRad) * Math.sin(distRad) * Math.cos(latRad),
        Math.cos(distRad) - Math.sin(latRad) * Math.sin(newLatRad)
    );
    return [newLatRad * 180 / Math.PI, newLonRad * 180 / Math.PI];
}

// Update map with routes and vertiports
function updateMap() {
    if (state.currentView !== 'map' || !map2D) {
        return;
    }

    // Clear existing markers and lines
    if (map2D.routeMarkers) map2D.routeMarkers.clearLayers();
    if (map2D.vertiportMarkers) map2D.vertiportMarkers.clearLayers();
    if (map2D.routeLines) map2D.routeLines.clearLayers();

    // Add trajectories first (so they appear under routes)
    if (state.trajectories && state.trajectories.length > 0) {
        state.trajectories.forEach((trajectory, trajIdx) => {
            if (trajectory.visible === false) return;
            const latlngs = trajectory.points ? trajectory.points.map(p => [p.lat, p.lon]) : [];

            if (latlngs.length > 0) {
                // Draw trajectory line in black with low thickness
                const polyline = L.polyline(latlngs, {
                    color: trajectory.color || '#000000',
                    weight: 0.8,
                    opacity: 0.5
                }).bindPopup(`<b>${escapeHtml(trajectory.name || 'Trajectory ' + (trajIdx + 1))}</b>`);

                if (map2D.routeLines) map2D.routeLines.addLayer(polyline);
            }
        });
    }

    // Add vertiports (draggable)
    if (state.vertiports && state.vertiports.size > 0) {
        state.vertiports.forEach((vertiport, name) => {
            if (!vertiport.visible) return;
            const vertiportColor = getVertiportColor(vertiport);

            // Create a custom icon for vertiports
            const icon = L.divIcon({
                className: 'vertiport-marker',
                html: `<div style="width: 16px; height: 16px; background: ${vertiportColor}; border: 2px solid #111827; border-radius: 50%; cursor: grab; display: flex; align-items: center; justify-content: center;"></div>`,
                iconSize: [16, 16],
                iconAnchor: [8, 8]
            });

            const marker = L.marker([vertiport.lat, vertiport.lon], {
                icon: icon,
                draggable: true,
                title: name
            }).bindPopup(`<b>${escapeHtml(name)}</b><br>${escapeHtml(vertiport.type)}`);

            // Store vertiport name in marker for reference
            marker.vertiportName = name;
            marker.vertiportData = vertiport;

            // Drag event handlers
            marker.on('dragstart', function() {
                this.setOpacity(0.6);
            });

            marker.on('drag', function() {
                const latlng = this.getLatLng();
                this.setPopupContent(`<b>${name}</b><br>Lat: ${latlng.lat.toFixed(6)}<br>Lon: ${latlng.lng.toFixed(6)}<br><em>(Dragging...)</em>`);
            });

            marker.on('dragend', function() {
                const latlng = this.getLatLng();
                // Update the vertiport data
                const updatedVertiport = {...vertiport, lat: latlng.lat, lon: latlng.lng};
                state.vertiports.set(name, updatedVertiport);
                this.setOpacity(1);
                this.setPopupContent(`<b>${name}</b><br>${vertiport.type}<br><small>Updated: Lat ${latlng.lat.toFixed(6)}, Lon ${latlng.lng.toFixed(6)}</small>`);
                this.openPopup();

                // Refresh the map and 3D view
                updateMap();
                renderScene();
            });

            if (map2D.vertiportMarkers) map2D.vertiportMarkers.addLayer(marker);
        });
    }

    // Add routes
    if (state.routes && state.routes.length > 0) {
        state.routes.forEach(route => {
            if (!route.visible || !route.waypoints || route.waypoints.length < 2) return;

            const latlngs = route.waypoints.map(wp => [wp.lat, wp.lon]);

            const colorStr = routeColorToCss(route);
            const displayAltitude = getDisplayValue(getRouteAltitude(route));
            const unit = getDisplayUnit();

            if (state.showVolumeProjection) {
                // Draw corridor volume projections
                for (let i = 0; i < route.waypoints.length - 1; i++) {
                    const wp1 = route.waypoints[i];
                    const wp2 = route.waypoints[i + 1];

                    if (!wp1 || !wp2 || wp1.lat === undefined || wp1.lon === undefined ||
                        wp2.lat === undefined || wp2.lon === undefined) {
                        continue;
                    }

                    const width = (wp1.width !== undefined && wp1.width > 0) ? wp1.width : 457;
                    const height = (wp1.height !== undefined && wp1.height > 0) ? wp1.height : 305;

                    // Calculate bearing and corridor offset
                    const bearing = calculateBearing(wp1.lat, wp1.lon, wp2.lat, wp2.lon);
                    const perpBearing = (bearing + 90) % 360;
                    const halfWidthKm = (width / 2) / 1000; // Convert meters to km

                    // Create rectangle corners (project on 2D by offsetting perpendicular)
                    const [lat1_left, lon1_left] = offsetPoint(wp1.lat, wp1.lon, halfWidthKm, perpBearing);
                    const [lat1_right, lon1_right] = offsetPoint(wp1.lat, wp1.lon, -halfWidthKm, perpBearing);
                    const [lat2_left, lon2_left] = offsetPoint(wp2.lat, wp2.lon, halfWidthKm, perpBearing);
                    const [lat2_right, lon2_right] = offsetPoint(wp2.lat, wp2.lon, -halfWidthKm, perpBearing);

                    const corners = [
                        [lat1_left, lon1_left],
                        [lat2_left, lon2_left],
                        [lat2_right, lon2_right],
                        [lat1_right, lon1_right]
                    ];

                    const polygon = L.polygon(corners, {
                        color: colorStr,
                        weight: 2,
                        opacity: 0.7,
                        fillOpacity: 0.2,
                        fillColor: colorStr
                    }).bindPopup(`<b>${escapeHtml(route.name)}</b><br>Width: ${width}m<br>Height (Alt): ${height}m<br>Path Altitude: ${displayAltitude}${unit}`);

                    if (map2D.routeLines) map2D.routeLines.addLayer(polygon);
                }
            } else {
                // Draw centerline (original behavior)
                const polyline = L.polyline(latlngs, {
                    color: colorStr,
                    weight: 3,
                    opacity: 0.7,
                    dashArray: '5, 5'
                }).bindPopup(`<b>${escapeHtml(route.name)}</b><br>Altitude: ${displayAltitude}${unit}`);

                if (map2D.routeLines) map2D.routeLines.addLayer(polyline);
            }

            // Add waypoint markers based on showNodes setting (draggable)
            if (state.showNodes) {
                latlngs.forEach((latlng, idx) => {
                    // Create icon with the route's color
                    const icon = L.divIcon({
                        className: 'waypoint-marker',
                        html: `<div style="width: 12px; height: 12px; background: ${colorStr}; border: 2px solid #000; border-radius: 50%; cursor: grab; display: flex; align-items: center; justify-content: center;"></div>`,
                        iconSize: [12, 12],
                        iconAnchor: [6, 6]
                    });

                    const marker = L.marker(latlng, {
                        icon: icon,
                        draggable: true,
                        title: route.waypoints[idx].name || 'WP ' + idx
                    }).bindPopup(`<b>${escapeHtml(route.waypoints[idx].name || 'WP ' + idx)}</b><br>Lat: ${route.waypoints[idx].lat.toFixed(6)}<br>Lon: ${route.waypoints[idx].lon.toFixed(6)}`);

                    // Store route and waypoint info in marker for reference
                    marker.routeId = route.id;
                    marker.waypointIndex = idx;
                    marker.routeData = route;

                    // Drag event handlers
                    marker.on('dragstart', function() {
                        this.setOpacity(0.6);
                    });

                    marker.on('drag', function() {
                        const latlng = this.getLatLng();
                        this.setPopupContent(`<b>${route.waypoints[idx].name || 'WP ' + idx}</b><br>Lat: ${latlng.lat.toFixed(6)}<br>Lon: ${latlng.lng.toFixed(6)}<br><em>(Dragging...)</em>`);
                    });

                    marker.on('dragend', function() {
                        const latlng = this.getLatLng();
                        const routeId = this.routeId;
                        const wpIndex = this.waypointIndex;

                        // Find and update the route
                        const routeToUpdate = state.routes.find(r => r.id === routeId);
                        if (routeToUpdate && routeToUpdate.waypoints[wpIndex]) {
                            // Update waypoint coordinates
                            routeToUpdate.waypoints[wpIndex].lat = latlng.lat;
                            routeToUpdate.waypoints[wpIndex].lon = latlng.lng;
                        }

                        this.setOpacity(1);
                        this.setPopupContent(`<b>${route.waypoints[wpIndex].name || 'WP ' + wpIndex}</b><br>Lat: ${latlng.lat.toFixed(6)}<br>Lon: ${latlng.lng.toFixed(6)}<br><small>Updated</small>`);
                        this.openPopup();

                        // Refresh the map and 3D view
                        updateMap();
                        renderScene();
                        updateUI();
                    });

                    if (map2D.routeMarkers) map2D.routeMarkers.addLayer(marker);
                });
            }
        });
    }

    drawOverlapMarkers();
}

// Toggle between 3D and Map view
function switchView(viewType) {
    state.currentView = viewType;

    const canvas = document.getElementById('canvas');
    const mapDiv = document.getElementById('map');
    const btn3d = document.getElementById('view3dBtn');
    const btnMap = document.getElementById('viewMapBtn');
    const mapControls = document.getElementById('mapControls');
    const viewControls3D = document.getElementById('viewControls3D');
    const mapControls3D = document.getElementById('mapControls3D');

    if (viewType === '3d') {
        canvas.style.display = 'block';
        mapDiv.style.display = 'none';
        mapControls.style.display = 'none';
        viewControls3D.style.display = 'block';
        mapControls3D.style.display = 'none';
        btn3d.classList.add('active');
        btnMap.classList.remove('active');
    } else {
        canvas.style.display = 'none';
        mapDiv.style.display = 'block';
        mapControls.style.display = 'block';
        viewControls3D.style.display = 'none';
        mapControls3D.style.display = 'block';
        btn3d.classList.remove('active');
        btnMap.classList.add('active');
        initMap();
        updateMap();
    }
}
