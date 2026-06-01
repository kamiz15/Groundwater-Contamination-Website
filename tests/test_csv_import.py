import pytest

import data_queries
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
        ["user@example.com", "Site A", "Benzene", None, None, None, None, None, None, None]
    ]
