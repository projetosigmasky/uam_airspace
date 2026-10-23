// UAM Airspace Dashboard: File layers, colors, unit conversion and HTML escaping.
// Classic script sharing one global scope with the others; load order is set in index.html.

function randomColorHex() {
    return '#' + Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0');
}

function createFileLayer(fileName, color, type) {
    const layer = {
        id: `file-layer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        name: fileName,
        color,
        type,
        visible: true
    };
    state.fileLayers.push(layer);
    return layer;
}

function routeColorToCss(route) {
    if (!route || !route.color) return '#0066cc';
    return `rgb(${Math.round(route.color.r * 255)}, ${Math.round(route.color.g * 255)}, ${Math.round(route.color.b * 255)})`;
}

function getVertiportColor(vertiport) {
    return (vertiport && vertiport.color) ? vertiport.color : '#4444ff';
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function getLayerStats(layerId) {
    const routeCount = state.routes.filter(route => route.layerId === layerId).length;
    let vertiportCount = 0;
    state.vertiports.forEach((vertiport) => {
        if (vertiport.layerId === layerId) vertiportCount++;
    });
    const trajectoryCount = state.trajectories.filter(trajectory => trajectory.layerId === layerId).length;

    const visibleRoutes = state.routes.filter(route => route.layerId === layerId && route.visible).length;
    let visibleVertiports = 0;
    state.vertiports.forEach((vertiport) => {
        if (vertiport.layerId === layerId && vertiport.visible) visibleVertiports++;
    });
    const visibleTrajectories = state.trajectories.filter(trajectory => trajectory.layerId === layerId && trajectory.visible).length;

    const total = routeCount + vertiportCount + trajectoryCount;
    const visible = visibleRoutes + visibleVertiports + visibleTrajectories;

    return { routeCount, vertiportCount, trajectoryCount, total, visible };
}

function setFileLayerVisibility(layerId, visible) {
    const layer = state.fileLayers.find(item => item.id === layerId);
    if (layer) layer.visible = visible;

    state.routes.forEach(route => {
        if (route.layerId === layerId) route.visible = visible;
    });
    state.vertiports.forEach((vertiport) => {
        if (vertiport.layerId === layerId) vertiport.visible = visible;
    });
    state.trajectories.forEach(trajectory => {
        if (trajectory.layerId === layerId) trajectory.visible = visible;
    });

    updateUI();
}

function setFileLayerColor(layerId, color) {
    const layer = state.fileLayers.find(item => item.id === layerId);
    if (layer) layer.color = color;

    state.routes.forEach(route => {
        if (route.layerId === layerId) route.color = new THREE.Color(color);
    });
    state.vertiports.forEach((vertiport) => {
        if (vertiport.layerId === layerId) vertiport.color = color;
    });
    state.trajectories.forEach(trajectory => {
        if (trajectory.layerId === layerId) trajectory.color = color;
    });

    updateUI();
}

// Unit conversion functions
function metersToFeet(meters) {
    return Math.round(meters * 3.28084); // Return whole number
}

function feetToMeters(feet) {
    return Math.round(feet / 3.28084); // Return whole number
}

function formatDistance(meters) {
    if (state.unit === 'feet') {
        return metersToFeet(meters) + ' ft';
    }
    return meters + ' m';
}

function getDisplayValue(meters) {
    if (state.unit === 'feet') {
        return metersToFeet(meters);
    }
    return meters;
}

function getDisplayUnit() {
    return state.unit === 'feet' ? 'ft' : 'm';
}
