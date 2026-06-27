import io
import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest

import app as app_module
import data_queries
import site_routes
from site_routes import _build_field_to_header_map, _detect_delimiter, _extra_field_keys


@pytest.mark.parametrize(
    "text, expected",
    [
        ("a,b,c\n1,2,3\n", ","),
        ("Lz;grid_size;al;atv;gamma;Cd;Ca\n10;1;1;0.1;3.5;5;8\n", ";"),
        ("a\tb\tc\n1\t2\t3\n", "\t"),
        ("a|b|c\n1|2|3\n", "|"),
        ("single\n1\n", ","),  # no delimiter present -> comma fallback
    ],
)
def test_detect_delimiter(text, expected):
    assert _detect_delimiter(text) == expected


def test_extra_field_keys_unions_in_first_seen_order():
    rows = [
        {"extra_data": {"SO4": "5", "Country": "DE"}},
        {"extra_data": {"Country": "US", "Fe(II)": "650"}},
        {"extra_data": {}},
    ]
    assert _extra_field_keys(rows) == ["SO4", "Country", "Fe(II)"]


class RecordingCursor:
    def __init__(self):
        self.rows = None

    def execute(self, *_args, **_kwargs):
        # Used by the duplicate-detection read (SELECT * FROM sites ...).
        return None

    def fetchall(self):
        # No pre-existing rows in these unit tests.
        return []

    def executemany(self, _query, rows):
        self.rows = rows

    def close(self):
        return None


class RecordingConnection:
    def __init__(self):
        self.cursor_instance = RecordingCursor()
        self.committed = False

    def cursor(self, *_args, **_kwargs):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        return None


def test_csv_header_aliases_normalise_to_site_fields():
    headers = [
        "Site Unit",
        "Compound",
        "Aquifer thickness[m]",
        "Plume length[m]",
        "Plume width[m]",
        "Hydraulic conductivity[10-3 [m/s]]",
        "Electron donor[mg/l]",
        "Electron acceptors : o2[mg/l]",
        "no3[mg/l]",
    ]

    assert _build_field_to_header_map(headers) == {
        "site_unit": "Site Unit",
        "compound": "Compound",
        "aquifer_thickness": "Aquifer thickness[m]",
        "plume_length": "Plume length[m]",
        "plume_width": "Plume width[m]",
        "hydraulic_conductivity": "Hydraulic conductivity[10-3 [m/s]]",
        "electron_donor": "Electron donor[mg/l]",
        "electron_acceptor_o2": "Electron acceptors : o2[mg/l]",
        "electron_acceptor_no3": "no3[mg/l]",
    }


@pytest.mark.parametrize("missing_value", ["N/A", "null", "-"])
def test_csv_missing_numeric_markers_become_sql_null(monkeypatch, missing_value):
    connection = RecordingConnection()
    monkeypatch.setattr(data_queries, "get_db_connection", lambda: connection)

    inserted = data_queries.insert_sites_bulk(
        "user@example.com",
        [
            {
                "site_unit": "Site A",
                "compound": "Benzene",
                "aquifer_thickness": missing_value,
                "plume_length": missing_value,
                "plume_width": missing_value,
                "hydraulic_conductivity": missing_value,
                "electron_donor": missing_value,
                "electron_acceptor_o2": missing_value,
                "electron_acceptor_no3": missing_value,
            }
        ],
    )

    assert inserted == (1, 0)
    assert connection.committed
    # email + 2 text fields + every numeric column (all NULL here) + extra_data.
    numeric_nulls = [None] * len(data_queries.NUMERIC_SITE_FIELDS)
    assert connection.cursor_instance.rows == [
        # Trailing None is extra_data: no unmapped columns -> SQL NULL.
        ["user@example.com", "Site A", "Benzene", *numeric_nulls, None]
    ]


def test_insert_sites_bulk_serialises_extra_data_to_json(monkeypatch):
    """Unmapped columns carried in payload['extra_data'] persist as a JSON
    string in the trailing INSERT element."""
    connection = RecordingConnection()
    monkeypatch.setattr(data_queries, "get_db_connection", lambda: connection)

    inserted = data_queries.insert_sites_bulk(
        "user@example.com",
        [
            {
                "site_unit": "Site A",
                "compound": "Benzene",
                "extra_data": {"Porosity": "0.3"},
            }
        ],
    )

    assert inserted == (1, 0)
    row = connection.cursor_instance.rows[0]
    # email + all SITE_FIELDS + extra_data.
    assert len(row) == len(data_queries.SITE_FIELDS) + 2
    # Compare order-independently: the last element is the JSON-encoded extras.
    assert json.loads(row[-1]) == {"Porosity": "0.3"}


