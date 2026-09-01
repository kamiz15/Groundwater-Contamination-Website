from contextlib import ExitStack
import csv
import io
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import aem_routes
import app as app_module
from aem_jobs import build_config, load_aem_design, save_aem_design
from aem_source_geometry import greedy_circle_pack
from aem.at_simulation import ATSimulation


VALID_CONFIG = {
    "alpha_l": 2.0, "alpha_t": 0.2, "ca": 8.0, "gamma": 3.5,
    "dom_xmin": 0.0, "dom_xmax": 300.0, "dom_ymin": -20.0,
    "dom_ymax": 20.0, "dom_inc": 1.0, "num_cp": 40, "num_terms": 5,
    "orientation": "vertical",
    # Authored directly below the water table (y <= 0): the new physical-coordinate
    # model no longer shifts vertical sources, so they must start below y=0.
    "elements": [{"kind": "circle", "x": 0.1, "y": -0.5, "c": 10.0, "r": 0.02}],
}


@pytest.fixture
def aem_client(tmp_path, monkeypatch):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    previous = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
    with patch.object(aem_routes, "_current_email", return_value="user@example.com"):
        yield app_module.app.test_client()
    app_module.app.config["LOGIN_DISABLED"] = previous


def _csrf_token(client):
    page = client.get("/aem").get_data(as_text=True)
    return re.search(r'data-csrf="([^"]+)"', page).group(1)


def _post(client, path, **kwargs):
    headers = dict(kwargs.pop("headers", {}), **{"X-CSRF-Token": _csrf_token(client)})
    return client.post(path, headers=headers, **kwargs)


def test_aem_pages_are_native_and_navigation_has_one_entry(aem_client):
    home = aem_client.get("/").get_data(as_text=True)
    designer = aem_client.get("/aem").get_data(as_text=True)

    assert home.count(">AEM Model<") == 1
    assert "aem.js" in designer
    assert "<canvas" in designer
    assert "<iframe" not in designer
    assert "panel_aem" not in designer


def test_panel_server_keeps_non_aem_apps_and_has_no_aem_registration():
    source = Path("panel_server.py").read_text(encoding="utf-8")

    assert "panel_aem" not in source
    assert '"panel_liedl_single"' in source
    assert '"panel_numerical_horizontal_single"' in source


def test_native_client_contract_covers_csrf_import_export_and_axis_rendering():
    source = Path("static/aem.js").read_text(encoding="utf-8")
    result_templates = (
        Path("templates/aem_forward.html").read_text(encoding="utf-8")
        + Path("templates/aem_inverse.html").read_text(encoding="utf-8")
    )

    assert '"X-CSRF-Token": root.dataset.csrf' in source
    assert 'id="aem-import"' in Path("templates/aem_designer.html").read_text(encoding="utf-8")
    assert "JSON.parse(await importInput.files[0].text())" in source
    assert 'link.download = "source_config.json"' in source
    assert "Math.min(rect.width / xspan, rect.height / yspan)" in source
    assert '"Full simulation domain"' in source
    assert "xs[0]" in source and "ys[0]" in source                # result axis extents
    assert "contourf(" in source and "eachTriangle" in source   # marching-triangle contour fill
    assert result_templates.count('id="aem-download-csv"') == 2
    assert result_templates.count('id="aem-open-workbench"') == 2
    assert "completed.workbench_url" in source
    assert 'ctx.fillText("x (m)"' in source                       # matplotlib-style axis label
    assert "DONOR_BANDS" in source                                # discrete contour bands
    assert "drawing.push(snapDrawPoint(point))" in source
    # The repack path still reselects the changed circle — now as a one-element
    # multi-selection, cleared to the empty selection when the circle is gone.
    assert 'selected = match ? [{type: "poly", p: key0.p, c: match.index}] : []' in source


