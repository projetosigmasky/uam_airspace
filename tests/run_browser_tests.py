#!/usr/bin/env python3
"""Run the dashboard tests in headless Chrome (or Edge/Chromium).

1. tests/core_tests.html: unit tests of the pure functions (overlap analysis, parallel-route geometry).
2. UI tests through index.html, as a user would load files:
   - loader: files that reuse route names are all kept, each route in its own layer
     (data/nodes_edges_reh.csv and data/nodes_edges_rea.csv share "Portão Cabreúva";
     fixtures/scenario_a.csv and scenario_b.csv share every route name);
   - export: same-named routes of different layers are not merged when the file is reloaded;
   - CSV text in HTML: names containing markup (fixtures/html_in_names.csv; the markup only sets
     window.__xss_* flags) are shown as text in lists, inputs and map popups;
   - batch parallel routes: one waypoint per base waypoint with its attributes, for a route with
     collinear edges, and the offset in metres.

Requirements: Python 3.8+, `pip install websocket-client`, and Chrome, Edge or Chromium (set
CHROME_PATH if it is not found). Usage, from anywhere:
    python tests/run_browser_tests.py
Exit status 0 when every test passes.
"""
import http.server
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from functools import partial
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_browser():
    candidates = [os.environ.get("CHROME_PATH"),
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser"),
                  shutil.which("chrome"), shutil.which("msedge")]
    for c in candidates:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome/Edge/Chromium not found; set CHROME_PATH")


class Page:
    """A browser tab driven through the Chrome DevTools Protocol."""

    def __init__(self, cdp_port, url):
        req = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json/new?about:blank", method="PUT")
        self.target = json.load(urllib.request.urlopen(req))
        self.cdp_port = cdp_port
        self.ws = websocket.create_connection(self.target["webSocketDebuggerUrl"], timeout=300, suppress_origin=True)
        self._id = 0
        for m in ("Runtime.enable", "Page.enable", "DOM.enable"):
            self.send(m)
        self.send("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
        self.send("Page.navigate", url=url)

    def send(self, method, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg["result"]

    def js(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=await_promise, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:1500])
        return r["result"].get("value")

    def wait(self, expr, timeout=30):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.js(expr):
                return
            time.sleep(0.2)
        raise TimeoutError(expr)

    def upload(self, path):
        """Load a CSV through the route file input and wait until the loader has finished."""
        n0 = self.js("state.fileLayers.length + window.__alerts.length")
        root = self.send("DOM.getDocument", depth=1)["root"]["nodeId"]
        node = self.send("DOM.querySelector", nodeId=root, selector="#csvFile")["nodeId"]
        self.send("DOM.setFileInputFiles", files=[str(path)], nodeId=node)
        self.wait(f"state.fileLayers.length + window.__alerts.length > {n0}", timeout=30)
        time.sleep(0.3)

    def close(self):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.cdp_port}/json/close/{self.target['id']}")
        except Exception:
            pass
        self.ws.close()


results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def ui_page(cdp_port, base):
    p = Page(cdp_port, base + "index.html")
    p.wait("document.readyState === 'complete' && typeof OverlapAnalysis === 'object' && typeof state === 'object'")
    p.js("window.__alerts = []; window.alert = m => window.__alerts.push(String(m)); window.confirm = () => true; 0")
    return p


