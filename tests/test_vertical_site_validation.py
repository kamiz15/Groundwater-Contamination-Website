from pathlib import Path

from numerical_input_validation import filter_valid_vertical_sites, vertical_inputs_from_site
import scripts.audit_vertical_sites as audit_vertical_sites


def _site(site_id, name, hydraulic_conductivity=0.001):
    return {
        "id": site_id,
        "site_unit": name,
        "compound": "BTEX",
        "aquifer_thickness": 10.0,
        "hydraulic_conductivity": hydraulic_conductivity,
        "electron_donor": 5.0,
        "electron_acceptor_o2": 0.0,
    }


def test_vertical_site_validation_reports_high_converted_hk():
    inputs, issues = vertical_inputs_from_site(_site(8, "Coarse Gravel", hydraulic_conductivity=0.026))

    assert inputs["hk"] if "hk" in inputs else True
    assert any(issue.reason == "hk 2246.4 m/d exceeds max 1000 m/d" for issue in issues)


def test_vertical_dropdown_filter_uses_shared_validation():
    valid = _site(7, "Valid Site")
    invalid = _site(8, "Coarse Gravel", hydraulic_conductivity=0.026)

    valid_sites, invalid_sites = filter_valid_vertical_sites([invalid, valid])

    assert [site["id"] for site in valid_sites] == [7]
    assert invalid_sites[8][0].reason == "hk 2246.4 m/d exceeds max 1000 m/d"


def test_audit_script_uses_shared_validation(monkeypatch):
    monkeypatch.setattr(
        audit_vertical_sites,
        "fetch_sites",
        lambda: [_site(8, "Coarse Gravel", hydraulic_conductivity=0.026)],
    )

    rows = audit_vertical_sites.audit_rows()

    assert rows == [
        {
            "site_id": 8,
            "site_name": "Coarse Gravel",
            "field": "hk",
            "value": 2246.4,
            "reason": "hk 2246.4 m/d exceeds max 1000 m/d",
        }
    ]


def test_audit_and_filter_import_same_validation_function():
    source = Path("scripts/audit_vertical_sites.py").read_text(encoding="utf-8")

    assert "from numerical_input_validation import vertical_inputs_from_site" in source
