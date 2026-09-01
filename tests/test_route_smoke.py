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


@pytest.mark.parametrize(
    ("path", "full_name"),
    [
        ("/chu/single", "Chu et al. (2005) - Single Simulation"),
        ("/ham/multiple", "Ham et al. (2004) - Multiple Simulation"),
        ("/liedl3d/single", "Liedl 3D (2011) - Single Simulation"),
        ("/bioscreen/single", "BIOSCREEN-AT 3D - Single Simulation"),
        ("/cirpka/multiple", "Cirpka et al. (2006) - Multiple Simulation"),
        ("/empirical/maier/single", "Maier &amp; Grathwohl (2006) - Single Simulation"),
        ("/empirical/birla/multiple", "Birla et al. (2020) - Multiple Simulation"),
    ],
)
def test_model_pages_use_full_about_page_names(path, full_name, authenticated_wrapper_client):
    page = authenticated_wrapper_client.get(path).get_data(as_text=True)

    assert full_name in page


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
    "path",
    ["/numerical/vertical/multiple", "/numerical/horizontal/multiple"],
)
def test_numerical_multiple_wrapper_places_panel_in_layout(
    path,
    authenticated_wrapper_client,
    monkeypatch,
):
    # The scenario table inside the frame is the run now, and the site picker is
    # in there with it. One panel frame, no separate runner frame, no sidebar, no
    # single-site loader and no conceptual model.
    monkeypatch.setattr(numerical_routes, "get_user_sites_rows", lambda _email: [{"id": 7, "site_unit": "Borden"}])

    page = authenticated_wrapper_client.get(path).get_data(as_text=True)
    iframe_srcs = [
        html.unescape(match)
        for match in re.findall(r'<iframe\s[^>]*src="([^"]+)"', page)
    ]

    assert len(iframe_srcs) == 1
    assert "model-input-form" not in page
    assert "Load Uploaded Site" not in page
    assert "conceptual-img" not in page
    assert 'name="compare_sites"' not in page     # the picker is inside the frame
    assert "model-workbench-sidebar" not in page
    assert 'id="scenarioDialog"' in page          # the Add-row dialog is the page's

    # Nothing picked: the panel is told so (empty value, which parse_qs drops)
    # and is NOT told to run, so a page load never queues a solver job.
    assert "compare_sites=" in iframe_srcs[0]
    assert "run=1" not in iframe_srcs[0]

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

ANALYTICAL_ABOUT_SLUGS = [
    "liedl",
    "liedl3d",
    "chu",
    "ham",
    "bioscreen",
    "cirpka",
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


@pytest.mark.parametrize("slug", ANALYTICAL_ABOUT_SLUGS)
def test_analytical_about_pages_label_equations_as_solutions(slug, public_client):
    page = public_client.get(f"/models/{slug}/about").get_data(as_text=True)

    assert '<span class="about-equation-label">Solution</span>' in page


def test_model_about_unknown_slug_returns_404(public_client):
    response = public_client.get("/models/does-not-exist/about")

    assert response.status_code == 404


def test_liedl_about_pilot_has_chips_and_no_placeholders(public_client):
    page = public_client.get("/models/liedl/about").get_data(as_text=True)

    assert "about-chips" in page
    assert "about-assumptions--check" in page
    assert "conceptual_liedl_2005.png" in page
    assert 'mathvariant="normal">max' in page
    assert "Closed form" not in page
    assert 'title="Source thickness [L]"><mi>T</mi><mi>s</mi>' in page
    assert "Transverse vertical dispersivity [L]" in page
    assert "Stoichiometry ratio [-]" in page
    assert "Donor concentration at source [ML⁻³]" in page
    assert "Water Resources Research 41, no. 12: 2005WR004000" in page
    assert "[TODO" not in page


def test_liedl3d_about_uses_corrected_symbols_dimensions_and_source(public_client):
    page = public_client.get("/models/liedl3d/about").get_data(as_text=True)

    assert "conceptual_liedl_2011.png" in page
    assert 'title="Source thickness [L]"><mi>T</mi><mi>s</mi>' in page
    assert 'title="Source width [L]"><mi>S</mi><mi>W</mi>' in page
    assert "Transverse horizontal dispersivity [L]" in page
    assert "Threshold donor concentration [ML⁻³]" in page
    assert "Liedl, R., P. K. Yadav, and P. Dietrich. 2011." in page
    assert "Resources Research 47, no. 8" in page


def test_chu_about_uses_corrected_symbol_dimensions_and_source(public_client):
    page = public_client.get("/models/chu/about").get_data(as_text=True)

    assert "conceptual_chu_2005.png" in page
    assert "Chu et al. (2005)" in page
    assert 'title="Source width [L]"><mi>S</mi><mi>W</mi>' in page
    assert "Transverse horizontal dispersivity [L]" in page
    assert "Biological concentration factor [ML⁻³]" in page
    assert "Chu, M., P. Kitanidis, and P. McCarty. 2005." in page
    assert "Research 41, no. 6: W06002" in page


def test_ham_about_uses_corrected_symbols_dimensions_and_source(public_client):
    page = public_client.get("/models/ham/about").get_data(as_text=True)

    assert "conceptual_ham_2004.png" in page
    assert 'title="Source flux [L²T⁻¹]">W</mi><mi>e</mi>' in page
    assert "flux <math><msub><mi>W</mi><mi>e</mi></msub></math>" in page
    assert "Transverse horizontal dispersivity [L]" in page
    assert "Donor concentration at source [LT⁻³]" in page
    assert "Ham, P. A. S., R. J. Schotting, H. Prommer, and G. B. Davis. 2004." in page
    assert "Advances in Water Resources 27, no. 8: 803&ndash;13" in page


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
