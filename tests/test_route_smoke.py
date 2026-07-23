from contextlib import ExitStack
import html
import re
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest

import analytical_routes
import app as app_module
import empirical_routes
import numerical_routes
from security import GENERIC_DATABASE_ERROR_MESSAGE


WRAPPER_ROUTES = [
    "/liedl/single",
    "/liedl/multiple",
    "/chu/single",
    "/chu/multiple",
    "/ham/single",
    "/ham/multiple",
    "/bioscreen/single",
    "/bioscreen/multiple",
    "/liedl3d/single",
    "/liedl3d/multiple",
    "/cirpka/single",
    "/cirpka/multiple",
    "/empirical/maier/single",
    "/empirical/maier/multiple",
    "/empirical/birla/single",
    "/empirical/birla/multiple",
    "/numerical/single",
    "/numerical/multiple",
    "/numerical/horizontal/single",
    "/numerical/horizontal/multiple",
    "/numerical/vertical/single",
    "/numerical/vertical/multiple",
]


@pytest.fixture
def authenticated_wrapper_client():
    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
    with ExitStack() as patches:
        for module in (analytical_routes, empirical_routes, numerical_routes):
            patches.enter_context(patch.object(module, "_current_email", return_value="user@example.com"))
            patches.enter_context(patch.object(module, "get_user_sites_rows", return_value=[]))
        yield app_module.app.test_client()
    app_module.app.config["LOGIN_DISABLED"] = previous_login_disabled


@pytest.mark.parametrize("path", WRAPPER_ROUTES)
def test_authenticated_wrapper_route_renders(path, authenticated_wrapper_client):
    response = authenticated_wrapper_client.get(path, follow_redirects=True)

    assert response.status_code == 200
    assert b"<html" in response.data.lower()


def test_headbar_contains_aem_model_dropdown(authenticated_wrapper_client):
    response = authenticated_wrapper_client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AEM Model" in page
    assert "Source Geometry" not in page
    assert "Source Inversion" not in page


@pytest.mark.parametrize(
    "path",
    [
        "/liedl/single/export",
        "/liedl3d/single/export",
        "/chu/single/export",
        "/ham/single/export",
        "/bioscreen/single/export",
        "/cirpka/single/export",
        "/empirical/maier/single/export",
        "/empirical/birla/single/export",
    ],
)
def test_single_run_pdf_export_returns_non_empty_pdf(path, authenticated_wrapper_client):
    response = authenticated_wrapper_client.get(path)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 1000


