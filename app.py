from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_login import LoginManager
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from site_routes import site_bp   # <-- import the blueprint
from analytical_routes import analytical_bp
from empirical_routes import empirical_bp
from plot_routes import plot_bp





app = Flask(__name__)


app.secret_key = 'supersecretkey'

# --- Flask-Login setup ---
login_manager = LoginManager(app)
login_manager.login_view = "login_page"



@login_manager.user_loader
def load_user(user_id):
    """
    TODO: replace with real lookup from DB.
    Right now just returns None so users are always 'not logged in'.
    """
    return None

# ----------------------------
# MySQL Connection
# ----------------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="cast_project"
    )

# Make available to other modules
app.config['DB_CONNECTION'] = get_db_connection

# ----------------------------
# Register Blueprint
# ----------------------------
app.register_blueprint(plot_bp)
app.register_blueprint(site_bp)
app.register_blueprint(analytical_bp)
app.register_blueprint(empirical_bp)


# ----------------------------
# Routes for Home / Login / Register
# ----------------------------
@app.route("/")
def home():
    user = session.get("user")
    return render_template("index.html", user=user)

@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login_user():
    data = request.get_json()
    email = data.get("username")
    password = data.get("password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user["password_hash"], password):
        session["user"] = user["username"]
        session["email"] = user["email"]
        return jsonify({"success": True, "redirect": url_for("home")})
    else:
        return jsonify({"success": False, "message": "Invalid email or password."})

@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")

@app.route("/register", methods=["POST"])
def register_user():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    confirm_password = data.get("confirmPassword")
    country = data.get("country")
    organisation = data.get("organisation")

    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."})

    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        cursor.execute("""
            INSERT INTO users (username, email, password_hash, country, organisation)
            VALUES (%s, %s, %s, %s, %s)
        """, (username, email, hashed_pw, country, organisation))
        conn.commit()
    except Error as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})
    finally:
        cursor.close()
        conn.close()

    return jsonify({"success": True, "redirect": url_for("login_page")})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))
print("\n".join(sorted(app.view_functions.keys())))

# ----------------------------
# Run App
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
