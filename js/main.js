// UAM Airspace Dashboard: Event wiring and start-up. Loaded last: every other script only declares functions and state.
// Classic script sharing one global scope with the others; load order is set in index.html.

// Event listeners
document.getElementById('csvFile').addEventListener('change', handleCSVUpload);
document.getElementById('trajectoryFile').addEventListener('change', handleTrajectoryUpload);
document.getElementById('addRouteBtn').addEventListener('click', addRoute);
document.getElementById('addVertiportBtn').addEventListener('click', addVertiport);
document.getElementById('toggleAllRoutesBtn').addEventListener('click', toggleAllRoutesVisibility);
document.getElementById('toggleAllVertiportsBtn').addEventListener('click', toggleAllVertiportsVisibility);
document.getElementById('exportBtn').addEventListener('click', exportToCSV);
document.getElementById('clearAllBtn').addEventListener('click', clearAll);

// Attach initial form listeners
attachFormListeners();

document.getElementById('gridToggle').addEventListener('change', (e) => {
    state.showGrid = e.target.checked;
    updateGrid();
});

// Update grid size display value
function updateGridSizeDisplay() {
    const unit = getDisplayUnit();
    let displaySize = state.gridCellSize;
    if (state.unit === 'feet') {
        displaySize = metersToFeet(state.gridCellSize);
    }
    document.getElementById('gridSizeValue').textContent = `${displaySize} ${unit}`;
}

document.getElementById('gridSizeSlider').addEventListener('input', (e) => {
    const newSize = parseInt(e.target.value);
    state.gridCellSize = newSize;
    updateGridSizeDisplay();
    updateGrid();
});

document.getElementById('solidVolumesToggle').addEventListener('change', (e) => {
    state.solidVolumes = e.target.checked;
    renderScene();
});

document.getElementById('volumeProjectionToggle').addEventListener('change', (e) => {
    state.showVolumeProjection = e.target.checked;
    if (state.currentView === 'map') {
        if (!map2D) initMap();
        updateMap();
    }
});

document.getElementById('showNodesToggle').addEventListener('change', (e) => {
    state.showNodes = e.target.checked;
    // Sync the other checkbox
    const otherToggle = document.getElementById('showNodesToggle3D');
    if (otherToggle) otherToggle.checked = e.target.checked;
    if (state.currentView === 'map') {
        if (!map2D) initMap();
        updateMap();
    } else {
        renderScene();
    }
});

document.getElementById('showNodesToggle3D').addEventListener('change', (e) => {
    state.showNodes = e.target.checked;
    // Sync the other checkbox
    const otherToggle = document.getElementById('showNodesToggle');
    if (otherToggle) otherToggle.checked = e.target.checked;
    if (state.currentView === 'map') {
        if (!map2D) initMap();
        updateMap();
    } else {
        renderScene();
    }
});

// Unit toggle listeners
document.getElementById('unitMetersBtn').addEventListener('click', () => {
    state.unit = 'meters';
    document.getElementById('unitMetersBtn').style.background = '#3b82f6';
    document.getElementById('unitMetersBtn').style.color = 'white';
    document.getElementById('unitMetersBtn').style.borderColor = '#2563eb';
    document.getElementById('unitFeetBtn').style.background = '#e5e7eb';
    document.getElementById('unitFeetBtn').style.color = '#374151';
    document.getElementById('unitFeetBtn').style.borderColor = '#d1d5db';
    updateGridSizeDisplay();
    updateUI();
});

document.getElementById('unitFeetBtn').addEventListener('click', () => {
    state.unit = 'feet';
    document.getElementById('unitFeetBtn').style.background = '#3b82f6';
    document.getElementById('unitFeetBtn').style.color = 'white';
    document.getElementById('unitFeetBtn').style.borderColor = '#2563eb';
    document.getElementById('unitMetersBtn').style.background = '#e5e7eb';
    document.getElementById('unitMetersBtn').style.color = '#374151';
    document.getElementById('unitMetersBtn').style.borderColor = '#d1d5db';
    updateGridSizeDisplay();
    updateUI();
});

// View toggle listeners
document.getElementById('view3dBtn').addEventListener('click', () => switchView('3d'));
document.getElementById('viewMapBtn').addEventListener('click', () => switchView('map'));
document.getElementById('mapTileToggle').addEventListener('click', switchMapTileLayer);

// Initialize
initThreeJS();
updateUI();

// Batch parallel routes modal event listeners
document.getElementById('batchParallelBtn').addEventListener('click', openBatchParallelModal);
document.getElementById('closeBatchModal').addEventListener('click', closeBatchParallelModal);
document.getElementById('cancelBatchBtn').addEventListener('click', closeBatchParallelModal);
document.getElementById('submitBatchBtn').addEventListener('click', generateParallelRoutesForAll);
document.getElementById('numParallelRoutes').addEventListener('change', updateBatchModalFields);

// Close modal when clicking outside of it
document.getElementById('batchParallelModal').addEventListener('click', (e) => {
    if (e.target.id === 'batchParallelModal') {
        closeBatchParallelModal();
    }
});

// Overlap analysis modal event listeners
document.getElementById('overlapBtn').addEventListener('click', openOverlapModal);
document.getElementById('closeOverlapModal').addEventListener('click', closeOverlapModal);
document.getElementById('ovSubject').addEventListener('change', renderOverlapObstacleChoices);
document.getElementById('ovRunBtn').addEventListener('click', runOverlapAnalysis);
document.getElementById('ovExportBtn').addEventListener('click', exportOverlapCSV);
document.getElementById('ovShowMarkers').addEventListener('change', (e) => {
    overlapState.showMarkers = e.target.checked;
    if (map2D) updateMap();
});
document.getElementById('overlapModal').addEventListener('click', (e) => {
    if (e.target.id === 'overlapModal') {
        closeOverlapModal();
    }
});