@pytest.mark.parametrize(
    "path",
    [
        (
            "/numerical/horizontal/single/export?"
            "Lx=6&Ly=4&source=1&ncol=6&nrow=4&al=1&at=0.1&"
            "prsity=0.3&hk=1&h1=10&h2=9&C_D=0.2&C_A=8&C0=8.1&gamma=3.5&"
            "perlen=1"
        ),
        (
            "/numerical/vertical/single/export?"
            "Lx=6&Lz=4&ncol=6&nlay=4&al=1&at=0.1&atv=0.1&prsity=0.3&"
            "hk=1&h1=10&h2=9&C_D=0.2&C_A=8&C0=8.1&gamma=3.5&perlen=1"
        ),
    ],
)
def test_numerical_export_submits_background_job(path, authenticated_wrapper_client, monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setattr(numerical_routes, "submit_job", lambda _kind, _params: "job-123")

    response = authenticated_wrapper_client.get(path)

    assert response.status_code == 202
    body = response.get_json()
    assert body["job_id"]
    assert body["status_url"].startswith("/numerical/jobs/")
    assert body["report_url"].startswith("/numerical/jobs/")
    # The export job is bound to the submitting user for later ownership checks.
    meta = numerical_routes.load_job_meta("job-123")
    assert meta["email"] == "user@example.com"
    assert meta["parameters"]


def test_numerical_job_endpoints_hide_other_users_jobs(authenticated_wrapper_client, monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    from numerical_jobs import save_job_meta

    save_job_meta("foreign-job", {"email": "someone.else@example.com"})

    status = authenticated_wrapper_client.get("/numerical/jobs/foreign-job")
    report = authenticated_wrapper_client.get("/numerical/jobs/foreign-job/report")

    assert status.status_code == 404
    assert report.status_code == 404


def test_numerical_job_report_rejected_until_done(authenticated_wrapper_client, monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    from numerical_jobs import save_job_meta

    save_job_meta("queued-job", {"email": "user@example.com"})
    monkeypatch.setattr(
        numerical_routes, "job_status", lambda _job_id: {"status": "queued", "queue_position": 1}
    )

    response = authenticated_wrapper_client.get("/numerical/jobs/queued-job/report")

    assert response.status_code == 409
    assert response.get_json()["status"] == "queued"


@pytest.mark.parametrize(
    "path, expected_fields",
    [
        ("/numerical/horizontal/single", ["source_thickness", "grid_size", "al", "at", "gamma", "C_D", "C_A"]),
        ("/numerical/vertical/single", ["Lz", "grid_size", "al", "atv", "gamma", "C_D", "C_A"]),
    ],
)
def test_numerical_orlando_grid_fields_are_rendered_and_forwarded(
    path, expected_fields, authenticated_wrapper_client
):
    response = authenticated_wrapper_client.get(path)
    page = response.get_data(as_text=True)
    iframe_src = html.unescape(page.split('iframe src="', 1)[1].split('"', 1)[0])
    iframe_query = parse_qs(urlparse(iframe_src).query)

    assert response.status_code == 200
    for field in expected_fields:
        assert f'name="{field}"' in page
        assert field in iframe_query
    assert 'name="ncol"' not in page
    assert "ncol" not in iframe_query


@pytest.mark.parametrize(
    "path",
    ["/numerical/horizontal/single", "/numerical/vertical/single"],
)
def test_numerical_single_wrapper_defers_solver_until_general_run(path, authenticated_wrapper_client):
    idle_response = authenticated_wrapper_client.get(path)
    idle_page = idle_response.get_data(as_text=True)
    idle_iframe_src = html.unescape(idle_page.split('iframe src="', 1)[1].split('"', 1)[0])

    run_response = authenticated_wrapper_client.get(f"{path}?run=1")
    run_page = run_response.get_data(as_text=True)
    run_iframe_src = html.unescape(run_page.split('iframe src="', 1)[1].split('"', 1)[0])

    assert "run" not in parse_qs(urlparse(idle_iframe_src).query)
    assert parse_qs(urlparse(run_iframe_src).query)["run"] == ["1"]
    assert idle_page.count(">Run Model<") == 1
    assert "Update Output" not in idle_page


@pytest.mark.parametrize(
    "path",
    ["/numerical/horizontal/multiple", "/numerical/vertical/multiple"],
)
def test_numerical_multiple_wrapper_has_only_panel_run_action(path, authenticated_wrapper_client):
    page = authenticated_wrapper_client.get(path).get_data(as_text=True)

    assert "model-input-form" not in page
    assert "Run Model" not in page


@pytest.mark.parametrize(
    ("path", "result_frame_id"),
    [
        ("/numerical/vertical/multiple", "verticalMultipleResultFrame"),
        ("/numerical/horizontal/multiple", "horizontalMultipleResultFrame"),
    ],
)
def test_numerical_multiple_wrapper_places_panel_in_layout(
    path,
    result_frame_id,
    authenticated_wrapper_client,
    monkeypatch,
):
    # Sites are added from the in-panel click-to-add picker, so the wrapper has
    # no server-side "Load Uploaded Site" loader. Layout: Simulation Panel on the
    # left, the result frame on the right; no conceptual model.
    monkeypatch.setattr(numerical_routes, "get_user_sites_rows", lambda _email: [{"id": 7}])

    page = authenticated_wrapper_client.get(path).get_data(as_text=True)
    iframe_srcs = [
        html.unescape(match)
        for match in re.findall(r'<iframe\b[^>]*\bsrc="([^"]+)"', page)
    ]
    input_query = parse_qs(urlparse(iframe_srcs[0]).query)
    result_query = parse_qs(urlparse(iframe_srcs[1]).query)

    assert "model-input-form" not in page
    assert "Load Uploaded Site" not in page
    assert "conceptual-img" not in page
    assert page.index("Simulation Panel") < page.index(f'id="{result_frame_id}"')
    assert len(iframe_srcs) == 2
    assert input_query["input_only"] == ["1"]
    assert "output_only" not in input_query
    assert result_query["output_only"] == ["1"]


def test_vertical_database_defaults_map_aquifer_thickness_to_lz(authenticated_wrapper_client, monkeypatch):
    site = {"id": 7, "aquifer_thickness": 3.5}
    monkeypatch.setattr(numerical_routes, "get_user_sites_rows", lambda _email: [site])

    page = authenticated_wrapper_client.get("/numerical/vertical/single?site_id=7").get_data(as_text=True)

    assert 'name="Lz"' in page
    assert 'value="3.5"' in page


def _field_markup(page, field):
    return page.split(f'name="{field}"', 1)[0].rsplit("<label>", 1)[-1]


def test_vertical_solver_extra_data_fields_show_db_badges(authenticated_wrapper_client, monkeypatch):
    site = {
        "id": 7,
        "extra_data": {"Lz": "12", "grid_size": "0.5", "al": "2.0"},
    }
    monkeypatch.setattr(numerical_routes, "get_user_sites_rows", lambda _email: [site])

    page = authenticated_wrapper_client.get("/numerical/vertical/single?site_id=7").get_data(as_text=True)

    for field, value in (("Lz", "12"), ("grid_size", "0.5"), ("al", "2")):
        assert f'name="{field}"' in page
        assert f'value="{value}"' in page
        assert 'input-source-badge--db">DB</em>' in _field_markup(page, field)


def test_horizontal_solver_extra_data_fields_show_db_badges(authenticated_wrapper_client, monkeypatch):
    site = {
        "id": 7,
        "extra_data": {"grid_size": "0.75", "al": "2.5", "at": "0.25"},
    }
    monkeypatch.setattr(numerical_routes, "get_user_sites_rows", lambda _email: [site])

    page = authenticated_wrapper_client.get("/numerical/horizontal/single?site_id=7").get_data(as_text=True)

    for field, value in (("grid_size", "0.75"), ("al", "2.5"), ("at", "0.25")):
        assert f'name="{field}"' in page
        assert f'value="{value}"' in page
        assert 'input-source-badge--db">DB</em>' in _field_markup(page, field)


def test_vertical_single_run_button_sits_under_conceptual_model(authenticated_wrapper_client):
    page = authenticated_wrapper_client.get("/numerical/vertical/single").get_data(as_text=True)

    assert page.count(">Run Model<") == 1
    assert page.index('class="conceptual-img"') < page.index('form="model-input-form"')


@pytest.mark.parametrize(
    "path",
    # The multiple page lists/validates sites inside the Panel now, so only the
    # single page renders the server-side dropdown this test inspects.
    ["/numerical/vertical/single"],
)
def test_vertical_pages_filter_invalid_high_hk_sites_and_still_load(path, authenticated_wrapper_client, monkeypatch):
    valid = {
        "id": 7,
        "site_unit": "Valid Site",
        "compound": "BTEX",
        "aquifer_thickness": 10.0,
        "hydraulic_conductivity": 0.001,
        "electron_donor": 5.0,
        "electron_acceptor_o2": 0.0,
    }
    invalid = {
        "id": 8,
        "site_unit": "Coarse Gravel",
        "compound": "BTEX",
        "aquifer_thickness": 10.0,
        "hydraulic_conductivity": 0.026,
        "electron_donor": 5.0,
        "electron_acceptor_o2": 0.0,
    }
    monkeypatch.setattr(numerical_routes, "get_user_sites_rows", lambda _email: [invalid, valid])

    page = authenticated_wrapper_client.get(f"{path}?site_id=8").get_data(as_text=True)
    unescaped_page = html.unescape(page)

    assert "This site can't be modelled" not in unescaped_page
    assert "#7 - Valid Site" in page
    assert "#8 - Coarse Gravel" in page


@pytest.mark.parametrize(
    "path",
    [
        "/liedl/single",
        "/liedl3d/single",
        "/chu/single",
        "/ham/single",
        "/bioscreen/single",
        "/cirpka/single",
        "/empirical/maier/single",
        "/empirical/birla/single",
        "/numerical/horizontal/single",
        "/numerical/vertical/single",
    ],
)
def test_single_model_pages_share_branded_report_card(path, authenticated_wrapper_client):
    page = authenticated_wrapper_client.get(path).get_data(as_text=True)

    assert "report-download-card" in page
    assert "Download the branded CAST PDF report" in page


ABOUT_SLUGS = [
    "liedl",
    "liedl3d",
    "chu",
    "ham",
    "bioscreen",
    "cirpka",
    "maier",
    "birla",
    "numerical",
]


@pytest.fixture
def public_client():
    # The per-model About pages must be reachable without authentication, so no
    # LOGIN_DISABLED and no auth fixture — just a plain test client.
    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    yield app_module.app.test_client()
    app_module.app.config["LOGIN_DISABLED"] = previous_login_disabled


@pytest.mark.parametrize("slug", ABOUT_SLUGS)
def test_model_about_page_is_public_and_has_mathml(slug, public_client):
    response = public_client.get(f"/models/{slug}/about")

    assert response.status_code == 200
    assert b"<math" in response.data


def test_model_about_unknown_slug_returns_404(public_client):
    response = public_client.get("/models/does-not-exist/about")

    assert response.status_code == 404


def test_liedl_about_pilot_has_chips_and_no_placeholders(public_client):
    page = public_client.get("/models/liedl/about").get_data(as_text=True)

    assert "about-chips" in page
    assert "about-assumptions--check" in page
    assert "[TODO" not in page


def test_non_pilot_about_pages_stay_plain(public_client):
    # The chips/checklist upgrades are gated to the Liedl pilot until approved.
    page = public_client.get("/models/chu/about").get_data(as_text=True)

    assert "about-chips" not in page


def test_cirpka_single_output_hides_internal_error_detail(monkeypatch, caplog):
    internal_detail = "private database exception detail"

    def fail_comparison_plot(*_args, **_kwargs):
        raise RuntimeError(internal_detail)

    monkeypatch.setattr(analytical_routes, "comparison_plot", fail_comparison_plot)

    output = analytical_routes._cirpka_single_output(
        {
            "Sw": 10.0,
            "alpha_Th": 0.1,
            "gamma": 3.5,
            "C_A": 8.0,
            "C_D": 5.0,
            "site_id": None,
            "email": "user@example.com",
        }
    )

    assert output["error"] == GENERIC_DATABASE_ERROR_MESSAGE
    assert internal_detail not in output["error"]
    assert internal_detail in caplog.text