def test_designer_canvas_cannot_feed_its_own_resize_observer():
    """Guard against a runaway canvas.

    resize() writes the backing store as cssHeight * devicePixelRatio. If the
    canvas CSS height resolved to auto, the element would adopt that attribute
    as its intrinsic height, the observer would fire again, and on any dpr > 1
    display it would grow without bound. Two things keep that from happening:
    the height stays definite, and the observer watches the parent, not the
    element we resize.
    """
    css = Path("static/styles.css").read_text(encoding="utf-8")
    # Several rules target the canvas; the last one wins, so that is the one
    # whose height decides whether the observer can feed itself.
    blocks = [chunk.split("}", 1)[0] for chunk in css.split("#aem-designer-canvas {")[1:]]
    assert blocks, "no #aem-designer-canvas rule found"
    assert not any("height: 100%" in b for b in blocks), "canvas height must stay definite"
    assert re.search(r"height:\s*\d+(\.\d+)?vh", blocks[-1]), (
        "the winning canvas rule needs a viewport-relative height"
    )

    source = Path("static/aem.js").read_text(encoding="utf-8")
    assert "ResizeObserver(() => resize()).observe(canvas)" not in source
    assert "observe(canvas.parentElement" in source


def _run_aem_js(expression):
    script = (
        "const h=require('./static/aem.js');"
        f"console.log(JSON.stringify({expression}));"
    )
    result = subprocess.run(
        ["node", "-e", script], cwd=Path.cwd(), check=True,
        capture_output=True, text=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(("point", "expected"), [
    ([0.124, 0.126], [0.1, 0.15]),
    ([0.075, 0.175], [0.05, 0.15]),
    ([0.125, 0.125], [0.1, 0.1]),
    ([-0.04, -0.02], [0, 0]),
    ([0.54, 0.01], [0.5, 0]),
])
def test_native_draw_snaps_and_clamps_like_reference(point, expected):
    assert _run_aem_js(f"h.snapDrawPoint({json.dumps(point)})") == expected


def test_native_exact_negative_halves_use_python_even_parity_before_clamp():
    assert _run_aem_js("[h.roundHalfEven(-1.5),h.roundHalfEven(-2.5)]") == [-2, -2]


@pytest.mark.parametrize(("value", "expected"), [
    (2, "2"), (2.5, "2.5"), (3.5, "3.5"), (0.2, "0.2"),
    (2.456, "2.46"), (2.999, "3"), (40, "40"), (-0.5, "-0.5"), (0, "0"),
])
def test_display_formatter_caps_at_two_decimals_and_drops_whole_number_zeros(value, expected):
    assert _run_aem_js(f"h.fmt2({value})") == expected


MARQUEE_ELEMENTS = [
    {"x": 0.10, "y": 0.10},   # 0 inside
    {"x": 0.30, "y": 0.30},   # 1 on the corner boundary
    {"x": 0.40, "y": 0.10},   # 2 outside in x
    {"x": 0.10, "y": 0.40},   # 3 outside in y
    {"x": 0.00, "y": 0.00},   # 4 on the opposite corner boundary
]


@pytest.mark.parametrize(("rect", "expected"), [
    ({"x0": 0, "y0": 0, "x1": 0.3, "y1": 0.3}, [0, 1, 4]),
    ({"x0": 0.3, "y0": 0.3, "x1": 0, "y1": 0}, [0, 1, 4]),      # reversed corners
    ({"x0": 0.05, "y0": 0.05, "x1": 0.2, "y1": 0.2}, [0]),      # boundaries excluded
    ({"x0": 0.5, "y0": 0.5, "x1": 0.6, "y1": 0.6}, []),         # empty sweep
])
def test_marquee_selects_elements_whose_centre_is_inside_the_rect(rect, expected):
    assert _run_aem_js(
        f"h.elementsInRect({json.dumps(MARQUEE_ELEMENTS)},{json.dumps(rect)})"
    ) == expected


def test_removal_plan_orders_indices_descending_per_container():
    keys = [
        {"type": "poly", "p": 0, "c": 1},
        {"type": "source", "i": 0},
        {"type": "poly", "p": 0, "c": 3},
        {"type": "source", "i": 2},
        {"type": "poly", "p": 1, "c": 0},
        {"type": "poly", "p": 0, "c": 0},
        {"type": "source", "i": 1},
    ]

    plan = _run_aem_js(f"h.removalPlan({json.dumps(keys)})")

    assert [(group["type"], group.get("p"), group["indices"]) for group in plan] == [
        ("poly", 0, [3, 1, 0]),
        ("source", None, [2, 1, 0]),
        ("poly", 1, [0]),
    ]
    # Ascending splices would delete the wrong elements; descending never shifts
    # an index that has not been used yet.
    for group in plan:
        assert group["indices"] == sorted(group["indices"], reverse=True)


def test_removal_plan_applied_descending_deletes_exactly_the_selected_elements():
    """The plan is only useful if splicing it leaves the unselected items intact."""
    expression = (
        "(()=>{const sources=['s0','s1','s2','s3'];"
        "const circles=['c0','c1','c2'];"
        "const keys=[{type:'source',i:0},{type:'poly',p:0,c:1},"
        "{type:'source',i:2},{type:'source',i:0}];"
        "h.removalPlan(keys).forEach((g)=>{"
        "const list=g.type==='source'?sources:circles;"
        "g.indices.forEach((i)=>list.splice(i,1));});"
        "return {sources,circles};})()"
    )

    assert _run_aem_js(expression) == {"sources": ["s1", "s3"], "circles": ["c0", "c2"]}


def test_repack_reselects_changed_circle_after_earlier_neighbor_removed():
    circles = [
        {"x": 0.2, "y": 0.2, "r": 0.04, "c": 10},
        {"x": 0.35, "y": 0.2, "r": 0.02, "c": 8},
    ]
    expression = (
        "(()=>{const circles=" + json.dumps(circles) + ";"
        "const selected=h.reselectCircle(circles,{x:0.35,y:0.2});"
        "selected.circle.c+=2;return {index:selected.index,circles};})()"
    )

    result = _run_aem_js(expression)

    assert result["index"] == 1
    assert result["circles"][0]["c"] == 10
    assert result["circles"][1]["c"] == 10


def test_repack_clears_selection_when_changed_circle_is_missing():
    assert _run_aem_js("h.reselectCircle([{x:0.1,y:0.1}],{x:0.2,y:0.2})") is None


def test_reference_greedy_pack_output_is_stable():
    circles = greedy_circle_pack(
        [(0, 0), (0.03, 0), (0.03, 0.03), (0, 0.03)], 10, 3
    )

    assert [{key: float(value) for key, value in circle.items()} for circle in circles] == [
        {"x": 0.009, "y": 0.009, "r": 0.0075, "c": 10.0},
        {"x": 0.021, "y": 0.021, "r": 0.0075, "c": 10.0},
        {"x": 0.009, "y": 0.021, "r": 0.0045, "c": 10.0},
    ]


def test_reference_greedy_pack_returns_empty_for_a_zero_area_polygon():
    # The endpoint rejects degenerate polygons before ever calling the packer
    # (test_pack_rejects_invalid_or_zero_area_polygon), so the function's own
    # guard is otherwise untested. Upstream: test_model.py TestGreedyPack.
    assert greedy_circle_pack([[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]) == []


def test_pack_endpoint_matches_reference_algorithm(aem_client):
    vertices = [[0, 0], [0.03, 0], [0.03, 0.03], [0, 0.03]]
    response = _post(aem_client,
        "/aem/api/pack",
        json={"vertices": vertices, "default_c": 10, "max_circles": 3},
    )

    assert response.status_code == 200
    assert response.get_json()["circles"] == [
        {key: float(value) for key, value in circle.items()}
        for circle in greedy_circle_pack(vertices, 10, 3)
    ]


def test_pack_endpoint_honours_a_custom_min_radius(aem_client):
    vertices = [[0, 0], [0.03, 0], [0.03, 0.03], [0, 0.03]]
    response = _post(aem_client, "/aem/api/pack",
                     json={"vertices": vertices, "default_c": 10, "max_circles": 3,
                           "min_radius": 0.006})

    assert response.status_code == 200
    assert response.get_json()["circles"] == [
        {key: float(value) for key, value in circle.items()}
        for circle in greedy_circle_pack(vertices, 10, 3, 0.006)
    ]
    # A coarser floor cannot produce the default packing.
    assert response.get_json()["circles"] != [
        {key: float(value) for key, value in circle.items()}
        for circle in greedy_circle_pack(vertices, 10, 3)
    ]


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"vertices": [[0, 0], [1, 1]]}, "3 to 128"),
        ({"vertices": [[0, 0], [0.03, 0], [0, 0.03]], "min_radius": 0}, "greater than zero"),
        ({"vertices": [[0, 0], [0.03, 0], [0.03, 0.03], [0, 0.03]],
          "min_radius": 1e-6}, "too large"),
        ({"vertices": [[0, 0], [100, 0], [100, 100], [0, 100]]}, "too large"),
        ({"vertices": [[0, 0], [0.03, 0], [0, 0.03]], "max_circles": 81}, "at most 80"),
    ],
)
def test_pack_endpoint_rejects_unbounded_work(aem_client, payload, message):
    response = _post(aem_client, "/aem/api/pack", json=payload)

    assert response.status_code == 400
    assert message in response.get_json()["message"]


