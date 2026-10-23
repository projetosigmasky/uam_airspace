// UAM Airspace Dashboard: Volumetric overlap analysis engine (pure functions, no DOM access; tested in tests/core_tests.html).
// Classic script sharing one global scope with the others; load order is set in index.html.

// Volumetric overlap analysis: pure functions without DOM access, so it can be tested on its own.
// The plan is rasterized into square cells; in each cell covered by the checked layer, the
// altitude intervals of its segments are merged (lanes and routes that share a waypoint segment
// count once) and intersected with the merged intervals of each other layer.
const OverlapAnalysis = (() => {
    const FT = 0.3048;
    const NM = 1852;
    const TERMINAL_TYPES = new Set(['Vertiport', 'Airport']);
    const DEFAULTS = { cellSize: 50, parallelDeg: 30, heightFt: null, significantPct: 10 };
    // 0: a 1-m slab at the axis altitude over the full corridor width (an axis-altitude
    // footprint share, not the length of the centerline inside other volumes)
    const SWEEP_HEIGHTS_FT = [1000, 800, 600, 400, 200, 0];
    const SHARE_THRESHOLDS = [0.01, 0.10, 0.50];
    const ALL_LAYERS = 'All layers';
    const HASH = 1000;   // coarse spatial hash for the other layers (m)

    // Local equirectangular plane (meters) centered on the bounding box of the given routes
    function makeProjection(routes) {
        let minLat = Infinity, maxLat = -Infinity, minLon = Infinity, maxLon = -Infinity;
        routes.forEach(route => route.waypoints.forEach(wp => {
            minLat = Math.min(minLat, wp.lat); maxLat = Math.max(maxLat, wp.lat);
            minLon = Math.min(minLon, wp.lon); maxLon = Math.max(maxLon, wp.lon);
        }));
        const lat0 = (minLat + maxLat) / 2;
        const lon0 = (minLon + maxLon) / 2;
        const phi = lat0 * Math.PI / 180;
        const mLat = 111132.92 - 559.82 * Math.cos(2 * phi) + 1.175 * Math.cos(4 * phi);
        const mLon = 111412.84 * Math.cos(phi) - 93.5 * Math.cos(3 * phi);
        return {
            toXY: (lat, lon) => [(lon - lon0) * mLon, (lat - lat0) * mLat],
            toLatLon: (x, y) => [lat0 + y / mLat, lon0 + x / mLon]
        };
    }

    // Segment volumes as rendered: a box with the width and height of the start waypoint
    function buildSegments(route, projection) {
        const segments = [];
        const wps = route.waypoints;
        for (let i = 0; i < wps.length - 1; i++) {
            const a = wps[i], b = wps[i + 1];
            const [x0, y0] = projection.toXY(a.lat, a.lon);
            const [x1, y1] = projection.toXY(b.lat, b.lon);
            const dx = x1 - x0, dy = y1 - y0;
            const len = Math.hypot(dx, dy);
            if (len === 0) continue;
            const n0 = String(a.name ?? ''), n1 = String(b.name ?? '');
            segments.push({
                route: route.name || route.id,
                key: [n0, n1].sort().join(' – '),
                x0, y0, ux: dx / len, uy: dy / len, len,
                hw: (a.width > 0 ? a.width : 457) / 2,
                half: (a.height > 0 ? a.height : 305) / 2,
                a0: a.altitude > 0 ? a.altitude : 760,
                a1: b.altitude > 0 ? b.altitude : 760,
                terminal: TERMINAL_TYPES.has(a.type) || TERMINAL_TYPES.has(b.type)
            });
        }
        return segments;
    }

    function bbox(s) {
        const xs = [], ys = [];
        [0, 1].forEach(k => [-1, 1].forEach(m => {
            xs.push(s.x0 + s.len * s.ux * k + s.hw * s.uy * m);
            ys.push(s.y0 + s.len * s.uy * k - s.hw * s.ux * m);
        }));
        return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    }

    // Axis parameter t of the cell center if it lies inside the footprint of s, else -1
    function insideT(s, i, j, cell) {
        const cx = (i + 0.5) * cell - s.x0, cy = (j + 0.5) * cell - s.y0;
        const along = cx * s.ux + cy * s.uy;
        const across = -cx * s.uy + cy * s.ux;
        return (along >= 0 && along <= s.len && Math.abs(across) <= s.hw) ? along / s.len : -1;
    }

    const cellKey = (i, j) => (i + 1e6) * 2.1e6 + (j + 1e6);

    function union(ivs) {
        ivs.sort((p, q) => p[0] - q[0] || p[1] - q[1]);
        const out = [];
        for (const [lo, hi] of ivs) {
            if (out.length && lo <= out[out.length - 1][1]) {
                out[out.length - 1][1] = Math.max(out[out.length - 1][1], hi);
            } else {
                out.push([lo, hi]);
            }
        }
        return out;
    }

    function interLen(a, b) {
        let i = 0, j = 0, total = 0;
        while (i < a.length && j < b.length) {
            const lo = Math.max(a[i][0], b[j][0]), hi = Math.min(a[i][1], b[j][1]);
            if (hi > lo) total += hi - lo;
            if (a[i][1] < b[j][1]) i++; else j++;
        }
        return total;
    }

    const total = ivs => ivs.reduce((s, [lo, hi]) => s + hi - lo, 0);

    // Rasterize the checked layer and collect, per covered cell, the intervals of the other
    // layers. The result does not depend on the corridor height, so one preparation serves
    // every evaluation (stored heights, test height, height sweep).
    function prepare(subjectRoutes, obstacleLayers, options = {}) {
        const opts = { ...DEFAULTS, ...options };
        const cell = opts.cellSize;
        const projection = makeProjection(subjectRoutes);
        const subject = subjectRoutes.flatMap(route => buildSegments(route, projection));
        const keys = Array.from(new Set(subject.map(s => s.key))).sort();
        const keyIndex = new Map(keys.map((k, n) => [k, n]));
        const keyTerminal = new Map(subject.map(s => [s.key, s.terminal]));
        const keyRoutes = new Map();
        subject.forEach(s => {
            if (!keyRoutes.has(s.key)) keyRoutes.set(s.key, new Set());
            keyRoutes.get(s.key).add(s.route);
        });

        const cells = new Map();
        subject.forEach(s => {
            const [x0, y0, x1, y1] = bbox(s);
            const kid = keyIndex.get(s.key);
            for (let i = Math.floor(x0 / cell); i <= Math.floor(x1 / cell); i++) {
                for (let j = Math.floor(y0 / cell); j <= Math.floor(y1 / cell); j++) {
                    const t = insideT(s, i, j, cell);
                    if (t < 0) continue;
                    const alt = s.a0 + (s.a1 - s.a0) * t;
                    const ck = cellKey(i, j);
                    let c = cells.get(ck);
                    if (!c) {
                        c = { i, j, entries: new Map(), obs: [] };
                        cells.set(ck, c);
                    }
                    const dedupe = kid + '|' + alt.toFixed(1);
                    if (!c.entries.has(dedupe)) {
                        c.entries.set(dedupe, { alt, half: s.half, ux: s.ux, uy: s.uy, terminal: s.terminal, kid });
                    }
                }
            }
        });

        const obstacles = obstacleLayers.flatMap(layer =>
            layer.routes.flatMap(route => buildSegments(route, projection).map(s => ({ ...s, layer: layer.name }))));
        const hash = new Map();
        obstacles.forEach((o, idx) => {
            const [x0, y0, x1, y1] = bbox(o);
            for (let hx = Math.floor(x0 / HASH); hx <= Math.floor(x1 / HASH); hx++) {
                for (let hy = Math.floor(y0 / HASH); hy <= Math.floor(y1 / HASH); hy++) {
                    const hk = cellKey(hx, hy);
                    if (!hash.has(hk)) hash.set(hk, []);
                    hash.get(hk).push(idx);
                }
            }
        });
        cells.forEach(c => {
            const hk = cellKey(Math.floor((c.i + 0.5) * cell / HASH), Math.floor((c.j + 0.5) * cell / HASH));
            (hash.get(hk) || []).forEach(idx => {
                const o = obstacles[idx];
                const t = insideT(o, c.i, c.j, cell);
                if (t < 0) return;
                const alt = o.a0 + (o.a1 - o.a0) * t;
                c.obs.push({ layer: o.layer, lo: alt - o.half, hi: alt + o.half, ux: o.ux, uy: o.uy });
            });
        });

        return {
            cells, keys, keyTerminal, keyRoutes, projection, opts,
            layerNames: obstacleLayers.map(layer => layer.name)
        };
    }

    // Volumes for one corridor height: stored heights, or heightFt for every segment
    function evaluate(prep, heightFt = null, options = {}) {
        const opts = { ...prep.opts, ...options };
        const area = opts.cellSize * opts.cellSize;
        const cosParallel = Math.cos(opts.parallelDeg * Math.PI / 180);
        const fixedHalf = heightFt === null ? null : (heightFt > 0 ? heightFt * FT / 2 : 0.5);
        const layers = prep.layerNames.concat([ALL_LAYERS]);
        const volume = { cruise: 0, approach: 0 };
        const overlap = { cruise: {}, approach: {} };
        const parallel = {};
        layers.forEach(L => { overlap.cruise[L] = 0; overlap.approach[L] = 0; parallel[L] = 0; });
        const nk = prep.keys.length;
        const kVol = new Float64Array(nk), kOv = new Float64Array(nk), kPar = new Float64Array(nk);
        const kX = new Float64Array(nk), kY = new Float64Array(nk);
        const kLayer = prep.layerNames.map(() => new Float64Array(nk));

        prep.cells.forEach(c => {
            const byLayer = new Map();
            c.obs.forEach(o => {
                if (!byLayer.has(o.layer)) byLayer.set(o.layer, []);
                byLayer.get(o.layer).push([o.lo, o.hi]);
            });
            const O = new Map(Array.from(byLayer, ([L, ivs]) => [L, union(ivs)]));
            const Oall = union(c.obs.map(o => [o.lo, o.hi]));
            const cx = (c.i + 0.5) * opts.cellSize, cy = (c.j + 0.5) * opts.cellSize;

            for (const group of ['cruise', 'approach']) {
                const ents = Array.from(c.entries.values()).filter(e => e.terminal === (group === 'approach'));
                if (!ents.length) continue;
                const ivs = ents.map(e => {
                    const h = fixedHalf === null ? e.half : fixedHalf;
                    return [e.alt - h, e.alt + h];
                });
                const U = union(ivs.map(iv => iv.slice()));
                volume[group] += total(U) * area;
                if (c.obs.length) {
                    O.forEach((OL, L) => { overlap[group][L] += interLen(U, OL) * area; });
                    overlap[group][ALL_LAYERS] += interLen(U, Oall) * area;
                }

                // parallel part: the overlap lying inside at least one segment-obstacle pair
                // within parallelDeg of each other; the rest is crossing. Pairs are intersected
                // interval by interval, so a cell with both kinds splits its overlap.
                if (group === 'cruise' && c.obs.length) {
                    const parByLayer = new Map();
                    const parAll = [];
                    ents.forEach((e, n) => c.obs.forEach(o => {
                        const lo = Math.max(ivs[n][0], o.lo), hi = Math.min(ivs[n][1], o.hi);
                        if (hi > lo && Math.abs(e.ux * o.ux + e.uy * o.uy) >= cosParallel) {
                            if (!parByLayer.has(o.layer)) parByLayer.set(o.layer, []);
                            parByLayer.get(o.layer).push([lo, hi]);
                            parAll.push([lo, hi]);
                        }
                    }));
                    parByLayer.forEach((pivs, L) => { parallel[L] += total(union(pivs)) * area; });
                    if (parAll.length) parallel[ALL_LAYERS] += total(union(parAll)) * area;
                }

                // per segment (both lanes and all routes that share it)
                const kids = Array.from(new Set(ents.map(e => e.kid)));
                kids.forEach(kid => {
                    const own = [], ownPar = [];
                    ents.forEach((e, n) => {
                        if (e.kid !== kid) return;
                        own.push(ivs[n].slice());
                        ownPar.push([e, ivs[n]]);
                    });
                    const Uk = union(own);
                    kVol[kid] += total(Uk) * area;
                    if (!c.obs.length) return;
                    const ov = interLen(Uk, Oall) * area;
                    kOv[kid] += ov;
                    kX[kid] += ov * cx;
                    kY[kid] += ov * cy;
                    prep.layerNames.forEach((L, li) => {
                        if (O.has(L)) kLayer[li][kid] += interLen(Uk, O.get(L)) * area;
                    });
                    const kp = [];
                    ownPar.forEach(([e, iv]) => c.obs.forEach(o => {
                        const lo = Math.max(iv[0], o.lo), hi = Math.min(iv[1], o.hi);
                        if (hi > lo && Math.abs(e.ux * o.ux + e.uy * o.uy) >= cosParallel) kp.push([lo, hi]);
                    }));
                    if (kp.length) kPar[kid] += total(union(kp)) * area;
                });
            }
        });

        const segments = prep.keys.map((key, kid) => {
            const [lat, lon] = kOv[kid] > 0 ? prep.projection.toLatLon(kX[kid] / kOv[kid], kY[kid] / kOv[kid]) : [null, null];
            return {
                key, approach: prep.keyTerminal.get(key), routes: prep.keyRoutes.get(key).size,
                volume: kVol[kid], overlap: kOv[kid], share: kVol[kid] ? kOv[kid] / kVol[kid] : 0,
                parallelShare: kOv[kid] ? kPar[kid] / kOv[kid] : 0,
                byLayer: Object.fromEntries(prep.layerNames.map((L, li) => [L, kLayer[li][kid]])),
                lat, lon
            };
        });
        const cruise = segments.filter(s => !s.approach);
        const significant = opts.significantPct / 100;
        const rows = layers.map((L, li) => {
            const shares = cruise.map(s => (L === ALL_LAYERS ? s.share : (s.volume ? s.byLayer[L] / s.volume : 0)));
            const ov = overlap.cruise[L];
            return {
                layer: L,
                overlap: ov,
                pct: volume.cruise ? 100 * ov / volume.cruise : 0,
                parallelPct: ov ? 100 * parallel[L] / ov : 0,
                segmentsAny: shares.filter(v => v > 0).length,
                segmentsAtLeast: SHARE_THRESHOLDS.map(t => shares.filter(v => v >= t).length),
                significant: shares.filter(v => v >= significant).length
            };
        });
        return {
            heightFt, volume: volume.cruise, approachVolume: volume.approach,
            approachPct: volume.approach ? 100 * overlap.approach[ALL_LAYERS] / volume.approach : 0,
            nCruise: cruise.length, nApproach: segments.length - cruise.length,
            rows, segments: segments.sort((p, q) => q.overlap - p.overlap), opts
        };
    }

    function analyze(subjectRoutes, obstacleLayers, options = {}) {
        const prep = prepare(subjectRoutes, obstacleLayers, options);
        const main = evaluate(prep, prep.opts.heightFt);
        main.sweep = SWEEP_HEIGHTS_FT.map(h => {
            const r = evaluate(prep, h);
            const all = r.rows[r.rows.length - 1];
            return { heightFt: h, pct: all.pct, significant: all.significant };
        });
        main.cellCount = prep.cells.size;
        return main;
    }

    return { analyze, prepare, evaluate, FT, NM, DEFAULTS, SHARE_THRESHOLDS, ALL_LAYERS };
})();
