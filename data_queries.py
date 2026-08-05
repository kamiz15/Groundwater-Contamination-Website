import csv
import json
import math
import os
import struct
from functools import lru_cache
from pathlib import Path
from threading import Lock

import mysql.connector
from mysql.connector import pooling

from settings import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, MAX_SITE_UPLOAD_ROWS
from symbol_registry import build_header_map, header_scale

# Reference database shipped with the app. Every model page reads it when the
# user has not uploaded sites of their own, so the app is usable out of the box.
REFERENCE_DATABASE_PATH = Path(__file__).resolve().parent / "static" / "original.csv"


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) NOT NULL,
        email VARCHAR(150) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        country VARCHAR(100),
        organisation VARCHAR(150)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sites (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_email VARCHAR(150) NOT NULL,
        site_unit VARCHAR(150),
        compound VARCHAR(50),
        aquifer_thickness FLOAT,
        plume_length FLOAT,
        plume_width FLOAT,
        hydraulic_conductivity FLOAT,
        electron_donor FLOAT,
        electron_acceptor_o2 FLOAT,
        electron_acceptor_no3 FLOAT,
        alpha_tv FLOAT,
        alpha_th FLOAT,
        alpha_t FLOAT,
        k_v FLOAT,
        source_thickness FLOAT,
        source_buffer_above FLOAT,
        source_buffer_below FLOAT,
        gamma FLOAT,
        epsilon FLOAT,
        cthres FLOAT,
        birla_r FLOAT,
        ham_q FLOAT,
        extra_data TEXT,
        CONSTRAINT fk_sites_user_email
            FOREIGN KEY (user_email) REFERENCES users(email)
            ON DELETE CASCADE
    )
    """,
]

# Typed model-parameter columns added after the original 9 fixed fields. Existing
# `sites` tables created before the catalog-driven upload feature lack these, so
# ensure_schema ALTERs them in idempotently (swallowing the duplicate-column
# errno 1060) the same way `extra_data` is handled.
ADDED_SITE_COLUMNS = [
    "alpha_tv",
    "alpha_th",
    "alpha_t",
    "k_v",
    "source_thickness",
    "source_buffer_above",
    "source_buffer_below",
    "gamma",
    "epsilon",
    "cthres",
    "birla_r",
    "ham_q",
]


def ensure_schema(connection):
    cursor = connection.cursor()
    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        # Idempotent migration: existing 'sites' tables created before the
        # flexible-CSV feature lack the extra_data column. CREATE TABLE IF NOT
        # EXISTS will not add it, so ALTER here and swallow the duplicate-column
        # error (errno 1060) when the column is already present.
        try:
            cursor.execute("ALTER TABLE sites ADD COLUMN extra_data TEXT")
        except mysql.connector.Error as exc:
            if getattr(exc, "errno", None) != 1060:
                raise
        # Same idempotent migration for the typed model-parameter columns.
        for column in ADDED_SITE_COLUMNS:
            try:
                cursor.execute(f"ALTER TABLE sites ADD COLUMN {column} FLOAT")
            except mysql.connector.Error as exc:
                if getattr(exc, "errno", None) != 1060:
                    raise
        connection.commit()
    finally:
        cursor.close()


_schema_initialized = False
_pool = None
_pool_lock = Lock()

DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))


def get_db_connection():
    """Return a pooled database connection.

    Connections come from a process-wide pool: calling .close() on the returned
    connection gives it back to the pool instead of tearing down the TCP
    session, so the per-request connect/auth overhead is paid only once per
    pool slot instead of on every query.
    """
    global _schema_initialized, _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pooling.MySQLConnectionPool(
                    pool_name="cast_pool",
                    pool_size=DB_POOL_SIZE,
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                )
    connection = _pool.get_connection()
    if not _schema_initialized:
        ensure_schema(connection)
        _schema_initialized = True
    return connection


# Text columns: cap input length to the schema width so over-long values are
# rejected with a clear message instead of being silently truncated (or raising
# an opaque database error).
TEXT_FIELD_MAX_LENGTH = {
    "site_unit": 150,
    "compound": 50,
}

TEXT_SITE_FIELDS = ["site_unit", "compound"]

# Original 9 fixed numeric columns, plus the typed model-parameter columns added
# for the catalog-driven upload feature (ADDED_SITE_COLUMNS).
NUMERIC_SITE_FIELDS = [
    "aquifer_thickness",
    "plume_length",
    "plume_width",
    "hydraulic_conductivity",
    "electron_donor",
    "electron_acceptor_o2",
    "electron_acceptor_no3",
    *ADDED_SITE_COLUMNS,
]

# Column order used by _clean_site_payload and the INSERT statements. The INSERT
# column list, placeholders, and value tuples are all derived from this so a new
# parameter only needs to be added to the schema + ADDED_SITE_COLUMNS.
SITE_FIELDS = [*TEXT_SITE_FIELDS, *NUMERIC_SITE_FIELDS]

_INSERT_COLUMNS = ["user_email", *SITE_FIELDS, "extra_data"]
_INSERT_SQL = (
    "INSERT INTO sites (" + ", ".join(_INSERT_COLUMNS) + ") "
    "VALUES (" + ", ".join(["%s"] * len(_INSERT_COLUMNS)) + ")"
)


def _as_float(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return None
        if value.lower() in {"na", "n/a", "nan", "null", "none", "-"}:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_numeric(field, value):
    number = _as_float(value)
    if number is None:
        return None
    if not math.isfinite(number):
        raise ValueError(f"{field.replace('_', ' ')} must be a finite number.")
    if number < 0:
        raise ValueError(f"{field.replace('_', ' ')} cannot be negative.")
    return number


def _clean_site_payload(payload):
    """Validate and normalise one site row. Raises ValueError on bad input."""
    cleaned = {}
    for field, max_length in TEXT_FIELD_MAX_LENGTH.items():
        raw = payload.get(field)
        text = "" if raw is None else str(raw).strip()
        if len(text) > max_length:
            raise ValueError(
                f"{field.replace('_', ' ')} must be at most {max_length} characters."
            )
        cleaned[field] = text
    for field in NUMERIC_SITE_FIELDS:
        cleaned[field] = _clean_numeric(field, payload.get(field))
    return [cleaned[field] for field in SITE_FIELDS]


def _extra_data_json(payload):
    """Serialise the unmapped CSV columns held in payload['extra_data'].

    Returns a JSON string of {trimmed_header: str_value} for a non-empty dict,
    otherwise None so the column is stored as SQL NULL.
    """
    extra = payload.get("extra_data")
    if not isinstance(extra, dict) or not extra:
        return None
    cleaned = {}
    for key, value in extra.items():
        if key is None:
            continue
        trimmed = str(key).strip()
        if trimmed == "":
            continue
        cleaned[trimmed] = "" if value is None else str(value)
    if not cleaned:
        return None
    return json.dumps(cleaned)


_PLOT_COLUMNS = [
    "id",
    "site_unit",
    "compound",
    "aquifer_thickness",
    "plume_length",
    "plume_width",
    "hydraulic_conductivity",
    "electron_donor",
    "electron_acceptor_o2",
    "electron_acceptor_no3",
]


def _plot_rows(rows):
    """Legacy list-of-lists view of site rows, used by the plotting helpers."""
    return [[row.get(column) for column in _PLOT_COLUMNS] for row in rows]


def get_user_sites(email):
    return _plot_rows(get_user_sites_rows(email))


def get_owned_sites(email):
    """List-of-lists of the user's own rows — for plots that already draw the
    reference database as their own series (see plot_functions)."""
    return _plot_rows(get_owned_sites_rows(email))


@lru_cache(maxsize=1)
def _reference_sites():
    """Parse the shipped reference CSV into rows shaped like database rows.

    Uses the same catalog header matching and unit scaling as the CSV upload
    path, so a reference site autofills a model exactly as an uploaded one does.
    """
    with REFERENCE_DATABASE_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames or []
        header_map = build_header_map(fieldnames)
        mapped = set(header_map.values())
        extra_headers = [
            header
            for header in fieldnames
            if header and header.strip() and header not in mapped
        ]
        scales = {
            column: header_scale(header)
            for column, header in header_map.items()
            if column in NUMERIC_SITE_FIELDS
        }

        rows = []
        for row_id, raw in enumerate(reader, start=1):
            row = {"id": row_id, "display_id": row_id}
            for field in SITE_FIELDS:
                header = header_map.get(field)
                value = (raw.get(header) or "").strip() if header else ""
                if field in NUMERIC_SITE_FIELDS:
                    number = _as_float(value)
                    row[field] = (
                        None if number is None else number * scales.get(field, 1.0)
                    )
                else:
                    row[field] = value
            row["extra_data"] = {
                header.strip(): (raw.get(header) or "").strip()
                for header in extra_headers
                if (raw.get(header) or "").strip()
            }
            rows.append(row)
    return rows


def reference_sites_rows():
    """Fresh copies of the reference rows (callers annotate the dicts they get)."""
    return [
        {**row, "extra_data": dict(row["extra_data"])} for row in _reference_sites()
    ]


def get_owned_sites_rows(email):
    """Only the rows this user uploaded — no reference fallback.

    Use this wherever the rows stand for the user's own data: their site table,
    their exports, and duplicate detection on upload. Everything that merely
    *reads* sites to run or plot a model wants get_user_sites_rows instead.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM sites WHERE user_email = %s ORDER BY id ASC", (email,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    for display_id, row in enumerate(rows, start=1):
        row["display_id"] = display_id
        raw = row.get("extra_data")
        if raw:
            try:
                parsed = json.loads(raw)
                row["extra_data"] = parsed if isinstance(parsed, dict) else {}
            except (ValueError, TypeError):
                row["extra_data"] = {}
        else:
            row["extra_data"] = {}
    return rows