def test_design_validation_and_owner_bound_token(aem_client):
    response = _post(aem_client, "/aem/api/design", json={"config": VALID_CONFIG})
    body = response.get_json()

    assert response.status_code == 201
    assert body["forward_url"].endswith(body["design"])
    expected = {
        "alpha_l": 2.0, "alpha_t": 0.2, "ca": 8.0, "gamma": 3.5,
        "dom_xmin": -1.92, "dom_xmax": 25.1, "dom_ymin": -5.52,
        "dom_ymax": 0.0, "dom_inc": 1.0, "num_cp": 40, "num_terms": 5,
        "orientation": "vertical", "plot_aspect": "",
        "elements": [{"kind": "circle", "x": 0.1, "y": -0.5,
                      "c": 10.0, "r": 0.02, "id": "source_0"}],
    }
    assert load_aem_design(body["design"], "user@example.com") == expected
    assert load_aem_design(body["design"], "other@example.com") is None


def test_design_rejects_missing_elements_and_oversized_payload(aem_client):
    invalid = _post(aem_client, "/aem/api/design", json={"config": VALID_CONFIG | {"elements": []}})
    excessive_grid = _post(aem_client,
        "/aem/api/design",
        json={"config": VALID_CONFIG | {"dom_inc": 0.0001}},
    )
    oversized = _post(aem_client,
        "/aem/api/design", data=b"x" * (aem_routes.MAX_JSON_BYTES + 1),
        content_type="application/json",
    )

    assert invalid.status_code == 400
    assert "grid exceeds" in excessive_grid.get_json()["message"]
    assert oversized.status_code == 400


