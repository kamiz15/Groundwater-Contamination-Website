import logging
import secrets

from bokeh.resources import CDN
from flask import Flask, render_template, jsonify, redirect, request, url_for
from werkzeug.exceptions import HTTPException
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user as flask_login_user,
    logout_user,
)
from mysql.connector import Error, IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from aem_routes import aem_bp
from analytical_routes import analytical_bp
from data_queries import get_db_connection
from empirical_routes import empirical_bp
from numerical_routes import numerical_bp
from security import (
    GENERIC_DATABASE_ERROR_MESSAGE,
    MAX_PASSWORD_LENGTH,
    MAX_USERNAME_LENGTH,
    csrf_protect,
    csrf_token,
    is_valid_email,
    json_object_or_400,
    password_policy_error,
    rate_limit,
    required_text_fields,
)
from settings import (
    DEMO_BYPASS_LOGIN,
    DEMO_USER_EMAIL,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    MAX_REQUEST_BYTES,
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
)
from site_routes import site_bp

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Cookie hardening for the login session and "remember me" cookie.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,      # not readable by JavaScript (mitigates XSS theft)
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,  # HTTPS-only (configurable for dev)
    SESSION_COOKIE_SAMESITE="Lax",     # blocks cross-site cookie sending (CSRF defense in depth)
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    REMEMBER_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,  # reject oversized request bodies
)
app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["demo_bypass_login"] = DEMO_BYPASS_LOGIN
app.jinja_env.globals["bokeh_js_files"] = [
    f"/{js_file}" if js_file.startswith("static/extensions/panel/") else js_file
    for js_file in CDN.js_files
]

login_manager = LoginManager(app)
login_manager.login_view = "login_page"

# Precomputed hash of a random password, used to equalize login response timing
# for non-existent accounts (prevents user-enumeration via timing).
_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email


_DEMO_USER = User(0, "Demo User", DEMO_USER_EMAIL)


@app.before_request
def demo_login_bypass():
    if not DEMO_BYPASS_LOGIN or app.config.get("TESTING"):
        return
    if not current_user.is_authenticated:
        flask_login_user(_DEMO_USER)


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
app.register_blueprint(aem_bp)


@app.errorhandler(HTTPException)
def handle_http_error(error):
    # JSON clients (login/register/report fetches) should get a JSON error
    # body they can parse, not Werkzeug's HTML error page.
    if request.is_json:
        return jsonify({"success": False, "message": error.description}), error.code
    return error


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

    # No stored password exceeds the registration cap, so reject oversized
    # input before hashing (a multi-MB password is a cheap CPU DoS otherwise).
    if len(password) > MAX_PASSWORD_LENGTH:
        return jsonify({"success": False, "message": "Invalid email or password."}), 401

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

    if user:
        password_ok = check_password_hash(user["password_hash"], password)
    else:
        # Run a hash comparison even when the account does not exist so the
        # response time does not reveal whether an email is registered.
        check_password_hash(_DUMMY_PASSWORD_HASH, password)
        password_ok = False

    if user and password_ok:
        authenticated_user = load_user(user["id"])
        if authenticated_user is None:
            return jsonify({"success": False, "message": "Invalid email or password."}), 401
        flask_login_user(authenticated_user)
        return jsonify({"success": True, "redirect": url_for("home")})
    return jsonify({"success": False, "message": "Invalid email or password."}), 401


@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")


@app.route("/auth/check")
def auth_check():
    if not current_user.is_authenticated:
        return ("", 401)
    # The reverse proxy copies this header into the upstream Panel request as the
    # trusted X-Auth-Email, so Panel never has to trust a client-supplied identity.
    return ("", 204, {"X-User-Email": current_user.email})


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
        return jsonify({"success": False, "message": "Passwords do not match."}), 400

    if not is_valid_email(email):
        return jsonify({"success": False, "message": "Please enter a valid email address."}), 400

    if len(username) > MAX_USERNAME_LENGTH:
        return jsonify(
            {"success": False, "message": f"Username must be at most {MAX_USERNAME_LENGTH} characters."}
        ), 400

    policy_error = password_policy_error(password)
    if policy_error:
        return jsonify({"success": False, "message": policy_error}), 400

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
    except IntegrityError:
        # Unique constraint on users.email: surface a clear conflict instead
        # of a generic server error.
        return jsonify(
            {
                "success": False,
                "message": "An account with this email already exists.",
            }
        ), 409
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


@app.route("/logout", methods=["POST"])
@login_required
@csrf_protect
def logout():
    logout_user()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