def get_user_sites_rows(email):
    """Sites for the models: the user's own rows, else the reference database.

    The ids of reference rows are CSV positions, not database keys; they only
    ever surface while the user has no rows of their own, so nothing can be
    deleted or matched against a real site through them.
    """
    owned = get_owned_sites_rows(email) if email else []
    return owned or reference_sites_rows()


def insert_site(email, payload):
    values = _clean_site_payload(payload)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            _INSERT_SQL,
            [email, *values, _extra_data_json(payload)],
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def delete_site(email, site_id):
    """Delete one site row, scoped to its owner. Returns True if a row was removed."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM sites WHERE id = %s AND user_email = %s",
            (site_id, email),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()

def delete_user_sites(email):
    """Delete all site rows owned by the user. Returns the number removed."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM sites WHERE user_email = %s", (email,))
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def _f32(value):
    """Quantise to single precision so a value matches how MySQL FLOAT stores it.

    Existing rows come back as single-precision floats; coercing incoming values
    the same way lets a re-uploaded number compare equal to the stored one.
    """
    if value is None:
        return None
    try:
        return struct.unpack("f", struct.pack("f", float(value)))[0]
    except (TypeError, ValueError, struct.error):
        return None


def _canonical_extra(extra):
    """Order-independent, string-normalised form of an extra_data dict."""
    if not isinstance(extra, dict) or not extra:
        return ""
    cleaned = {}
    for key, val in extra.items():
        if key is None:
            continue
        trimmed = str(key).strip()
        if trimmed == "":
            continue
        cleaned[trimmed] = "" if val is None else str(val)
    return json.dumps(cleaned, sort_keys=True) if cleaned else ""


