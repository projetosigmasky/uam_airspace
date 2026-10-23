// UAM Airspace Dashboard: Parallel-route geometry (pure functions, no DOM access; tested in tests/core_tests.html).
// Classic script sharing one global scope with the others; load order is set in index.html.

// Route geometry used when generating parallel routes: pure functions without DOM access,
// so they can be tested on their own (tests/core_tests.html).
// Offset a route sideways by offsetMeters (positive: to the left of the direction of
// travel), keeping its first and last waypoints fixed. Interior waypoints move to the
// intersection of the two adjacent offset edges (miter); where those edges are collinear
// the waypoint moves perpendicular to them, so every input waypoint has one output
// waypoint with its own attributes. A two-waypoint route gets one extra point, the offset
// end of its edge, before the fixed end. Distances are meters in a local plane with the
// same meters-per-degree as the overlap analysis.
function offsetWaypointsHorizontally(waypoints, offsetMeters) {
    const n = waypoints.length;
    if (n < 2 || !offsetMeters) return waypoints.map(wp => ({ ...wp }));
    const lat0 = waypoints[0].lat, lon0 = waypoints[0].lon;
    const phi = (waypoints.reduce((sum, wp) => sum + wp.lat, 0) / n) * Math.PI / 180;
    const mLat = 111132.92 - 559.82 * Math.cos(2 * phi) + 1.175 * Math.cos(4 * phi);
    const mLon = 111412.84 * Math.cos(phi) - 93.5 * Math.cos(3 * phi);
    const pts = waypoints.map(wp => ({ x: (wp.lon - lon0) * mLon, y: (wp.lat - lat0) * mLat }));
    const toWaypoint = (wp, x, y) => ({ ...wp, lat: lat0 + y / mLat, lon: lon0 + x / mLon });
    const dirs = [];   // unit direction of each edge, null for a zero-length edge
    for (let i = 0; i < n - 1; i++) {
        const dx = pts[i + 1].x - pts[i].x, dy = pts[i + 1].y - pts[i].y;
        const len = Math.hypot(dx, dy);
        dirs.push(len > 1e-6 ? { x: dx / len, y: dy / len } : null);
    }
    const leftOf = d => ({ x: -d.y, y: d.x });

    if (n === 2) {
        if (!dirs[0]) return waypoints.map(wp => ({ ...wp }));
        const nl = leftOf(dirs[0]);
        const end = waypoints[1];
        return [{ ...waypoints[0] },
                toWaypoint({ ...end, name: `${end.name || 'WP 2'} offset`, type: 'Waypoint' },
                           pts[1].x + offsetMeters * nl.x, pts[1].y + offsetMeters * nl.y),
                { ...end }];
    }
    return waypoints.map((wp, i) => {
        if (i === 0 || i === n - 1) return { ...wp };
        let a = null, b = null;
        for (let k = i - 1; k >= 0 && !a; k--) a = dirs[k];
        for (let k = i; k < n - 1 && !b; k++) b = dirs[k];
        a = a || b; b = b || a;
        if (!a) return { ...wp };
        const na = leftOf(a), nb = leftOf(b);
        const c = 1 + a.x * b.x + a.y * b.y;   // 1 + cos(turn); 0 for a full reversal
        const m = c > 1e-6 ? { x: (na.x + nb.x) / c, y: (na.y + nb.y) / c } : na;
        return toWaypoint(wp, pts[i].x + offsetMeters * m.x, pts[i].y + offsetMeters * m.y);
    });
}
