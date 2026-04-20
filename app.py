from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_login import LoginManager, UserMixin
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash

from analytical_routes import analytical_bp
from data_queries import get_db_connection
from empirical_routes import empirical_bp
from numerical_routes import numerical_bp
from plot_routes import plot_bp
from settings import FLASK_DEBUG, FLASK_HOST, FLASK_PORT, SECRET_KEY
from site_routes import site_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY

login_manager = LoginManager(app)
login_manager.login_view = "login_page"


class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, username, email FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    if row:
        return User(row["id"], row["username"], row["email"])
    return None

app.config['DB_CONNECTION'] = get_db_connection

app.register_blueprint(plot_bp)
app.register_blueprint(site_bp)
app.register_blueprint(analytical_bp)
app.register_blueprint(empirical_bp)
app.register_blueprint(numerical_bp)


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
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, country, organisation)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username, email, hashed_pw, country, organisation),
        )
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


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