def run(cdp_port, base):
    print("Core tests (tests/core_tests.html)")
    p = Page(cdp_port, base + "tests/core_tests.html")
    p.wait("Array.isArray(window.__testResults)", timeout=120)
    for r in p.js("window.__testResults"):
        check(r["name"], r["ok"], r["detail"])
    p.close()

    print("Loader and export")
    p = ui_page(cdp_port, base)
    p.upload(ROOT / "data" / "nodes_edges_reh.csv")
    p.upload(ROOT / "data" / "nodes_edges_rea.csv")
    layers = p.js("JSON.stringify(state.routes.filter(r => r.name === 'Portão Cabreúva').map(r => r.layerId))")
    layers = json.loads(layers)
    check("REH and REA files both keep their 'Portão Cabreúva' route", len(layers) == 2 and len(set(layers)) == 2,
          f"{len(layers)} route(s)")
    p.upload(FIX / "scenario_a.csv")
    p.upload(FIX / "scenario_b.csv")
    counts = dict(json.loads(p.js(
        "JSON.stringify(state.fileLayers.map(l => [l.name, state.routes.filter(r => r.layerId === l.id).length]))")))
    check("two scenario files with the same route names keep 2 routes each",
          counts.get("scenario_a.csv") == 2 and counts.get("scenario_b.csv") == 2, json.dumps(counts, ensure_ascii=False))
    alt = p.js("(() => { const r = state.routes.find(r => r.name === 'R1' && state.fileLayers.find(l => l.id === r.layerId).name === 'scenario_b.csv');"
               " return r ? r.waypoints[1].altitude : null; })()")
    check("each same-named route keeps its own waypoints", alt == 914, f"R1 of scenario_b: N1 altitude {alt} m")
    p.js("""window.__csv = null;
            URL.createObjectURL = b => { b.text().then(t => { window.__csv = t; }); return 'blob:test'; };
            URL.revokeObjectURL = () => {}; HTMLAnchorElement.prototype.click = function () {};
            exportToCSV(); 0""")
    p.wait("window.__csv !== null")
    n_names = p.js("new Set(window.__csv.trim().split('\\n').slice(1).map(r => r.split('\",')[0])).size")
    n_routes = p.js("state.routes.length")
    check("exported file has one route name per route", n_names == n_routes, f"{n_names} names, {n_routes} routes")
    p.close()

    print("CSV text in HTML")
    p = ui_page(cdp_port, base)
    p.upload(FIX / "html_in_names.csv")
    p.js("selectRoute(state.routes[0].id); updateUI(); 0")
    p.js("const b = document.getElementById('viewMapBtn'); if (b) b.click(); 0")
    time.sleep(1.5)
    n_popups = p.js("(() => { let n = 0; map2D.eachLayer(l => { if (l.getPopup && l.getPopup()) { n++; l.openPopup(); } }); return n; })()")
    time.sleep(1.0)
    flags = json.loads(p.js("JSON.stringify(Object.keys(window).filter(k => k.startsWith('__xss')))"))
    check("markup in route, waypoint and vertiport names is not executed", flags == [] and n_popups > 0,
          f"{n_popups} popups opened, flags set: {flags}")
    check("no element is created from CSV markup", p.js("document.querySelectorAll('img[src=\"x\"], svg[onload]').length") == 0)
    names = json.loads(p.js("JSON.stringify(Array.from(document.querySelectorAll('.waypoint-name-input')).map(i => i.value))"))
    expected = ["Portão Cabreúva & O'Hara <i>VP</i>", "<img src=x onerror=window.__xss_wp=1>", "<svg onload=window.__xss_vp=1>"]
    check("names are shown verbatim (accents, &, ', <)", names == expected, json.dumps(names, ensure_ascii=False))
    p.close()

    print("Batch parallel routes")
    p = ui_page(cdp_port, base)
    phi = math.radians(-23.55)
    m_lat = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
    m_lon = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
    coords = [(-6000, 300), (-3000, 0), (0, 0), (3000, 0), (6000, 300)]   # collinear middle edges
    wps = [dict(name=f"W{i}", lat=-23.55 + y / m_lat, lon=-46.63 + x / m_lon, altitude=760 if i in (0, 4) else 1219,
                width=457, height=305, type="Vertiport" if i in (0, 4) else "Node") for i, (x, y) in enumerate(coords)]
    p.js(f"""(() => {{
        state.routes = [{{ id: 'base', name: 'BASE', waypoints: {json.dumps(wps)}, color: new THREE.Color('#888888'),
                          visible: true, layerId: null }}];
        document.getElementById('numParallelRoutes').value = 2;
        updateBatchModalFields();
        const h = document.querySelectorAll('.horizontal-offset-input');
        h[0].value = 228.6; h[1].value = -228.6;
        document.querySelectorAll('.vertical-offset-input').forEach(v => v.value = 0);
        document.getElementById('deleteOriginalRoutes').checked = false;
        generateParallelRoutesForAll();
    }})()""")
    lanes = json.loads(p.js("JSON.stringify(state.routes.filter(r => r.name.startsWith('BASE (Parallel')).map(r => r.waypoints))"))
    ok_attrs = len(lanes) == 2 and all(
        [(w["name"], w["type"], w["altitude"]) for w in lane] == [(w["name"], w["type"], w["altitude"]) for w in wps]
        for lane in lanes)
    check("lanes keep one waypoint per base waypoint with its name, type and altitude (collinear edges)", ok_attrs,
          f"{[len(l) for l in lanes]} waypoints")
    if lanes:
        y = [(lane[2]["lat"] + 23.55) * m_lat for lane in lanes]
        check("lane offsets are in metres (+/-228.6 m at the middle waypoint)",
              abs(y[0] - 228.6) < 0.1 and abs(y[1] + 228.6) < 0.1, f"{y[0]:.2f} m, {y[1]:.2f} m")
    p.close()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class QuietServer(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass   # the browser resets idle connections when tabs close


def main():
    http_port, cdp_port = free_port(), free_port()
    server = QuietServer(("127.0.0.1", http_port), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = tempfile.mkdtemp(prefix="uam-dashboard-tests-")
    flags = ["--headless=new", f"--remote-debugging-port={cdp_port}", f"--user-data-dir={profile}",
             "--no-first-run", "--disable-gpu"]
    if os.environ.get("CI"):
        flags.append("--no-sandbox")   # CI containers often lack the user namespaces Chrome's sandbox needs
    browser = subprocess.Popen([find_browser(), *flags, "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        t0 = time.time()
        while True:
            try:
                version = json.load(urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/version", timeout=1))
                print(f"Browser: {version.get('Browser')}; Python {sys.version.split()[0]}")
                break
            except Exception:
                if time.time() - t0 > 30:
                    sys.exit("browser did not start")
                time.sleep(0.3)
        run(cdp_port, f"http://127.0.0.1:{http_port}/")
    finally:
        browser.terminate()
        server.shutdown()
        try:
            browser.wait(timeout=10)
        except subprocess.TimeoutExpired:
            browser.kill()
        shutil.rmtree(profile, ignore_errors=True)
    failed = results.count(False)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