def test_settings_panel_is_editable_in_designer_html():
    html = Path("templates/aem_designer.html").read_text(encoding="utf-8")

    assert "Simulation Settings" in html
    assert 'id="aem-orientation"' in html
    # Every reference SettingsPanel field is an editable input, not a fixed hidden one.
    for name in ("alpha_l", "alpha_t", "ca", "gamma", "dom_inc",
                 "num_cp", "num_terms", "ws", "plot_aspect"):
        assert re.search(rf'<input[^>]*name="{name}"', html)
        assert f'type="hidden" name="{name}"' not in html


def test_designer_mobile_layout_keeps_settings_visible():
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert re.search(
        r"@media \(max-width: 760px\) \{\s*"
        r"\.aem-designer-app \{\s*height: auto;\s*min-height: 0;\s*\}.*?"
        r"\.aem-designer-layout \{\s*flex: none;\s*"
        r"grid-template-columns: 1fr;\s*\}\s*\}",
        styles,
        re.DOTALL,
    )
    assert re.search(
        r"@media \(max-width: 620px\) \{\s*"
        r"\.aem-designer-form \.aem-field-grid \{ grid-template-columns: 1fr; \}\s*\}",
        styles,
    )


def test_aem_action_labels_and_forward_summary_fields():
    designer = Path("templates/aem_designer.html").read_text(encoding="utf-8")
    forward = Path("templates/aem_forward.html").read_text(encoding="utf-8")
    script = Path("static/aem.js").read_text(encoding="utf-8")
    styles = Path("static/styles.css").read_text(encoding="utf-8")

    assert ">Run Simulation</button>" in designer
    assert "Continue and Run Simulation" not in designer
    for element_id in ("aem-cancel", "aem-download-csv", "aem-open-workbench"):
        assert re.search(rf'id="{element_id}"[^>]*class="primary-btn"', forward)
    assert re.search(r'id="aem-cancel-actions"[^>]*hidden', forward)
    assert ".aem-result-card .primary-btn {" in styles
    assert "setCancelVisible(false); show(\"Simulation complete.\")" in script
    assert '["field", "xaxis", "yaxis", "validation_passed"]' in script


