(() => {
  "use strict";

  const GRID_SPACING = 0.05;
  const SNAP_TO_GRID = true;
  const roundHalfEven = (value) => {
    const lower = Math.floor(value);
    const fraction = value - lower;
    if (fraction === 0.5) return lower % 2 === 0 ? lower : lower + 1;
    return Math.round(value);
  };
  const snapDrawPoint = ([x, y]) => {
    const snappedX = SNAP_TO_GRID ? roundHalfEven(x / GRID_SPACING) * GRID_SPACING : x;
    const snappedY = SNAP_TO_GRID ? roundHalfEven(y / GRID_SPACING) * GRID_SPACING : y;
    return [Math.max(0, Math.min(0.5, +snappedX.toFixed(10))),
      Math.max(0, +snappedY.toFixed(10))];
  };
  const reselectCircle = (circles, changed) => {
    const index = circles.findIndex((circle) =>
      Math.abs(circle.x - changed.x) <= 1e-9 && Math.abs(circle.y - changed.y) <= 1e-9);
    return index < 0 ? null : {index, circle: circles[index]};
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {roundHalfEven, snapDrawPoint, reselectCircle};
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

  function referenceConfig(circles, values) {
    const elements = circles.map((circle, index) => ({
      kind: "circle", x: +circle.x, y: +circle.y, r: +circle.r, c: +circle.c,
      id: circle.id || `src_${index}`
    }));
    const base = {
      alpha_l: +values.alpha_l, alpha_t: +values.alpha_t, ca: +values.ca,
      gamma: +values.gamma, dom_inc: +values.dom_inc, num_cp: +values.num_cp,
      num_terms: +values.num_terms, orientation: values.orientation,
      plot_aspect: "", elements
    };
    if (!elements.length) return base;
    const maxR = Math.max(...elements.map((element) => element.r));
    if (values.orientation === "vertical") {
      const shift = Math.max(...elements.map((element) => element.y)) + maxR + 0.15;
      if (shift > 0) elements.forEach((element) => { element.y = +(element.y - shift).toFixed(5); });
    }
    const xs = elements.map((element) => element.x);
    const ys = elements.map((element) => element.y);
    return {
      ...base,
      dom_xmin: +(Math.min(...xs) - maxR - 2).toFixed(3),
      dom_xmax: +(Math.max(...xs) + 150).toFixed(1),
      dom_ymin: +(Math.min(...ys) - maxR - 5).toFixed(3),
      dom_ymax: values.orientation === "vertical" ? 0 : +(Math.max(...ys) + maxR + 5).toFixed(3),
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
    const WS = 0.5;
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
    const polygons = [];
    let drawing = [];
    let selected = null;          // {p, c} keyed by (polygonIndex, circleIndex)
    let dragOffset = [0, 0];
    let dragging = false;
    let panning = false;
    let panStart = null;
    let mode = "draw";            // "draw" | "edit"
    let fullView = false;
    let repacking = false;        // re-entrancy guard for radius repacks
    let dpr = 1;
    const view = {xmin: -0.05, xmax: WS + 0.05, ymin: -0.1, ymax: WS + 0.1};

    let importedDomain = null;   // explicit dom_* carried from an imported design
    let importedSig = null;      // geometry signature when importedDomain was captured
    const formValues = () => Object.fromEntries(new FormData(form));
    const allCircles = () => polygons.flatMap((polygon) => polygon.circles);
    const geomSignature = () => allCircles().map((c) => `${c.x},${c.y},${c.r}`).join(";");
    const buildConfig = () => {
      const config = referenceConfig(allCircles(), formValues());
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
      const circles = allCircles(); if (!circles.length) return;
      const padding = Math.max(0.05, ...circles.map((circle) => circle.r * 2));
      view.xmin = Math.min(...circles.map((circle) => circle.x - circle.r)) - padding;
      view.xmax = Math.max(...circles.map((circle) => circle.x + circle.r)) + padding;
      view.ymin = Math.min(...circles.map((circle) => circle.y - circle.r)) - padding;
      view.ymax = Math.max(...circles.map((circle) => circle.y + circle.r)) + padding;
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
    const hit = (point) => {
      let best = Infinity, found = null;
      for (let p = 0; p < polygons.length; p++) {
        for (let c = 0; c < polygons[p].circles.length; c++) {
          const circle = polygons[p].circles[c];
          const dist = Math.hypot(point[0] - circle.x, point[1] - circle.y);
          if (dist <= circle.r * 1.5 && dist < best) { best = dist; found = {p, c}; }
        }
      }
      return found;
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
      const label = `Ws = ${ws.toFixed(3)} m`;
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
        ctx.fillText(xv.toFixed(Math.abs(xv) >= 10 ? 0 : 2), px, panelTop + panelH + 2);
      }
      ctx.textAlign = "right"; ctx.textBaseline = "middle";
      for (let i = 0; i <= ny; i++) {
        const yv = vp.bounds.ymin + (vp.bounds.ymax - vp.bounds.ymin) * (i / ny);
        const [, py] = toPixel([0, yv], vp);
        ctx.fillText(yv.toFixed(Math.abs(yv) >= 10 ? 0 : 2), panelLeft - 2, py);
      }
      ctx.restore();
    };

    // View is a read-only refresh of the SAME polygons/circles in both panels
    // (matches source_designer.py ViewWindow: identical coordinate set, the
    // domain panel just frames them within the full simulation extents).
    const drawFullView = () => {
      const b = box();
      const raw = allCircles();
      const splitX = b.width * 0.30;
      const panelH = b.height - 56;
      const panelTop = 30;
      // Shared y-range and source width from the SAME (unshifted) circles.
      const ws = Math.max(WS, ...raw.map((c) => c.x + c.r));
      const allX = raw.map((c) => c.x);
      const ymin = Math.min(...raw.map((c) => c.y - c.r));
      const ymax = Math.max(...raw.map((c) => c.y + c.r));
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
      drawCircleList(srcVp, raw);
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
      drawCircleList(domVp, raw);
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
      if (fullView && allCircles().length) { drawFullView(); return; }
      if (fullView) { fullView = false; }
      const vp = sourceViewport();
      drawGrid(vp);
      drawPolygons(vp, polygons, selected);
      drawInProgress(vp);
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
      cb.textAlign = "right"; cb.fillText(String(CONC_MAX), w - 1, h);
    };

    const updateInfo = () => {
      if (!selected) { setInfo(""); return; }
      const c = polygons[selected.p].circles[selected.c];
      setInfo(`Circle ${selected.c}  |  r = ${c.r.toFixed(4)} m  |  c = ${c.c.toFixed(1)} mg/l  |  pos = (${c.x.toFixed(4)}, ${c.y.toFixed(4)})`);
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

    const setMode = (next) => {
      mode = next;
      selected = null; dragging = false; dragOffset = [0, 0];
      const drawBtn = document.getElementById("aem-mode-draw");
      const editBtn = document.getElementById("aem-mode-edit");
      if (drawBtn) drawBtn.classList.toggle("aem-btn--active", mode === "draw");
      if (editBtn) editBtn.classList.toggle("aem-btn--active", mode === "edit");
      if (mode === "draw") {
        setStatus("DRAW — left-click to add vertices, then 'Close & Pack polygon' (or right-click / Enter). Scroll = zoom, Shift+drag = pan.");
      } else {
        setStatus("EDIT — click circle, ↑↓ radius, +/- conc, Del remove, 'x' delete polygon.");
      }
      updateInfo();
      draw();
    };

    canvas.addEventListener("mousedown", (event) => {
      if (event.button === 1 || (event.button === 0 && event.shiftKey)) {
        panning = true; panStart = {x: event.clientX, y: event.clientY, ...view}; return;
      }
      if (event.button !== 0 || fullView) return;
      const point = toData(event);
      if (mode === "draw") {
        drawing.push(snapDrawPoint(point));
        setStatus(`Vertex ${drawing.length} — right-click to close polygon.`);
        draw();
        return;
      }
      // EDIT: select nearest circle, else deselect (no stray vertices).
      const found = hit(point);
      if (found) {
        selected = found; dragging = true;
        const circle = polygons[found.p].circles[found.c];
        dragOffset = [circle.x - point[0], circle.y - point[1]];
        updateInfo();
        setStatus("↑↓ radius | +/- conc | Del remove | drag to move");
      } else {
        selected = null; dragging = false;
        updateInfo();
        setStatus("EDIT — click a circle to select it.");
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
      if (!dragging || !selected || mode !== "edit") return;
      const [x, y] = toData(event); const circle = polygons[selected.p].circles[selected.c];
      circle.x = +(x + dragOffset[0]).toFixed(5); circle.y = +(y + dragOffset[1]).toFixed(5);
      updateInfo(); draw();
    });
    window.addEventListener("mouseup", () => { dragging = false; panning = false; });
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
      if (mode !== "draw") { show("Switch to Draw mode to add and pack a polygon.", true); setMode("draw"); return; }
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
        setStatus(`${data.circles.length} circles packed. Switched to Edit mode.`);
        show(`${data.circles.length} circles packed.`);
        setMode("edit");
      } catch (error) { show(error.message, true); setStatus(error.message); }
    };
    canvas.addEventListener("contextmenu", (event) => { event.preventDefault(); packPolygon(); });
    window.addEventListener("keydown", async (event) => {
      const tag = document.activeElement ? document.activeElement.tagName : "";
      if (["INPUT", "SELECT"].includes(tag)) return;
      const key = event.key;
      if (key === "d") { event.preventDefault(); setMode("draw"); return; }
      if (key === "e") { event.preventDefault(); setMode("edit"); return; }
      if (key === "v") { event.preventDefault(); toggleView(); return; }
      if (key === "s") { event.preventDefault(); exportJson(); return; }
      if (key === "Escape") { event.preventDefault(); drawing = []; setStatus("Drawing cancelled."); draw(); return; }
      if (key === "n" && mode === "draw") { event.preventDefault(); drawing = []; setStatus("New polygon — click to place vertices."); draw(); return; }
      if (key === "Enter" && mode === "draw" && drawing.length >= 3) { event.preventDefault(); packPolygon(); return; }
      if (!selected) {
        if (["Backspace", " ", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(key)) event.preventDefault();
        return;
      }
      const poly = polygons[selected.p]; const circle = poly.circles[selected.c];
      if (["Delete", "Backspace"].includes(key)) { event.preventDefault(); poly.circles.splice(selected.c, 1); selected = null; updateInfo(); setStatus("Circle deleted."); draw(); return; }
      if (key === "x") { event.preventDefault(); polygons.splice(selected.p, 1); selected = null; updateInfo(); setStatus("Polygon deleted."); draw(); return; }
      if (["+", "="].includes(key)) { event.preventDefault(); circle.c = +(Math.max(0.1, circle.c + CONC_STEP)).toFixed(1); updateInfo(); draw(); return; }
      if (["-", "_"].includes(key)) { event.preventDefault(); circle.c = +(Math.max(0.1, circle.c - CONC_STEP)).toFixed(1); updateInfo(); draw(); return; }
      if (["ArrowUp", "ArrowDown"].includes(key)) {
        event.preventDefault();
        if (repacking) return;                       // ignore held arrows mid-repack
        circle.r = Math.max(MIN_RADIUS, +(circle.r + (key === "ArrowUp" ? RADIUS_STEP : -RADIUS_STEP)).toFixed(5));
        if (poly.vertices.length) {
          const changed = {x: circle.x, y: circle.y};
          repacking = true;
          try {
            const data = await post("/aem/api/repack", {vertices: poly.vertices,
              circles: poly.circles, changed_idx: selected.c});
            poly.circles = data.circles;
            const match = reselectCircle(poly.circles, changed);
            selected = match ? {p: selected.p, c: match.index} : null;
          }
          catch (error) { show(error.message, true); setStatus(error.message); }
          finally { repacking = false; }
        }
        updateInfo();
        setStatus(`Radius → ${circle.r.toFixed(4)} m (${poly.circles.length} circles)`);
        draw();
        return;
      }
    });

    const toggleView = () => {
      if (!fullView && !allCircles().length) { show("Draw and pack at least one polygon first.", true); return; }
      fullView = !fullView;
      const viewBtn = document.getElementById("aem-view");
      if (viewBtn) viewBtn.textContent = fullView ? "Back to design (v)" : "View (v)";
      setStatus(fullView ? "VIEW — full simulation domain." : (mode === "edit" ? "EDIT mode." : "DRAW mode."));
      draw();
    };

    const exportJson = () => {
      const blob = new Blob([JSON.stringify(buildConfig(), null, 2)], {type: "application/json"});
      const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
      link.download = "source_config.json"; link.click(); URL.revokeObjectURL(link.href);
    };

    document.getElementById("aem-mode-draw").addEventListener("click", () => setMode("draw"));
    document.getElementById("aem-mode-edit").addEventListener("click", () => setMode("edit"));
    const packBtn = document.getElementById("aem-pack");
    if (packBtn) packBtn.addEventListener("click", packPolygon);
    document.getElementById("aem-clear").addEventListener("click", () => {
      polygons.length = 0; drawing = []; selected = null; fullView = false;
      const viewBtn = document.getElementById("aem-view"); if (viewBtn) viewBtn.textContent = "View (v)";
      setMode("draw"); updateInfo(); setStatus("Cleared all polygons."); draw();
    });
    document.getElementById("aem-view").addEventListener("click", toggleView);
    const importInput = document.getElementById("aem-import");
    document.getElementById("aem-import-trigger").addEventListener("click", () => importInput.click());
    importInput.addEventListener("change", async () => {
      try {
        const config = JSON.parse(await importInput.files[0].text());
        if (!Array.isArray(config.elements) || config.elements.some((element) => element.kind !== "circle")) {
          throw new Error("Imported AEM designs must contain circle elements.");
        }
        ["orientation", "alpha_l", "alpha_t", "ca", "gamma", "dom_inc", "num_cp", "num_terms"].forEach((name) => {
          if (config[name] !== undefined) form.elements[name].value = config[name];
        });
        polygons.length = 0;
        polygons.push({vertices: [], circles: config.elements.map((element) => ({...element}))});
        // Remember the file's own domain bounds so the run frames exactly as the
        // file specifies (matching main.py in the source), unless the geometry is edited.
        const domainKeys = ["dom_xmin", "dom_xmax", "dom_ymin", "dom_ymax"];
        importedDomain = domainKeys.every((k) => Number.isFinite(config[k]))
          ? Object.fromEntries(domainKeys.map((k) => [k, config[k]])) : null;
        importedSig = importedDomain ? geomSignature() : null;
        drawing = []; selected = null; fitSource(); show(`Imported ${config.elements.length} source circles.`); setStatus(`Imported ${config.elements.length} circles.`);
        setMode("edit"); draw();
      } catch (error) { show(`Invalid AEM JSON: ${error.message}`, true); }
      importInput.value = "";
    });
    document.getElementById("aem-export").addEventListener("click", exportJson);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!allCircles().length) { show("Draw and pack at least one polygon first.", true); setStatus("Nothing to submit — draw and pack a polygon."); return; }
      try {
        show("Saving source design..."); const data = await post("/aem/api/design", {config: buildConfig()});
        window.location.assign(data.forward_url);
      } catch (error) { show(error.message, true); }
    });

    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => resize()).observe(canvas);
    }
    window.addEventListener("resize", resize);
    setMode("draw");
    resize();
  }

  const renderSummary = (result) => {
    const summary = document.getElementById("aem-summary"); summary.innerHTML = "";
    Object.entries(result).filter(([key, value]) => !["field", "xaxis", "yaxis"].includes(key) && value !== null)
      .forEach(([key, value]) => { const dt = document.createElement("dt"); dt.textContent = key.replaceAll("_", " ");
        const dd = document.createElement("dd"); dd.textContent = typeof value === "number" ? value.toPrecision(6) : String(value); summary.append(dt, dd); });
  };
  // Render the concentration field the way the source simulation does
  // (at_simulation.py: contourf): discrete filled bands — electron donor (C >= 0)
  // in Reds (0..max), electron acceptor (C < 0) in Blues_r (0..|min|) — plus a
  // black zero-concentration interface line and stepped donor/acceptor colorbars.
  // The coarse grid is interpolated up to display resolution and then quantised to
  // bands, so boundaries are smooth and crisp like contourf instead of a blurry
  // upscaled bitmap.
  const DONOR_BANDS = 10, ACC_BANDS = 8;   // 11 donor / 9 acceptor levels, like the source
  // "Nice" evenly-spaced tick values in [lo, hi] (like matplotlib's MaxNLocator).
  const niceTicks = (lo, hi, target) => {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const mag = Math.pow(10, Math.floor(Math.log10(span / Math.max(1, target))));
    const norm = span / Math.max(1, target) / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const ticks = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) {
      ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    }
    return ticks;
  };
  const fmtTick = (v) => (Number.isInteger(v) ? String(v) : v.toFixed(Math.abs(v) < 1 ? 2 : 1));
  const renderField = (result) => {
    if (!result.field || !result.field.length || !result.xaxis?.length || !result.yaxis?.length) return;
    const canvas = document.getElementById("aem-result-canvas");
    // Size the backing store to the displayed width (× DPR) so the plot is crisp
    // instead of a CSS-upscaled 1000px bitmap. Layout constants below were tuned for
    // a 1000-wide canvas, so scale them all by s.
    const BASE_W = 1000, BASE_H = 560, dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(BASE_W, Math.round((canvas.clientWidth || BASE_W) * dpr));
    canvas.height = Math.round(canvas.width * BASE_H / BASE_W);
    const s = canvas.width / BASE_W;
    const ctx = canvas.getContext("2d");
    const field = result.field; const rows = field.length, cols = field[0].length;
    let min = Infinity, max = -Infinity;
    field.forEach((row) => row.forEach((v) => { if (Number.isFinite(v)) { min = Math.min(min, v); max = Math.max(max, v); } }));
    const maxDonor = max > 0 ? max : 1;          // donor band scale 0..max
    const minAcc = min < 0 ? min : -1;            // acceptor band scale 0..|min|

    // Discrete band colour, mirroring contourf's stepped levels.
    const bandColor = (v) => {
      if (!Number.isFinite(v)) return [247, 251, 255];                    // background
      if (v >= 0) {
        const band = Math.min(DONOR_BANDS - 1, Math.floor((v / maxDonor) * DONOR_BANDS));
        return sampleStops(REDS_STOPS, (band + 0.5) / DONOR_BANDS);
      }
      const band = Math.min(ACC_BANDS - 1, Math.floor((v / minAcc) * ACC_BANDS));  // (|v|/|min|)
      return sampleStops(BLUES_STOPS, (band + 0.5) / ACC_BANDS);
    };
    // Bilinear sample at fractional grid (col, row); NaN if any node is non-finite.
    const sampleField = (c, r) => {
      const c0 = Math.min(cols - 1, Math.floor(c)), r0 = Math.min(rows - 1, Math.floor(r));
      const c1 = Math.min(cols - 1, c0 + 1), r1 = Math.min(rows - 1, r0 + 1);
      const fc = c - c0, fr = r - r0;
      const a = field[r0][c0], b = field[r0][c1], d = field[r1][c0], e = field[r1][c1];
      if (!(Number.isFinite(a) && Number.isFinite(b) && Number.isFinite(d) && Number.isFinite(e))) return NaN;
      const top = a + (b - a) * fc, bot = d + (e - d) * fc;
      return top + (bot - top) * fr;
    };

    const plot = {left: 80 * s, top: 35 * s, width: canvas.width - 160 * s, height: canvas.height - 130 * s};
    const bufW = Math.max(1, Math.round(plot.width)), bufH = Math.max(1, Math.round(plot.height));
    const image = ctx.createImageData(bufW, bufH);
    const vals = new Float64Array(bufW * bufH);
    for (let py = 0; py < bufH; py++) {
      const r = (1 - py / (bufH - 1 || 1)) * (rows - 1);   // image top = high y; data row 0 = low y
      for (let px = 0; px < bufW; px++) {
        const c = (px / (bufW - 1 || 1)) * (cols - 1);
        const v = sampleField(c, r); vals[py * bufW + px] = v;
        const rgb = bandColor(v); const i = (py * bufW + px) * 4;
        image.data[i] = rgb[0]; image.data[i + 1] = rgb[1]; image.data[i + 2] = rgb[2]; image.data[i + 3] = 255;
      }
    }
    // Black zero-concentration interface line: pixels where the interpolated field
    // changes sign vs the left/upper neighbour (thickness scales with resolution).
    const paintBlack = (px, py) => {
      if (px < 0 || py < 0 || px >= bufW || py >= bufH) return;
      const i = (py * bufW + px) * 4; image.data[i] = image.data[i + 1] = image.data[i + 2] = 0; image.data[i + 3] = 255;
    };
    const lw = Math.max(1, Math.round(s));
    for (let py = 0; py < bufH; py++) for (let px = 0; px < bufW; px++) {
      const v = vals[py * bufW + px]; if (!Number.isFinite(v)) continue;
      const left = px > 0 ? vals[py * bufW + px - 1] : v, up = py > 0 ? vals[(py - 1) * bufW + px] : v;
      if ((Number.isFinite(left) && (v >= 0) !== (left >= 0)) || (Number.isFinite(up) && (v >= 0) !== (up >= 0))) {
        for (let dy = 0; dy <= lw; dy++) for (let dx = 0; dx <= lw; dx++) paintBlack(px + dx, py + dy);
      }
    }
    const buffer = document.createElement("canvas"); buffer.width = bufW; buffer.height = bufH;
    buffer.getContext("2d").putImageData(image, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.imageSmoothingEnabled = false;
    ctx.drawImage(buffer, plot.left, plot.top);   // 1:1 — no upscaling blur

    // Axes — matplotlib-style: "x (m)" plus orientation-specific "y (m)" (horizontal)
    // or "z (m)" (vertical), with several evenly-spaced "nice" ticks, not just the ends.
    const xmin = result.xaxis[0], xmax = result.xaxis[result.xaxis.length - 1];
    const ymin = result.yaxis[0], ymax = result.yaxis[result.yaxis.length - 1];
    const xPix = (v) => plot.left + (v - xmin) / (xmax - xmin) * plot.width;
    const yPix = (v) => plot.top + (ymax - v) / (ymax - ymin) * plot.height;
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
    niceTicks(ymin, ymax, 6).forEach((v) => {
      if (v < ymin || v > ymax) return; const py = yPix(v);
      ctx.beginPath(); ctx.moveTo(plot.left - 5 * s, py); ctx.lineTo(plot.left, py); ctx.stroke();
      ctx.fillText(fmtTick(v), plot.left - 8 * s, py + 4 * s);
    });
    ctx.textAlign = "center"; ctx.font = `${Math.round(15 * s)}px sans-serif`;
    ctx.fillText("x (m)", plot.left + plot.width / 2, plot.top + plot.height + 40 * s);
    ctx.save(); ctx.translate(18 * s, plot.top + plot.height / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText(result.orientation === "vertical" ? "z (m)" : "y (m)", 0, 0); ctx.restore();

    // Stepped colorbars matching the contour levels: donor (Reds, 0..max) left,
    // acceptor (Blues, |min|..0) right.
    const barY = canvas.height - 40 * s, barH = 9 * s, half = plot.width / 2 - 12 * s;
    for (let b = 0; b < DONOR_BANDS; b++) {
      const c = sampleStops(REDS_STOPS, (b + 0.5) / DONOR_BANDS);
      ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; ctx.fillRect(plot.left + (b * half) / DONOR_BANDS, barY, half / DONOR_BANDS + 1, barH);
    }
    const accLeft = plot.left + plot.width - half;
    for (let b = 0; b < ACC_BANDS; b++) {
      const c = sampleStops(BLUES_STOPS, 1 - (b + 0.5) / ACC_BANDS);
      ctx.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; ctx.fillRect(accLeft + (b * half) / ACC_BANDS, barY, half / ACC_BANDS + 1, barH);
    }
    ctx.fillStyle = "#26384d"; ctx.font = `${Math.round(11 * s)}px sans-serif`; ctx.textAlign = "left";
    ctx.fillText("Donor 0", plot.left, barY - 3 * s); ctx.fillText(`${maxDonor.toPrecision(3)} mg/L`, plot.left + half - 60 * s, barY - 3 * s);
    ctx.fillText(`Acceptor ${Math.abs(minAcc).toPrecision(3)}`, accLeft, barY - 3 * s); ctx.fillText("0 mg/L", accLeft + half - 40 * s, barY - 3 * s);
  };
  async function runJob(endpoint, payload) {
    const cancel = document.getElementById("aem-cancel");
    try {
      const submitted = await post(endpoint, payload); cancel.hidden = false;
      cancel.onclick = () => post(submitted.cancel_url, {}).then(() => show("Job cancelled."));
      while (true) {
        const status = await json(submitted.status_url); show(`Simulation ${status.status}${status.queue_position ? ` (queue position ${status.queue_position})` : ""}...`);
        if (status.status === "done") break; if (["failed", "cancelled"].includes(status.status)) throw new Error(status.error || `Job ${status.status}.`);
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      const completed = await json(submitted.result_url); cancel.hidden = true; show("Simulation complete."); renderSummary(completed.result); renderField(completed.result);
    } catch (error) { cancel.hidden = true; show(error.message, true); }
  }
  if (root.dataset.aemPage === "designer") designer();
  if (root.dataset.aemPage === "forward") runJob("/aem/api/forward", {design: root.dataset.designToken});
  if (root.dataset.aemPage === "inverse") document.getElementById("aem-inverse-form").addEventListener("submit", (event) => {
    event.preventDefault(); const payload = Object.fromEntries(new FormData(event.currentTarget));
    ["target_Lmax", "r", "C0", "ca", "gamma", "tolerance"].forEach((name) => payload[name] = +payload[name]); runJob("/aem/api/inverse", payload);
  });
})();
