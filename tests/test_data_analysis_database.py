import pandas as pd

from data_analysis.datasets import site_rows_frame


def test_site_rows_frame_uses_visible_numbers_and_excludes_internal_fields():
    rows = [
        {
            "id": 1580,
            "display_id": 1,
            "user_email": "user@example.com",
            "site_unit": "Site A",
            "compound": "BTEX",
            "aquifer_thickness": 10.0,
            "plume_length": 25.0,
            "extra_data": {"Temperature": "12.5", "Comment": "review"},
        },
        {
            "id": 1581,
            "display_id": 2,
            "user_email": "user@example.com",
            "site_unit": "Site B",
            "compound": "MTBE",
            "aquifer_thickness": 12.0,
            "plume_length": 30.0,
            "extra_data": {"Temperature": "14.0", "Comment": "check"},
        },
    ]

    frame = site_rows_frame(rows)

    assert list(frame["Site Number"]) == [1, 2]
    assert list(frame["Site unit"]) == ["Site A", "Site B"]
    assert "id" not in frame.columns
    assert "user_email" not in frame.columns
    assert "extra_data" not in frame.columns
    assert pd.api.types.is_numeric_dtype(frame["Temperature"])
    assert list(frame["Comment"]) == ["review", "check"]


def test_site_rows_frame_keeps_only_populated_database_columns():
    frame = site_rows_frame([
        {
            "id": 10,
            "site_unit": "Site A",
            "compound": "BTEX",
            "aquifer_thickness": None,
            "plume_length": 20.0,
            "extra_data": {"Empty custom": ""},
        }
    ])

    assert "Plume Length [m]" in frame.columns
    assert "Aquifer Thickness M [m]" not in frame.columns
    assert "Empty custom" not in frame.columns


def test_site_rows_frame_returns_empty_frame_without_database_rows():
    assert site_rows_frame([]).empty