def test_vertical_config_rejects_sources_above_water_table():
    raw = VALID_CONFIG | {"elements": [{"kind": "circle", "x": 0.1, "y": 0.0, "c": 10.0, "r": 0.02}]}

    with pytest.raises(ValueError, match="water table"):
        aem_routes._validated_config(raw)


def test_config_rejects_num_cp_below_num_terms():
    with pytest.raises(ValueError, match="num_terms"):
        aem_routes._validated_config(VALID_CONFIG | {"num_cp": 4, "num_terms": 5})


@pytest.mark.parametrize("vertices", [
    [[0, 0], [0.04, 0.04], [0, 0.04], [0.04, 0]],
    [[0, 0], [0.02, 0.02], [0.04, 0.04]],
])
def test_pack_rejects_invalid_or_zero_area_polygon(aem_client, vertices):
    response = _post(aem_client, "/aem/api/pack", json={"vertices": vertices})

    assert response.status_code == 400
    assert "Polygon must be valid" in response.get_json()["message"]


def test_reference_config_round_trips_exact_schema(aem_client):
    first = _post(aem_client, "/aem/api/design", json={"config": VALID_CONFIG}).get_json()
    saved = load_aem_design(first["design"], "user@example.com")
    second = _post(aem_client, "/aem/api/design", json={"config": saved}).get_json()

    assert load_aem_design(second["design"], "user@example.com") == saved


def test_default_vertical_config_satisfies_real_solver_geometry_guard():
    validated = aem_routes._validated_config(VALID_CONFIG)
    config = build_config({"config_json": validated})
    simulation = ATSimulation(config)

    assert simulation.config.orientation == "vertical"
    assert simulation.config.dom_ymax == 0.0
    assert all(element.y < -(element.r * __import__("math").sin(element.theta) + 0.1)
               for element in simulation.config.elements)
    for element in simulation.config.elements:
        element.calc_d_q(config.alpha_t, config.alpha_l, config.beta)
        element.set_outline(config.num_cp)
        assert len(element.outline) == config.num_cp


def test_vertical_assembly_adds_mirror_images_and_no_zero_isoline(monkeypatch):
    """Vertical setup pairs each source with its mirror image and nothing else.

    The reference commented out create_zero_isoline (at_simulation.py:381-385);
    aem/ matches it. Re-enabling it changes solved concentrations — on a single
    source it moved L_max 58 -> 55 m — so pin the assembly. The append also sat
    OUTSIDE the loop, so it only ever added an isoline for the LAST source.

    conc_array is stubbed out: it starts a multiprocessing Pool that costs ~13 s
    on Windows (spawn re-imports matplotlib per worker) regardless of grid size,
    and element assembly happens before it.
    """
    config = build_config({"config_json": aem_routes._validated_config({
        **VALID_CONFIG,
        "elements": [
            {"kind": "circle", "x": 1.0, "y": -2.0, "c": 20.0, "r": 0.5, "id": "src_0"},
            {"kind": "circle", "x": 3.0, "y": -2.5, "c": 20.0, "r": 0.4, "id": "src_1"},
        ],
    })})
    simulation = ATSimulation(config)

    class _StopAfterSetup(Exception):
        pass

    monkeypatch.setattr(ATSimulation, "conc_array",
                        lambda *args, **kwargs: (_ for _ in ()).throw(_StopAfterSetup()))
    with pytest.raises(_StopAfterSetup):
        simulation.run()

    assert [element.id for element in simulation.config.elements] == [
        "src_0", "image_src_0", "src_1", "image_src_1",
    ]


