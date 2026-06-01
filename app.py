import logging

from bokeh.resources import CDN
from flask import Flask, render_template, jsonify, redirect, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user as flask_login_user,
    logout_user,
)
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash

from analytical_routes import analytical_bp
from data_queries import get_db_connection
from empirical_routes import empirical_bp
from numerical_routes import numerical_bp
from source_geometry_routes import source_geometry_bp
from source_inversion_routes import source_inversion_bp
from security import (
    GENERIC_DATABASE_ERROR_MESSAGE,
    csrf_protect,
    csrf_token,
    json_object_or_400,
    rate_limit,
    required_text_fields,
)
from settings import FLASK_DEBUG, FLASK_HOST, FLASK_PORT, SECRET_KEY
from site_routes import site_bp

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["bokeh_js_files"] = [
    f"/{js_file}" if js_file.startswith("static/extensions/panel/") else js_file
    for js_file in CDN.js_files
]

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

app.register_blueprint(site_bp)
app.register_blueprint(analytical_bp)
app.register_blueprint(empirical_bp)
app.register_blueprint(numerical_bp)
app.register_blueprint(source_geometry_bp)
app.register_blueprint(source_inversion_bp)


@app.errorhandler(Error)
def handle_database_error(error):
    logger.error(
        "Unhandled database error",
        exc_info=(type(error), error, error.__traceback__),
    )
    return jsonify({"success": False, "message": GENERIC_DATABASE_ERROR_MESSAGE}), 503


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
@rate_limit(limit=5, window_seconds=60)
@csrf_protect
def authenticate():
    data = json_object_or_400()
    email, password = required_text_fields(data, "username", "password")

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
    except Error:
        logger.exception("Database error while authenticating account")
        return jsonify(
            {
                "success": False,
                "message": "Unable to log in right now. Please try again later.",
            }
        ), 503
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    if user and check_password_hash(user["password_hash"], password):
        authenticated_user = load_user(user["id"])
        if authenticated_user is None:
            return jsonify({"success": False, "message": "Invalid email or password."})
        flask_login_user(authenticated_user)
        return jsonify({"success": True, "redirect": url_for("home")})
    return jsonify({"success": False, "message": "Invalid email or password."})


@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")


@app.route("/auth/check")
def auth_check():
    return ("", 204) if current_user.is_authenticated else ("", 401)


@app.route("/register", methods=["POST"])
@rate_limit(limit=3, window_seconds=60)
@csrf_protect
def register_user():
    data = json_object_or_400()
    username, email, password, confirm_password = required_text_fields(
        data,
        "username",
        "email",
        "password",
        "confirmPassword",
    )

    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."})

    conn = None
    cursor = None
    hashed_pw = generate_password_hash(password)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, country, organisation)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username, email, hashed_pw, None, None),
        )
        conn.commit()
    except Error:
        logger.exception("Database error while registering account")
        return jsonify(
            {
                "success": False,
                "message": "Unable to create account. Please try again later.",
            }
        ), 503
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    return jsonify({"success": True, "redirect": url_for("login_page")})


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