def test_flexible_upload_routes_extra_column_into_extra_data():
    """POSTing a CSV that carries the recognized headers PLUS a recognized
    model parameter ('gamma') and a genuinely-unknown column ('Porosity')
    imports cleanly. 'gamma' is captured into its typed column; only the
    unrecognized 'Porosity' is routed into extra_data."""
    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)

    captured = {}

    def fake_bulk(email, payloads):
        captured["email"] = email
        captured["payloads"] = payloads
        return len(payloads), 0

    csv_text = (
        "Site Unit,Compound,Aquifer thickness[m],Plume length[m],Plume width[m],"
        "Hydraulic conductivity[10-3 [m/s]],Electron donor[mg/l],"
        "Electron acceptors : o2[mg/l],no3[mg/l],gamma,Porosity\r\n"
        "Site A,Benzene,10,100,5,0.001,5,8,0,4.2,0.3\r\n"
    )

    try:
        with ExitStack() as patches:
            patches.enter_context(
                patch.object(site_routes, "_current_email", return_value="user@example.com")
            )
            patches.enter_context(
                patch.object(site_routes, "insert_sites_bulk", fake_bulk)
            )
            # The view re-renders the site table after the insert; keep that
            # off the real database.
            patches.enter_context(
                patch.object(site_routes, "get_user_sites_rows", return_value=[])
            )
            client = app_module.app.test_client()
            client.get("/login")
            with client.session_transaction() as session:
                token = session["_csrf_token"]

            response = client.post(
                "/sites",
                data={
                    "action": "upload_csv",
                    "csv_file": (io.BytesIO(csv_text.encode("utf-8")), "sites.csv"),
                },
                content_type="multipart/form-data",
                headers={"X-CSRF-Token": token},
            )
    finally:
        app_module.app.config["LOGIN_DISABLED"] = previous_login_disabled

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    # No upload-error flash on the rendered page.
    assert "Missing required CSV columns" not in page
    assert "No valid data rows" not in page

    assert captured["email"] == "user@example.com"
    payloads = captured["payloads"]
    assert len(payloads) == 1
    extra = payloads[0]["extra_data"]
    # Only the genuinely-unrecognized column lands in extra_data.
    assert extra == {"Porosity": "0.3"}
    # The recognized columns map to their typed fields, including 'gamma' which
    # now has its own column instead of being an opaque extra.
    assert payloads[0]["site_unit"] == "Site A"
    assert payloads[0]["compound"] == "Benzene"
    assert payloads[0]["gamma"] == "4.2"


def test_site_no_does_not_steal_site_unit_column():
    """When both 'Site No.' (a row index) and 'Site Unit' (the name) are present,
    the name owns site_unit; the index is not mapped to it."""
    mapping = _build_field_to_header_map(["Site No.", "Site Unit", "Compound"])
    assert mapping["site_unit"] == "Site Unit"
    assert "Site No." not in mapping.values()


def _upload_csv_capture(csv_text):
    """Post a CSV through the real upload route, returning captured payloads."""
    previous = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
    captured = {}

    def fake_bulk(email, payloads):
        captured["payloads"] = payloads
        return len(payloads), 0

    try:
        with ExitStack() as patches:
            patches.enter_context(
                patch.object(site_routes, "_current_email", return_value="user@example.com")
            )
            patches.enter_context(patch.object(site_routes, "insert_sites_bulk", fake_bulk))
            patches.enter_context(
                patch.object(site_routes, "get_user_sites_rows", return_value=[])
            )
            client = app_module.app.test_client()
            client.get("/login")
            with client.session_transaction() as session:
                token = session["_csrf_token"]
            client.post(
                "/sites",
                data={
                    "action": "upload_csv",
                    "csv_file": (io.BytesIO(csv_text.encode("utf-8")), "sites.csv"),
                },
                content_type="multipart/form-data",
                headers={"X-CSRF-Token": token},
            )
    finally:
        app_module.app.config["LOGIN_DISABLED"] = previous
    return captured["payloads"]


def test_declared_unit_scale_applied_to_hydraulic_conductivity():
    csv_text = (
        "Site Unit,Hydraulic conductivity[10-3 [m/s]]\r\n"
        "Site A,0.4\r\n"
    )
    payloads = _upload_csv_capture(csv_text)
    # 0.4 declared in 10^-3 m/s -> stored as 0.4e-3 m/s.
    assert float(payloads[0]["hydraulic_conductivity"]) == pytest.approx(0.4e-3)


def test_insert_sites_bulk_skips_exact_duplicates(monkeypatch):
    connection = RecordingConnection()
    monkeypatch.setattr(data_queries, "get_db_connection", lambda: connection)
    existing = [{"site_unit": "Site A", "compound": "Benzene",
                 "aquifer_thickness": 10.0, "extra_data": {}}]
    monkeypatch.setattr(data_queries, "get_user_sites_rows", lambda email: existing)

    inserted, skipped = data_queries.insert_sites_bulk(
        "user@example.com",
        [
            {"site_unit": "Site A", "compound": "Benzene", "aquifer_thickness": "10"},  # dup
            {"site_unit": "Site B", "compound": "Toluene", "aquifer_thickness": "8"},   # new
        ],
    )

    assert (inserted, skipped) == (1, 1)
    written = connection.cursor_instance.rows
    assert len(written) == 1
    assert written[0][1] == "Site B"  # only the non-duplicate row reached the DB
