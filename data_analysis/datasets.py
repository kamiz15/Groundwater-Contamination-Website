"""CSV intake and column-typing helpers for the data-analysis workbench.

Pure pandas/numpy; no Panel imports so this stays unit-testable. Every failure
mode raises ``ValueError`` with a message that is safe to show a user.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from symbol_registry import SITE_COLUMN_DEFS, TEXT_COLUMN_DEFS

# Try a few encodings in order. utf-8-sig transparently strips a BOM, which
# spreadsheets on Windows frequently add.
_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1")


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
    df.columns = [str(c).strip() for c in df.columns]
    return df


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
