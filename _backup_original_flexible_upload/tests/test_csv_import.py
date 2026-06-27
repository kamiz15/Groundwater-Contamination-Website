import io
import json
from contextlib import ExitStack
from unittest.mock import patch

import pytest

import app as app_module
import data_queries
import site_routes
from site_routes import _build_field_to_header_map


class RecordingCursor:
    def __init__(self):
        self.rows = None

    def executemany(self, _query, rows):
        self.rows = rows

    def close(self):
        return None


class RecordingConnection:
    def __init__(self):
        self.cursor_instance = RecordingCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        return None


def test_csv_header_aliases_normalise_to_site_fields():
    headers = [
        "Site no.",
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
        "site_unit": "Site no.",
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

    assert inserted == 1
    assert connection.committed
    assert connection.cursor_instance.rows == [
        # Trailing None is extra_data: no unmapped columns -> SQL NULL.
        ["user@example.com", "Site A", "Benzene", None, None, None, None, None, None, None, None]
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

    assert inserted == 1
    row = connection.cursor_instance.rows[0]
    assert len(row) == 11
    # Compare order-independently: the last element is the JSON-encoded extras.
    assert json.loads(row[-1]) == {"Porosity": "0.3"}


def test_flexible_upload_routes_extra_column_into_extra_data():
    """POSTing a CSV that carries the 9 recognized headers PLUS an unmapped
    'gamma' column imports cleanly, and the captured payload routes 'gamma'
    into extra_data rather than discarding or rejecting it."""
    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)

    captured = {}

    def fake_bulk(email, payloads):
        captured["email"] = email
        captured["payloads"] = payloads
        return len(payloads)

    csv_text = (
        "Site no.,Compound,Aquifer thickness[m],Plume length[m],Plume width[m],"
        "Hydraulic conductivity[10-3 [m/s]],Electron donor[mg/l],"
        "Electron acceptors : o2[mg/l],no3[mg/l],gamma\r\n"
        "Site A,Benzene,10,100,5,0.001,5,8,0,4.2\r\n"
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
    assert extra == {"gamma": "4.2"}
    # The recognized columns still map to their fixed fields.
    assert payloads[0]["site_unit"] == "Site A"
    assert payloads[0]["compound"] == "Benzene"
