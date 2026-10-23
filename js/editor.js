// UAM Airspace Dashboard: Sidebar: layer, vertiport, route and waypoint lists and editors, and their form handlers.
// Classic script sharing one global scope with the others; load order is set in index.html.

// Update UI
function updateUI() {
    // Update file layer list
    const fileLayersSection = document.getElementById('fileLayersSection');
    const fileLayersList = document.getElementById('fileLayersList');
    const fileLayerCount = document.getElementById('fileLayerCount');
    if (fileLayersSection && fileLayersList && fileLayerCount) {
        fileLayersSection.style.display = state.fileLayers.length > 0 ? 'block' : 'none';
        fileLayerCount.textContent = state.fileLayers.length;
        fileLayersList.innerHTML = '';

        state.fileLayers.forEach(layer => {
            const stats = getLayerStats(layer.id);
            const layerHasVisibleItems = stats.total > 0 ? stats.visible > 0 : layer.visible;
            const layerEl = document.createElement('div');
            layerEl.className = 'route-item';
            layerEl.innerHTML = `
                <div class="route-item-header">
                    <div class="route-item-name">
                        <div class="route-color-swatch" style="background-color: ${layer.color}"></div>
                        <span>${escapeHtml(layer.name)}</span>
                    </div>
                    <div class="layer-controls">
                        <input class="layer-color-input" type="color" value="${layer.color}" data-layer-color="${layer.id}" title="Change layer color">
                        <button class="button-small" style="background: none; border: none; cursor: pointer;" data-layer-visibility="${layer.id}" data-layer-current-visible="${layerHasVisibleItems}">
                            ${layerHasVisibleItems ? 'Hide' : 'Show'}
                        </button>
                    </div>
                </div>
                <div class="route-item-info">
                    ${stats.visible}/${stats.total} visible - ${stats.routeCount} routes, ${stats.vertiportCount} vertiports, ${stats.trajectoryCount} trajectories
                </div>
            `;

            const colorInput = layerEl.querySelector('[data-layer-color]');
            colorInput.addEventListener('change', (e) => {
                setFileLayerColor(e.target.dataset.layerColor, e.target.value);
            });

            const visibilityBtn = layerEl.querySelector('[data-layer-visibility]');
            visibilityBtn.addEventListener('click', (e) => {
                setFileLayerVisibility(e.target.dataset.layerVisibility, e.target.dataset.layerCurrentVisible !== 'true');
            });

            fileLayersList.appendChild(layerEl);
        });
    }

    // Update vertiports list
    const vertiportsList = document.getElementById('vertiportsList');
    vertiportsList.innerHTML = '';
    state.vertiports.forEach((vertiport, name) => {
        const vertiportEl = document.createElement('div');
        vertiportEl.className = `route-item ${state.selectedVertiportName === name ? 'selected' : ''}`;
        const displayRadius = getDisplayValue(vertiport.radius);
        const displayHeight = getDisplayValue(vertiport.height);
        const unit = getDisplayUnit();
        const vertiportColor = getVertiportColor(vertiport);
        vertiportEl.innerHTML = `
            <div class="route-item-header">
                <div class="route-item-name">
                    <div class="route-color-swatch" style="background-color: ${vertiportColor}"></div>
                    <span>${escapeHtml(name)}</span>
                </div>
                <button class="button-small" style="background: none; border: none; cursor: pointer;" data-vertiport-name="${escapeHtml(name)}">
                    ${vertiport.visible ? '👁️' : '🙈'}
                </button>
            </div>
            <div class="route-item-info">
                ${escapeHtml(vertiport.type)}, R: ${displayRadius}${unit}, H: ${displayHeight}${unit}
            </div>
        `;
        vertiportEl.addEventListener('click', () => selectVertiport(name));
        const visibilityBtn = vertiportEl.querySelector('button');
        visibilityBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleVertiportVisibility(name);
        });
        vertiportsList.appendChild(vertiportEl);
    });

    document.getElementById('vertiportCount').textContent = state.vertiports.size;

    // Update vertiport editor
    const vertiportEditor = document.getElementById('vertiportEditor');
    const selectedVertiport = state.selectedVertiportName ? state.vertiports.get(state.selectedVertiportName) : null;
    if (selectedVertiport) {
        vertiportEditor.style.display = 'block';
        if (state.editingFieldId !== 'vertiportName') document.getElementById('vertiportName').value = state.selectedVertiportName;
        if (state.editingFieldId !== 'vertiportLat') document.getElementById('vertiportLat').value = selectedVertiport.lat;
        if (state.editingFieldId !== 'vertiportLon') document.getElementById('vertiportLon').value = selectedVertiport.lon;
        if (state.editingFieldId !== 'vertiportRadius') document.getElementById('vertiportRadius').value = getDisplayValue(selectedVertiport.radius);
        if (state.editingFieldId !== 'vertiportHeight') document.getElementById('vertiportHeight').value = getDisplayValue(selectedVertiport.height);
        if (state.editingFieldId !== 'vertiportType') document.getElementById('vertiportType').value = selectedVertiport.type;
        // Update labels
        const unit = getDisplayUnit();
        const radiusLabel = document.querySelector('label[for="vertiportRadius"]');
        const heightLabel = document.querySelector('label[for="vertiportHeight"]');
        if (radiusLabel) radiusLabel.textContent = `Radius (${unit})`;
        if (heightLabel) heightLabel.textContent = `Height (${unit})`;
    } else {
        vertiportEditor.style.display = 'none';
    }

    // Update routes list
    const routesList = document.getElementById('routesList');
    routesList.innerHTML = '';
    state.routes.forEach(route => {
        const routeEl = document.createElement('div');
        routeEl.className = `route-item ${state.selectedRouteId === route.id ? 'selected' : ''}`;
        const displayAltitude = getDisplayValue(getRouteAltitude(route));
        const unit = getDisplayUnit();
        const routeColor = routeColorToCss(route);
        routeEl.innerHTML = `
            <div class="route-item-header">
                <div class="route-item-name">
                    <div class="route-color-swatch" style="background-color: ${routeColor}"></div>
                    <span>${escapeHtml(route.name)}</span>
                </div>
                <button class="button-small" style="background: none; border: none; cursor: pointer;" data-route-id="${escapeHtml(route.id)}">
                    ${route.visible ? '👁️' : '🙈'}
                </button>
            </div>
            <div class="route-item-info">
                ${route.waypoints.length} waypoints, Alt: ${displayAltitude}${unit}
            </div>
        `;
        routeEl.addEventListener('click', () => selectRoute(route.id));
        const visibilityBtn = routeEl.querySelector('button');
        visibilityBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleRouteVisibility(route.id);
        });
        routesList.appendChild(routeEl);
    });

    document.getElementById('routeCount').textContent = state.routes.length;

    // Update editor
    const routeEditor = document.getElementById('routeEditor');
    const selectedRoute = state.routes.find(r => r.id === state.selectedRouteId);
    if (selectedRoute) {
        routeEditor.style.display = 'block';
        const unit = getDisplayUnit();
        if (state.editingFieldId !== 'routeName') document.getElementById('routeName').value = selectedRoute.name;
        const routeAltEl = document.getElementById('routeAltitude');
        const routeWidthEl = document.getElementById('routeCorridorWidth');
        const routeHeightEl = document.getElementById('routeCorridorHeight');
        if (routeAltEl) routeAltEl.value = getDisplayValue(getRouteAltitude(selectedRoute));
        if (routeWidthEl) routeWidthEl.value = getDisplayValue(getRouteWidth(selectedRoute));
        if (routeHeightEl) routeHeightEl.value = getDisplayValue(getRouteHeight(selectedRoute));
        // Note: corridor width/height inputs are now read-only, showing mean values of all waypoints
        // Update labels
        const altitudeLabel = document.querySelector('label[for="routeAltitude"]');
        const widthLabel = document.querySelector('label[for="routeCorridorWidth"]');
        const heightLabelRoute = document.querySelector('label[for="routeCorridorHeight"]');
        const horizontalLabel = document.querySelector('label[for="horizontalOffset"]');
        const verticalLabel = document.querySelector('label[for="verticalOffset"]');
        if (altitudeLabel) altitudeLabel.textContent = `Altitude (Mean - ${unit})`;
        if (widthLabel) widthLabel.textContent = `Corridor Width (Mean - ${unit})`;
        if (heightLabelRoute) heightLabelRoute.textContent = `Corridor Height (Mean - ${unit})`;
        if (horizontalLabel) horizontalLabel.textContent = `Horizontal Distance (${unit})`;
        if (verticalLabel) verticalLabel.textContent = `Vertical Distance (${unit})`;

        // Update waypoints
        const waypointsList = document.getElementById('waypointsList');
        waypointsList.innerHTML = '';
        selectedRoute.waypoints.forEach((wp, idx) => {
            const wpEl = document.createElement('div');
            wpEl.className = 'waypoint-item';
            wpEl.draggable = true;
            wpEl.dataset.waypointIndex = idx;
            wpEl.style.cursor = 'move';
            // Use CSV altitude for all waypoints
            const displayedAlt = wp.altitude || 760;
            const displayAlt = getDisplayValue(displayedAlt);
            const unit_wp = getDisplayUnit();
            const wpWidth = (wp.width !== undefined) ? wp.width : 457;
            const wpHeight = (wp.height !== undefined) ? wp.height : 305;
            const displayWidth = getDisplayValue(wpWidth);
            const displayHeight = getDisplayValue(wpHeight);
            wpEl.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.25rem;">
                    <div style="flex: 1;">
                        <label style="display: block; font-size: 0.7rem; margin-bottom: 0.125rem;">Name</label>
                        <input type="text" data-waypoint-index="${idx}" data-waypoint-field="name" class="waypoint-name-input" value="${escapeHtml(wp.name)}" style="width: 100%; padding: 0.25rem; border: 1px solid #d1d5db; border-radius: 0.25rem; font-size: 0.75rem; box-sizing: border-box;">
                    </div>
                    <button class="waypoint-delete-btn" data-waypoint-index="${idx}" style="background: #ef4444; color: white; border: none; border-radius: 0.25rem; padding: 0.25rem 0.5rem; font-size: 0.7rem; cursor: pointer; flex-shrink: 0; margin-top: 1.25rem;">Delete</button>
                </div>
                <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem; display: flex; gap: 0.5rem;">
                    <div style="flex: 1;">
                        <label style="display: block; font-size: 0.7rem; margin-bottom: 0.125rem;">Lat</label>
                        <input type="number" data-waypoint-index="${idx}" data-waypoint-field="lat" class="waypoint-coord-input" value="${wp.lat.toFixed(6)}" step="0.000001" style="width: 100%; padding: 0.25rem; border: 1px solid #d1d5db; border-radius: 0.25rem; font-size: 0.75rem; box-sizing: border-box;">
                    </div>
                    <div style="flex: 1;">
                        <label style="display: block; font-size: 0.7rem; margin-bottom: 0.125rem;">Lon</label>
                        <input type="number" data-waypoint-index="${idx}" data-waypoint-field="lon" class="waypoint-coord-input" value="${wp.lon.toFixed(6)}" step="0.000001" style="width: 100%; padding: 0.25rem; border: 1px solid #d1d5db; border-radius: 0.25rem; font-size: 0.75rem; box-sizing: border-box;">
                    </div>
                </div>
                <div class="waypoint-altitude" style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem;">
                    Altitude: <input type="number" data-waypoint-index="${idx}" class="waypoint-alt-input" value="${displayAlt}" style="width: 70px; padding: 0.25rem; border: 1px solid #d1d5db; border-radius: 0.25rem; font-size: 0.75rem;"> ${unit_wp}
                </div>
                <div style="font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem; display: flex; gap: 0.5rem;">
                    <div style="flex: 1;">
                        <label style="display: block; font-size: 0.7rem; margin-bottom: 0.125rem;">Corridor Width</label>
                        <input type="number" data-waypoint-index="${idx}" class="waypoint-width-input" value="${displayWidth}" style="width: 100%; padding: 0.25rem; border: 1px solid #d1d5db; border-radius: 0.25rem; font-size: 0.75rem;">
                    </div>
                    <div style="flex: 1;">
                        <label style="display: block; font-size: 0.7rem; margin-bottom: 0.125rem;">Height</label>
                        <input type="number" data-waypoint-index="${idx}" class="waypoint-height-input" value="${displayHeight}" style="width: 100%; padding: 0.25rem; border: 1px solid #d1d5db; border-radius: 0.25rem; font-size: 0.75rem;">
                    </div>
                </div>
                <div style="font-size: 0.7rem; color: #9ca3af;">${unit_wp}</div>
            `;
            waypointsList.appendChild(wpEl);
        });
    } else {
        routeEditor.style.display = 'none';
    }

    // Update statistics
    document.getElementById('statRoutes').textContent = state.routes.length;
    document.getElementById('statVertiports').textContent = state.vertiports.size;
    document.getElementById('statWaypoints').textContent = state.routes.reduce((sum, r) => sum + r.waypoints.length, 0);

    updateMapPlane();
    renderScene();

    // Re-attach form listeners after DOM regeneration
    attachFormListeners();

    // Update map in background if initialized (always keep it in sync)
    if (map2D) {
        updateMap();
    }
}

// Vertiport management functions
function selectVertiport(name) {
    state.selectedVertiportName = name;
    updateUI();
}

function addVertiport() {
    const name = `Vertiport ${state.vertiports.size + 1}`;
    state.vertiports.set(name, {
        lat: -23.55,
        lon: -46.63,
        height: 760,
        radius: 610,
        type: 'Vertiport',
        color: '#4444ff',
        visible: true
    });
    state.selectedVertiportName = name;
    updateUI();
}

function toggleVertiportVisibility(name) {
    const vertiport = state.vertiports.get(name);
    if (vertiport) {
        vertiport.visible = !vertiport.visible;
        updateUI();
    }
}

function toggleAllVertiportsVisibility() {
    state.allVertiportsVisible = !state.allVertiportsVisible;
    state.vertiports.forEach((vertiport) => {
        vertiport.visible = state.allVertiportsVisible;
    });
    updateUI();
}

function updateVertiport(updates) {
    if (!state.selectedVertiportName) return;
    const vertiport = state.vertiports.get(state.selectedVertiportName);
    if (!vertiport) return;

    // Handle name change
    if (updates.name && updates.name !== state.selectedVertiportName) {
        state.vertiports.set(updates.name, vertiport);
        state.vertiports.delete(state.selectedVertiportName);
        state.selectedVertiportName = updates.name;
        delete updates.name;
    }

    Object.assign(vertiport, updates);
    updateUI();
}

function deleteVertiport() {
    if (!state.selectedVertiportName) return;
    state.vertiports.delete(state.selectedVertiportName);
    state.selectedVertiportName = null;
    updateUI();
}

// Route management functions
function selectRoute(routeId) {
    state.selectedRouteId = routeId;
    updateUI();
}

function toggleRouteVisibility(routeId) {
    const route = state.routes.find(r => r.id === routeId);
    if (route) {
        route.visible = !route.visible;
        updateUI();
    }
}

function toggleAllRoutesVisibility() {
    state.allRoutesVisible = !state.allRoutesVisible;
    state.routes.forEach((route) => {
        route.visible = state.allRoutesVisible;
    });
    updateUI();
}

function addRoute() {
    const color = {
        r: Math.floor(Math.random() * 256),
        g: Math.floor(Math.random() * 256),
        b: Math.floor(Math.random() * 256)
    };
    const newRoute = {
        id: `route-${Date.now()}`,
        name: `New Route ${state.routes.length + 1}`,
        waypoints: [],
        corridorWidth: 457,
        corridorHeight: 152,
        color: new THREE.Color(color.r / 255, color.g / 255, color.b / 255),
        visible: true
    };
    state.routes.push(newRoute);
    state.selectedRouteId = newRoute.id;
    updateUI();
}

// Calculate mean altitude of all waypoints in a route (excluding start and end points)
function getRouteAltitude(route) {
    if (route.waypoints.length === 0) return 1219; // default altitude (4000 ft)
    if (route.waypoints.length <= 2) return 1219; // if 2 or fewer waypoints, return default (all are start/end)

    // Calculate mean of middle waypoints (exclude first and last)
    const middleWaypoints = route.waypoints.slice(1, -1);
    const totalAltitude = middleWaypoints.reduce((sum, wp) => sum + (wp.altitude || 1219), 0);
    return Math.round(totalAltitude / middleWaypoints.length);
}

function getRouteWidth(route) {
    if (route.waypoints.length === 0) return 457; // default width

    // Calculate mean of all waypoint widths
    const totalWidth = route.waypoints.reduce((sum, wp) => sum + (wp.width || 457), 0);
    return Math.round(totalWidth / route.waypoints.length);
}

function getRouteHeight(route) {
    if (route.waypoints.length === 0) return 1219; // default height (4000 ft) for terminal airspace

    // Calculate mean of all waypoint heights
    const totalHeight = route.waypoints.reduce((sum, wp) => sum + (wp.height || 305), 0);
    return Math.round(totalHeight / route.waypoints.length);
}

function updateRoute(updates) {
    const route = state.routes.find(r => r.id === state.selectedRouteId);
    if (!route) return;
    Object.assign(route, updates);
    updateUI();
}

function deleteRoute() {
    state.routes = state.routes.filter(r => r.id !== state.selectedRouteId);
    state.selectedRouteId = null;
    updateUI();
}

function addWaypoint() {
    const route = state.routes.find(r => r.id === state.selectedRouteId);
    if (!route) return;

    // Get default dimensions from last waypoint or use defaults
    let defaultWidth = 457;  // 1500 ft
    let defaultHeight = 305; // 1000 ft
    if (route.waypoints.length > 0) {
        const lastWp = route.waypoints[route.waypoints.length - 1];
        defaultWidth = (lastWp.width !== undefined) ? lastWp.width : 457;
        defaultHeight = (lastWp.height !== undefined) ? lastWp.height : 305;
    }

    route.waypoints.push({
        name: `WP ${route.waypoints.length + 1}`,
        lat: -23.55,
        lon: -46.63,
        altitude: 1219,
        width: defaultWidth,
        height: defaultHeight,
        type: 'Waypoint'
    });
    updateUI();
}

function deleteWaypoint(waypointIndex) {
    const route = state.routes.find(r => r.id === state.selectedRouteId);
    if (!route) return;
    if (waypointIndex >= 0 && waypointIndex < route.waypoints.length) {
        route.waypoints.splice(waypointIndex, 1);
        updateUI();
    }
}

// Waypoint fields of a generated parallel route (defaults as for loaded routes)
function parallelWaypointFields(wp, idx) {
    return {
        name: wp.name || `WP ${idx + 1}`,
        lat: wp.lat,
        lon: wp.lon,
        altitude: wp.altitude || 1219,
        width: wp.width || 457,
        height: wp.height || 305,
        type: wp.type || 'Waypoint'
    };
}

function createParallelCorridor(offset, direction) {
    const route = state.routes.find(r => r.id === state.selectedRouteId);
    if (!route || route.waypoints.length < 2) return;

    if (direction === 'horizontal') {
        const newWaypoints = offsetWaypointsHorizontally(route.waypoints, offset)
            .map(parallelWaypointFields);

        const color = {
            r: Math.floor(Math.random() * 256),
            g: Math.floor(Math.random() * 256),
            b: Math.floor(Math.random() * 256)
        };

        // Count existing parallel routes from this parent to get a unique number
        const parallelCount = state.routes.filter(r => 
            r.name.startsWith(`${route.name} (Parallel`)
        ).length + 1;

        const newRoute = {
            ...route,
            id: `route-${Date.now()}`,
            name: `${route.name} (Parallel ${parallelCount})`,
            waypoints: newWaypoints,
            color: new THREE.Color(color.r / 255, color.g / 255, color.b / 255),
            layerId: null
        };

        state.routes.push(newRoute);
        updateUI();
    } else {
        // Vertical offset (altitude change)
        // Keep start and end waypoints altitude fixed
        const color = {
            r: Math.floor(Math.random() * 256),
            g: Math.floor(Math.random() * 256),
            b: Math.floor(Math.random() * 256)
        };

        // Count existing parallel routes from this parent to get a unique number
        const parallelCount = state.routes.filter(r => 
            r.name.startsWith(`${route.name} (Parallel`)
        ).length + 1;

        const newRoute = {
            ...route,
            id: `route-${Date.now()}`,
            name: `${route.name} (Parallel ${parallelCount})`,
            waypoints: route.waypoints.map((wp, idx) => {
                // Keep start and end waypoints at original altitude
                if (idx === 0 || idx === route.waypoints.length - 1) {
                    return { ...wp };
                }
                // Apply offset to middle waypoints
                return {
                    ...wp,
                    altitude: (wp.altitude || 1219) + offset
                };
            }),
            color: new THREE.Color(color.r / 255, color.g / 255, color.b / 255),
            layerId: null
        };

        state.routes.push(newRoute);
        updateUI();
    }
}

// Handler functions for form listeners
const handleVertiportNameChange = (e) => {
    state.editingFieldId = 'vertiportName';
    updateVertiport({ name: e.target.value });
};
const handleVertiportLatChange = (e) => {
    state.editingFieldId = 'vertiportLat';
    updateVertiport({ lat: Number(e.target.value) });
};
const handleVertiportLonChange = (e) => {
    state.editingFieldId = 'vertiportLon';
    updateVertiport({ lon: Number(e.target.value) });
};
const handleVertiportRadiusChange = (e) => {
    state.editingFieldId = 'vertiportRadius';
    const displayValue = Number(e.target.value);
    const metersValue = state.unit === 'feet' ? feetToMeters(displayValue) : displayValue;
    updateVertiport({ radius: metersValue });
};
const handleVertiportHeightChange = (e) => {
    state.editingFieldId = 'vertiportHeight';
    const displayValue = Number(e.target.value);
    const metersValue = state.unit === 'feet' ? feetToMeters(displayValue) : displayValue;
    updateVertiport({ height: metersValue });
};
const handleVertiportTypeChange = (e) => {
    state.editingFieldId = 'vertiportType';
    updateVertiport({ type: e.target.value });
};
const handleRouteNameChange = (e) => {
    state.editingFieldId = 'routeName';
    updateRoute({ name: e.target.value });
};
const handleRouteAltitudeChange = (e) => {
    state.editingFieldId = 'routeAltitude';
    // Route altitude is now read-only (computed from waypoints)
    updateRoute({});
};
const handleRouteWidthChange = (e) => {
    state.editingFieldId = 'routeCorridorWidth';
    // Route width is now read-only (computed from waypoints)
    updateRoute({});
};
const handleRouteHeightChange = (e) => {
    state.editingFieldId = 'routeCorridorHeight';
    // Route height is now read-only (computed from waypoints)
    updateRoute({});
};
const handleHorizontalCorridor = () => {
    const displayValue = parseInt(document.getElementById('horizontalOffset').value) || 500;
    const metersValue = state.unit === 'feet' ? feetToMeters(displayValue) : displayValue;
    createParallelCorridor(metersValue, 'horizontal');
};
const handleVerticalCorridor = () => {
    const displayValue = parseInt(document.getElementById('verticalOffset').value) || 100;
    const metersValue = state.unit === 'feet' ? feetToMeters(displayValue) : displayValue;
    createParallelCorridor(metersValue, 'vertical');
};

// Form listener management functions
function attachFormListeners() {
    // Vertiport event listeners
    const vertiportNameEl = document.getElementById('vertiportName');
    const vertiportLatEl = document.getElementById('vertiportLat');
    const vertiportLonEl = document.getElementById('vertiportLon');
    const vertiportRadiusEl = document.getElementById('vertiportRadius');
    const vertiportHeightEl = document.getElementById('vertiportHeight');
    const vertiportTypeEl = document.getElementById('vertiportType');
    const deleteVertiportBtnEl = document.getElementById('deleteVertiportBtn');

    if (vertiportNameEl) {
        vertiportNameEl.addEventListener('input', handleVertiportNameChange);
        vertiportNameEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    if (vertiportLatEl) {
        vertiportLatEl.addEventListener('input', handleVertiportLatChange);
        vertiportLatEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    if (vertiportLonEl) {
        vertiportLonEl.addEventListener('input', handleVertiportLonChange);
        vertiportLonEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    if (vertiportRadiusEl) {
        vertiportRadiusEl.addEventListener('input', handleVertiportRadiusChange);
        vertiportRadiusEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    if (vertiportHeightEl) {
        vertiportHeightEl.addEventListener('input', handleVertiportHeightChange);
        vertiportHeightEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    if (vertiportTypeEl) {
        vertiportTypeEl.addEventListener('input', handleVertiportTypeChange);
        vertiportTypeEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    if (deleteVertiportBtnEl) deleteVertiportBtnEl.addEventListener('click', deleteVertiport);

    // Route event listeners
    const routeNameEl = document.getElementById('routeName');
    const routeAltitudeEl = document.getElementById('routeAltitude');
    const routeWidthEl = document.getElementById('routeCorridorWidth');
    const routeHeightEl = document.getElementById('routeCorridorHeight');
    const addWaypointEl = document.getElementById('addWaypointBtn');
    const deleteRouteEl = document.getElementById('deleteRouteBtn');
    const horizontalBtn = document.getElementById('horizontalCorridorBtn');
    const verticalBtn = document.getElementById('verticalCorridorBtn');

    if (routeNameEl) {
        routeNameEl.addEventListener('input', handleRouteNameChange);
        routeNameEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    if (routeAltitudeEl) {
        routeAltitudeEl.addEventListener('input', handleRouteAltitudeChange);
        routeAltitudeEl.addEventListener('blur', () => { state.editingFieldId = null; });
    }
    // Route-level width/height inputs are now hidden since dimensions are per-waypoint
    // if (routeWidthEl) { ... }
    // if (routeHeightEl) { ... }
    if (addWaypointEl) addWaypointEl.addEventListener('click', addWaypoint);
    if (deleteRouteEl) deleteRouteEl.addEventListener('click', deleteRoute);
    if (horizontalBtn) horizontalBtn.addEventListener('click', handleHorizontalCorridor);
    if (verticalBtn) verticalBtn.addEventListener('click', handleVerticalCorridor);

    // Waypoint altitude event listeners
    const waypointAltInputs = document.querySelectorAll('.waypoint-alt-input');
    waypointAltInputs.forEach(input => {
        input.addEventListener('input', (e) => {
            const route = state.routes.find(r => r.id === state.selectedRouteId);
            if (!route) return;

            const waypointIndex = parseInt(e.target.dataset.waypointIndex);
            const displayValue = Number(e.target.value);
            const metersValue = state.unit === 'feet' ? feetToMeters(displayValue) : displayValue;

            if (route.waypoints[waypointIndex]) {
                route.waypoints[waypointIndex].altitude = metersValue;
                // Update route altitude display without rebuilding the entire UI
                const routeAltEl = document.getElementById('routeAltitude');
                if (routeAltEl) routeAltEl.value = getDisplayValue(getRouteAltitude(route));
                // Update visualizations
                renderScene();
                if (map2D) updateMap();
            }
        });
    });

    // Waypoint width event listeners
    const waypointWidthInputs = document.querySelectorAll('.waypoint-width-input');
    waypointWidthInputs.forEach(input => {
        input.addEventListener('input', (e) => {
            const route = state.routes.find(r => r.id === state.selectedRouteId);
            if (!route) return;

            const waypointIndex = parseInt(e.target.dataset.waypointIndex);
            const displayValue = Number(e.target.value);
            const metersValue = state.unit === 'feet' ? feetToMeters(displayValue) : displayValue;

            if (route.waypoints[waypointIndex]) {
                route.waypoints[waypointIndex].width = metersValue;
                renderScene();
            }
        });
    });

    // Waypoint height event listeners
    const waypointHeightInputs = document.querySelectorAll('.waypoint-height-input');
    waypointHeightInputs.forEach(input => {
        input.addEventListener('input', (e) => {
            const route = state.routes.find(r => r.id === state.selectedRouteId);
            if (!route) return;

            const waypointIndex = parseInt(e.target.dataset.waypointIndex);
            const displayValue = Number(e.target.value);
            const metersValue = state.unit === 'feet' ? feetToMeters(displayValue) : displayValue;

            if (route.waypoints[waypointIndex]) {
                route.waypoints[waypointIndex].height = metersValue;
                renderScene();
            }
        });
    });

    // Waypoint name event listeners
    const waypointNameInputs = document.querySelectorAll('.waypoint-name-input');
    waypointNameInputs.forEach(input => {
        input.addEventListener('input', (e) => {
            const route = state.routes.find(r => r.id === state.selectedRouteId);
            if (!route) return;

            const waypointIndex = parseInt(e.target.dataset.waypointIndex);
            const value = e.target.value;

            if (route.waypoints[waypointIndex]) {
                route.waypoints[waypointIndex].name = value;
                // Update visualizations without rebuilding the entire UI
                renderScene();
                if (map2D) updateMap();
            }
        });
    });

    // Waypoint coordinate event listeners
    const waypointCoordInputs = document.querySelectorAll('.waypoint-coord-input');
    waypointCoordInputs.forEach(input => {
        input.addEventListener('input', (e) => {
            const route = state.routes.find(r => r.id === state.selectedRouteId);
            if (!route) return;

            const waypointIndex = parseInt(e.target.dataset.waypointIndex);
            const field = e.target.dataset.waypointField;
            const value = Number(e.target.value);

            if (route.waypoints[waypointIndex]) {
                route.waypoints[waypointIndex][field] = value;
                // Update visualizations without rebuilding the entire UI
                updateMapPlane();
                renderScene();
                if (map2D) updateMap();
            }
        });
    });

    // Waypoint delete button listeners
    const waypointDeleteBtns = document.querySelectorAll('.waypoint-delete-btn');
    waypointDeleteBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const waypointIndex = parseInt(e.target.dataset.waypointIndex);
            deleteWaypoint(waypointIndex);
        });
    });

    // Waypoint drag-and-drop listeners
    const waypointItems = document.querySelectorAll('.waypoint-item');
    waypointItems.forEach(item => {
        item.addEventListener('dragstart', (e) => {
            const waypointIndex = parseInt(e.currentTarget.dataset.waypointIndex);
            state.draggedWaypointIndex = waypointIndex;
            e.dataTransfer.effectAllowed = 'move';
            e.currentTarget.style.opacity = '0.5';
        });

        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            e.currentTarget.style.borderTop = '2px solid #3b82f6';
        });

        item.addEventListener('dragleave', (e) => {
            e.currentTarget.style.borderTop = 'none';
        });

        item.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();

            const route = state.routes.find(r => r.id === state.selectedRouteId);
            if (!route || state.draggedWaypointIndex === null) return;

            const dropIndex = parseInt(e.currentTarget.dataset.waypointIndex);
            const dragIndex = state.draggedWaypointIndex;

            if (dragIndex !== dropIndex) {
                // Reorder waypoints
                const draggedWaypoint = route.waypoints[dragIndex];
                route.waypoints.splice(dragIndex, 1);
                const insertIndex = dragIndex > dropIndex ? dropIndex : dropIndex - 1;
                route.waypoints.splice(insertIndex, 0, draggedWaypoint);
            }

            state.draggedWaypointIndex = null;
            e.currentTarget.style.borderTop = 'none';
            updateUI();
        });

        item.addEventListener('dragend', (e) => {
            e.currentTarget.style.opacity = '1';
            e.currentTarget.style.borderTop = 'none';
            state.draggedWaypointIndex = null;
        });
    });
}
