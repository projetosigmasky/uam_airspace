// UAM Airspace Dashboard: Application state and the shared handles of the 3D scene and the 2D map.
// Classic script sharing one global scope with the others; load order is set in index.html.

// State management
const state = {
    routes: [],
    selectedRouteId: null,
    vertiports: new Map(),
    selectedVertiportName: null,
    showGrid: true,
    gridCellSize: 500, // Grid cell size in meters
    currentView: '3d',
    unit: 'meters', // 'meters' or 'feet'
    editingFieldId: null, // Track which input field is currently being edited
    draggedWaypointIndex: null, // Track dragged waypoint for reordering
    solidVolumes: false, // Toggle between transparent (0.2) and solid (0.8) corridor volumes
    showVolumeProjection: false, // Show volume projections in 2D map instead of centerlines
    showNodes: true, // Show/hide waypoint nodes
    trajectories: [], // Array of loaded trajectories for 2D map display
    fileLayers: [], // File-level groups for batch color and visibility controls
    allRoutesVisible: true, // Track if all routes are currently visible
    allVertiportsVisible: true // Track if all vertiports are currently visible
};

// Three.js variables
let scene, camera, renderer, cssRenderer, gridHelper;
let cameraTarget, cameraDistance, cameraYaw, cameraPitch;
const canvasElement = document.getElementById('canvas');
const MIN_CAMERA_DISTANCE = 500;
const DEFAULT_MAX_CAMERA_DISTANCE = 100000;
const DEFAULT_CAMERA_FAR = 500000;

// Leaflet map variable
let map2D = null;
const mapElement = document.getElementById('map');
