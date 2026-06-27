"""Native Flask pages and bounded JSON APIs for AEM workflows."""

import math

import numpy as np
from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from shapely.geometry import Polygon as ShapelyPolygon

from aem_jobs import INVERSE_PARAMS, load_aem_design, save_aem_design
from aem_source_geometry import greedy_circle_pack, repack_after_resize
from numerical_jobs import (
    cancel_job,
    fetch_result,
    job_status,
    load_job_meta,
    save_job_meta,
    submit_job,
)
from security import csrf_protect

aem_bp = Blueprint("aem_bp", __name__)

MAX_JSON_BYTES = 1024 * 1024
MAX_VERTICES = 128
MAX_ELEMENTS = 240
MAX_PACK_CIRCLES = 80
MAX_PACK_CANDIDATES = 300_000
MAX_GRID_CELLS = 500_000
MAX_COORDINATE = 10_000.0


def _current_email():
    return current_user.email


def _error(message, status=400):
    return jsonify({"success": False, "message": message}), status


def _json_body():
    if request.content_length is not None and request.content_length > MAX_JSON_BYTES:
        raise ValueError("JSON payload exceeds the 1 MiB limit.")
    if not request.is_json:
        raise ValueError("Content-Type must be application/json.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("JSON payload must be an object.")
    return data


def _number(value, name, *, positive=False, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    if positive and number <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be at most {maximum}.")
    return number


def _vertices(raw):
    if not isinstance(raw, list) or not 3 <= len(raw) <= MAX_VERTICES:
        raise ValueError(f"vertices must contain 3 to {MAX_VERTICES} points.")
    vertices = []
    for index, point in enumerate(raw):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(f"vertices[{index}] must be an [x, y] pair.")
        vertices.append((
            _number(point[0], f"vertices[{index}][0]", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE),
            _number(point[1], f"vertices[{index}][1]", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE),
        ))
    width = max(x for x, _ in vertices) - min(x for x, _ in vertices)
    height = max(y for _, y in vertices) - min(y for _, y in vertices)
    candidates = (int(width / 0.006) + 2) * (int(height / 0.006) + 2)
    if width <= 0 or height <= 0 or candidates > MAX_PACK_CANDIDATES:
        raise ValueError("Polygon extent is empty or too large to pack safely.")
    polygon = ShapelyPolygon(vertices)
    if not polygon.is_valid or polygon.area == 0:
        raise ValueError("Polygon must be valid, non-self-intersecting, and have positive area.")
    return vertices


def _provided_domain(raw):
    """Validated explicit domain bounds from a config, or None if not all four are
    present. Lets an imported design keep its own framing instead of having it
    recomputed — the same way the reference (at_config.from_json / main.py) reads
    dom_* straight from the JSON."""
    keys = ("dom_xmin", "dom_xmax", "dom_ymin", "dom_ymax")
    if any(raw.get(key) is None for key in keys):
        return None
    bounds = {key: _number(raw.get(key), key, minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE)
              for key in keys}
    if bounds["dom_xmax"] <= bounds["dom_xmin"] or bounds["dom_ymax"] <= bounds["dom_ymin"]:
        raise ValueError("Domain bounds must satisfy dom_xmax > dom_xmin and dom_ymax > dom_ymin.")
    return bounds


def _validated_config(raw):
    if not isinstance(raw, dict):
        raise ValueError("config must be an object.")
    config = {}
    defaults = {"alpha_l": 2.0, "alpha_t": 0.2, "ca": 8.0,
                "gamma": 3.5, "dom_inc": 1.0}
    for name, default in defaults.items():
        config[name] = _number(raw.get(name, default), name,
                               positive=name in {"alpha_l", "alpha_t", "ca", "gamma", "dom_inc"},
                               maximum=MAX_COORDINATE)
    config["num_cp"] = int(_number(raw.get("num_cp", 40), "num_cp", minimum=4, maximum=500))
    config["num_terms"] = int(_number(raw.get("num_terms", 5), "num_terms", minimum=1, maximum=50))
    orientation = raw.get("orientation", "vertical")
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError("orientation must be horizontal or vertical.")
    config["orientation"] = orientation
    config["plot_aspect"] = ""

    raw_elements = raw.get("elements")
    if not isinstance(raw_elements, list) or not 1 <= len(raw_elements) <= MAX_ELEMENTS:
        raise ValueError(f"elements must contain 1 to {MAX_ELEMENTS} sources.")
    elements = []
    for index, raw_element in enumerate(raw_elements):
        if not isinstance(raw_element, dict):
            raise ValueError(f"elements[{index}] must be an object.")
        kind = raw_element.get("kind", "circle")
        if kind not in {"circle", "line", "ellipse"}:
            raise ValueError(f"elements[{index}].kind is not supported.")
        element = {
            "kind": kind,
            "x": _number(raw_element.get("x"), f"elements[{index}].x", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE),
            "y": _number(raw_element.get("y"), f"elements[{index}].y", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE),
            "c": _number(raw_element.get("c"), f"elements[{index}].c", positive=True, maximum=10_000),
            "id": str(raw_element.get("id", f"source_{index}"))[:80],
        }
        if kind == "circle":
            element["r"] = _number(raw_element.get("r"), f"elements[{index}].r", positive=True, maximum=MAX_COORDINATE)
        elif kind == "line":
            element["l"] = _number(raw_element.get("l"), f"elements[{index}].l", positive=True, maximum=MAX_COORDINATE)
            element["theta"] = _number(raw_element.get("theta", 90), f"elements[{index}].theta", minimum=-360, maximum=360)
        else:
            element["a"] = _number(raw_element.get("a"), f"elements[{index}].a", positive=True, maximum=MAX_COORDINATE)
            element["b"] = _number(raw_element.get("b"), f"elements[{index}].b", positive=True, maximum=MAX_COORDINATE)
            element["theta"] = _number(raw_element.get("theta", 0), f"elements[{index}].theta", minimum=-360, maximum=360)
        elements.append(element)
    config["elements"] = elements
    all_x = [element["x"] for element in elements]
    all_y = [element["y"] for element in elements]
    max_r = max(element.get("r", element.get("a", element.get("l", 0) / 2))
                for element in elements)
    # "vertical" pins sources to the water table (shift elements + dom_ymax=0) — a
    # deliberate solver-geometry guard, so its box is always derived. "horizontal"
    # has no such convention: if the config carries explicit bounds (an imported
    # design), honour them so it frames exactly as authored — same as the reference
    # (main.py), which reads dom_* from the JSON. Otherwise derive them.
    bounds = None if orientation == "vertical" else _provided_domain(raw)
    if bounds is not None:
        config.update(bounds)
    else:
        if orientation == "vertical":
            shift = max(all_y) + max_r + 0.15
            if shift > 0:
                for element in elements:
                    element["y"] = round(element["y"] - shift, 5)
            all_y = [element["y"] for element in elements]
            config["dom_ymax"] = 0.0
        else:
            config["dom_ymax"] = round(max(all_y) + max_r + 5.0, 3)
        config["dom_xmin"] = round(min(all_x) - max_r - 2.0, 3)
        config["dom_xmax"] = round(max(all_x) + 150.0, 1)
        config["dom_ymin"] = round(min(all_y) - max_r - 5.0, 3)
    nx = int((config["dom_xmax"] - config["dom_xmin"]) / config["dom_inc"]) + 1
    ny = int((config["dom_ymax"] - config["dom_ymin"]) / config["dom_inc"]) + 1
    if nx * ny > MAX_GRID_CELLS:
        raise ValueError(f"Simulation grid exceeds the {MAX_GRID_CELLS:,} cell limit.")
    return config


def _owned_job_meta(job_id):
    meta = load_job_meta(job_id)
    if meta is None or meta.get("email") != _current_email() or meta.get("kind") not in {"aem_forward", "aem_inverse"}:
        return None
    return meta


def _submit(kind, params):
    job_id = submit_job(kind, params)
    save_job_meta(job_id, {"email": _current_email(), "kind": kind})
    return jsonify({
        "success": True,
        "job_id": job_id,
        "status_url": url_for("aem_bp.aem_job_status", job_id=job_id),
        "result_url": url_for("aem_bp.aem_job_result", job_id=job_id),
        "cancel_url": url_for("aem_bp.aem_job_cancel", job_id=job_id),
    }), 202


@aem_bp.get("/aem")
@login_required
def aem_landing():
    return render_template("aem_designer.html")


@aem_bp.get("/aem/designer")
@login_required
def aem_designer():
    return redirect(url_for("aem_bp.aem_landing"), code=302)


@aem_bp.get("/aem/forward")
@login_required
def aem_forward():
    token = request.args.get("design", "")
    if load_aem_design(token, _current_email()) is None:
        abort(404)
    return render_template("aem_forward.html", design_token=token)


@aem_bp.get("/aem/inverse")
@login_required
def aem_inverse():
    return render_template("aem_inverse.html", inverse_params=INVERSE_PARAMS)


@aem_bp.post("/aem/api/pack")
@login_required
@csrf_protect
def aem_pack():
    try:
        data = _json_body()
        vertices = _vertices(data.get("vertices"))
        concentration = _number(data.get("default_c", 10), "default_c", positive=True, maximum=10_000)
        count = int(_number(data.get("max_circles", 80), "max_circles", minimum=1, maximum=MAX_PACK_CIRCLES))
        circles = greedy_circle_pack(vertices, concentration, count)
        return jsonify({"success": True, "circles": [
            {name: float(value) for name, value in circle.items()} for circle in circles
        ]})
    except ValueError as exc:
        return _error(str(exc))


@aem_bp.post("/aem/api/repack")
@login_required
@csrf_protect
def aem_repack():
    try:
        data = _json_body()
        vertices = _vertices(data.get("vertices"))
        raw_circles = data.get("circles")
        if not isinstance(raw_circles, list) or not 1 <= len(raw_circles) <= MAX_PACK_CIRCLES:
            raise ValueError(f"circles must contain 1 to {MAX_PACK_CIRCLES} items.")
        circles = []
        for index, item in enumerate(raw_circles):
            if not isinstance(item, dict):
                raise ValueError(f"circles[{index}] must be an object.")
            circles.append({
                "x": _number(item.get("x"), f"circles[{index}].x", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE),
                "y": _number(item.get("y"), f"circles[{index}].y", minimum=-MAX_COORDINATE, maximum=MAX_COORDINATE),
                "r": _number(item.get("r"), f"circles[{index}].r", positive=True, maximum=MAX_COORDINATE),
                "c": _number(item.get("c"), f"circles[{index}].c", positive=True, maximum=10_000),
            })
        changed = int(_number(data.get("changed_idx"), "changed_idx", minimum=0, maximum=len(circles) - 1))
        return jsonify({"success": True, "circles": repack_after_resize(circles, changed, vertices)})
    except (ValueError, IndexError) as exc:
        return _error(str(exc))


@aem_bp.post("/aem/api/design")
@login_required
@csrf_protect
def aem_design_create():
    try:
        config = _validated_config(_json_body().get("config"))
        token = save_aem_design(_current_email(), config)
        return jsonify({"success": True, "design": token,
                        "forward_url": url_for("aem_bp.aem_forward", design=token)}), 201
    except ValueError as exc:
        return _error(str(exc))


@aem_bp.post("/aem/api/forward")
@login_required
@csrf_protect
def aem_forward_submit():
    try:
        token = str(_json_body().get("design", ""))
        config = load_aem_design(token, _current_email())
        if config is None:
            return _error("Unknown AEM design.", 404)
        return _submit("aem_forward", {"config_json": config})
    except ValueError as exc:
        return _error(str(exc))


@aem_bp.post("/aem/api/inverse")
@login_required
@csrf_protect
def aem_inverse_submit():
    try:
        data = _json_body()
        estimate_param = data.get("estimate_param", "alpha_t")
        if estimate_param not in INVERSE_PARAMS:
            raise ValueError("estimate_param is not supported.")
        orientation = data.get("orientation", "horizontal")
        elem_kind = data.get("elem_kind", "Circle")
        if orientation not in {"horizontal", "vertical"} or elem_kind not in {"Circle", "Line"}:
            raise ValueError("Invalid orientation or source element.")
        params = {"estimate_param": estimate_param, "orientation": orientation, "elem_kind": elem_kind}
        for name in ("target_Lmax", "r", "C0", "ca", "gamma", "tolerance"):
            params[name] = _number(data.get(name), name, positive=True, maximum=MAX_COORDINATE)
        for name in ("lower_bound", "upper_bound"):
            value = data.get(name)
            params[name] = None if value in (None, "") else _number(value, name, positive=True, maximum=MAX_COORDINATE)
        if params["lower_bound"] is not None and params["upper_bound"] is not None and params["lower_bound"] >= params["upper_bound"]:
            raise ValueError("lower_bound must be less than upper_bound.")
        return _submit("aem_inverse", params)
    except ValueError as exc:
        return _error(str(exc))


@aem_bp.get("/aem/jobs/<job_id>")
@login_required
def aem_job_status(job_id):
    if _owned_job_meta(job_id) is None:
        return _error("Unknown AEM job.", 404)
    status = job_status(job_id)
    if status is None:
        return _error("Unknown AEM job.", 404)
    return jsonify({"job_id": job_id, "status": status["status"],
                    "queue_position": status.get("queue_position"),
                    "plume_length": status.get("plume_length"),
                    "error": "Simulation failed. Please check your inputs and try again."
                    if status["status"] == "failed" else None})


@aem_bp.post("/aem/jobs/<job_id>/cancel")
@login_required
@csrf_protect
def aem_job_cancel(job_id):
    if _owned_job_meta(job_id) is None:
        return _error("Unknown AEM job.", 404)
    return jsonify({"success": cancel_job(job_id)})


def _array(value):
    if value is None:
        return None
    array = np.asarray(value, dtype=float)
    clean = array.astype(object)
    clean[~np.isfinite(array)] = None
    return clean.tolist()


@aem_bp.get("/aem/jobs/<job_id>/result")
@login_required
def aem_job_result(job_id):
    meta = _owned_job_meta(job_id)
    status = job_status(job_id) if meta else None
    if status is None:
        return _error("Unknown AEM job.", 404)
    if status["status"] != "done":
        return _error("AEM job is not complete.", 409)
    result = fetch_result(job_id)
    if meta["kind"] == "aem_forward":
        payload = {
            "kind": "forward", "field": _array(result.result),
            "xaxis": _array(result.xaxis), "yaxis": _array(result.yaxis),
            "L_max": result.L_max, "ca": result.ca, "gamma": result.gamma,
            "orientation": result.orientation, "num_elements": result.num_elements,
            "interface_length": result.interface_length,
            "validation_passed": result.validation_passed,
        }
    else:
        payload = {
            "kind": "inverse", "field": _array(result.result),
            "xaxis": _array(result.xaxis), "yaxis": _array(result.yaxis),
            "estimate_param": result.estimate_param,
            "recovered_value": result.recovered_value,
            "target_L_max": result.target_L_max,
            "achieved_L_max": result.achieved_L_max,
            "lower_bound": result.lower_bound, "upper_bound": result.upper_bound,
            "converged": result.converged, "ca": result.ca, "gamma": result.gamma,
            "orientation": result.orientation,
        }
    return jsonify({"success": True, "result": payload})
