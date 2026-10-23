// UAM Airspace Dashboard: Batch Operations > Generate Parallel Routes.
// Classic script sharing one global scope with the others; load order is set in index.html.

// Batch Parallel Routes Modal Functions
function openBatchParallelModal() {
    document.getElementById('batchParallelModal').classList.add('active');
    // Initialize modal fields based on current state
    updateBatchModalFields();
}

function closeBatchParallelModal() {
    document.getElementById('batchParallelModal').classList.remove('active');
}

function updateTotalRoutesPreview() {
    // Get all offset inputs
    const horizontalInputs = Array.from(document.querySelectorAll('.horizontal-offset-input'));
    const verticalInputs = Array.from(document.querySelectorAll('.vertical-offset-input'));

    // Each pair of (horizontal, vertical) offsets creates ONE parallel route
    // The number of parallel routes per original route = max number of offset pairs
    const numOffsetsPerRoute = Math.max(horizontalInputs.length, verticalInputs.length);

    // Count valid offset pairs (at least one non-zero offset per pair)
    let validPairs = 0;
    for (let i = 0; i < numOffsetsPerRoute; i++) {
        const hOffset = horizontalInputs[i] ? parseFloat(horizontalInputs[i].value) : 0;
        const vOffset = verticalInputs[i] ? parseFloat(verticalInputs[i].value) : 0;

        // Count as valid if horizontal !== 0 OR vertical !== 0 (allows negative values)
        if (hOffset !== 0 || vOffset !== 0) {
            validPairs++;
        }
    }

    // Total = existing routes * valid parallel routes per original
    const totalRoutes = state.routes.length * validPairs;
    document.getElementById('totalRoutesCount').textContent = totalRoutes;
}

function updateBatchModalFields() {
    const numRoutes = parseInt(document.getElementById('numParallelRoutes').value) || 1;
    const horizontalContainer = document.getElementById('horizontalOffsetsContainer');
    const verticalContainer = document.getElementById('verticalOffsetsContainer');

    // Clear and rebuild horizontal offset fields
    horizontalContainer.innerHTML = '';
    for (let i = 1; i <= numRoutes; i++) {
        const field = document.createElement('div');
        field.className = 'offset-field';
        const input = document.createElement('input');
        input.type = 'number';
        input.className = 'horizontal-offset-input';
        input.value = 500 * i;
        input.step = '1';
        input.addEventListener('change', updateTotalRoutesPreview);
        input.addEventListener('input', updateTotalRoutesPreview);

        const label = document.createElement('label');
        label.className = 'offset-field-label';
        label.textContent = `Route ${i} Horizontal Offset`;

        const groupDiv = document.createElement('div');
        groupDiv.className = 'offset-field-group';
        groupDiv.appendChild(label);
        groupDiv.appendChild(input);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-offset-btn';
        removeBtn.textContent = '×';
        removeBtn.title = 'Remove this offset';
        removeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            field.remove();
            updateTotalRoutesPreview();
        });

        field.appendChild(groupDiv);
        field.appendChild(removeBtn);
        horizontalContainer.appendChild(field);
    }

    // Clear and rebuild vertical offset fields
    verticalContainer.innerHTML = '';
    for (let i = 1; i <= numRoutes; i++) {
        const field = document.createElement('div');
        field.className = 'offset-field';
        const input = document.createElement('input');
        input.type = 'number';
        input.className = 'vertical-offset-input';
        input.value = 100 * i;
        input.step = '1';
        input.addEventListener('change', updateTotalRoutesPreview);
        input.addEventListener('input', updateTotalRoutesPreview);

        const label = document.createElement('label');
        label.className = 'offset-field-label';
        label.textContent = `Route ${i} Vertical Offset`;

        const groupDiv = document.createElement('div');
        groupDiv.className = 'offset-field-group';
        groupDiv.appendChild(label);
        groupDiv.appendChild(input);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-offset-btn';
        removeBtn.textContent = '×';
        removeBtn.title = 'Remove this offset';
        removeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            field.remove();
            updateTotalRoutesPreview();
        });

        field.appendChild(groupDiv);
        field.appendChild(removeBtn);
        verticalContainer.appendChild(field);
    }

    // Initial preview update
    updateTotalRoutesPreview();
}

