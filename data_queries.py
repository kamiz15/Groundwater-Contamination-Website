import mysql.connector

from settings import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100),
        email VARCHAR(150) UNIQUE,
        password_hash VARCHAR(255),
        country VARCHAR(100),
        organisation VARCHAR(150)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sites (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_email VARCHAR(150),
        site_unit VARCHAR(150),
        compound VARCHAR(50),
        aquifer_thickness FLOAT,
        plume_length FLOAT,
        plume_width FLOAT,
        hydraulic_conductivity FLOAT,
        electron_donor FLOAT,
        electron_acceptor_o2 FLOAT,
        electron_acceptor_no3 FLOAT,
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
        connection.commit()
    finally:
        cursor.close()


_schema_initialized = False


def get_db_connection():
    global _schema_initialized
    connection = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )
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
    return rows


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


def insert_site(email, payload):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        values = [payload.get(field) for field in SITE_FIELDS]
        values[2:] = [_as_float(v) for v in values[2:]]

        cursor.execute(
            """
            INSERT INTO sites (
                user_email, site_unit, compound, aquifer_thickness, plume_length,
                plume_width, hydraulic_conductivity, electron_donor, electron_acceptor_o2, electron_acceptor_no3
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [email, *values],
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def insert_sites_bulk(email, payloads):
    if not payloads:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        rows = []
        for payload in payloads:
            values = [payload.get(field) for field in SITE_FIELDS]
            values[2:] = [_as_float(v) for v in values[2:]]
            rows.append([email, *values])

        cursor.executemany(
            """
            INSERT INTO sites (
                user_email, site_unit, compound, aquifer_thickness, plume_length,
                plume_width, hydraulic_conductivity, electron_donor, electron_acceptor_o2, electron_acceptor_no3
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        cursor.close()
        conn.close()
