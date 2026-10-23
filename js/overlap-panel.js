// UAM Airspace Dashboard: Batch Operations > Overlap Analysis: options, results, map markers and CSV export.
// Classic script sharing one global scope with the others; load order is set in index.html.

// Overlap analysis (UI). The geometry is in js/overlap-analysis.js; results are a
// snapshot of the loaded routes at the time of the run.
let overlapState = { summary: null, subjectName: '', elapsed: 0, showMarkers: false };

function overlapRouteLayers() {
    return state.fileLayers.filter(layer => layer.type === 'routes' && state.routes.some(r => r.layerId === layer.id));
}

function layerNameById(layerId) {
    const layer = state.fileLayers.find(item => item.id === layerId);
    return layer ? layer.name : layerId;
}

function openOverlapModal() {
    const layers = overlapRouteLayers();
    if (layers.length < 2) {
        alert('Load at least two route files: the corridors to check and the airspace structures to check them against.');
        return;
    }
    const subjectSelect = document.getElementById('ovSubject');
    const previous = subjectSelect.value;
    subjectSelect.innerHTML = layers.map(layer => `<option value="${layer.id}">${escapeHtml(layer.name)}</option>`).join('');
    if (layers.some(layer => layer.id === previous)) subjectSelect.value = previous;
    renderOverlapObstacleChoices();
    document.getElementById('overlapModal').classList.add('active');
}

function closeOverlapModal() {
    document.getElementById('overlapModal').classList.remove('active');
}

function renderOverlapObstacleChoices() {
    const subjectId = document.getElementById('ovSubject').value;
    document.getElementById('ovObstacles').innerHTML = overlapRouteLayers()
        .filter(layer => layer.id !== subjectId)
        .map(layer => `
            <label class="checkbox-group">
                <input type="checkbox" value="${layer.id}" checked>
                <span>${escapeHtml(layer.name)}</span>
            </label>`).join('');
}

function readOverlapOptions() {
    const numberOr = (id, fallback, min, max) => {
        const value = parseFloat(document.getElementById(id).value);
        return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
    };
    const height = parseFloat(document.getElementById('ovHeight').value);
    const D = OverlapAnalysis.DEFAULTS;
    return {
        cellSize: numberOr('ovCell', D.cellSize, 10, 500),
        significantPct: numberOr('ovSignificant', D.significantPct, 0, 100),
        parallelDeg: numberOr('ovAngle', D.parallelDeg, 0, 90),
        heightFt: Number.isFinite(height) && height > 0 ? height : null
    };
}

function runOverlapAnalysis() {
    const subjectId = document.getElementById('ovSubject').value;
    const obstacleIds = Array.from(document.querySelectorAll('#ovObstacles input:checked')).map(input => input.value);
    if (!obstacleIds.length) {
        alert('Select at least one layer to check against.');
        return;
    }
    const obstacleLayers = obstacleIds.map(id => ({
        name: layerNameById(id),
        routes: state.routes.filter(route => route.layerId === id)
    }));
    const started = performance.now();
    const summary = OverlapAnalysis.analyze(state.routes.filter(route => route.layerId === subjectId), obstacleLayers, readOverlapOptions());
    overlapState = { ...overlapState, summary, subjectName: layerNameById(subjectId), elapsed: performance.now() - started };
    renderOverlapResults();
    updateOverlapStatistics();
    if (map2D) updateMap();
}

const KM3 = 1e9;
const fmtPct = v => (v >= 10 ? v.toFixed(1) : v.toFixed(2)) + '%';

function shareClass(share, significant) {
    if (share >= 0.5) return 'high';
    if (share >= significant) return 'medium';
    return 'low';
}

