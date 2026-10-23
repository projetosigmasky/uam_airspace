// UAM Airspace Dashboard: 3D view (Three.js): reference plane, camera, grid and scene rendering.
// Classic script sharing one global scope with the others; load order is set in index.html.

// Create a dark reference surface texture for the 3D plane
function createMapTexture() {
    const canvas = document.createElement('canvas');
    const size = 256;
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');

    const gradient = ctx.createRadialGradient(
        size * 0.5,
        size * 0.5,
        size * 0.1,
        size * 0.5,
        size * 0.5,
        size * 0.75
    );
    gradient.addColorStop(0, '#1b2835');
    gradient.addColorStop(1, '#141d27');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);

    return new THREE.CanvasTexture(canvas);
}

// Calculate bounding box of all routes and vertiports
function calculateSceneBounds() {
    let minX = Infinity, maxX = -Infinity;
    let minZ = Infinity, maxZ = -Infinity;
    let maxY = 0;

    // Check vertiports
    state.vertiports.forEach((vertiport) => {
        const pos = latLonToXYZ(vertiport.lat, vertiport.lon, 0);
        const padding = vertiport.radius + 500;
        minX = Math.min(minX, pos.x - padding);
        maxX = Math.max(maxX, pos.x + padding);
        minZ = Math.min(minZ, pos.z - padding);
        maxZ = Math.max(maxZ, pos.z + padding);
        maxY = Math.max(maxY, vertiport.height || 0);
    });

    // Check routes
    state.routes.forEach(route => {
        route.waypoints.forEach(wp => {
            const pos = latLonToXYZ(wp.lat, wp.lon, 0);
            const padding = 500;
            minX = Math.min(minX, pos.x - padding);
            maxX = Math.max(maxX, pos.x + padding);
            minZ = Math.min(minZ, pos.z - padding);
            maxZ = Math.max(maxZ, pos.z + padding);
            maxY = Math.max(maxY, (wp.altitude || 0) + (wp.height || 0));
        });
    });

    // If no routes or vertiports, use default bounds
    if (!isFinite(minX)) {
        minX = -10000;
        maxX = 10000;
        minZ = -10000;
        maxZ = 10000;
    }

    const width = maxX - minX;
    const height = maxZ - minZ;
    const centerX = (minX + maxX) / 2;
    const centerZ = (minZ + maxZ) / 2;
    const diagonal = Math.sqrt(width * width + height * height + maxY * maxY);

    return { width, height, centerX, centerZ, minX, maxX, minZ, maxZ, maxY, diagonal };
}

function getMaxCameraDistance() {
    const bounds = calculateSceneBounds();
    return Math.max(DEFAULT_MAX_CAMERA_DISTANCE, bounds.diagonal * 3);
}

function updateCameraClipping() {
    if (!camera) return;
    const maxDistance = getMaxCameraDistance();
    camera.far = Math.max(DEFAULT_CAMERA_FAR, maxDistance * 2);
    camera.updateProjectionMatrix();
}

function fitCameraToScene() {
    if (!camera || !cameraTarget) return;
    const bounds = calculateSceneBounds();
    const maxDistance = getMaxCameraDistance();
    const fitDistance = Math.max(MIN_CAMERA_DISTANCE, Math.min(maxDistance, bounds.diagonal * 1.25));

    cameraTarget.set(bounds.centerX, 0, bounds.centerZ);
    cameraDistance = fitDistance;
    cameraYaw = Math.PI / 4;
    cameraPitch = Math.PI / 3;
    updateCameraClipping();
}

// Create map ground plane with dynamic size
function createMapPlane() {
    const bounds = calculateSceneBounds();
    const size = Math.max(bounds.width, bounds.height) * 2.0; // Add 100% padding to prevent disappearing at zoom

    const texture = createMapTexture();
    const geometry = new THREE.PlaneGeometry(size, size);
    const material = new THREE.MeshLambertMaterial({ 
        map: texture,
        color: 0xffffff,
        emissive: 0x070b10,
        side: THREE.DoubleSide
    });
    const plane = new THREE.Mesh(geometry, material);
    plane.rotation.x = -Math.PI / 2;
    plane.position.set(bounds.centerX, 0, bounds.centerZ);
    plane.userData.isMap = true;
    plane.userData.bounds = bounds;
    return plane;
}