@pytest.mark.parametrize("path", [
    "/aem/api/pack", "/aem/api/repack", "/aem/api/design",
    "/aem/api/forward", "/aem/api/inverse", "/aem/jobs/job-1/cancel",
])
def test_aem_mutations_require_csrf(aem_client, path):
    assert aem_client.post(path, json={}).status_code == 400


def test_forward_submission_uses_owner_design_and_existing_queue(aem_client, monkeypatch):
    token = save_aem_design("user@example.com", VALID_CONFIG)
    saved = {}
    monkeypatch.setattr(aem_routes, "submit_job", lambda kind, params: saved.update(kind=kind, params=params) or "job-1")
    monkeypatch.setattr(aem_routes, "save_job_meta", lambda job_id, meta: saved.update(job_id=job_id, meta=meta))

    response = _post(aem_client, "/aem/api/forward", json={"design": token})

    assert response.status_code == 202
    assert saved["kind"] == "aem_forward"
    # The forward path re-derives the domain at run time (idempotent re-validation),
    # so the queued config is the validated form, not the raw stored bounds.
    # "email" rides along so the worker can key its per-user .npz grid export.
    assert saved["params"] == {"config_json": aem_routes._validated_config(VALID_CONFIG),
                               "email": "user@example.com"}
    assert saved["meta"] == {"email": "user@example.com", "kind": "aem_forward"}


def test_forward_hides_another_users_design(aem_client):
    token = save_aem_design("other@example.com", VALID_CONFIG)

    assert aem_client.get(f"/aem/forward?design={token}").status_code == 404
    assert _post(aem_client, "/aem/api/forward", json={"design": token}).status_code == 404


def test_inverse_submission_uses_existing_queue(aem_client, monkeypatch):
    saved = {}
    monkeypatch.setattr(aem_routes, "submit_job", lambda kind, params: saved.update(kind=kind, params=params) or "job-2")
    monkeypatch.setattr(aem_routes, "save_job_meta", lambda job_id, meta: saved.update(meta=meta))
    response = _post(aem_client, "/aem/api/inverse", json={
        "estimate_param": "alpha_t", "orientation": "horizontal", "elem_kind": "Circle",
        "target_Lmax": 100, "r": 1, "C0": 5, "ca": 8, "gamma": 3.5,
        "tolerance": 10, "lower_bound": "", "upper_bound": "",
    })

    assert response.status_code == 202
    assert saved["kind"] == "aem_inverse"
    assert saved["meta"]["kind"] == "aem_inverse"


def test_owned_job_status_cancel_and_result(aem_client, monkeypatch):
    meta = {"email": "user@example.com", "kind": "aem_forward"}
    result = SimpleNamespace(
        result=[[0.0, float("nan")]], xaxis=[0, 1], yaxis=[0], L_max=12.0,
        ca=8.0, gamma=3.5, orientation="horizontal", num_elements=1,
        interface_length=None, validation_passed=True,
    )
    monkeypatch.setattr(aem_routes, "load_job_meta", lambda _job_id: meta)
    monkeypatch.setattr(aem_routes, "job_status", lambda _job_id: {"status": "done", "plume_length": 12.0})
    monkeypatch.setattr(aem_routes, "cancel_job", lambda _job_id: True)
    monkeypatch.setattr(aem_routes, "fetch_result", lambda _job_id: result)

    assert aem_client.get("/aem/jobs/job-1").status_code == 200
    assert _post(aem_client, "/aem/jobs/job-1/cancel", json={}).get_json()["success"] is True
    payload = aem_client.get("/aem/jobs/job-1/result").get_json()["result"]
    assert payload["field"] == [[0.0, None]]
    assert payload["L_max"] == 12.0