function generateParallelRoutesForAll() {
    if (state.routes.length === 0) {
        alert('No routes to generate parallel routes from. Please add or load routes first.');
        return;
    }

    const numRoutes = parseInt(document.getElementById('numParallelRoutes').value) || 1;
    const horizontalInputs = document.querySelectorAll('.horizontal-offset-input');
    const verticalInputs = document.querySelectorAll('.vertical-offset-input');
    const deleteOriginal = document.getElementById('deleteOriginalRoutes').checked;

    // Validate we have enough offset inputs
    if (horizontalInputs.length === 0 && verticalInputs.length === 0) {
        alert('Please add at least one offset value.');
        return;
    }

    // Get the offset values (can be positive or negative)
    const horizontalOffsets = Array.from(horizontalInputs).map(input => parseFloat(input.value) || 0);
    const verticalOffsets = Array.from(verticalInputs).map(input => parseFloat(input.value) || 0);

    // Determine number of parallel routes to create per original route
    const numParallelsPerRoute = Math.max(horizontalOffsets.length, verticalOffsets.length);

    // Generate parallel routes for each existing route
    const originalRouteIds = state.routes.map(r => r.id);
    const originalRouteCount = originalRouteIds.length;
    let routesCreatedCount = 0;

    originalRouteIds.forEach(routeId => {
        const route = state.routes.find(r => r.id === routeId);
        if (!route || route.waypoints.length < 2) return;

        // For each set of offsets, create one parallel route with both offsets applied
        for (let i = 0; i < numParallelsPerRoute; i++) {
            const horizontalOffset = horizontalOffsets[i] || 0;
            const verticalOffset = verticalOffsets[i] || 0;

            // Skip only if both offsets are zero
            if (horizontalOffset === 0 && verticalOffset === 0) continue;

            // Create a new route with both offsets applied
            let parallelWaypoints = [...route.waypoints];

            // Apply horizontal offset first (if any) - works with positive and negative values
            if (horizontalOffset !== 0) {
                parallelWaypoints = offsetWaypointsHorizontally(route.waypoints, horizontalOffset)
                    .map(parallelWaypointFields);
            }

            // Apply vertical offset (to the waypoints we have, whether horizontally offset or not)
            if (verticalOffset !== 0) {
                parallelWaypoints = parallelWaypoints.map((wp, idx) => {
                    // Keep start and end waypoints at original altitude
                    if (idx === 0 || idx === parallelWaypoints.length - 1) {
                        return { ...wp };
                    }
                    return {
                        ...wp,
                        altitude: (wp.altitude || 1219) + verticalOffset
                    };
                });
            }

            // Create the new parallel route
            const color = {
                r: Math.floor(Math.random() * 256),
                g: Math.floor(Math.random() * 256),
                b: Math.floor(Math.random() * 256)
            };

            const parallelCount = state.routes.filter(r => 
                r.name.startsWith(`${route.name} (Parallel`)
            ).length + 1;

            const newRoute = {
                ...route,
                id: `route-${Date.now()}-${i}`,
                name: `${route.name} (Parallel ${parallelCount})`,
                waypoints: parallelWaypoints,
                color: new THREE.Color(color.r / 255, color.g / 255, color.b / 255),
                layerId: null
            };

            state.routes.push(newRoute);
            routesCreatedCount++;
        }
    });

    // Delete original routes if requested
    if (deleteOriginal) {
        originalRouteIds.forEach(routeId => {
            state.routes = state.routes.filter(r => r.id !== routeId);
        });
    }

    // Clear selection and update UI
    state.selectedRouteId = null;
    updateUI();
    closeBatchParallelModal();
    alert(`Successfully generated ${routesCreatedCount} parallel routes!${deleteOriginal ? ' Original routes deleted.' : ''}`);
}