// Update map plane size dynamically
function updateMapPlane() {
    const mapPlane = scene.children.find(child => child.userData && child.userData.isMap);
    if (!mapPlane) return;

    const bounds = calculateSceneBounds();
    const size = Math.max(bounds.width, bounds.height) * 2.0;

    mapPlane.geometry.dispose();
    mapPlane.geometry = new THREE.PlaneGeometry(size, size);
    mapPlane.position.set(bounds.centerX, 0, bounds.centerZ);
    mapPlane.userData.bounds = bounds;
    updateCameraClipping();

    // Update grid to match the new plane size
    updateGrid();
}

// Initialize Three.js with map plane
function initThreeJS() {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0c1218);

    camera = new THREE.PerspectiveCamera(
        60,
        canvasElement.clientWidth / canvasElement.clientHeight,
        1,
        DEFAULT_CAMERA_FAR
    );
    camera.position.set(5000, 3000, 5000);
    camera.lookAt(0, 0, 0);

    // Initialize camera spherical coordinates from starting position
    cameraTarget = new THREE.Vector3(0, 0, 0);
    const initialDist = camera.position.length();
    cameraDistance = initialDist;
    cameraYaw = Math.atan2(camera.position.x, camera.position.z);
    cameraPitch = Math.acos(camera.position.y / initialDist);

    // WebGL renderer for 3D objects
    renderer = new THREE.WebGLRenderer({ canvas: canvasElement, antialias: true, alpha: true });
    renderer.setSize(canvasElement.clientWidth, canvasElement.clientHeight);
    renderer.setClearColor(0x0c1218, 1);

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1000, 2000, 1000);
    scene.add(directionalLight);

    // Create the map ground plane
    const mapPlane = createMapPlane();
    scene.add(mapPlane);

    // Grid
    updateGrid();
    updateGrid();

    // Camera controls
    let isDragging = false;
    let previousMousePosition = { x: 0, y: 0 };
    const keyState = {
        ArrowUp: false,
        ArrowDown: false,
        ArrowLeft: false,
        ArrowRight: false
    };

    // Keyboard controls for camera panning
    document.addEventListener('keydown', (e) => {
        if (e.key in keyState) {
            keyState[e.key] = true;
        }
    });

    document.addEventListener('keyup', (e) => {
        if (e.key in keyState) {
            keyState[e.key] = false;
        }
    });

    canvasElement.addEventListener('mousedown', (e) => {
        isDragging = true;
        previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    canvasElement.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const deltaX = e.clientX - previousMousePosition.x;
        const deltaY = e.clientY - previousMousePosition.y;

        if (e.shiftKey) {
            // Shift+drag = pan camera and target together
            const forward = new THREE.Vector3();
            const right = new THREE.Vector3();
            camera.getWorldDirection(forward);
            forward.y = 0;
            forward.normalize();
            right.crossVectors(new THREE.Vector3(0, 1, 0), forward).normalize();

            cameraTarget.addScaledVector(right, -deltaX * 5);
            cameraTarget.addScaledVector(forward, deltaY * 5);
        } else {
            // Normal drag = rotate around target point
            cameraYaw -= deltaX * 0.01;
            cameraPitch = Math.max(0.1, Math.min(Math.PI - 0.1, cameraPitch - deltaY * 0.01));
        }

        previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    canvasElement.addEventListener('mouseup', () => {
        isDragging = false;
    });

    canvasElement.addEventListener('wheel', (e) => {
        e.preventDefault();
        // Adjust distance from target for zoom
        const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
        cameraDistance = Math.max(MIN_CAMERA_DISTANCE, Math.min(getMaxCameraDistance(), cameraDistance * zoomFactor));
        updateCameraClipping();
    });

    window.addEventListener('resize', () => {
        camera.aspect = canvasElement.clientWidth / canvasElement.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(canvasElement.clientWidth, canvasElement.clientHeight);
    });

    // Animation loop
    function animate() {
        // Handle keyboard arrow key panning - moves camera and target together
        const isArrowPressed = keyState.ArrowUp || keyState.ArrowDown || keyState.ArrowLeft || keyState.ArrowRight;

        if (!isDragging && isArrowPressed) {
            const panSpeed = 100;
            const forward = new THREE.Vector3();
            const right = new THREE.Vector3();

            camera.getWorldDirection(forward);
            forward.y = 0;
            forward.normalize();
            right.crossVectors(new THREE.Vector3(0, 1, 0), forward).normalize();

            if (keyState.ArrowUp) {
                camera.position.addScaledVector(forward, panSpeed);
                cameraTarget.addScaledVector(forward, panSpeed);
            }
            if (keyState.ArrowDown) {
                camera.position.addScaledVector(forward, -panSpeed);
                cameraTarget.addScaledVector(forward, -panSpeed);
            }
            if (keyState.ArrowLeft) {
                camera.position.addScaledVector(right, panSpeed);
                cameraTarget.addScaledVector(right, panSpeed);
            }
            if (keyState.ArrowRight) {
                camera.position.addScaledVector(right, -panSpeed);
                cameraTarget.addScaledVector(right, -panSpeed);
            }

            // Keep spherical coords in sync with camera position when panning
            const relativePos = new THREE.Vector3(
                camera.position.x - cameraTarget.x,
                camera.position.y - cameraTarget.y,
                camera.position.z - cameraTarget.z
            );
            cameraDistance = relativePos.length();
            cameraYaw = Math.atan2(relativePos.x, relativePos.z);
            cameraPitch = Math.acos(Math.max(-1, Math.min(1, relativePos.y / cameraDistance)));
        } else if (isDragging) {
            // Update camera position based on yaw/pitch around target when dragging
            camera.position.x = cameraTarget.x + cameraDistance * Math.sin(cameraYaw) * Math.sin(cameraPitch);
            camera.position.z = cameraTarget.z + cameraDistance * Math.cos(cameraYaw) * Math.sin(cameraPitch);
            camera.position.y = Math.max(100, cameraTarget.y + cameraDistance * Math.cos(cameraPitch));
        } else {
            // Not dragging and no arrows pressed - just update position from spherical coords (for zoom to work)
            camera.position.x = cameraTarget.x + cameraDistance * Math.sin(cameraYaw) * Math.sin(cameraPitch);
            camera.position.z = cameraTarget.z + cameraDistance * Math.cos(cameraYaw) * Math.sin(cameraPitch);
            camera.position.y = Math.max(100, cameraTarget.y + cameraDistance * Math.cos(cameraPitch));
        }

        camera.lookAt(cameraTarget);

        requestAnimationFrame(animate);
        renderer.render(scene, camera);
    }
    animate();
}

// Update grid visibility and size
function updateGrid() {
    if (gridHelper) scene.remove(gridHelper);
    if (state.showGrid) {
        const bounds = calculateSceneBounds();
        const size = Math.max(bounds.width, bounds.height) * 2.0;
        const divisions = Math.ceil(size / state.gridCellSize);

        gridHelper = new THREE.GridHelper(size, divisions, 0x7a869b, 0x3f4a5a);
        gridHelper.position.set(bounds.centerX, 0, bounds.centerZ);
        scene.add(gridHelper);
    }
}

// Convert lat/lon to 3D coordinates
function latLonToXYZ(lat, lon, alt = 0) {
    const centerLat = -23.55;
    const centerLon = -46.63;
    const scale = 100000;

    const x = (lon - centerLon) * scale * Math.cos(centerLat * Math.PI / 180);
    const z = -(lat - centerLat) * scale;
    const y = alt;

    return { x, y, z };
}

// Render all routes and vertiports
// Track renderScene calls for debugging
let renderSceneCallCount = 0;

function renderScene() {
    // Clear previous route objects - properly dispose geometries and materials
    const objectsToRemove = scene.children.filter(
        child => child.userData && (child.userData.isRoute || child.userData.isVertiport)
    );
    objectsToRemove.forEach(obj => {
        scene.remove(obj);
        // Dispose of geometry and material to prevent memory leaks
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
            if (Array.isArray(obj.material)) {
                obj.material.forEach(mat => {
                    if (mat.map) mat.map.dispose();
                    mat.dispose();
                });
            } else {
                if (obj.material.map) obj.material.map.dispose();
                obj.material.dispose();
            }
        }
    });

    // Render vertiports
    state.vertiports.forEach((vertiport, name) => {
        if (!vertiport.visible) return;
        const pos = latLonToXYZ(vertiport.lat, vertiport.lon, 0);
        const vertiportColor = getVertiportColor(vertiport);

        // Cylinder for vertiport zone
        const geometry = new THREE.CylinderGeometry(
            vertiport.radius,
            vertiport.radius,
            vertiport.height,
            32
        );
        const material = new THREE.MeshLambertMaterial({
            color: vertiportColor,
            transparent: true,
            opacity: 0.3
        });
        const cylinder = new THREE.Mesh(geometry, material);
        cylinder.position.set(pos.x, vertiport.height / 2, pos.z);
        cylinder.userData.isVertiport = true;
        scene.add(cylinder);

        // Label
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 256;
        canvas.height = 64;
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, 256, 64);
        ctx.fillStyle = '#000000';
        ctx.font = 'bold 24px Arial';
        ctx.fillText(name, 10, 40);

        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
        const sprite = new THREE.Sprite(spriteMaterial);
        sprite.position.set(pos.x, vertiport.height + 50, pos.z);
        sprite.scale.set(200, 50, 1);
        sprite.userData.isVertiport = true;
        scene.add(sprite);
    });

    // Render routes
    state.routes.forEach(route => {
        if (!route.visible) return;

        const points = route.waypoints.map((wp, idx) => {
            // Use the altitude from CSV, or 760m as default if not provided
            const altitude = wp.altitude || 760;
            const pos = latLonToXYZ(wp.lat, wp.lon, altitude);
            return new THREE.Vector3(pos.x, pos.y, pos.z);
        });

        // Centerline
        const lineGeometry = new THREE.BufferGeometry().setFromPoints(points);
        const lineMaterial = new THREE.LineBasicMaterial({
            color: route.color,
            linewidth: 2
        });
        const line = new THREE.Line(lineGeometry, lineMaterial);
        line.userData.isRoute = true;
        scene.add(line);

        // Corridor tubes
        for (let i = 0; i < points.length - 1; i++) {
            const start = points[i];
            const end = points[i + 1];
            const direction = new THREE.Vector3().subVectors(end, start);
            const length = direction.length();
            if (length === 0) continue; // Skip if points are identical

            const center = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);

            // Use width and height from the start waypoint of this segment
            const startWaypoint = route.waypoints[i];
            const segmentWidth = (startWaypoint && startWaypoint.width) ? startWaypoint.width : 457;
            const segmentHeight = (startWaypoint && startWaypoint.height) ? startWaypoint.height : 305;

            // Skip rendering if both dimensions are 0 or negative
            if (segmentWidth <= 0 || segmentHeight <= 0) continue;

            const boxGeometry = new THREE.BoxGeometry(
                segmentWidth,
                segmentHeight,
                length
            );
                const boxMaterial = new THREE.MeshLambertMaterial({
                    color: route.color,
                    transparent: true,
                    opacity: state.solidVolumes ? 0.8 : 0.2,
                    side: THREE.DoubleSide
                });
                const box = new THREE.Mesh(boxGeometry, boxMaterial);

                box.position.copy(center);

                // Properly align box along the path using lookAt-like rotation
                const normalizedDir = direction.normalize();
                const upVector = new THREE.Vector3(0, 1, 0);
                if (Math.abs(normalizedDir.dot(upVector)) > 0.99) {
                    upVector.set(0, 0, 1);
                }
                const rightVector = new THREE.Vector3().crossVectors(upVector, normalizedDir).normalize();
                const trueUp = new THREE.Vector3().crossVectors(normalizedDir, rightVector);

                const rotMatrix = new THREE.Matrix4();
                rotMatrix.makeBasis(rightVector, trueUp, normalizedDir);
                box.setRotationFromMatrix(rotMatrix);
                box.userData.isRoute = true;
                scene.add(box);

                // Wireframe
                const edges = new THREE.EdgesGeometry(boxGeometry);
                const lineMat = new THREE.LineBasicMaterial({ color: route.color });
                const wireframe = new THREE.LineSegments(edges, lineMat);
                wireframe.position.copy(box.position);
                wireframe.setRotationFromMatrix(rotMatrix);
                wireframe.userData.isRoute = true;
                scene.add(wireframe);
            }

        // Waypoint markers - using points array like the working version
        if (state.showNodes) {
            points.forEach((point, idx) => {
                const wp = route.waypoints[idx];
                if (!wp) return;

                const sphereGeometry = new THREE.SphereGeometry(20, 16, 16);
                const sphereMaterial = new THREE.MeshLambertMaterial({ color: 0xffff00 });
                const sphere = new THREE.Mesh(sphereGeometry, sphereMaterial);
                sphere.position.copy(point);
                sphere.userData.isRoute = true;
                scene.add(sphere);

                // Add waypoint name label (optional - BKP 4 doesn't have this, but keeping for UX)
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                canvas.width = 256;
                canvas.height = 64;
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, 256, 64);
                ctx.fillStyle = '#000000';
                ctx.font = 'bold 18px Arial';
                ctx.fillText(`${wp.name}`, 10, 35);
                ctx.font = '12px Arial';
                // Display altitude from CSV, or 760m as default if not provided
                const displayAltitude = wp.altitude || 760;
                ctx.fillText(`Alt: ${Math.round(displayAltitude)}m`, 10, 50);

                const texture = new THREE.CanvasTexture(canvas);
                const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
                const sprite = new THREE.Sprite(spriteMaterial);
                sprite.position.copy(point);
                sprite.position.y += 100;
                sprite.scale.set(150, 40, 1);
                sprite.userData.isRoute = true;
                scene.add(sprite);
            });
        }

    });
}
