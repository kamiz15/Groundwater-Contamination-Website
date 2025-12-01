import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="cast_project"
    )

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
