import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="cast_project"
    )

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
