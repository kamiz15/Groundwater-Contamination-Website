(() => {
  "use strict";

  const GRID_SPACING = 0.05;
  const SNAP_TO_GRID = true;
  // Mutable snap bounds, updated by the designer when Ws / orientation change.
  // Defaults (Ws = 0.5, horizontal) keep snapDrawPoint a pure function for the
  // node-based unit tests, which never touch the DOM or the settings form.
  const snapConfig = {wsMax: 0.5, orientation: "horizontal"};
  const roundHalfEven = (value) => {
    const lower = Math.floor(value);
    const fraction = value - lower;
    if (fraction === 0.5) return lower % 2 === 0 ? lower : lower + 1;
    return Math.round(value);
  };
  const snapDrawPoint = ([x, y]) => {
    const snappedX = SNAP_TO_GRID ? roundHalfEven(x / GRID_SPACING) * GRID_SPACING : x;
    const snappedY = SNAP_TO_GRID ? roundHalfEven(y / GRID_SPACING) * GRID_SPACING : y;
    const cx = Math.max(0, Math.min(snapConfig.wsMax, +snappedX.toFixed(10)));
    const cy = +snappedY.toFixed(10);
    // Vertical: the aquifer is below the water table (y <= 0); horizontal: y >= 0.
    return [cx, snapConfig.orientation === "vertical" ? Math.min(0, cy) : Math.max(0, cy)];
  };
  const reselectCircle = (circles, changed) => {
    const index = circles.findIndex((circle) =>
      Math.abs(circle.x - changed.x) <= 1e-9 && Math.abs(circle.y - changed.y) <= 1e-9);
    return index < 0 ? null : {index, circle: circles[index]};
  };
  // Display formatter: at most 2 decimals, with trailing zeros (and a bare whole
  // number's decimals) dropped — 2 → "2", 3.5 → "3.5", 2.456 → "2.46". Used for
  // every value shown to the user (inputs, readouts, axis ticks, result summary).
  // Internal geometry/config precision is unaffected.
  const fmt2 = (value) => {
    const n = +value;
    if (!Number.isFinite(n)) return String(value);
    return String(parseFloat(n.toFixed(2)));
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {roundHalfEven, snapDrawPoint, reselectCircle, fmt2};
  }
  if (typeof document === "undefined") return;

  const root = document.querySelector("[data-aem-page]");
  if (!root) return;
  const message = document.getElementById("aem-message");
  const show = (text, error = false) => {
    if (!message) return;
    message.textContent = text;
    message.classList.toggle("aem-message--error", error);
  };
  const json = async (url, options = {}) => {
    const response = await fetch(url, options);
    const body = await response.json();
    if (!response.ok) throw new Error(body.message || `Request failed (${response.status})`);
    return body;
  };
  const post = (url, body) => json(url, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf},
    body: JSON.stringify(body)
  });

  // Radius proxy for domain/shift sizing: circle radius, ellipse semi-major,
  // or half the line length.
  const elementRadius = (e) => e.kind === "circle" ? +e.r
    : e.kind === "ellipse" ? Math.max(+e.a, +e.b)
    : (+e.l) / 2;

  // Rotation-aware half-width / half-height of an element's bounding box,
  // mirroring designer_model.py:_elem_half_width / _elem_half_height. Used for
  // scale-aware domain padding so the web domain matches the reference solver.
  const elemHalfWidth = (e) => {
    if (e.kind === "circle") return +e.r || 0;
    if (e.kind === "ellipse") {
      const a = +e.a || 0, b = +e.b || 0, t = (+e.theta || 0) * Math.PI / 180;
      return Math.sqrt((a * Math.cos(t)) ** 2 + (b * Math.sin(t)) ** 2);
    }
    const t = (+e.theta || 0) * Math.PI / 180;
    return (+e.l || 0) / 2 * Math.abs(Math.cos(t));
  };
  const elemHalfHeight = (e) => {
    if (e.kind === "circle") return +e.r || 0;
    if (e.kind === "ellipse") {
      const a = +e.a || 0, b = +e.b || 0, t = (+e.theta || 0) * Math.PI / 180;
      return Math.sqrt((a * Math.sin(t)) ** 2 + (b * Math.cos(t)) ** 2);
    }
    const t = (+e.theta || 0) * Math.PI / 180;
    return (+e.l || 0) / 2 * Math.abs(Math.sin(t));
  };

  function referenceConfig(elementDicts, values) {
    // Copy so the vertical shift below never mutates the live design objects.
    const elements = (elementDicts || []).map((e, index) => ({
      ...e, id: e.id || `src_${index}`
    }));
    const base = {
      alpha_l: +values.alpha_l, alpha_t: +values.alpha_t, ca: +values.ca,
      gamma: +values.gamma, dom_inc: +values.dom_inc, num_cp: +values.num_cp,
      num_terms: +values.num_terms, orientation: values.orientation,
      plot_aspect: "", elements
    };
    if (!elements.length) return base;
    // Coordinates are physical and authoritative — no vertical shift. In vertical
    // orientation the source zone is authored directly below the water table (y<=0),
    // matching the reference designer_model.to_config_dict (which never shifts) and
    // its validate_for_export guard (every element must sit below y=0).
    const xs = elements.map((element) => element.x);
    const ys = elements.map((element) => element.y);
    const maxHW = Math.max(...elements.map(elemHalfWidth));
    const maxHH = Math.max(...elements.map(elemHalfHeight));
    // Scale-aware x-padding (mirrors designer_model.py:to_config_dict). A fixed
    // +150 m is pathological for sub-metre sources — it produces a huge, mostly
    // empty grid and lets exp(beta*x) blow up far downstream. Scale the padding
    // to the source size, capped at 150 m; the solver extends it if the plume
    // actually needs it.
    const xSpan = Math.max(...xs) - Math.min(...xs);
    const char = Math.max(2 * maxHW, 2 * maxHH, xSpan, 1.0);
    const xPad = Math.min(150.0, Math.max(20.0, 25.0 * char));
    return {
      ...base,
      dom_xmin: +(Math.min(...xs) - maxHW - 2).toFixed(3),
      dom_xmax: +(Math.max(...xs) + xPad).toFixed(1),
      dom_ymin: +(Math.min(...ys) - maxHH - 5).toFixed(3),
      dom_ymax: values.orientation === "vertical" ? 0 : +(Math.max(...ys) + maxHH + 5).toFixed(3),
    };
  }

  // Faithful matplotlib "Reds" colormap, sampled c/CONC_MAX. Piecewise-linear
  // through the canonical Reds anchor stops (#fff5f0 -> #67000d).
  const REDS_STOPS = [
    [1.000, 0.961, 0.941], [0.996, 0.878, 0.824], [0.988, 0.733, 0.631],
    [0.988, 0.573, 0.447], [0.984, 0.416, 0.290], [0.937, 0.231, 0.173],
    [0.796, 0.094, 0.114], [0.647, 0.059, 0.082], [0.404, 0.000, 0.051]
  ];
  // Faithful matplotlib "Blues" anchors (#f7fbff light -> #08306b dark), used
  // for the electron-acceptor (negative-concentration) field, matching the
  // source simulation's Blues_r scheme.
  const BLUES_STOPS = [
    [0.969, 0.984, 1.000], [0.871, 0.922, 0.969], [0.776, 0.859, 0.937],
    [0.620, 0.792, 0.882], [0.420, 0.682, 0.839], [0.259, 0.573, 0.776],
    [0.129, 0.443, 0.710], [0.031, 0.318, 0.612], [0.031, 0.188, 0.420]
  ];
  // Sample a stop list at t in [0,1], returning an [r,g,b] byte triple.
  const sampleStops = (stops, t) => {
    const u = Math.max(0, Math.min(1, t)) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(u));
    const f = u - i;
    const a = stops[i], b = stops[i + 1];
    return [0, 1, 2].map((k) => Math.round((a[k] + (b[k] - a[k]) * f) * 255));
  };
  const redsColor = (t) => {
    const u = Math.max(0, Math.min(1, t)) * (REDS_STOPS.length - 1);
    const i = Math.min(REDS_STOPS.length - 2, Math.floor(u));
    const f = u - i;
    const a = REDS_STOPS[i], b = REDS_STOPS[i + 1];
    const ch = (k) => Math.round((a[k] + (b[k] - a[k]) * f) * 255);
    return `rgb(${ch(0)}, ${ch(1)}, ${ch(2)})`;
  };

  function designer() {
    let WS = 0.5;                 // source-zone width guide; driven by the Ws field
    const GRID = 0.05;
    const GRID_HEIGHT = 15.0;
    const CONC_MAX = 50.0;
    const MIN_RADIUS = 0.003;
    const RADIUS_STEP = 0.002;
    const CONC_STEP = 2.0;

    const canvas = document.getElementById("aem-designer-canvas");
    const ctx = canvas.getContext("2d");
    const form = document.getElementById("aem-design-form");
    const statusEl = document.getElementById("aem-status");
    const infoEl = document.getElementById("aem-info");
    const colorbar = document.getElementById("aem-colorbar");
    const DEFAULT_R = 0.02;       // fallback size for a click without a drag
    const polygons = [];
    const sources = [];           // standalone simple sources: {kind,x,y,c,r|a,b|l,theta,id}
    let drawing = [];
    // selected is a tagged union:
    //   {type:"poly", p, c}  -> a packed circle inside polygons[p].circles[c]
    //   {type:"source", i}   -> sources[i]
    let selected = null;
    let dragOffset = [0, 0];
    let dragging = false;
    let placing = null;           // {kind, x0, y0, x1, y1} during a press-drag shape draw
    let panning = false;
    let panStart = null;
    let tool = "polygon";         // "polygon" | "circle" | "ellipse" | "line" | "select"
    let mode = "draw";            // derived: "edit" when tool==="select", else "draw"
    let fullView = false;
    let showIndices = false;      // "Index # (i)" toggle: number each element on the canvas
    let repacking = false;        // re-entrancy guard for radius repacks
    let dpr = 1;
    const view = {xmin: -0.05, xmax: WS + 0.05, ymin: -0.1, ymax: WS + 0.1};

    let importedDomain = null;   // explicit dom_* carried from an imported design
    let importedSig = null;      // geometry signature when importedDomain was captured
    const formValues = () => Object.fromEntries(new FormData(form));
    const orientation = () => formValues().orientation || "vertical";
    // Pull the live Ws / orientation from the form into the drawing state. Ws drives
    // the source-zone width guide and the x-snap ceiling; orientation drives the
    // y-snap half-plane and the canvas framing.
    const syncSettings = () => {
      WS = +formValues().ws || 0.5;
      snapConfig.wsMax = WS;
      snapConfig.orientation = orientation();
    };
    // Re-frame the view to the orientation convention, mirroring
    // source_designer.py:_reframe_for_orientation:
    //   vertical   → aquifer below the water table, y in [-(Ws+m), +m]
    //   horizontal → transverse band,               y in [-m, Ws+m]
    const reframeView = () => {
      const m = Math.max(WS * 0.10, 0.05);
      view.xmin = -m; view.xmax = WS + m;
      if (orientation() === "vertical") { view.ymin = -(WS + m); view.ymax = m; }
      else { view.ymin = -m; view.ymax = WS + m; }
    };
    const allCircles = () => polygons.flatMap((polygon) => polygon.circles);
    // Unified element dicts (copies) for config, signatures, bounds and rendering:
    // packed circles plus standalone simple sources.
    const allElementDicts = () => [
      ...polygons.flatMap((poly) => poly.circles.map((c) => ({
        kind: "circle", x: +c.x, y: +c.y, r: +c.r, c: +c.c, id: c.id,
      }))),
      ...sources.map((s) => ({ ...s })),
    ];
    const hasElements = () => polygons.some((p) => p.circles.length) || sources.length > 0;
    const elemBBox = (e) => {
      if (e.kind === "circle") return {minx: e.x - e.r, maxx: e.x + e.r, miny: e.y - e.r, maxy: e.y + e.r};
      if (e.kind === "ellipse") { const m = Math.max(e.a, e.b); return {minx: e.x - m, maxx: e.x + m, miny: e.y - m, maxy: e.y + m}; }
      const th = (e.theta || 0) * Math.PI / 180;
      const hx = Math.abs(Math.cos(th) * e.l / 2), hy = Math.abs(Math.sin(th) * e.l / 2);
      return {minx: e.x - hx, maxx: e.x + hx, miny: e.y - hy, maxy: e.y + hy};
    };
    const importNumber = (element, name, index, fallback = null) => {
      if (element[name] === undefined || element[name] === null || element[name] === "") {
        if (fallback !== null) return fallback;
        throw new Error(`Element ${index + 1} requires numeric '${name}'.`);
      }
      const value = Number(element[name]);
      if (!Number.isFinite(value)) throw new Error(`Element ${index + 1} has invalid '${name}'.`);
      return value;
    };
    const normalizeImportedElement = (element, index) => {
      const kind = String(element.kind || "").toLowerCase();
      if (!["circle", "ellipse", "line"].includes(kind)) {
        throw new Error(`Element ${index + 1} has unsupported kind '${element.kind}'.`);
      }
      const base = {
        kind,
        x: importNumber(element, "x", index),
        y: importNumber(element, "y", index),
        c: importNumber(element, "c", index, +form.default_c.value || 10),
        id: element.id || newId(),
      };
      if (element.label !== undefined) base.label = element.label;
      if (element.index !== undefined) base.index = element.index;
      if (kind === "circle") return {...base, r: importNumber(element, "r", index)};
      if (kind === "ellipse") {
        return {...base, a: importNumber(element, "a", index),
          b: importNumber(element, "b", index), theta: importNumber(element, "theta", index, 0)};
      }
      return {...base, l: importNumber(element, "l", index), theta: importNumber(element, "theta", index, 90)};
    };
    const geomSignature = () => allElementDicts().map((e) =>
      `${e.kind}:${e.x},${e.y},${e.r || e.a || e.l},${e.b || 0},${e.theta || 0}`).join(";");
    const buildConfig = () => {
      const config = referenceConfig(allElementDicts(), formValues());
      // For an imported design, keep the file's own domain bounds (like main.py in
      // the source, which reads dom_* from the JSON) instead of the recomputed box —
      // but only while its geometry is unchanged. Any edit changes the signature and
      // falls back to the recomputed frame.
      if (importedDomain && importedSig === geomSignature()) Object.assign(config, importedDomain);
      return config;
    };
    const yLabel = () => (formValues().orientation === "horizontal" ? "y (m)" : "z (m)");
    const setStatus = (text) => { if (statusEl) statusEl.textContent = text; };
    const setInfo = (text) => { if (infoEl) infoEl.textContent = text; };

    // Displayed CSS box of the canvas (independent of backing-store pixels).
    const box = () => {
      const rect = canvas.getBoundingClientRect();
      return {width: rect.width || canvas.clientWidth, height: rect.height || canvas.clientHeight};
    };
    const fitSource = () => {
      const els = allElementDicts(); if (!els.length) return;
      const boxes = els.map(elemBBox);
      const padding = Math.max(0.05, ...els.map((e) => elementRadius(e) * 2));
      view.xmin = Math.min(...boxes.map((b) => b.minx)) - padding;
      view.xmax = Math.max(...boxes.map((b) => b.maxx)) + padding;
      view.ymin = Math.min(...boxes.map((b) => b.miny)) - padding;
      view.ymax = Math.max(...boxes.map((b) => b.maxy)) + padding;
    };
    // Equal-aspect viewport: uniform scale so circles always render circular.
    const viewport = (bounds, rect) => {
      const xspan = bounds.xmax - bounds.xmin;
      const yspan = bounds.ymax - bounds.ymin;
      const scale = Math.min(rect.width / xspan, rect.height / yspan);
      return {bounds, scale, left: rect.left + (rect.width - xspan * scale) / 2,
              top: rect.top + (rect.height - yspan * scale) / 2};
    };
    const sourceViewport = () => {
      const b = box();
      return viewport(view, {left: 0, top: 0, width: b.width, height: b.height});
    };
    const toPixel = ([x, y], vp) => [vp.left + (x - vp.bounds.xmin) * vp.scale,
      vp.top + (vp.bounds.ymax - y) * vp.scale];
    // Map a mouse event to data coords using the DISPLAYED box (DPR-aware
    // backing store is handled by the ctx scale, so we work in CSS px here).
    const toData = (event) => {
      const rect = canvas.getBoundingClientRect();
      const vp = sourceViewport();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      return [view.xmin + (px - vp.left) / vp.scale, view.ymax - (py - vp.top) / vp.scale];
    };
    const distToSegment = (px, py, ax, ay, bx, by) => {
      const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
      let t = len2 ? ((px - ax) * dx + (py - ay) * dy) / len2 : 0;
      t = Math.max(0, Math.min(1, t));
      return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
    };
    const hit = (point) => {
      let best = Infinity, found = null;
      for (let p = 0; p < polygons.length; p++) {
        for (let c = 0; c < polygons[p].circles.length; c++) {
          const circle = polygons[p].circles[c];
          const dist = Math.hypot(point[0] - circle.x, point[1] - circle.y);
          if (dist <= circle.r * 1.5 && dist < best) { best = dist; found = {type: "poly", p, c}; }
        }
      }
      for (let i = 0; i < sources.length; i++) {
        const s = sources[i];
        let dist, reach;
        if (s.kind === "line") {
          const th = (s.theta || 0) * Math.PI / 180, hx = Math.cos(th) * s.l / 2, hy = Math.sin(th) * s.l / 2;
          dist = distToSegment(point[0], point[1], s.x - hx, s.y - hy, s.x + hx, s.y + hy);
          reach = Math.max(0.01, elementRadius(s) * 0.4);
        } else {
          dist = Math.hypot(point[0] - s.x, point[1] - s.y);
          reach = elementRadius(s) * 1.5;
        }
        if (dist <= reach && dist < best) { best = dist; found = {type: "source", i}; }
      }
      return found;
    };
    const selectedElem = () => {
      if (!selected) return null;
      return selected.type === "source" ? sources[selected.i] : polygons[selected.p].circles[selected.c];
    };

    const drawGrid = (vp) => {
      ctx.strokeStyle = "#ececec"; ctx.lineWidth = 0.3;
      for (let x = 0; x <= WS + 1e-9; x += GRID) {
        const [px] = toPixel([x, 0], vp);
        ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, box().height); ctx.stroke();
      }
      const y0 = Math.max(-GRID_HEIGHT, Math.floor(view.ymin / GRID) * GRID);
      const y1 = Math.min(GRID_HEIGHT, Math.ceil(view.ymax / GRID) * GRID);
      for (let y = y0; y <= y1 + 1e-9; y += GRID) {
        const [, py] = toPixel([0, y], vp);
        ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(box().width, py); ctx.stroke();
      }
      // Gold dashed source-zone boundaries at x=0 and x=WS.
      ctx.save();
      ctx.strokeStyle = "gold"; ctx.lineWidth = 1.5; ctx.setLineDash([6, 4]);
      [0, WS].forEach((x) => {
        const [px] = toPixel([x, 0], vp);
        ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, box().height); ctx.stroke();
      });
      ctx.restore();
      // Vertical orientation: water table plus the minimum valid source-top line.
      if (orientation() === "vertical") {
        const [, py0] = toPixel([0, 0], vp);
        const [, pyMinTop] = toPixel([0, -0.1], vp);
        ctx.save();
        ctx.strokeStyle = "#1565c0"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(0, py0); ctx.lineTo(box().width, py0); ctx.stroke();
        ctx.fillStyle = "#1565c0"; ctx.font = "11px sans-serif";
        ctx.textAlign = "left"; ctx.textBaseline = "bottom";
        ctx.fillText("water table (y = 0) - draw below", 8, py0 - 4);

        ctx.strokeStyle = "#d97706"; ctx.lineWidth = 1.4; ctx.setLineDash([5, 4]);
        ctx.beginPath(); ctx.moveTo(0, pyMinTop); ctx.lineTo(box().width, pyMinTop); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = "#92400e"; ctx.textBaseline = "top";
        ctx.fillText("minimum source top (y = -0.1 m)", 8, pyMinTop + 4);
        ctx.restore();
      }
    };

    const drawAxes = (vp) => {
      const b = box();
      ctx.fillStyle = "#444"; ctx.font = "12px sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
      ctx.fillText("x (m)", b.width / 2, b.height - 4);
      ctx.save();
      ctx.translate(12, b.height / 2); ctx.rotate(-Math.PI / 2);
      ctx.fillText(yLabel(), 0, 0);
      ctx.restore();
      ctx.textAlign = "left";
      ctx.fillStyle = "#222"; ctx.font = "bold 14px sans-serif";
      const title = fullView ? "Source zone" : (mode === "edit" ? "Source zone — Edit" : "Source zone — Draw");
      ctx.fillText(title, 8, 18);
    };

    const drawWsAnnotation = (vp, ws, b) => {
      ctx.save();
      ctx.font = "11px sans-serif"; ctx.textAlign = "right"; ctx.textBaseline = "top";
      const label = `Ws = ${fmt2(ws)} m`;
      const tw = ctx.measureText(label).width;
      const rx = (b.left !== undefined ? b.left + b.width : box().width) - 6;
      const ry = (b.top !== undefined ? b.top : 0) + 6;
      ctx.fillStyle = "rgba(255,255,255,0.6)";
      ctx.fillRect(rx - tw - 6, ry - 2, tw + 8, 16);
      ctx.fillStyle = "goldenrod";
      ctx.fillText(label, rx, ry);
      ctx.restore();
    };

    const drawPolygons = (vp, polygonList, selKey) => {
      polygonList.forEach((poly, pi) => {
        if (poly.vertices.length >= 3) {
          ctx.beginPath();
          poly.vertices.forEach((vertex, index) => {
            const point = toPixel(vertex, vp);
            index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1]);
          });
          ctx.closePath();
          ctx.fillStyle = "rgba(255,215,0,0.08)"; ctx.fill();
          ctx.strokeStyle = "goldenrod"; ctx.lineWidth = 1; ctx.stroke();
        }
        poly.circles.forEach((circle, ci) => {
          const point = toPixel([circle.x, circle.y], vp);
          ctx.beginPath(); ctx.arc(point[0], point[1], circle.r * vp.scale, 0, Math.PI * 2);
          ctx.fillStyle = redsColor(circle.c / CONC_MAX); ctx.fill();
          const active = selKey && selKey.p === pi && selKey.c === ci;
          ctx.strokeStyle = active ? "#e94560" : "black";
          ctx.lineWidth = active ? 2 : 0.5; ctx.stroke();
        });
      });
    };

    const drawCircleList = (vp, circles) => {
      circles.forEach((circle) => {
        const point = toPixel([circle.x, circle.y], vp);
        ctx.beginPath(); ctx.arc(point[0], point[1], circle.r * vp.scale, 0, Math.PI * 2);
        ctx.fillStyle = redsColor(circle.c / CONC_MAX); ctx.fill();
        ctx.strokeStyle = "black"; ctx.lineWidth = 0.5; ctx.stroke();
      });
    };

    // Draw any simple-source element (circle/ellipse/line); active = selected.
    const drawShape = (vp, e, active) => {
      const [cx, cy] = toPixel([e.x, e.y], vp);
      ctx.save();
      if (e.kind === "circle") {
        ctx.beginPath(); ctx.arc(cx, cy, e.r * vp.scale, 0, Math.PI * 2);
        ctx.fillStyle = redsColor(e.c / CONC_MAX); ctx.fill();
        ctx.strokeStyle = active ? "#e94560" : "black"; ctx.lineWidth = active ? 2 : 0.5; ctx.stroke();
      } else if (e.kind === "ellipse") {
        const th = (e.theta || 0) * Math.PI / 180;   // -th: data CCW vs canvas y-down
        ctx.beginPath(); ctx.ellipse(cx, cy, e.a * vp.scale, e.b * vp.scale, -th, 0, Math.PI * 2);
        ctx.fillStyle = redsColor(e.c / CONC_MAX); ctx.fill();
        ctx.strokeStyle = active ? "#e94560" : "black"; ctx.lineWidth = active ? 2 : 0.5; ctx.stroke();
      } else {                                         // line
        const th = (e.theta || 0) * Math.PI / 180, hx = Math.cos(th) * e.l / 2, hy = Math.sin(th) * e.l / 2;
        const [ax, ay] = toPixel([e.x - hx, e.y - hy], vp);
        const [bx, by] = toPixel([e.x + hx, e.y + hy], vp);
        ctx.lineCap = "round";
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
        ctx.strokeStyle = redsColor(e.c / CONC_MAX); ctx.lineWidth = active ? 7 : 5; ctx.stroke();
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
        ctx.strokeStyle = active ? "#e94560" : "black"; ctx.lineWidth = active ? 2 : 1; ctx.stroke();
      }
      ctx.restore();
    };
    const drawSources = (vp) => {
      sources.forEach((s, i) => drawShape(vp, s, selected && selected.type === "source" && selected.i === i));
    };
    // Faint ordinal at each element centroid, in allElementDicts order.
    // ponytail: collection order, not the reference's spatial reindex — it's a visual aid.
    const drawIndices = (vp) => {
      if (!showIndices) return;
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0,0.8)"; ctx.font = "9px sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      allElementDicts().forEach((e, i) => {
        const [px, py] = toPixel([e.x, e.y], vp);
        ctx.fillText(String(i), px, py);
      });
      ctx.restore();
    };

    const newId = () => "src_" + Math.random().toString(36).slice(2, 8);
    // Convert an in-progress press-drag into a source object. preview=true keeps
    // tiny drags visible; on commit, sub-threshold drags fall back to defaults.
    const placingToSource = (pl, preview) => {
      const c = +form.default_c.value || 10;
      const dx = pl.x1 - pl.x0, dy = pl.y1 - pl.y0, dist = Math.hypot(dx, dy);
      if (pl.kind === "circle") {
        const r = preview ? Math.max(dist, 1e-4) : (dist > 0.003 ? dist : DEFAULT_R);
        return {kind: "circle", x: pl.x0, y: pl.y0, r: +r.toFixed(5), c, id: pl.id};
      }
      if (pl.kind === "ellipse") {
        const a = preview ? Math.max(Math.abs(dx), 1e-4) : (Math.abs(dx) > 0.003 ? Math.abs(dx) : DEFAULT_R);
        const b = preview ? Math.max(Math.abs(dy), 1e-4) : (Math.abs(dy) > 0.003 ? Math.abs(dy) : DEFAULT_R * 0.6);
        return {kind: "ellipse", x: pl.x0, y: pl.y0, a: +a.toFixed(5), b: +b.toFixed(5), theta: 0, c, id: pl.id};
      }
      const l = preview ? Math.max(dist, 1e-4) : (dist > 0.003 ? dist : 0.05);
      const theta = dist > 0.003 ? +(Math.atan2(dy, dx) * 180 / Math.PI).toFixed(3) : 90;
      return {kind: "line", x: +((pl.x0 + pl.x1) / 2).toFixed(5), y: +((pl.y0 + pl.y1) / 2).toFixed(5),
              l: +l.toFixed(5), theta, c, id: pl.id};
    };
    const drawPlacing = (vp) => {
      if (!placing) return;
      ctx.save(); ctx.globalAlpha = 0.6; drawShape(vp, placingToSource(placing, true), true); ctx.restore();
    };

    const drawInProgress = (vp) => {
      if (!drawing.length) return;
      ctx.beginPath();
      drawing.forEach((vertex, index) => {
        const point = toPixel(vertex, vp);
        index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1]);
      });
      ctx.strokeStyle = "black"; ctx.lineWidth = 1.5; ctx.stroke();
      drawing.forEach((vertex) => {
        const [px, py] = toPixel(vertex, vp);
        ctx.fillStyle = "goldenrod"; ctx.fillRect(px - 4, py - 4, 8, 8);
      });
    };

    // Draw a few axis tick labels (matplotlib MaxNLocator-style) on a panel.
    const drawPanelTicks = (vp, panelLeft, panelTop, panelW, panelH, nx, ny) => {
      ctx.save();
      ctx.fillStyle = "#666"; ctx.font = "9px sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      for (let i = 0; i <= nx; i++) {
        const xv = vp.bounds.xmin + (vp.bounds.xmax - vp.bounds.xmin) * (i / nx);
        const [px] = toPixel([xv, 0], vp);
        ctx.fillText(fmt2(xv), px, panelTop + panelH + 2);
      }
      ctx.textAlign = "right"; ctx.textBaseline = "middle";
      for (let i = 0; i <= ny; i++) {
        const yv = vp.bounds.ymin + (vp.bounds.ymax - vp.bounds.ymin) * (i / ny);
        const [, py] = toPixel([0, yv], vp);
        ctx.fillText(fmt2(yv), panelLeft - 2, py);
      }
      ctx.restore();
    };

    // View is a read-only refresh of the SAME polygons/circles in both panels
    // (matches source_designer.py ViewWindow: identical coordinate set, the
    // domain panel just frames them within the full simulation extents).
    const drawFullView = () => {
      const b = box();
      const raw = allElementDicts();
      const boxes = raw.map(elemBBox);
      const splitX = b.width * 0.30;
      const panelH = b.height - 56;
      const panelTop = 30;
      // Shared y-range and source width from the SAME (unshifted) elements.
      const ws = Math.max(WS, ...boxes.map((bb) => bb.maxx));
      const allX = raw.map((e) => e.x);
      const ymin = Math.min(...boxes.map((bb) => bb.miny));
      const ymax = Math.max(...boxes.map((bb) => bb.maxy));
      const pad = Math.max((ymax - ymin) * 0.08, 0.5);

      // Left: equal-aspect Source zone panel.
      const srcW = splitX - 24;
      const srcBounds = {xmin: -0.05 * ws, xmax: 1.15 * ws, ymin: ymin - pad, ymax: ymax + pad};
      const srcVp = viewport(srcBounds, {left: 30, top: panelTop, width: srcW, height: panelH});
      ctx.save(); ctx.strokeStyle = "#ccc"; ctx.strokeRect(30, panelTop, srcW, panelH); ctx.restore();
      [0, ws].forEach((x) => {
        const [px] = toPixel([x, 0], srcVp);
        ctx.save(); ctx.strokeStyle = "gold"; ctx.lineWidth = 1.2; ctx.setLineDash([6, 4]);
        ctx.beginPath(); ctx.moveTo(px, panelTop); ctx.lineTo(px, panelTop + panelH); ctx.stroke(); ctx.restore();
      });
      raw.forEach((e) => drawShape(srcVp, e, false));
      drawPanelTicks(srcVp, 30, panelTop, srcW, panelH, 3, 8);
      ctx.fillStyle = "#222"; ctx.font = "bold 13px sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      ctx.fillText("Source zone", 30, 22);
      drawWsAnnotation(srcVp, ws, {left: 30, top: panelTop, width: srcW});

      // Right: Full simulation domain — SAME circles, x range [min_x-2, max_x+150],
      // shared y-range, gold source-zone band (axvspan 0..ws).
      const domLeft = splitX + 30;
      const domW = b.width - domLeft - 12;
      const domBounds = {xmin: Math.min(...allX) - 2.0, xmax: Math.max(...allX) + 150.0,
        ymin: ymin - pad, ymax: ymax + pad};
      const domVp = viewport(domBounds, {left: domLeft, top: panelTop, width: domW, height: panelH});
      ctx.save(); ctx.strokeStyle = "#ccc"; ctx.strokeRect(domLeft, panelTop, domW, panelH); ctx.restore();
      const [bx0] = toPixel([0, 0], domVp);
      const [bx1] = toPixel([ws, 0], domVp);
      ctx.save(); ctx.fillStyle = "rgba(255,215,0,0.18)";
      ctx.fillRect(Math.min(bx0, bx1), panelTop, Math.abs(bx1 - bx0), panelH); ctx.restore();
      raw.forEach((e) => drawShape(domVp, e, false));
      drawPanelTicks(domVp, domLeft, panelTop, domW, panelH, 7, 8);
      ctx.fillStyle = "#222"; ctx.font = "bold 13px sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      ctx.fillText("Full simulation domain", domLeft, 22);
      // legend
      ctx.font = "11px sans-serif"; ctx.fillStyle = "rgba(255,215,0,0.6)";
      ctx.fillRect(domLeft + domW - 96, 32, 12, 12);
      ctx.fillStyle = "#444"; ctx.textBaseline = "alphabetic"; ctx.fillText("Source zone", domLeft + domW - 80, 42);
    };

    const draw = () => {
      const b = box();
      ctx.clearRect(0, 0, b.width, b.height);
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, b.width, b.height);
      ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
      if (fullView && hasElements()) { drawFullView(); return; }
      if (fullView) { fullView = false; }
      const vp = sourceViewport();
      drawGrid(vp);
      drawPolygons(vp, polygons, selected && selected.type === "poly" ? selected : null);
      drawSources(vp);
      drawPlacing(vp);
      drawInProgress(vp);
      drawIndices(vp);
      drawAxes(vp);
      drawWsAnnotation(vp, WS, {});
    };

    const drawColorbar = () => {
      if (!colorbar) return;
      const rect = colorbar.getBoundingClientRect();
      const w = Math.max(1, Math.round(rect.width));
      const h = Math.max(1, Math.round(rect.height));
      colorbar.width = Math.round(w * dpr); colorbar.height = Math.round(h * dpr);
      const cb = colorbar.getContext("2d");
      cb.setTransform(dpr, 0, 0, dpr, 0, 0);
      cb.clearRect(0, 0, w, h);
      const grad = cb.createLinearGradient(0, 0, w, 0);
      for (let s = 0; s <= 10; s++) grad.addColorStop(s / 10, redsColor(s / 10));
      cb.fillStyle = grad; cb.fillRect(0, 0, w, h - 12);
      cb.strokeStyle = "#ccc"; cb.strokeRect(0.5, 0.5, w - 1, h - 12);
      cb.fillStyle = "#444"; cb.font = "10px sans-serif";
      cb.textBaseline = "bottom";
      cb.textAlign = "left"; cb.fillText("0", 1, h);
      cb.textAlign = "center"; cb.fillText("Electron donor concentration [mg/l]", w / 2, h);
      cb.textAlign = "right"; cb.fillText(fmt2(CONC_MAX), w - 1, h);
    };

    const updateInfo = () => {
      const e = selectedElem();
      if (!e) { setInfo(""); return; }
      const size = e.kind === "circle" ? `r = ${fmt2(e.r)} m`
        : e.kind === "ellipse" ? `a = ${fmt2(e.a)}, b = ${fmt2(e.b)} m`
        : `l = ${fmt2(e.l)} m, θ = ${fmt2(e.theta || 0)}°`;
      const label = selected.type === "source" ? e.kind : "circle";
      setInfo(`${label}  |  ${size}  |  c = ${fmt2(e.c)} mg/l  |  pos = (${fmt2(e.x)}, ${fmt2(e.y)})`);
    };

    // Resize backing store to displayed box (DPR-aware) and redraw.
    // If layout has not flushed yet (box ~0), defer to the next frame so the
    // first paint always lands once the flex box has real dimensions.
    const resize = () => {
      const b = box();
      if (b.width < 2 || b.height < 2) {
        if (typeof requestAnimationFrame !== "undefined") requestAnimationFrame(resize);
        return;
      }
      dpr = window.devicePixelRatio || 1;
      const pxW = Math.max(1, Math.round(b.width * dpr));
      const pxH = Math.max(1, Math.round(b.height * dpr));
      if (canvas.width !== pxW || canvas.height !== pxH) {
        canvas.width = pxW; canvas.height = pxH;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
      drawColorbar();
    };

    const TOOL_BTNS = ["polygon", "circle", "ellipse", "line", "select"];
    const TOOL_HINTS = {
      polygon: "POLYGON — left-click vertices, then 'Close & Pack' (right-click / Enter) to fill with circles.",
      circle: "CIRCLE — press and drag from the centre to set the radius.",
      ellipse: "ELLIPSE — press and drag to set the semi-axes (a horizontal, b vertical).",
      line: "LINE — press and drag from one end to the other.",
      select: "SELECT — click an element; drag to move, ↑↓ size (←→ ellipse b), +/- conc, Del remove, 'x' delete polygon.",
    };
    const setTool = (next) => {
      tool = next;
      mode = tool === "select" ? "edit" : "draw";
      selected = null; dragging = false; placing = null; dragOffset = [0, 0];
      if (tool !== "polygon") drawing = [];
      TOOL_BTNS.forEach((t) => {
        const btn = document.getElementById(`aem-tool-${t}`);
        if (btn) btn.classList.toggle("aem-btn--active", t === tool);
      });
      setStatus(TOOL_HINTS[tool] || "");
      updateInfo();
      draw();
    };
    // Back-compat shim for the existing draw/edit call sites.
    const setMode = (m) => setTool(m === "edit" ? "select" : "polygon");

    canvas.addEventListener("mousedown", (event) => {
      if (event.button === 1 || (event.button === 0 && event.shiftKey)) {
        panning = true; panStart = {x: event.clientX, y: event.clientY, ...view}; return;
      }
      if (event.button !== 0 || fullView) return;
      const point = toData(event);
      if (tool === "polygon") {
        drawing.push(snapDrawPoint(point));
        setStatus(`Vertex ${drawing.length} — right-click to close polygon.`);
        draw();
        return;
      }
      if (tool === "circle" || tool === "ellipse" || tool === "line") {
        const [sx, sy] = snapDrawPoint(point);
        placing = {kind: tool, x0: sx, y0: sy, x1: sx, y1: sy, id: newId()};
        draw();
        return;
      }
      // SELECT: pick nearest element (packed circle or standalone source).
      const found = hit(point);
      if (found) {
        selected = found; dragging = true;
        const e = selectedElem();
        dragOffset = [e.x - point[0], e.y - point[1]];
        updateInfo();
        setStatus("drag to move | ↑↓ size | +/- conc | Del remove");
      } else {
        selected = null; dragging = false;
        updateInfo();
        setStatus("SELECT — click an element to select it.");
      }
      draw();
    });
    canvas.addEventListener("mousemove", (event) => {
      if (panning && panStart) {
        const b = box();
        const dx = (event.clientX - panStart.x) / b.width * (panStart.xmax - panStart.xmin);
        const dy = (event.clientY - panStart.y) / b.height * (panStart.ymax - panStart.ymin);
        view.xmin = panStart.xmin - dx; view.xmax = panStart.xmax - dx;
        view.ymin = panStart.ymin + dy; view.ymax = panStart.ymax + dy; draw(); return;
      }
      if (placing) {
        const [x, y] = toData(event);
        placing.x1 = +x.toFixed(5); placing.y1 = +y.toFixed(5);
        draw(); return;
      }
      if (!dragging || !selected || tool !== "select") return;
      const [x, y] = toData(event); const e = selectedElem();
      e.x = +(x + dragOffset[0]).toFixed(5); e.y = +(y + dragOffset[1]).toFixed(5);
      updateInfo(); draw();
    });
    window.addEventListener("mouseup", () => {
      if (placing) {
        const s = placingToSource(placing, false);
        sources.push(s);
        selected = {type: "source", i: sources.length - 1};
        placing = null;
        updateInfo();
        setStatus(`${s.kind} placed — keep placing, or switch to Select to edit.`);
        draw();
      }
      dragging = false; panning = false;
    });
    canvas.addEventListener("wheel", (event) => {
      if (fullView) return;
      event.preventDefault(); const center = toData(event); const factor = event.deltaY < 0 ? 0.85 : 1.18;
      view.xmin = center[0] + (view.xmin - center[0]) * factor;
      view.xmax = center[0] + (view.xmax - center[0]) * factor;
      view.ymin = center[1] + (view.ymin - center[1]) * factor;
      view.ymax = center[1] + (view.ymax - center[1]) * factor; draw();
    }, {passive: false});
    // Close the in-progress polygon and fill it with circles. Triggered by the
    // "Close & Pack" button, a right-click, or Enter — so packing never depends
    // on the user discovering the right-click gesture.
    const packPolygon = async () => {
      if (fullView) { show("Leave View mode before packing.", true); return; }
      if (tool !== "polygon") { show("Switch to the Polygon tool to add and pack a polygon.", true); setTool("polygon"); return; }
      if (drawing.length < 3) {
        const msg = "Place at least 3 polygon vertices first (left-click on the canvas).";
        show(msg, true); setStatus(msg); return;
      }
      try {
        setStatus("Packing circles (greedy)...");
        const data = await post("/aem/api/pack", {vertices: drawing,
          default_c: +form.default_c.value, max_circles: 80});
        if (!data.circles.length) {
          show("That polygon is too small to fit any circles — draw a larger one.", true);
          setStatus("No circles fit — draw a larger polygon."); return;
        }
        polygons.push({vertices: drawing, circles: data.circles}); drawing = []; selected = null;
        setStatus(`${data.circles.length} circles packed. Switched to Select.`);
        show(`${data.circles.length} circles packed.`);
        setTool("select");
      } catch (error) { show(error.message, true); setStatus(error.message); }
    };
    canvas.addEventListener("contextmenu", (event) => { event.preventDefault(); packPolygon(); });
    window.addEventListener("keydown", async (event) => {
      const tag = document.activeElement ? document.activeElement.tagName : "";
      if (["INPUT", "SELECT"].includes(tag)) return;
      const key = event.key;
      const TOOL_KEYS = {"1": "polygon", "2": "circle", "3": "ellipse", "4": "line", "5": "select"};
      if (TOOL_KEYS[key]) { event.preventDefault(); setTool(TOOL_KEYS[key]); return; }
      if (key === "d") { event.preventDefault(); setTool("polygon"); return; }
      if (key === "e") { event.preventDefault(); setTool("select"); return; }
      if (key === "s") { event.preventDefault(); exportJson(); return; }
      if (key === "i") { event.preventDefault(); toggleIndices(); return; }
      if (key === "Escape") { event.preventDefault(); drawing = []; placing = null; setStatus("Cancelled."); draw(); return; }
      if (key === "n" && tool === "polygon") { event.preventDefault(); drawing = []; setStatus("New polygon — click to place vertices."); draw(); return; }
      if (key === "Enter" && tool === "polygon" && drawing.length >= 3) { event.preventDefault(); packPolygon(); return; }
      const elem = selectedElem();
      if (!elem) {
        if (["Backspace", " ", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(key)) event.preventDefault();
        return;
      }
      if (["Delete", "Backspace"].includes(key)) {
        event.preventDefault();
        if (selected.type === "source") sources.splice(selected.i, 1);
        else polygons[selected.p].circles.splice(selected.c, 1);
        selected = null; updateInfo(); setStatus("Element deleted."); draw(); return;
      }
      if (key === "x" && selected.type === "poly") { event.preventDefault(); polygons.splice(selected.p, 1); selected = null; updateInfo(); setStatus("Polygon deleted."); draw(); return; }
      if (["+", "="].includes(key)) { event.preventDefault(); elem.c = +(Math.max(0.1, elem.c + CONC_STEP)).toFixed(1); updateInfo(); draw(); return; }
      if (["-", "_"].includes(key)) { event.preventDefault(); elem.c = +(Math.max(0.1, elem.c - CONC_STEP)).toFixed(1); updateInfo(); draw(); return; }
      if (["ArrowLeft", "ArrowRight"].includes(key) && selected.type === "source" && elem.kind === "ellipse") {
        event.preventDefault();
        elem.b = Math.max(MIN_RADIUS, +(elem.b + (key === "ArrowRight" ? RADIUS_STEP : -RADIUS_STEP)).toFixed(5));
        updateInfo(); setStatus(`b → ${fmt2(elem.b)} m`); draw(); return;
      }
      if (["ArrowUp", "ArrowDown"].includes(key)) {
        event.preventDefault();
        const step = key === "ArrowUp" ? RADIUS_STEP : -RADIUS_STEP;
        if (selected.type === "source") {
          if (elem.kind === "circle") elem.r = Math.max(MIN_RADIUS, +(elem.r + step).toFixed(5));
          else if (elem.kind === "ellipse") elem.a = Math.max(MIN_RADIUS, +(elem.a + step).toFixed(5));
          else elem.l = Math.max(MIN_RADIUS, +(elem.l + 2 * step).toFixed(5));
          updateInfo(); setStatus("Resized."); draw(); return;
        }
        if (repacking) return;                       // ignore held arrows mid-repack
        const poly = polygons[selected.p];
        elem.r = Math.max(MIN_RADIUS, +(elem.r + step).toFixed(5));
        if (poly.vertices.length) {
          const changed = {x: elem.x, y: elem.y};
          repacking = true;
          try {
            const data = await post("/aem/api/repack", {vertices: poly.vertices,
              circles: poly.circles, changed_idx: selected.c});
            poly.circles = data.circles;
            const match = reselectCircle(poly.circles, changed);
            selected = match ? {type: "poly", p: selected.p, c: match.index} : null;
          }
          catch (error) { show(error.message, true); setStatus(error.message); }
          finally { repacking = false; }
        }
        updateInfo();
        setStatus(`Radius → ${fmt2(elem.r)} m`);
        draw();
        return;
      }
    });

    const exportJson = () => {
      const blob = new Blob([JSON.stringify(buildConfig(), null, 2)], {type: "application/json"});
      const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
      link.download = "source_config.json"; link.click(); URL.revokeObjectURL(link.href);
    };

    TOOL_BTNS.forEach((t) => {
      const btn = document.getElementById(`aem-tool-${t}`);
      if (btn) btn.addEventListener("click", () => setTool(t));
    });
    const packBtn = document.getElementById("aem-pack");
    if (packBtn) packBtn.addEventListener("click", packPolygon);
    document.getElementById("aem-clear").addEventListener("click", () => {
      polygons.length = 0; sources.length = 0; drawing = []; placing = null; selected = null; fullView = false;
      setTool("polygon"); updateInfo(); setStatus("Cleared all sources."); draw();
    });
    const importInput = document.getElementById("aem-import");
    document.getElementById("aem-import-trigger").addEventListener("click", (event) => {
      event.preventDefault();
      importInput.value = "";
      importInput.click();
    });
    importInput.addEventListener("change", async () => {
      try {
        if (!importInput.files || !importInput.files[0]) return;
        const config = JSON.parse(await importInput.files[0].text());
        if (!Array.isArray(config.elements) || !config.elements.length) {
          throw new Error("Imported AEM designs must contain circle, ellipse, or line elements.");
        }
        const importedElements = config.elements.map(normalizeImportedElement);
        ["orientation", "alpha_l", "alpha_t", "ca", "gamma", "dom_inc", "num_cp", "num_terms", "ws", "plot_aspect"].forEach((name) => {
          if (config[name] !== undefined && form.elements[name]) form.elements[name].value = config[name];
        });
        if (form.elements.orientation) {
          const importedOrientation = String(form.elements.orientation.value || "").toLowerCase();
          form.elements.orientation.value = importedOrientation === "horizontal" ? "horizontal" : "vertical";
        }
        syncSettings(); syncOrientationLabel();
        polygons.length = 0; sources.length = 0;
        importedElements.forEach((element) => sources.push(element));
        // Remember the file's own domain bounds so the run frames exactly as the
        // file specifies (matching main.py in the source), unless the geometry is edited.
        const domainKeys = ["dom_xmin", "dom_xmax", "dom_ymin", "dom_ymax"];
        importedDomain = domainKeys.every((k) => Number.isFinite(config[k]))
          ? Object.fromEntries(domainKeys.map((k) => [k, config[k]])) : null;
        importedSig = importedDomain ? geomSignature() : null;
        drawing = []; selected = null; fitSource();
        show(`Imported ${config.elements.length} source element(s).`);
        setStatus(`Imported ${config.elements.length} element(s).`);
        setTool("select"); draw();
      } catch (error) { show(`Invalid AEM JSON: ${error.message}`, true); }
      importInput.value = "";
    });
    document.getElementById("aem-export").addEventListener("click", exportJson);
    const indexBtn = document.getElementById("aem-index");
    const toggleIndices = () => {
      showIndices = !showIndices;
      if (indexBtn) indexBtn.classList.toggle("aem-btn--active", showIndices);
      setStatus(`Index labels ${showIndices ? "on" : "off"}.`);
      draw();
    };
    if (indexBtn) indexBtn.addEventListener("click", toggleIndices);

    // ── Simulation Settings panel ────────────────────────────────────────────
    // Mirrors source_designer.py:SettingsPanel — live apply with ✓/error feedback,
    // and an orientation toggle that re-frames the canvas.
    const settingsMsg = document.getElementById("aem-settings-msg");
    const showSettingsMsg = (text, ok) => {
      if (!settingsMsg) return;
      settingsMsg.textContent = text;
      settingsMsg.classList.toggle("aem-settings-msg--ok", ok);
      settingsMsg.classList.toggle("aem-settings-msg--error", !ok);
    };
    // Per-field validators, matching SettingsPanel.FIELDS in the reference.
    const FIELD_RULES = {
      alpha_l: (v) => v > 0, alpha_t: (v) => v > 0, ca: () => true,
      gamma: (v) => v > 0, dom_inc: (v) => v > 0,
      num_cp: (v) => v >= 1, num_terms: (v) => v >= 1, ws: (v) => v > 0,
    };
    const applyField = (name) => {
      const input = form.elements[name];
      if (!input) return;
      if (name === "plot_aspect") { showSettingsMsg(`aspect = ${input.value || "(auto)"}  ✓`, true); return; }
      const value = +input.value;
      const rule = FIELD_RULES[name];
      if (!Number.isFinite(value) || (rule && !rule(value))) {
        showSettingsMsg(`${name}: invalid value`, false); return;
      }
      // num_cp must stay ≥ num_terms (reference validate_for_export).
      if (name === "num_cp" || name === "num_terms") {
        const ncp = +form.elements.num_cp.value, nt = +form.elements.num_terms.value;
        if (Number.isFinite(ncp) && Number.isFinite(nt) && ncp < nt) {
          showSettingsMsg(`ctrl pts (${ncp}) must be ≥ terms (${nt})`, false); return;
        }
      }
      // Normalise the field to at most 2 displayed decimals (whole numbers bare).
      input.value = fmt2(value);
      if (name === "ws") { syncSettings(); reframeView(); draw(); }
      // Non-blocking dispersivity-ratio warning (reference warnings_for_export).
      if (name === "alpha_l" || name === "alpha_t") {
        const al = +form.elements.alpha_l.value, at = +form.elements.alpha_t.value;
        const ratio = al / at;
        if (at > 0 && (ratio > 100 || ratio < 1)) {
          showSettingsMsg(`alpha_l/alpha_t = ${ratio.toFixed(1)} is extreme — thin/wide plumes can be slow to solve.`, false);
          return;
        }
      }
      showSettingsMsg(`${name} = ${fmt2(value)}  ✓`, true);
    };
    ["alpha_l", "alpha_t", "ca", "gamma", "dom_inc", "num_cp", "num_terms", "ws", "plot_aspect"]
      .forEach((name) => {
        const input = form.elements[name];
        if (input) input.addEventListener("change", () => applyField(name));
      });
    const orientBtn = document.getElementById("aem-orientation");
    const syncOrientationLabel = () => { if (orientBtn) orientBtn.textContent = `Orientation: ${orientation()}`; };
    if (orientBtn) orientBtn.addEventListener("click", () => {
      form.elements.orientation.value = orientation() === "vertical" ? "horizontal" : "vertical";
      syncOrientationLabel(); syncSettings(); reframeView();
      showSettingsMsg(`orientation = ${orientation()}  ✓`, true);
      setStatus(TOOL_HINTS[tool] || ""); draw();
    });

    // Highest y the solver sees for an element (mirrors designer_model._elem_solver_top);
    // in vertical orientation every element must sit below the water table (top < -0.1).
    const elemSolverTop = (e) => {
      if (e.kind === "circle") return e.y + (+e.r || 0);
      const th = ((e.theta != null ? e.theta : 90) || 0) * Math.PI / 180;
      if (e.kind === "ellipse") return e.y + (+e.a || 0) * Math.abs(Math.sin(th));
      return e.y + (+e.l || 0) / 2 * Math.abs(Math.sin(th));
    };

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!hasElements()) { show("Add at least one source first (draw a shape or pack a polygon).", true); setStatus("Nothing to submit — add a source."); return; }
      // Instant feedback for the obvious cases; the server re-checks everything.
      const ncp = +form.elements.num_cp.value, nt = +form.elements.num_terms.value;
      if (Number.isFinite(ncp) && Number.isFinite(nt) && ncp < nt) {
        show(`num_cp (${ncp}) must be >= num_terms (${nt}).`, true);
        setStatus("Fix the simulation settings before running."); return;
      }
      if (orientation() === "vertical") {
        const above = allElementDicts().filter((e) => elemSolverTop(e) >= -0.1);
        if (above.length) {
          show(`${above.length} source(s) too close to the water table — in vertical orientation every source `
            + "(its top edge included) must sit at least 0.1 m below the water table (y = 0).", true);
          setStatus("Move sources at least 0.1 m below the water table before running."); return;
        }
      }
      try {
        show("Saving source design..."); const data = await post("/aem/api/design", {config: buildConfig()});
        window.location.assign(data.forward_url);
      } catch (error) { show(error.message, true); }
    });

    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => resize()).observe(canvas);
    }
    window.addEventListener("resize", resize);
    // Initialise the drawing frame from the form's default settings (vertical, Ws=0.5).
    syncSettings(); reframeView(); syncOrientationLabel();
    setMode("draw");
    resize();
  }

  const renderSummary = (result) => {
    const summary = document.getElementById("aem-summary"); summary.innerHTML = "";
    Object.entries(result).filter(([key, value]) => !["field", "xaxis", "yaxis"].includes(key) && value !== null)
      .forEach(([key, value]) => { const dt = document.createElement("dt"); dt.textContent = key.replaceAll("_", " ");
        const dd = document.createElement("dd"); dd.textContent = typeof value === "number" ? fmt2(value) : String(value); summary.append(dt, dd); });
  };
  // Render the concentration field the way the source simulation does
  // (at_simulation.py: contourf): discrete filled bands — electron donor (C >= 0)
  // in Reds (0..max), electron acceptor (C < 0) in Blues_r (0..|min|) — plus a
  // black zero-concentration interface line and stepped donor/acceptor colorbars.
  // The coarse grid is interpolated up to display resolution and then quantised to
  // bands, so boundaries are smooth and crisp like contourf instead of a blurry
  // upscaled bitmap.
  const DONOR_BANDS = 10, ACC_BANDS = 8;   // 11 donor / 9 acceptor levels, like the source
  // Tick values in [lo, hi], reproducing matplotlib's MaxNLocator: choose the
  // smallest "nice" step (from its default multiplier set) that is >= range/nbins,
  // then place ticks at integer multiples of that step. This matches the
  // reference plot's axes exactly (e.g. x-range ~27, nbins=7 -> step 4 -> 0,4,..,24).
  const NICE_STEPS = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
  const niceTicks = (lo, hi, nbins) => {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const rawStep = span / nbins;
    const scale = Math.pow(10, Math.floor(Math.log10(rawStep)));
    let step = 10 * scale;
    for (const m of NICE_STEPS) { if (m * scale >= rawStep) { step = m * scale; break; } }
    const ticks = [];
    const kStart = Math.ceil(lo / step - 1e-9), kEnd = Math.floor(hi / step + 1e-9);
    for (let k = kStart; k <= kEnd; k++) {
      const v = k * step;
      ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    }
    return ticks;
  };
  const fmtTick = (v) => fmt2(v);
  const renderField = (result) => {
    if (!result.field || !result.field.length || !result.xaxis?.length || !result.yaxis?.length) return;
    const canvas = document.getElementById("aem-result-canvas");
    // Size the backing store to the displayed width (× DPR) so the plot is crisp
    // instead of a CSS-upscaled 1000px bitmap. Layout constants below were tuned for
    // a 1000-wide canvas, so scale them all by s.
    const BASE_W = 1000, BASE_H = 660, dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(BASE_W, Math.round((canvas.clientWidth || BASE_W) * dpr));
    canvas.height = Math.round(canvas.width * BASE_H / BASE_W);
    const s = canvas.width / BASE_W;
    const ctx = canvas.getContext("2d");
    const field = result.field; const rows = field.length, cols = field[0].length;
    let min = Infinity, max = -Infinity;
    field.forEach((row) => row.forEach((v) => { if (Number.isFinite(v)) { min = Math.min(min, v); max = Math.max(max, v); } }));
    const maxDonor = max > 0 ? max : 1;          // donor band scale 0..max
    const minAcc = min < 0 ? min : -1;            // acceptor band scale 0..|min|

    // Bottom margin (175·s) holds the x-axis label plus two stacked, full-width
    // colorbars (acceptor over donor), matching the reference matplotlib layout.
    const plot = {left: 80 * s, top: 35 * s, width: canvas.width - 160 * s, height: canvas.height - 210 * s};
    const xs = result.xaxis, ys = result.yaxis;
    const xmin = xs[0], xmax = xs[xs.length - 1];
    const ymin = ys[0], ymax = ys[ys.length - 1];
    const xPix = (v) => plot.left + (v - xmin) / (xmax - xmin) * plot.width;
    const yPix = (v) => plot.top + (ymax - v) / (ymax - ymin) * plot.height;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Filled contour bands as true vector polygons, matching matplotlib contourf:
    // each grid quad is split into 4 triangles about its centre and linearly
    // interpolated, then every triangle is clipped to each [lo,hi] band and
    // filled. This reproduces contourf's straight, triangulated band edges
    // instead of a quantised raster bitmap.
    //
    // Clip a convex polygon of [x,y,v] vertices to the half-space v>=t (keepGE)
    // or v<=t; new vertices are interpolated on crossed edges. The field is
    // linear across a triangle, so each threshold is a single straight cut.
    const clipPoly = (poly, t, keepGE) => {
      const out = [], inside = (v) => keepGE ? v >= t : v <= t;
      for (let i = 0; i < poly.length; i++) {
        const A = poly[i], B = poly[(i + 1) % poly.length];
        const ina = inside(A[2]), inb = inside(B[2]);
        if (ina) out.push(A);
        if (ina !== inb) {
          const f = (t - A[2]) / (B[2] - A[2]);
          out.push([A[0] + (B[0] - A[0]) * f, A[1] + (B[1] - A[1]) * f, t]);
        }
      }
      return out;
    };
    const fillBand = (poly, lo, hi, col) => {
      let p = clipPoly(poly, lo, true); if (p.length < 3) return;
      p = clipPoly(p, hi, false); if (p.length < 3) return;
      ctx.fillStyle = ctx.strokeStyle = `rgb(${col[0]},${col[1]},${col[2]})`;
      ctx.beginPath(); ctx.moveTo(p[0][0], p[0][1]);
      for (let k = 1; k < p.length; k++) ctx.lineTo(p[k][0], p[k][1]);
      ctx.closePath(); ctx.fill();
      ctx.stroke();   // hairline same-colour stroke hides AA seams between polys
    };
    // Visit each quad's 4 centre-triangles, invoking cb([A,B,C]) per triangle.
    const eachTriangle = (cb) => {
      for (let r = 0; r < rows - 1; r++) {
        for (let c = 0; c < cols - 1; c++) {
          const v00 = field[r][c], v01 = field[r][c + 1], v10 = field[r + 1][c], v11 = field[r + 1][c + 1];
          if (!(Number.isFinite(v00) && Number.isFinite(v01) && Number.isFinite(v10) && Number.isFinite(v11))) continue;
          const xL = xPix(xs[c]), xR = xPix(xs[c + 1]), yB = yPix(ys[r]), yT = yPix(ys[r + 1]);
          const p00 = [xL, yB, v00], p01 = [xR, yB, v01], p11 = [xR, yT, v11], p10 = [xL, yT, v10];
          const pc = [(xL + xR) / 2, (yB + yT) / 2, (v00 + v01 + v10 + v11) / 4];
          cb([p00, p01, pc]); cb([p01, p11, pc]); cb([p11, p10, pc]); cb([p10, p00, pc]);
        }
      }
    };
    const contourf = (levels, bands, colorForBand) => {
      eachTriangle((tri) => {
        for (let i = 0; i < bands; i++) fillBand(tri, levels[i], levels[i + 1], colorForBand(i));
      });
    };
    ctx.lineWidth = Math.max(0.6, 0.6 * s); ctx.lineJoin = "round";
    if (max > 0) {   // donor: levels 0..max, Reds (light->dark)
      const dl = []; for (let i = 0; i <= DONOR_BANDS; i++) dl.push((i / DONOR_BANDS) * maxDonor);
      contourf(dl, DONOR_BANDS, (i) => sampleStops(REDS_STOPS, (i + 0.5) / DONOR_BANDS));
    }
    if (min < 0) {   // acceptor: levels -|min|..0, Blues_r (dark->light)
      const al = []; for (let i = 0; i <= ACC_BANDS; i++) al.push(minAcc - (i / ACC_BANDS) * minAcc);
      // Band i is the i-th interval up from |min| (most negative first), so the
      // colour fraction is flipped: most-negative -> darkest (Blues_r).
      contourf(al, ACC_BANDS, (i) => sampleStops(BLUES_STOPS, 1 - (i + 0.5) / ACC_BANDS));
    }

    // Black zero-concentration interface line (plume envelope): the 0-level
    // contour drawn as straight per-triangle segments — matplotlib's vector
    // contour(levels=[0], linewidths=2), not a thresholded pixel trace.
    ctx.strokeStyle = "#000"; ctx.lineWidth = Math.max(1.5, 2 * s);
    ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.beginPath();
    eachTriangle((tri) => {
      const pts = [];
      for (let i = 0; i < 3; i++) {
        const A = tri[i], B = tri[(i + 1) % 3];
        if ((A[2] < 0) !== (B[2] < 0)) {
          const f = (0 - A[2]) / (B[2] - A[2]);
          pts.push([A[0] + (B[0] - A[0]) * f, A[1] + (B[1] - A[1]) * f]);
        }
      }
      if (pts.length === 2) { ctx.moveTo(pts[0][0], pts[0][1]); ctx.lineTo(pts[1][0], pts[1][1]); }
    });
    ctx.stroke();

    // Axes — matplotlib-style: "x (m)" plus orientation-specific "y (m)" (horizontal)
    // or "z (m)" (vertical), with several evenly-spaced "nice" ticks, not just the ends.
    ctx.strokeStyle = "#26384d"; ctx.fillStyle = "#26384d"; ctx.lineWidth = Math.max(1, s);
    ctx.strokeRect(plot.left, plot.top, plot.width, plot.height);
    ctx.font = `${Math.round(13 * s)}px sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
    niceTicks(xmin, xmax, 7).forEach((v) => {
      if (v < xmin || v > xmax) return; const px = xPix(v);
      ctx.beginPath(); ctx.moveTo(px, plot.top + plot.height); ctx.lineTo(px, plot.top + plot.height + 5 * s); ctx.stroke();
      ctx.fillText(fmtTick(v), px, plot.top + plot.height + 20 * s);
    });
    ctx.textAlign = "right";
    niceTicks(ymin, ymax, 5).forEach((v) => {
      if (v < ymin || v > ymax) return; const py = yPix(v);
      ctx.beginPath(); ctx.moveTo(plot.left - 5 * s, py); ctx.lineTo(plot.left, py); ctx.stroke();
      ctx.fillText(fmtTick(v), plot.left - 8 * s, py + 4 * s);
    });
    ctx.textAlign = "center"; ctx.font = `${Math.round(15 * s)}px sans-serif`;
    ctx.fillText("x (m)", plot.left + plot.width / 2, plot.top + plot.height + 40 * s);
    ctx.save(); ctx.translate(18 * s, plot.top + plot.height / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText(result.orientation === "vertical" ? "z (m)" : "y (m)", 0, 0); ctx.restore();

    // Two stacked, full-width colorbars matching the reference matplotlib layout
    // (at_simulation.py: fig.colorbar location="bottom"): the acceptor bar
    // (Blues_r, extend="min", left arrow, ticks |min|..0) sits above the donor
    // bar (Reds, extend="max", right arrow, ticks 0..max). Tick marks at every
    // contour level with numeric labels, plus a centered axis title.
    const drawCbar = (top, bands, sampleBand, capColor, capSide, labelAt, title) => {
      const x0 = plot.left, w = plot.width, barH = 12 * s, cap = 9 * s;
      const stepX0 = capSide === "min" ? x0 + cap : x0;
      const stepW = w - cap, bw = stepW / bands;
      for (let b = 0; b < bands; b++) {
        const c = sampleBand(b);
        ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`;
        ctx.fillRect(stepX0 + b * bw, top, bw + 0.7, barH);
      }
      // Extend triangle cap (the matplotlib over/under colour) on the dark end.
      ctx.fillStyle = `rgb(${capColor[0]},${capColor[1]},${capColor[2]})`;
      ctx.beginPath();
      if (capSide === "max") { ctx.moveTo(x0 + w - cap, top); ctx.lineTo(x0 + w, top + barH / 2); ctx.lineTo(x0 + w - cap, top + barH); }
      else { ctx.moveTo(x0 + cap, top); ctx.lineTo(x0, top + barH / 2); ctx.lineTo(x0 + cap, top + barH); }
      ctx.closePath(); ctx.fill();
      ctx.strokeStyle = "#26384d"; ctx.lineWidth = Math.max(1, 0.7 * s);
      ctx.strokeRect(stepX0, top, stepW, barH);
      // Tick marks + numeric labels at every level boundary.
      ctx.fillStyle = "#26384d"; ctx.font = `${Math.round(11 * s)}px sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "top";
      for (let i = 0; i <= bands; i++) {
        const x = stepX0 + i * bw;
        ctx.beginPath(); ctx.moveTo(x, top + barH); ctx.lineTo(x, top + barH + 4 * s); ctx.stroke();
        ctx.fillText(labelAt(i), x, top + barH + 6 * s);
      }
      ctx.font = `${Math.round(12 * s)}px sans-serif`; ctx.textBaseline = "alphabetic";
      ctx.fillText(title, x0 + w / 2, top + barH + 28 * s);
    };
    const plotBottom = plot.top + plot.height;
    // Acceptor bar (upper): dark blue (|min|) on the left, fading to white (0).
    drawCbar(plotBottom + 58 * s, ACC_BANDS,
      (b) => sampleStops(BLUES_STOPS, 1 - (b + 0.5) / ACC_BANDS),
      sampleStops(BLUES_STOPS, 1), "min",
      (i) => fmt2(Math.abs(minAcc) * (1 - i / ACC_BANDS)),
      "Electron acceptor concentration [mg/l]");
    // Donor bar (lower): white (0) on the left, deepening to dark red (max).
    drawCbar(plotBottom + 110 * s, DONOR_BANDS,
      (b) => sampleStops(REDS_STOPS, (b + 0.5) / DONOR_BANDS),
      sampleStops(REDS_STOPS, 1), "max",
      (i) => fmt2(i * maxDonor / DONOR_BANDS),
      "Electron donor concentration [mg/l]");

    // Full-height dashed L_max marker + upper-right legend, matching the reference
    // (source_designer.py: ax.axvline(L_max, navy, dashed) + legend "upper right").
    if (Number.isFinite(result.L_max) && result.L_max >= xmin && result.L_max <= xmax) {
      const lx = xPix(result.L_max);
      const dash = [5 * s, 4 * s], navy = "#000080", lw = Math.max(1.6, 2.4 * s);
      ctx.save();
      ctx.strokeStyle = navy; ctx.lineWidth = lw; ctx.setLineDash(dash);
      ctx.beginPath(); ctx.moveTo(lx, plot.top); ctx.lineTo(lx, plot.top + plot.height); ctx.stroke();
      ctx.setLineDash([]);
      // Legend box in the upper-right corner.
      const text = `L_max = ${fmt2(result.L_max)} m`;
      ctx.font = `${Math.round(12 * s)}px sans-serif`;
      const tw = ctx.measureText(text).width;
      const padX = 8 * s, sample = 22 * s, gap = 6 * s, boxH = 24 * s;
      const boxW = padX * 2 + sample + gap + tw;
      const bx = plot.left + plot.width - boxW - 8 * s, by = plot.top + 8 * s;
      ctx.fillStyle = "rgba(255,255,255,0.78)"; ctx.strokeStyle = "#c2c2c2"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.rect(bx, by, boxW, boxH); ctx.fill(); ctx.stroke();
      ctx.strokeStyle = navy; ctx.lineWidth = lw; ctx.setLineDash(dash);
      ctx.beginPath(); ctx.moveTo(bx + padX, by + boxH / 2); ctx.lineTo(bx + padX + sample, by + boxH / 2); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#111"; ctx.textBaseline = "middle"; ctx.textAlign = "left";
      ctx.fillText(text, bx + padX + sample + gap, by + boxH / 2);
      ctx.restore();
    }
  };
  async function runJob(endpoint, payload) {
    const cancel = document.getElementById("aem-cancel");
    const actions = document.getElementById("aem-result-actions");
    const csvLink = document.getElementById("aem-download-csv");
    const workbenchLink = document.getElementById("aem-open-workbench");
    if (actions) actions.hidden = true;
    try {
      const submitted = await post(endpoint, payload); cancel.hidden = false;
      cancel.onclick = () => post(submitted.cancel_url, {}).then(() => show("Job cancelled."));
      while (true) {
        const status = await json(submitted.status_url); show(`Simulation ${status.status}${status.queue_position ? ` (queue position ${status.queue_position})` : ""}...`);
        if (status.status === "done") break; if (["failed", "cancelled"].includes(status.status)) throw new Error(status.error || `Job ${status.status}.`);
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      const completed = await json(submitted.result_url); cancel.hidden = true; show("Simulation complete."); renderSummary(completed.result); renderField(completed.result);
      if (csvLink) csvLink.hidden = !completed.csv_url;
      if (workbenchLink) workbenchLink.hidden = !completed.workbench_url;
      if (completed.csv_url && csvLink) csvLink.href = completed.csv_url;
      if (completed.workbench_url && workbenchLink) workbenchLink.href = completed.workbench_url;
      if (actions) actions.hidden = !(completed.csv_url || completed.workbench_url);
    } catch (error) { cancel.hidden = true; show(error.message, true); }
  }
  if (root.dataset.aemPage === "designer") designer();
  if (root.dataset.aemPage === "forward") runJob("/aem/api/forward", {design: root.dataset.designToken});
  if (root.dataset.aemPage === "inverse") document.getElementById("aem-inverse-form").addEventListener("submit", (event) => {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget));
    ["target_Lmax", "r", "C0", "ca", "gamma", "tolerance"].forEach((name) => payload[name] = +payload[name]); runJob("/aem/api/inverse", payload);
  });
})();
