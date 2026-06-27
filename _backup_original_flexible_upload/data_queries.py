import json
import math
import os
from threading import Lock

import mysql.connector
from mysql.connector import pooling

from settings import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, MAX_SITE_UPLOAD_ROWS


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
        extra_data TEXT,
        CONSTRAINT fk_sites_user_email
            FOREIGN KEY (user_email) REFERENCES users(email)
            ON DELETE CASCADE
    )
    """,
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


SITE_FIELDS = [
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

# Text columns: cap input length to the schema width so over-long values are
# rejected with a clear message instead of being silently truncated (or raising
# an opaque database error).
TEXT_FIELD_MAX_LENGTH = {
    "site_unit": 150,
    "compound": 50,
}
NUMERIC_SITE_FIELDS = [
    "aquifer_thickness",
    "plume_length",
    "plume_width",
    "hydraulic_conductivity",
    "electron_donor",
    "electron_acceptor_o2",
    "electron_acceptor_no3",
]


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


def get_user_sites(email):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM sites WHERE user_email = %s", (email,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()

    table_data = []
    for s in data:
        table_data.append([
            s["id"],
            s["site_unit"],
            s["compound"],
            s["aquifer_thickness"],
            s["plume_length"],
            s["plume_width"],
            s["hydraulic_conductivity"],
            s["electron_donor"],
            s["electron_acceptor_o2"],
            s["electron_acceptor_no3"]
        ])
    return table_data


def get_user_sites_rows(email):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM sites WHERE user_email = %s ORDER BY id DESC", (email,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    for row in rows:
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


def insert_site(email, payload):
    values = _clean_site_payload(payload)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO sites (
                user_email, site_unit, compound, aquifer_thickness, plume_length,
                plume_width, hydraulic_conductivity, electron_donor, electron_acceptor_o2, electron_acceptor_no3,
                extra_data
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
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


def insert_sites_bulk(email, payloads):
    if not payloads:
        return 0
    if len(payloads) > MAX_SITE_UPLOAD_ROWS:
        raise ValueError(
            f"Too many rows: a single upload is limited to {MAX_SITE_UPLOAD_ROWS} sites."
        )

    rows = [
        [email, *_clean_site_payload(payload), _extra_data_json(payload)]
        for payload in payloads
    ]

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.executemany(
            """
            INSERT INTO sites (
                user_email, site_unit, compound, aquifer_thickness, plume_length,
                plume_width, hydraulic_conductivity, electron_donor, electron_acceptor_o2, electron_acceptor_no3,
                extra_data
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        cursor.close()
        conn.close()