def test_completed_aem_grid_exposes_csv_and_workbench_links(aem_client, monkeypatch):
    meta = {"email": "user@example.com", "kind": "aem_forward"}
    result = SimpleNamespace(
        result=[[1.0, 2.0], [3.0, 4.0]],
        xaxis=[0.0, 1.0], yaxis=[-1.0, 0.0], L_max=12.0,
        ca=8.0, gamma=3.5, orientation="vertical", num_elements=1,
        interface_length=None, validation_passed=True,
    )
    monkeypatch.setattr(aem_routes, "load_job_meta", lambda _job_id: meta)
    monkeypatch.setattr(aem_routes, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(aem_routes, "fetch_result", lambda _job_id: result)

    body = aem_client.get("/aem/jobs/job-1/result").get_json()

    assert body["csv_url"] == "/aem/jobs/job-1/result.csv"
    assert body["workbench_url"] == "/data_analysis?aem_job=job-1"

    download = aem_client.get(body["csv_url"])
    rows = list(csv.DictReader(io.StringIO(download.get_data(as_text=True))))
    assert download.status_code == 200
    assert download.mimetype == "text/csv"
    assert list(rows[0]) == ["x [m]", "z [m]", "concentration [mg/L]"]
    assert [row["concentration [mg/L]"] for row in rows] == ["1.0", "2.0", "3.0", "4.0"]


def test_inverse_aem_grid_uses_the_same_handoff(aem_client, monkeypatch):
    meta = {"email": "user@example.com", "kind": "aem_inverse"}
    result = SimpleNamespace(
        result=[[1.0, 2.0], [3.0, 4.0]],
        xaxis=[0.0, 1.0], yaxis=[0.0, 1.0],
        estimate_param="alpha_t", recovered_value=0.2,
        target_L_max=10.0, achieved_L_max=10.1,
        lower_bound=0.1, upper_bound=0.3, converged=True,
        ca=8.0, gamma=3.5, orientation="horizontal",
    )
    monkeypatch.setattr(aem_routes, "load_job_meta", lambda _job_id: meta)
    monkeypatch.setattr(aem_routes, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(aem_routes, "fetch_result", lambda _job_id: result)

    body = aem_client.get("/aem/jobs/job-2/result").get_json()
    download = aem_client.get(body["csv_url"])

    assert body["workbench_url"] == "/data_analysis?aem_job=job-2"
    assert list(csv.DictReader(io.StringIO(download.get_data(as_text=True))))[0]["y [m]"] == "0.0"
    assert "aem_inverse_job2.csv" in download.headers["Content-Disposition"]


def test_aem_csv_leaves_nonfinite_cells_blank(aem_client, monkeypatch):
    meta = {"email": "user@example.com", "kind": "aem_forward"}
    result = SimpleNamespace(
        result=[[1.0, float("nan")], [3.0, 4.0]],
        xaxis=[0.0, 1.0], yaxis=[0.0, 1.0], L_max=12.0,
        ca=8.0, gamma=3.5, orientation="horizontal", num_elements=1,
        interface_length=None, validation_passed=True,
    )
    monkeypatch.setattr(aem_routes, "load_job_meta", lambda _job_id: meta)
    monkeypatch.setattr(aem_routes, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(aem_routes, "fetch_result", lambda _job_id: result)

    body = aem_client.get("/aem/jobs/job-1/result").get_json()
    rows = list(csv.DictReader(io.StringIO(
        aem_client.get(body["csv_url"]).get_data(as_text=True)
    )))

    assert "workbench_url" not in body
    assert rows[1]["concentration [mg/L]"] == ""


def test_job_endpoints_enforce_owner(aem_client, monkeypatch):
    monkeypatch.setattr(aem_routes, "load_job_meta", lambda _job_id: {"email": "other@example.com", "kind": "aem_forward"})

    assert aem_client.get("/aem/jobs/job-1").status_code == 404
    assert aem_client.get("/aem/jobs/job-1/result").status_code == 404
    assert aem_client.get("/aem/jobs/job-1/result.csv").status_code == 404
    assert _post(aem_client, "/aem/jobs/job-1/cancel", json={}).status_code == 404