function renderOverlapResults() {
    const s = overlapState.summary;
    const container = document.getElementById('ovResults');
    if (!s) {
        container.innerHTML = '';
        document.getElementById('ovExportBtn').disabled = true;
        return;
    }
    const sig = s.opts.significantPct;
    const total = s.rows[s.rows.length - 1];
    const heightText = s.opts.heightFt ? `${s.opts.heightFt} ft for every segment (test value)` : 'stored heights';
    const layerRows = s.rows.map(row => `
        <tr class="${row.layer === OverlapAnalysis.ALL_LAYERS ? 'ov-total' : ''}">
            <td>${escapeHtml(row.layer)}</td>
            <td>${(row.overlap / KM3).toFixed(2)}</td>
            <td>${fmtPct(row.pct)}</td>
            <td>${row.overlap > 0 ? row.parallelPct.toFixed(0) + '%' : '–'}</td>
            <td>${row.segmentsAny}</td>
            ${row.segmentsAtLeast.map(n => `<td>${n}</td>`).join('')}
        </tr>`).join('');
    const top = s.segments.filter(seg => !seg.approach && seg.overlap > 0).slice(0, 5).map(seg => `
        <tr>
            <td>${escapeHtml(seg.key)}</td>
            <td>${(seg.overlap / KM3).toFixed(3)}</td>
            <td>${(100 * seg.share).toFixed(0)}%</td>
            <td>${escapeHtml(Object.entries(seg.byLayer).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([L]) => L).join(', '))}</td>
        </tr>`).join('');
    const sweepLabel = h => (h === 0 ? 'axis altitude (1-m slab)' : h);
    const axis = s.sweep.find(x => x.heightFt === 0);

    container.innerHTML = `
        <p class="ov-note"><strong>${escapeHtml(overlapState.subjectName)}</strong>: ${s.nCruise} cruise and ${s.nApproach} approach segments; cruise corridor volume ${(s.volume / KM3).toFixed(1)} km³; corridor height: ${heightText}; ${s.cellCount.toLocaleString()} cells of ${s.opts.cellSize} m (${Math.round(overlapState.elapsed)} ms).</p>
        <table class="ov-table">
            <thead><tr>
                <th>Layer</th><th>Overlap (km³)</th><th>% of corridor volume</th><th>Parallel (% of overlap)</th>
                <th>Segments with any overlap</th>${OverlapAnalysis.SHARE_THRESHOLDS.map(t => `<th>Segments ≥ ${t * 100}%</th>`).join('')}
            </tr></thead>
            <tbody>${layerRows}</tbody>
        </table>
        <p class="ov-note">Segment columns count cruise segments by the share of their own volume that lies inside the layer. The parallel part is the overlap lying inside segment–obstacle pairs within ${s.opts.parallelDeg}° of each other; the rest is crossing. Approach segments: ${fmtPct(s.approachPct)} of their volume overlaps.</p>
        <table class="ov-table">
            <thead><tr><th>Corridor height (ft)</th>${s.sweep.map(x => `<th>${sweepLabel(x.heightFt)}</th>`).join('')}</tr></thead>
            <tbody>
                <tr><td>% of corridor volume overlapping</td>${s.sweep.map(x => `<td>${fmtPct(x.pct)}</td>`).join('')}</tr>
                <tr><td>Segments ≥ ${sig}% of their volume</td>${s.sweep.map(x => `<td>${x.significant}</td>`).join('')}</tr>
            </tbody>
        </table>
        <p class="ov-note">${axis ? `At the axis altitude, ${fmtPct(axis.pct)} of the corridor footprint (a 1-m slab over the full corridor width) lies inside other volumes; reducing the corridor height cannot remove that part. This is an area share, not the length of the centerline inside other volumes.` : ''}</p>
        ${top ? `<table class="ov-table">
            <thead><tr><th>Largest overlaps (cruise)</th><th>km³</th><th>Share</th><th>Layers</th></tr></thead>
            <tbody>${top}</tbody>
        </table>` : ''}
        <p class="ov-note">Map markers, one per segment with at least ${sig}% of its volume overlapping, at the center of the overlap:<span class="ov-marker ov-legend parallel medium"></span>mostly parallel<span class="ov-marker ov-legend crossing medium"></span>mostly crossing<span class="ov-marker ov-legend approach medium"></span>approach segment; amber: ${sig}–50%, red: ≥ 50% of the segment volume.</p>`;
    document.getElementById('ovExportBtn').disabled = false;
}

function updateOverlapStatistics() {
    const el = document.getElementById('statOverlaps');
    const s = overlapState.summary;
    if (!s) {
        el.style.display = 'none';
        return;
    }
    const total = s.rows[s.rows.length - 1];
    el.textContent = `Overlap: ${fmtPct(total.pct)} of corridor volume (${total.significant} of ${s.nCruise} segments ≥ ${s.opts.significantPct}%)`;
    el.style.display = 'block';
}

function drawOverlapMarkers() {
    if (!map2D || !map2D.overlapMarkers) return;
    map2D.overlapMarkers.clearLayers();
    const s = overlapState.summary;
    if (!overlapState.showMarkers || !s) return;
    const significant = s.opts.significantPct / 100;
    s.segments.filter(seg => seg.overlap > 0 && seg.share >= significant && seg.lat !== null).forEach(seg => {
        const shape = seg.approach ? 'approach' : (seg.parallelShare >= 0.5 ? 'parallel' : 'crossing');
        const icon = L.divIcon({
            className: 'ov-marker-icon',
            html: `<div class="ov-marker ${shape} ${shareClass(seg.share, significant)}"></div>`,
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });
        const layers = Object.entries(seg.byLayer).filter(([, v]) => v > 0)
            .map(([L, v]) => `${escapeHtml(L)}: ${(v / KM3).toFixed(3)} km³`).join('<br>');
        L.marker([seg.lat, seg.lon], { icon, pane: 'overlapPane', keyboard: false })
            .bindPopup(`<b>${escapeHtml(seg.key)}</b>${seg.approach ? ' (approach)' : ''}<br>${(100 * seg.share).toFixed(1)}% of its volume overlaps (${(seg.overlap / KM3).toFixed(3)} of ${(seg.volume / KM3).toFixed(3)} km³), ${(100 * seg.parallelShare).toFixed(0)}% parallel<br>${layers}`)
            .addTo(map2D.overlapMarkers);
    });
}

function exportOverlapCSV() {
    const s = overlapState.summary;
    if (!s) return;
    const quote = v => `"${String(v).replace(/"/g, '""')}"`;
    const layerNames = s.rows.slice(0, -1).map(row => row.layer);
    const header = ['segment', 'segment_type', 'routes', 'volume_km3', 'overlap_km3', 'overlap_share', 'parallel_share']
        .concat(layerNames.map(L => quote(`overlap_km3_${L}`)), ['lat', 'lon']).join(',');
    const lines = s.segments.map(seg => [
        quote(seg.key), seg.approach ? 'approach' : 'cruise', seg.routes,
        (seg.volume / KM3).toFixed(5), (seg.overlap / KM3).toFixed(5), seg.share.toFixed(4), seg.parallelShare.toFixed(4)
    ].concat(layerNames.map(L => (seg.byLayer[L] / KM3).toFixed(5)),
        [seg.lat === null ? '' : seg.lat.toFixed(6), seg.lon === null ? '' : seg.lon.toFixed(6)]).join(','));
    const blob = new Blob([[header].concat(lines).join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'uam_overlap_segments.csv';
    a.click();
    URL.revokeObjectURL(url);
}

function resetOverlapAnalysis() {
    overlapState = { ...overlapState, summary: null };
    renderOverlapResults();
    updateOverlapStatistics();
}
