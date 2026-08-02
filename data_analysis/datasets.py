"""CSV intake and column-typing helpers for the data-analysis workbench.

Pure pandas/numpy; no Panel imports so this stays unit-testable. Every failure
mode raises ``ValueError`` with a message that is safe to show a user.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from symbol_registry import SITE_COLUMN_DEFS, TEXT_COLUMN_DEFS, header_to_site_column

# Try a few encodings in order. utf-8-sig transparently strips a BOM, which
# spreadsheets on Windows frequently add.
_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1")

_CANONICAL_SITE_LABELS = {
    **{field: meta["ui"] for field, meta in TEXT_COLUMN_DEFS.items()},
    **{field: label for field, label, _unit in SITE_COLUMN_DEFS},
}


def _canonical_workbench_columns(columns) -> list[str]:
    """Normalize recognized site headers; preserve unknown CSV columns verbatim."""
    normalized = []
    used = set()
    for raw_column in columns:
        original = str(raw_column).strip()
        site_field = header_to_site_column(original)
        candidate = _CANONICAL_SITE_LABELS.get(site_field, original)
        if candidate in used:
            base = f"{candidate} (additional)"
            candidate = base
            suffix = 2
            while candidate in used:
                candidate = f"{base} {suffix}"
                suffix += 1
        normalized.append(candidate)
        used.add(candidate)
    return normalized


def _has_value(value) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def site_rows_frame(rows: list[dict]) -> pd.DataFrame:
    """Build the workbench dataset from the current user's site rows.

    Internal database fields stay hidden. Recognized fields retain the same
    labels and order as the Database page, while populated custom upload
    columns are flattened out of ``extra_data`` in first-seen order.
    """
    if not rows:
        return pd.DataFrame()

    field_defs = [
        ("site_unit", TEXT_COLUMN_DEFS["site_unit"]["ui"]),
        ("compound", TEXT_COLUMN_DEFS["compound"]["ui"]),
        *((field, label) for field, label, _unit in SITE_COLUMN_DEFS),
    ]
    visible_fields = [
        (field, label)
        for field, label in field_defs
        if field in {"site_unit", "compound"}
        or any(_has_value(row.get(field)) for row in rows)
    ]

    extra_keys = []
    seen_extra = set()
    for row in rows:
        extra = row.get("extra_data") or {}
        if not isinstance(extra, dict):
            continue
        for key, value in extra.items():
            if key not in seen_extra and _has_value(value):
                seen_extra.add(key)
                extra_keys.append(key)

    used_labels = {"Site Number", *(label for _field, label in visible_fields)}
    extra_labels = {}
    for key in extra_keys:
        label = str(key)
        if label in used_labels:
            label = f"{label} (additional)"
        used_labels.add(label)
        extra_labels[key] = label

    records = []
    for site_number, row in enumerate(rows, start=1):
        record = {"Site Number": row.get("display_id") or site_number}
        for field, label in visible_fields:
            record[label] = row.get(field)
        extra = row.get("extra_data") or {}
        for key, label in extra_labels.items():
            record[label] = extra.get(key) if isinstance(extra, dict) else None
        records.append(record)

    frame = pd.DataFrame.from_records(records)
    for label in extra_labels.values():
        populated = frame[label].map(_has_value)
        converted = pd.to_numeric(frame[label], errors="coerce")
        if populated.any() and converted[populated].notna().all():
            frame[label] = converted
    return frame


def load_csv(raw: bytes) -> pd.DataFrame:
    """Parse uploaded CSV bytes into a DataFrame.

    Raises ``ValueError`` for empty input or unparseable content.
    """
    if raw is None or len(raw) == 0:
        raise ValueError("The uploaded file is empty.")

    last_error: Exception | None = None
    for encoding in _ENCODINGS:
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except pd.errors.EmptyDataError as exc:
            raise ValueError("The uploaded file has no readable columns.") from exc
        except Exception as exc:  # pandas raises a grab-bag of parser errors
            raise ValueError(f"Could not read the CSV file: {exc}") from exc
    else:
        raise ValueError(
            "Could not decode the file. Save it as UTF-8 CSV and try again."
        ) from last_error

    if df.shape[1] == 0:
        raise ValueError("The uploaded file has no columns.")
    if df.shape[0] == 0:
        raise ValueError("The uploaded file has a header but no data rows.")

    # Column labels come in as whatever the header row held; make them strings
    # so downstream Select widgets always get hashable, displayable options.
    df.columns = _canonical_workbench_columns(df.columns)
    return df


def load_npz(raw: bytes) -> pd.DataFrame:
    """Expand an uploaded ``.npz`` grid into the long-form frame ``load_csv`` yields.

    The archive holds the *native* grid — ``x_m`` and ``y_m`` as 1D axes and
    ``concentration_mgL`` as a 2D array of shape ``(len(y_m), len(x_m))``. One
    meshgrid turns it into one row per point, so every tab and ``pivot_gridded``
    see exactly what a CSV upload produces.

    The keys are a contract with the model's exporter, so they are kept verbatim
    rather than canonicalised — ``notation.py`` reads ``concentration_mgL``.

    Raises ``ValueError`` for empty, unreadable or mis-shaped input.
    """
    if raw is None or len(raw) == 0:
        raise ValueError("The uploaded file is empty.")

    try:
        # allow_pickle=False: an uploaded archive is untrusted, and a pickled
        # array inside it would execute arbitrary code on load.
        with np.load(io.BytesIO(raw), allow_pickle=False) as d:
            x, y, c = d["x_m"], d["y_m"], d["concentration_mgL"]
    except KeyError as exc:
        raise ValueError(
            "The .npz file must contain x_m, y_m and concentration_mgL arrays."
        ) from exc
    except Exception as exc:  # numpy/zipfile raise a grab-bag of read errors
        raise ValueError(f"Could not read the .npz file: {exc}") from exc

    if c.shape != (y.size, x.size):
        raise ValueError("NPZ concentration shape does not match its axes.")

    X, Y = np.meshgrid(x, y)
    return pd.DataFrame({
        "x_m": X.ravel(), "y_m": Y.ravel(), "concentration_mgL": c.ravel(),
    })


def numeric_columns(df: pd.DataFrame) -> list[str]:
    """Column names whose dtype is numeric."""
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def categorical_columns(df: pd.DataFrame) -> list[str]:
    """Non-numeric column names, useful as grouping keys."""
    return [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]


def numeric_series(df: pd.DataFrame, column: str) -> np.ndarray:
    """Return a finite float array for ``column``, dropping NaN/inf.

    Raises ``ValueError`` if the column is missing or has no usable values.
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' is not in the dataset.")
    values = pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError(f"Column '{column}' has no numeric values.")
    return values


def dataset_summary(df: pd.DataFrame) -> dict:
    """Compact description used for the intake info card."""
    numeric = numeric_columns(df)
    missing = int(df.isna().to_numpy().sum())
    return {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "numeric_cols": numeric,
        "categorical_cols": categorical_columns(df),
        "missing_cells": missing,
    }
