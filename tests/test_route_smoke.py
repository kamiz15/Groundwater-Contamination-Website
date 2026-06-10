from contextlib import ExitStack
import html
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
    "/source/geometry",
    "/source/inversion",
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


def test_headbar_contains_source_geometry_routes(authenticated_wrapper_client):
    response = authenticated_wrapper_client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/source/geometry"' in page
    assert 'href="/source/inversion"' in page
    assert ">Source Geometry</a>" in page
    assert ">Source Inversion</a>" in page


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
def test_numerical_export_submits_background_job(path, authenticated_wrapper_client, monkeypatch):
    monkeypatch.setattr(numerical_routes, "submit_job", lambda _kind, _params: "job-123")

    response = authenticated_wrapper_client.get(path)

    assert response.status_code == 202
    body = response.get_json()
    assert body["job_id"]
    assert body["status_url"].startswith("/numerical/jobs/")


@pytest.mark.parametrize(
    "path",
    ["/numerical/horizontal/single", "/numerical/vertical/single"],
)
def test_numerical_orlando_grid_fields_are_rendered_and_forwarded(path, authenticated_wrapper_client):
    response = authenticated_wrapper_client.get(path)
    page = response.get_data(as_text=True)
    iframe_src = html.unescape(page.split('iframe src="', 1)[1].split('"', 1)[0])
    iframe_query = parse_qs(urlparse(iframe_src).query)

    assert response.status_code == 200
    assert 'name="Lx"' in page
    assert 'name="ncol"' in page
    assert "Lx" in iframe_query
    assert "ncol" in iframe_query


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


def test_vertical_database_defaults_map_aquifer_thickness_to_lz(authenticated_wrapper_client, monkeypatch):
    site = {"id": 7, "aquifer_thickness": 3.5}
    monkeypatch.setattr(numerical_routes, "get_user_sites_rows", lambda _email: [site])

    page = authenticated_wrapper_client.get("/numerical/vertical/single?site_id=7").get_data(as_text=True)

    assert 'name="Lz"' in page
    assert 'value="3.5"' in page


@pytest.mark.parametrize(
    "path",
    ["/numerical/vertical/single", "/numerical/vertical/multiple"],
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

    assert "This site can't be modelled: hk 2246.4 m/d exceeds max" in unescaped_page
    assert "#7 - Valid Site" in page
    assert "#8 - Coarse Gravel" not in page


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