def _signature_from_cleaned(cleaned_values, extra):
    """Identity signature for a to-be-inserted row (text + numeric + extras)."""
    n_text = len(TEXT_SITE_FIELDS)
    text_part = tuple(str(v or "").strip().lower() for v in cleaned_values[:n_text])
    numeric_part = tuple(_f32(v) for v in cleaned_values[n_text:])
    return (text_part, numeric_part, _canonical_extra(extra))


def _existing_signatures(email):
    """Signatures of the user's current rows, for duplicate detection."""
    signatures = set()
    for row in get_owned_sites_rows(email):
        text_part = tuple(str(row.get(f) or "").strip().lower() for f in TEXT_SITE_FIELDS)
        numeric_part = tuple(_f32(row.get(f)) for f in NUMERIC_SITE_FIELDS)
        signatures.add((text_part, numeric_part, _canonical_extra(row.get("extra_data"))))
    return signatures


def insert_sites_bulk(email, payloads):
    """Insert rows that are not exact duplicates of existing or earlier-in-batch
    rows. Returns (inserted_count, skipped_duplicate_count)."""
    if not payloads:
        return (0, 0)
    if len(payloads) > MAX_SITE_UPLOAD_ROWS:
        raise ValueError(
            f"Too many rows: a single upload is limited to {MAX_SITE_UPLOAD_ROWS} sites."
        )

    seen = _existing_signatures(email)
    rows = []
    skipped = 0
    for payload in payloads:
        cleaned = _clean_site_payload(payload)
        signature = _signature_from_cleaned(cleaned, payload.get("extra_data"))
        if signature in seen:
            skipped += 1
            continue
        seen.add(signature)
        rows.append([email, *cleaned, _extra_data_json(payload)])

    if not rows:
        return (0, skipped)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.executemany(_INSERT_SQL, rows)
        conn.commit()
        return (len(rows), skipped)
    finally:
        cursor.close()
        conn.close()
