"""Regression tests for site-input validation in the data layer.

Covers the database-hardening pass: bad numeric values, over-long text, and
oversized bulk uploads are rejected before reaching MySQL, with clear messages.
"""

import pytest

import data_queries


def _valid_payload(**overrides):
    payload = {
        "site_unit": "Unit-A",
        "compound": "TCE",
        "aquifer_thickness": "10",
        "plume_length": "120",
        "plume_width": "30",
        "hydraulic_conductivity": "0.0001",
        "electron_donor": "5",
        "electron_acceptor_o2": "8",
        "electron_acceptor_no3": "2",
    }
    payload.update(overrides)
    return payload


def test_clean_payload_accepts_valid_row():
    values = data_queries._clean_site_payload(_valid_payload())
    assert values[0] == "Unit-A"
    assert values[1] == "TCE"
    assert values[2] == 10.0


def test_clean_payload_rejects_negative_numeric():
    with pytest.raises(ValueError, match="cannot be negative"):
        data_queries._clean_site_payload(_valid_payload(plume_length="-5"))


@pytest.mark.parametrize("bad", ["inf", "-inf", "Infinity", "1e9999"])
def test_clean_payload_rejects_non_finite(bad):
    with pytest.raises(ValueError, match="finite"):
        data_queries._clean_site_payload(_valid_payload(aquifer_thickness=bad))


def test_clean_payload_rejects_overlong_text():
    with pytest.raises(ValueError, match="at most 50 characters"):
        data_queries._clean_site_payload(_valid_payload(compound="X" * 51))


def test_clean_payload_treats_blank_and_na_as_null():
    values = data_queries._clean_site_payload(
        _valid_payload(electron_donor="", electron_acceptor_o2="N/A")
    )
    # electron_donor and electron_acceptor_o2 are positions 6 and 7 in SITE_FIELDS
    assert values[6] is None
    assert values[7] is None


def test_bulk_upload_row_cap_enforced(monkeypatch):
    monkeypatch.setattr(data_queries, "MAX_SITE_UPLOAD_ROWS", 3)
    payloads = [_valid_payload(site_unit=f"U{i}") for i in range(4)]
    with pytest.raises(ValueError, match="Too many rows"):
        data_queries.insert_sites_bulk("user@example.com", payloads)


def test_bulk_upload_validates_each_row_before_insert(monkeypatch):
    """A single bad row must abort the whole upload (no partial inserts)."""
    calls = {"executemany": 0}

    class _Cursor:
        def executemany(self, *a):
            calls["executemany"] += 1

        def execute(self, *a):
            pass

        def fetchall(self):
            return []  # duplicate-detection read: no existing rows

        def close(self):
            pass

    class _Conn:
        def cursor(self, *a, **k):
            return _Cursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(data_queries, "get_db_connection", lambda: _Conn())
    payloads = [_valid_payload(), _valid_payload(plume_width="-1")]
    with pytest.raises(ValueError):
        data_queries.insert_sites_bulk("user@example.com", payloads)
    assert calls["executemany"] == 0  # nothing written when any row is invalid
