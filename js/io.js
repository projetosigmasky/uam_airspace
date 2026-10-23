// UAM Airspace Dashboard: File import (route CSVs, trajectories), CSV export and clearing the workspace.
// Classic script sharing one global scope with the others; load order is set in index.html.

// File handling
function handleTrajectoryUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const layerColor = randomColorHex();

    const reader = new FileReader();
    reader.onload = (event) => {
        const text = event.target.result;
        const lines = text.split('\n');
        if (lines.length < 2) return;

        const headerLine = lines[0];
        const headers = headerLine.split(',').map(h => h.replace(/"/g, '').trim());

        // Detect trajectory structure - should have lat, lon, possibly time/id
        const hasLat = headers.includes('lat') || headers.includes('latitude');
        const hasLon = headers.includes('lon') || headers.includes('longitude');
        const hasId = headers.includes('trajectory_id') || headers.includes('id') || headers.includes('trajectory');
        const hasTime = headers.includes('time') || headers.includes('timestamp');

        if (!hasLat || !hasLon) {
            alert('CSV must contain "lat" and "lon" columns');
            return;
        }

        const fileLayer = createFileLayer(file.name, layerColor, 'trajectories');
        const trajectoryMap = new Map();

        lines.slice(1).forEach((line, lineIdx) => {
            if (!line.trim()) return;

            const fields = [];
            let currentField = '';
            let insideQuotes = false;
            for (let i = 0; i < line.length; i++) {
                const char = line[i];
                if (char === '"') {
                    insideQuotes = !insideQuotes;
                } else if (char === ',' && !insideQuotes) {
                    fields.push(currentField.replace(/"/g, '').trim());
                    currentField = '';
                } else {
                    currentField += char;
                }
            }
            fields.push(currentField.replace(/"/g, '').trim());

            const latIdx = headers.findIndex(h => h === 'lat' || h === 'latitude');
            const lonIdx = headers.findIndex(h => h === 'lon' || h === 'longitude');
            const idIdx = headers.findIndex(h => h === 'indicat' || h === 'trajectory_id' || h === 'id' || h === 'trajectory' || h === 'route');
            const lat = parseFloat(fields[latIdx]);
            const lon = parseFloat(fields[lonIdx]);
            const trajId = (idIdx >= 0) ? fields[idIdx] : '0';

            if (!isNaN(lat) && !isNaN(lon)) {
                if (!trajectoryMap.has(trajId)) {
                    trajectoryMap.set(trajId, {
                        name: trajId !== '0' ? `Trajectory ${trajId}` : `Trajectory from ${file.name}`,
                        points: [],
                        color: layerColor,
                        visible: true,
                        layerId: fileLayer.id
                    });
                }
                trajectoryMap.get(trajId).points.push({ lat, lon });
            }
        });

        const newTrajectories = Array.from(trajectoryMap.values());
        if (newTrajectories.length === 0) {
            state.fileLayers = state.fileLayers.filter(layer => layer.id !== fileLayer.id);
            alert('No valid trajectories found in the selected file.');
            return;
        }

        // Add trajectories to state without clearing previous file layers
        state.trajectories = state.trajectories.concat(newTrajectories);

        // Switch to map view to see trajectories
        if (state.currentView === '3d') {
            switchView('map');
        }

        updateUI();
        updateMap();
        e.target.value = '';
        alert(`Loaded ${newTrajectories.length} trajectory(ies) with ${newTrajectories.reduce((sum, t) => sum + t.points.length, 0)} total points`);
    };
    reader.readAsText(file);
}

function handleCSVUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const layerColor = randomColorHex();

    const reader = new FileReader();
    reader.onload = (event) => {
        const text = event.target.result;
        const lines = text.split('\n');
        const headerLine = lines[0];
        const headers = headerLine.split(',').map(h => h.replace(/"/g, '').trim());
        const hasAltitude = headers.includes('altitude');
        const hasHeight = headers.includes('height');
        const hasWidth = headers.includes('width');
        const fileLayer = createFileLayer(file.name, layerColor, 'routes');

        const routeMap = new Map();
        const vertiportMap = new Map();

        lines.slice(1).forEach(line => {
            if (!line.trim()) return;

            // Parse CSV line handling quoted values
            const fields = [];
            let currentField = '';
            let insideQuotes = false;
            for (let i = 0; i < line.length; i++) {
                const char = line[i];
                if (char === '"') {
                    insideQuotes = !insideQuotes;
                } else if (char === ',' && !insideQuotes) {
                    fields.push(currentField.replace(/"/g, '').trim());
                    currentField = '';
                } else {
                    currentField += char;
                }
            }
            fields.push(currentField.replace(/"/g, '').trim());

            const [routeName, id, name, lat, lon, type] = fields.slice(0, 6);

            // Read geometric values if they exist in CSV, otherwise use defaults
            // Altitude defaults: 760 m for airports/vertiports, 1219 m (4000 ft) for others
            let waypointAltitude = (type === 'Airport' || type === 'Vertiport') ? 760 : 1219;
            let height = 305;        // default corridor height in meters (~1000 ft)
            let width = 457;         // default corridor width in meters (~1500 ft)

            if (hasAltitude && fields[6]) {
                waypointAltitude = parseFloat(fields[6]) || waypointAltitude;
            }
            if (hasHeight && fields[7]) {
                height = parseFloat(fields[7]) || 305;
            }
            if (hasWidth && fields[8]) {
                width = parseFloat(fields[8]) || 457;
            }

            if (type === 'Vertiport' || type === 'Airport') {
                if (!vertiportMap.has(name)) {
                    vertiportMap.set(name, {
                        lat: parseFloat(lat),
                        lon: parseFloat(lon),
                        height: 914,
                        radius: 457,
                        type,
                        visible: true,
                        color: layerColor,
                        layerId: fileLayer.id
                    });
                }
            }

            if (!routeMap.has(routeName)) {
                routeMap.set(routeName, {
                    // ids are scoped to the file layer: different files may reuse a
                    // route name (an REH and an REA route, two versions of a scenario)
                    id: `${fileLayer.id}::${routeName}`,
                    name: routeName,
                    waypoints: [],
                    color: new THREE.Color(layerColor),
                    visible: true,
                    layerId: fileLayer.id
                });
            }

            const wpLat = parseFloat(lat);
            const wpLon = parseFloat(lon);

            routeMap.get(routeName).waypoints.push({
                name,
                lat: wpLat,
                lon: wpLon,
                altitude: waypointAltitude,
                width: width,
                height: height,
                type
            });
        });

        // Merge new routes with existing routes (don't clear on new file upload)
        const newRoutes = Array.from(routeMap.values());
        if (newRoutes.length === 0 && vertiportMap.size === 0) {
            state.fileLayers = state.fileLayers.filter(layer => layer.id !== fileLayer.id);
            alert('No valid routes or vertiports found in the selected file.');
            return;
        }

        // Every route of the file is kept in its own layer, even if another layer has a
        // route with the same name
        newRoutes.forEach(route => state.routes.push(route));

        // Merge new vertiports with existing ones
        vertiportMap.forEach((vp, name) => {
            state.vertiports.set(name, vp);
        });

        state.selectedRouteId = state.routes.length > 0 ? state.routes[0].id : null;

        // Re-attach form listeners to ensure fresh event handlers after CSV load
        attachFormListeners();
        updateUI();
        fitCameraToScene();
        e.target.value = '';
    };
    reader.readAsText(file);
}

function exportToCSV() {
    let csv = 'route,id,name,lat,lon,type,altitude,height,width\n';
    // Routes are written by name, so a name used in more than one layer gets the layer
    // name appended; otherwise the routes would merge into one when the file is reloaded
    const nameCount = new Map();
    state.routes.forEach(route => nameCount.set(route.name, (nameCount.get(route.name) || 0) + 1));
    const renamed = new Set();
    const exportName = route => {
        if (nameCount.get(route.name) === 1) return route.name;
        renamed.add(route.name);
        return `${route.name} [${route.layerId ? layerNameById(route.layerId) : 'generated'}]`;
    };
    state.routes.forEach(route => {
        const routeName = exportName(route);
        route.waypoints.forEach((wp, idx) => {
            const wpWidth = (wp.width !== undefined) ? wp.width : 457;
            const wpHeight = (wp.height !== undefined) ? wp.height : 305;
            csv += `"${routeName}",${idx + 1},"${wp.name}",${wp.lat},${wp.lon},"${wp.type}",${wp.altitude || 1219},${wpHeight},${wpWidth}\n`;
        });
    });
    if (renamed.size > 0) {
        alert(`${renamed.size} route name(s) are used in more than one layer; the layer name was appended to them in the exported file.`);
    }

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'uam_routes.csv';
    a.click();
    URL.revokeObjectURL(url);
}

function clearAll() {
    if (confirm('Are you sure you want to clear all routes, vertiports, trajectories, and file layers? This cannot be undone.')) {
        state.routes = [];
        state.vertiports = new Map();
        state.trajectories = [];
        state.fileLayers = [];
        state.selectedRouteId = null;
        state.selectedVertiportName = null;
        resetOverlapAnalysis();
        // Reset file input so files can be loaded again
        document.getElementById('csvFile').value = '';
        document.getElementById('trajectoryFile').value = '';
        updateUI();
    }
}
