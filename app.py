import hashlib
import json
import os
import re
import secrets
import sqlite3
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, render_template, request, session, stream_with_context
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None

try:
    import firebase_admin
    from firebase_admin import credentials as firebase_credentials
    from firebase_admin import messaging as firebase_messaging
except ImportError:  # pragma: no cover - handled at runtime
    firebase_admin = None
    firebase_credentials = None
    firebase_messaging = None


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_PATH = BASE_DIR / "chatbot.txt"
DB_PATH = BASE_DIR / "app.db"
MAX_HISTORY_ITEMS = 8
MAX_CONTEXT_CHUNKS = 6
PIN_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 12
PIN_LOCK_MINUTES = 5
PIN_MAX_ATTEMPTS = 5
RESET_TOKEN_MINUTES = 30
CALL_PROVIDER = (os.getenv("CALL_PROVIDER", "zegocloud") or "zegocloud").strip().lower()
CALL_RING_TIMEOUT_SECONDS = int(os.getenv("CALL_RING_TIMEOUT_SECONDS", "25"))
CALL_MAX_TARGETS = int(os.getenv("CALL_MAX_TARGETS", "3"))
FIREBASE_SERVICE_ACCOUNT_JSON = (os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "") or "").strip()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=180)
app.json.ensure_ascii = False

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

model = None
if genai and API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)

knowledge = KNOWLEDGE_PATH.read_text(encoding="utf-8") if KNOWLEDGE_PATH.exists() else ""
knowledge_chunks = [line.strip() for line in knowledge.splitlines() if line.strip()]
chat_store = defaultdict(list)
pin_serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="device-pin-token")
firebase_push_app = None


def utcnow() -> datetime:
    return datetime.utcnow()


def utcnow_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


@app.teardown_appcontext
def close_db(_exception=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        age INTEGER NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone_number TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        gemini_api_key TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS user_devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        device_id TEXT NOT NULL,
        device_name TEXT NOT NULL,
        pin_code_hash TEXT,
        pin_enabled INTEGER NOT NULL DEFAULT 0,
        pin_failed_attempts INTEGER NOT NULL DEFAULT 0,
        pin_locked_until TEXT,
        is_revoked INTEGER NOT NULL DEFAULT 0,
        last_login_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, device_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS family_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_name TEXT NOT NULL,
        created_by_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS family_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'member')),
        status TEXT NOT NULL CHECK(status IN ('active', 'removed')),
        joined_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(family_group_id, user_id),
        FOREIGN KEY(family_group_id) REFERENCES family_groups(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS family_invitations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_group_id INTEGER NOT NULL,
        invited_user_id INTEGER NOT NULL,
        invited_by_user_id INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending', 'accepted', 'declined', 'cancelled')),
        created_at TEXT NOT NULL,
        responded_at TEXT,
        FOREIGN KEY(family_group_id) REFERENCES family_groups(id) ON DELETE CASCADE,
        FOREIGN KEY(invited_user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(invited_by_user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token_hash TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS device_push_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        device_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        push_token TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, device_id, push_token),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS family_relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_group_id INTEGER NOT NULL,
        owner_user_id INTEGER NOT NULL,
        relative_user_id INTEGER NOT NULL,
        relationship_key TEXT NOT NULL,
        custom_aliases TEXT NOT NULL DEFAULT '',
        priority_order INTEGER NOT NULL DEFAULT 1,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(owner_user_id, relative_user_id, relationship_key),
        FOREIGN KEY(family_group_id) REFERENCES family_groups(id) ON DELETE CASCADE,
        FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(relative_user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS call_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id TEXT NOT NULL UNIQUE,
        initiated_by_user_id INTEGER NOT NULL,
        caller_user_id INTEGER NOT NULL,
        trigger_source TEXT NOT NULL,
        transcript_text TEXT,
        detected_intent TEXT,
        relationship_key TEXT,
        status TEXT NOT NULL,
        accepted_by_user_id INTEGER,
        started_at TEXT,
        accepted_at TEXT,
        ended_at TEXT,
        end_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(initiated_by_user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(caller_user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(accepted_by_user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS call_session_targets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_session_id INTEGER NOT NULL,
        target_user_id INTEGER NOT NULL,
        relationship_key TEXT NOT NULL,
        priority_order INTEGER NOT NULL,
        status TEXT NOT NULL,
        rung_at TEXT,
        responded_at TEXT,
        response_reason TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(call_session_id, target_user_id, priority_order),
        FOREIGN KEY(call_session_id) REFERENCES call_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY(target_user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS call_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_session_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        actor_user_id INTEGER,
        payload_json TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(call_session_id) REFERENCES call_sessions(id) ON DELETE CASCADE,
        FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """

    db = get_db()
    db.executescript(schema)
    user_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(users)").fetchall()
    }
    if "gemini_api_key" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN gemini_api_key TEXT NOT NULL DEFAULT ''")

    relationship_columns = {
        row["name"]
        for row in db.execute("PRAGMA table_info(family_relationships)").fetchall()
    }
    if "custom_aliases" not in relationship_columns:
        db.execute("ALTER TABLE family_relationships ADD COLUMN custom_aliases TEXT NOT NULL DEFAULT ''")
    db.commit()


def json_error(message: str, status: int, code: str | None = None):
    payload = {"error": message}
    if code:
        payload["code"] = code
    return jsonify(payload), status


def get_firebase_push_app():
    global firebase_push_app

    if firebase_push_app is not None:
        return firebase_push_app

    if firebase_admin is None or firebase_credentials is None or firebase_messaging is None:
        return None
    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        return None

    try:
        service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        credential = firebase_credentials.Certificate(service_account_info)
        firebase_push_app = firebase_admin.initialize_app(credential, name="push-app")
    except Exception:
        firebase_push_app = None

    return firebase_push_app


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", (value or "").strip())
    if cleaned.count("+") > 1:
        cleaned = cleaned.replace("+", "")
    if "+" in cleaned and not cleaned.startswith("+"):
        cleaned = cleaned.replace("+", "")
    return cleaned


def normalize_device_id(value: str) -> str:
    trimmed = (value or "").strip()
    if not trimmed:
        return ""
    return trimmed[:120]


def validate_email(value: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def validate_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return 9 <= len(digits) <= 15


def validate_password(value: str) -> bool:
    return len((value or "").strip()) >= 6


def validate_pin(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", value or ""))


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def fetch_one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_db().execute(query, params).fetchone()


def fetch_all(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_db().execute(query, params).fetchall()


def load_authenticated_context() -> tuple[sqlite3.Row | None, sqlite3.Row | None]:
    user_id = session.get("user_id")
    device_id = session.get("device_id")

    if not user_id or not device_id:
        return None, None

    user_row = fetch_user_by_id(int(user_id))
    if not user_row or not user_row["is_active"]:
        session.clear()
        return None, None

    device_row = fetch_device(user_row["id"], device_id)
    if not device_row or device_row["is_revoked"]:
        session.clear()
        return None, None

    return user_row, device_row


@app.before_request
def hydrate_auth_context() -> None:
    g.current_user, g.current_device = load_authenticated_context()


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if g.current_user is None or g.current_device is None:
            return json_error("Bạn cần đăng nhập trước.", 401, "auth_required")
        return view_func(*args, **kwargs)

    return wrapped


def pin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if g.current_user is None or g.current_device is None:
            return json_error("Bạn cần đăng nhập trước.", 401, "auth_required")

        if not g.current_device["pin_enabled"]:
            return json_error("Thiết bị này chưa thiết lập PIN 4 số.", 403, "pin_not_configured")

        pin_token = request.headers.get("X-PIN-Token", "").strip()
        if not validate_pin_token(pin_token, g.current_user["id"], g.current_device["device_id"]):
            return json_error("Bạn cần nhập PIN để mở khóa ứng dụng.", 403, "pin_required")

        mark_device_seen(g.current_device)
        return view_func(*args, **kwargs)

    return wrapped


@app.route("/api/auth/pin/setup", methods=["POST"])
@login_required
def pin_setup():
    payload = require_json()
    pin = payload.get("pin") or ""
    confirm_pin = payload.get("confirm_pin") or ""

    if not validate_pin(pin):
        return json_error("PIN phải gồm đúng 4 chữ số.", 400, "invalid_pin")
    if pin != confirm_pin:
        return json_error("PIN xác nhận chưa khớp.", 400, "pin_mismatch")

    now = utcnow_iso()
    get_db().execute(
        """
        UPDATE user_devices
        SET pin_code_hash = ?, pin_enabled = 1, pin_failed_attempts = 0, pin_locked_until = NULL, updated_at = ?
        WHERE id = ?
        """,
        (generate_password_hash(pin), now, g.current_device["id"]),
    )
    get_db().commit()
    g.current_device = fetch_device(g.current_user["id"], g.current_device["device_id"])

    return jsonify(
        {
            "message": "Thiết lập PIN thành công.",
            "pin_token": issue_pin_token(g.current_user["id"], g.current_device["device_id"]),
            "bootstrap": build_bootstrap_payload(),
        }
    )


@app.route("/api/auth/pin/verify", methods=["POST"])
@login_required
def pin_verify():
    if not g.current_device["pin_enabled"]:
        return json_error("Thiết bị này chưa có PIN. Bạn hãy tạo PIN trước nhé.", 400, "pin_not_configured")

    payload = require_json()
    pin = payload.get("pin") or ""

    locked_until = parse_iso_datetime(g.current_device["pin_locked_until"])
    if locked_until and locked_until > utcnow():
        return json_error(
            f"PIN đang bị khóa tạm thời đến {locked_until.strftime('%H:%M')}.",
            423,
            "pin_locked",
        )

    if not check_password_hash(g.current_device["pin_code_hash"], pin):
        failed_attempts = int(g.current_device["pin_failed_attempts"]) + 1
        locked_until_value = None

        if failed_attempts >= PIN_MAX_ATTEMPTS:
            locked_until_value = (utcnow() + timedelta(minutes=PIN_LOCK_MINUTES)).isoformat(timespec="seconds")
            failed_attempts = 0

        get_db().execute(
            """
            UPDATE user_devices
            SET pin_failed_attempts = ?, pin_locked_until = ?, updated_at = ?
            WHERE id = ?
            """,
            (failed_attempts, locked_until_value, utcnow_iso(), g.current_device["id"]),
        )
        get_db().commit()
        g.current_device = fetch_device(g.current_user["id"], g.current_device["device_id"])

        if locked_until_value:
            return json_error(
                "Bạn nhập sai PIN quá nhiều lần nên thiết bị bị khóa tạm thời.",
                423,
                "pin_locked",
            )

        remaining = PIN_MAX_ATTEMPTS - failed_attempts
        return json_error(f"PIN chưa đúng. Bạn còn {remaining} lần thử.", 401, "invalid_pin")

    now = utcnow_iso()
    get_db().execute(
        """
        UPDATE user_devices
        SET pin_failed_attempts = 0, pin_locked_until = NULL, last_seen_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, g.current_device["id"]),
    )
    get_db().commit()

    return jsonify(
        {
            "message": "Mở khóa thành công.",
            "pin_token": issue_pin_token(g.current_user["id"], g.current_device["device_id"]),
        }
    )


@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    payload = require_json()
    email = normalize_email(payload.get("email") or "")

    if not validate_email(email):
        return json_error("Bạn cần nhập email hợp lệ.", 400, "invalid_email")

    user_row = fetch_user_by_email(email)
    if not user_row:
        return jsonify({"message": "Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu sẽ được tạo."})

    raw_token = secrets.token_urlsafe(24)
    now = utcnow()
    get_db().execute(
        """
        INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_row["id"],
            token_hash(raw_token),
            (now + timedelta(minutes=RESET_TOKEN_MINUTES)).isoformat(timespec="seconds"),
            now.isoformat(timespec="seconds"),
        ),
    )
    get_db().commit()

    return jsonify(
        {
            "message": "Đã tạo yêu cầu đặt lại mật khẩu. Ở môi trường local, token được trả thẳng để bạn test.",
            "reset_token": raw_token,
            "expires_in_minutes": RESET_TOKEN_MINUTES,
        }
    )


@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    payload = require_json()
    raw_token = (payload.get("token") or "").strip()
    new_password = payload.get("new_password") or ""

    if not raw_token:
        return json_error("Thiếu mã đặt lại mật khẩu.", 400, "missing_token")
    if not validate_password(new_password):
        return json_error("Mật khẩu mới cần ít nhất 6 ký tự.", 400, "invalid_password")

    token_row = fetch_one(
        """
        SELECT * FROM password_reset_tokens
        WHERE token_hash = ? AND used_at IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (token_hash(raw_token),),
    )

    if not token_row:
        return json_error("Mã đặt lại mật khẩu không hợp lệ hoặc đã dùng.", 400, "invalid_token")

    expires_at = parse_iso_datetime(token_row["expires_at"])
    if expires_at is None or expires_at <= utcnow():
        return json_error("Mã đặt lại mật khẩu đã hết hạn.", 400, "expired_token")

    now = utcnow_iso()
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (generate_password_hash(new_password), now, token_row["user_id"]),
    )
    db.execute("UPDATE password_reset_tokens SET used_at = ? WHERE id = ?", (now, token_row["id"]))
    db.execute(
        "UPDATE user_devices SET is_revoked = 1, updated_at = ? WHERE user_id = ?",
        (now, token_row["user_id"]),
    )
    db.commit()

    if g.current_user and g.current_user["id"] == token_row["user_id"]:
        session.clear()

    return jsonify({"message": "Đặt lại mật khẩu thành công. Bạn hãy đăng nhập lại nhé."})


@app.route("/api/me", methods=["GET"])
@pin_required
def me():
    return jsonify(
        {
            "user": serialize_user(g.current_user),
            "family": build_family_payload(g.current_user["id"]),
            "invitations": list_pending_family_invitations(g.current_user["id"]),
            "call_relationships": list_call_relationships(g.current_user["id"]),
            "supported_relationships": build_supported_relationships_payload(),
        }
    )


@app.route("/api/me", methods=["PATCH"])
@pin_required
def update_me():
    payload = require_json()
    full_name = (payload.get("full_name") or "").strip()
    age_raw = str(payload.get("age") or "").strip()
    email = normalize_email(payload.get("email") or "")
    phone_number = normalize_phone(payload.get("phone_number") or "")

    if not full_name:
        return json_error("Bạn chưa nhập họ tên.", 400, "invalid_full_name")
    if not age_raw.isdigit():
        return json_error("Tuổi phải là số hợp lệ.", 400, "invalid_age")

    age = int(age_raw)
    if age < 1 or age > 120:
        return json_error("Tuổi cần nằm trong khoảng hợp lý.", 400, "invalid_age")
    if not validate_email(email):
        return json_error("Email chưa đúng định dạng.", 400, "invalid_email")
    if not validate_phone(phone_number):
        return json_error("Số điện thoại chưa đúng định dạng.", 400, "invalid_phone")

    email_owner = fetch_user_by_email(email)
    if email_owner and email_owner["id"] != g.current_user["id"]:
        return json_error("Email này đã thuộc về tài khoản khác.", 409, "email_exists")

    phone_owner = fetch_user_by_phone(phone_number)
    if phone_owner and phone_owner["id"] != g.current_user["id"]:
        return json_error("Số điện thoại này đã thuộc về tài khoản khác.", 409, "phone_exists")

    now = utcnow_iso()
    get_db().execute(
        """
        UPDATE users
        SET full_name = ?, age = ?, email = ?, phone_number = ?, updated_at = ?
        WHERE id = ?
        """,
        (full_name, age, email, phone_number, now, g.current_user["id"]),
    )
    get_db().commit()
    g.current_user = fetch_user_by_id(g.current_user["id"])

    return jsonify({"message": "Đã cập nhật hồ sơ.", "user": serialize_user(g.current_user)})


@app.route("/api/me/change-password", methods=["POST"])
@pin_required
def change_password():
    payload = require_json()
    new_password = payload.get("new_password") or ""
    confirm_password = payload.get("confirm_password") or ""

    if not validate_password(new_password):
        return json_error("Mật khẩu mới cần ít nhất 6 ký tự.", 400, "invalid_password")
    if new_password != confirm_password:
        return json_error("Mật khẩu xác nhận chưa khớp.", 400, "password_mismatch")

    get_db().execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (generate_password_hash(new_password), utcnow_iso(), g.current_user["id"]),
    )
    get_db().commit()
    return jsonify({"message": "Đổi mật khẩu thành công."})


@app.route("/api/me/gemini-key", methods=["POST"])
@pin_required
def update_gemini_key():
    payload = require_json()
    api_key = (payload.get("api_key") or "").strip()

    if not api_key:
        return json_error("Bạn cần nhập Gemini API key trước khi lưu.", 400, "missing_gemini_api_key")

    get_db().execute(
        "UPDATE users SET gemini_api_key = ?, updated_at = ? WHERE id = ?",
        (api_key, utcnow_iso(), g.current_user["id"]),
    )
    get_db().commit()
    g.current_user = fetch_user_by_id(g.current_user["id"])
    return jsonify({"message": "Đã lưu Gemini API key cá nhân.", "user": serialize_user(g.current_user)})


@app.route("/api/me/gemini-key", methods=["DELETE"])
@pin_required
def clear_gemini_key():
    get_db().execute(
        "UPDATE users SET gemini_api_key = '', updated_at = ? WHERE id = ?",
        (utcnow_iso(), g.current_user["id"]),
    )
    get_db().commit()
    g.current_user = fetch_user_by_id(g.current_user["id"])
    return jsonify({"message": "Đã xóa Gemini API key cá nhân.", "user": serialize_user(g.current_user)})


@app.route("/api/families/current", methods=["GET"])
@pin_required
def current_family():
    return jsonify(
        {
            "family": build_family_payload(g.current_user["id"]),
            "invitations": list_pending_family_invitations(g.current_user["id"]),
            "call_relationships": list_call_relationships(g.current_user["id"]),
            "supported_relationships": build_supported_relationships_payload(),
        }
    )


@app.route("/api/families", methods=["POST"])
@pin_required
def create_family():
    if get_active_family_membership(g.current_user["id"]):
        return json_error("Bạn đã thuộc một nhóm gia đình rồi.", 409, "family_exists")

    payload = require_json()
    family_name = (payload.get("family_name") or "").strip()
    if not family_name:
        return json_error("Bạn cần nhập tên nhóm gia đình.", 400, "invalid_family_name")

    now = utcnow_iso()
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO family_groups (family_name, created_by_user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (family_name, g.current_user["id"], now, now),
    )
    family_group_id = cursor.lastrowid
    db.execute(
        """
        INSERT INTO family_members (family_group_id, user_id, role, status, joined_at, updated_at)
        VALUES (?, ?, 'admin', 'active', ?, ?)
        """,
        (family_group_id, g.current_user["id"], now, now),
    )
    db.commit()

    return jsonify({"message": "Đã tạo nhóm gia đình.", "family": build_family_payload(g.current_user["id"])})


@app.route("/api/families/current", methods=["PATCH"])
@pin_required
def rename_family():
    membership = get_active_family_membership(g.current_user["id"])
    if not membership:
        return json_error("Bạn chưa tham gia nhóm gia đình nào.", 404, "family_not_found")
    if membership["role"] != "admin":
        return json_error("Chỉ admin mới được sửa tên nhóm.", 403, "not_family_admin")

    payload = require_json()
    family_name = (payload.get("family_name") or "").strip()
    if not family_name:
        return json_error("Tên nhóm gia đình không được để trống.", 400, "invalid_family_name")

    get_db().execute(
        "UPDATE family_groups SET family_name = ?, updated_at = ? WHERE id = ?",
        (family_name, utcnow_iso(), membership["family_group_id"]),
    )
    get_db().commit()

    return jsonify({"message": "Đã cập nhật tên nhóm.", "family": build_family_payload(g.current_user["id"])})


@app.route("/api/families/current/invitations", methods=["POST"])
@pin_required
def invite_to_family():
    membership = get_active_family_membership(g.current_user["id"])
    if not membership:
        return json_error("Bạn chưa có nhóm gia đình để mời thêm thành viên.", 404, "family_not_found")
    if membership["role"] != "admin":
        return json_error("Chỉ admin mới được mời thành viên.", 403, "not_family_admin")

    payload = require_json()
    identifier = (payload.get("identifier") or "").strip()
    if not identifier:
        return json_error("Bạn cần nhập email hoặc số điện thoại của người được mời.", 400, "missing_identifier")

    invited_user = fetch_user_by_identifier(identifier)
    if not invited_user:
        return json_error("Chưa tìm thấy tài khoản với thông tin bạn nhập.", 404, "user_not_found")
    if invited_user["id"] == g.current_user["id"]:
        return json_error("Bạn không thể tự mời chính mình.", 400, "invite_self")
    if get_active_family_membership(invited_user["id"]):
        return json_error("Người này đã thuộc một nhóm gia đình khác.", 409, "target_has_family")

    existing_invitation = fetch_one(
        """
        SELECT * FROM family_invitations
        WHERE family_group_id = ? AND invited_user_id = ? AND status = 'pending'
        """,
        (membership["family_group_id"], invited_user["id"]),
    )
    if existing_invitation:
        return json_error("Người này đã có lời mời đang chờ.", 409, "invitation_exists")

    now = utcnow_iso()
    get_db().execute(
        """
        INSERT INTO family_invitations (
            family_group_id, invited_user_id, invited_by_user_id, status, created_at
        ) VALUES (?, ?, ?, 'pending', ?)
        """,
        (membership["family_group_id"], invited_user["id"], g.current_user["id"], now),
    )
    get_db().commit()
    invitation_id = fetch_one(
        "SELECT id FROM family_invitations WHERE family_group_id = ? AND invited_user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (membership["family_group_id"], invited_user["id"]),
    )["id"]

    send_push_notification(
        target_user_id=invited_user["id"],
        title="Loi moi gia dinh moi",
        body=f"{g.current_user['full_name']} vua moi ban vao nhom {membership['family_name']}.",
        data={
            "event_type": "family_invitation",
            "invitation_id": invitation_id,
            "family_group_id": membership["family_group_id"],
            "family_name": membership["family_name"],
            "invited_by_user_id": g.current_user["id"],
        },
    )

    return jsonify({"message": f"Đã gửi lời mời cho {invited_user['full_name']}."})


@app.route("/api/families/invitations", methods=["GET"])
@pin_required
def family_invitations():
    return jsonify({"invitations": list_pending_family_invitations(g.current_user["id"])})


@app.route("/api/families/invitations/<int:invitation_id>/respond", methods=["POST"])
@pin_required
def respond_family_invitation(invitation_id: int):
    payload = require_json()
    action = (payload.get("action") or "").strip().lower()

    if action not in {"accept", "decline"}:
        return json_error("Hành động không hợp lệ.", 400, "invalid_action")

    invitation = fetch_one(
        """
        SELECT * FROM family_invitations
        WHERE id = ? AND invited_user_id = ? AND status = 'pending'
        """,
        (invitation_id, g.current_user["id"]),
    )
    if not invitation:
        return json_error("Không tìm thấy lời mời hợp lệ.", 404, "invitation_not_found")

    if action == "accept":
        if get_active_family_membership(g.current_user["id"]):
            return json_error("Bạn đã thuộc một nhóm gia đình khác.", 409, "family_exists")

        now = utcnow_iso()
        db = get_db()
        db.execute(
            """
            INSERT INTO family_members (family_group_id, user_id, role, status, joined_at, updated_at)
            VALUES (?, ?, 'member', 'active', ?, ?)
            ON CONFLICT(family_group_id, user_id)
            DO UPDATE SET status = 'active', role = 'member', updated_at = excluded.updated_at
            """,
            (invitation["family_group_id"], g.current_user["id"], now, now),
        )
        db.execute(
            "UPDATE family_invitations SET status = 'accepted', responded_at = ? WHERE id = ?",
            (now, invitation_id),
        )
        db.commit()
        send_push_notification(
            target_user_id=invitation["invited_by_user_id"],
            title="Loi moi da duoc chap nhan",
            body=f"{g.current_user['full_name']} da tham gia nhom gia dinh cua ban.",
            data={
                "event_type": "family_invitation_accepted",
                "invitation_id": invitation_id,
                "family_group_id": invitation["family_group_id"],
                "user_id": g.current_user["id"],
            },
        )
        return jsonify({"message": "Bạn đã tham gia nhóm gia đình.", "family": build_family_payload(g.current_user["id"])})

    get_db().execute(
        "UPDATE family_invitations SET status = 'declined', responded_at = ? WHERE id = ?",
        (utcnow_iso(), invitation_id),
    )
    get_db().commit()
    send_push_notification(
        target_user_id=invitation["invited_by_user_id"],
        title="Loi moi da bi tu choi",
        body=f"{g.current_user['full_name']} da tu choi loi moi vao nhom gia dinh.",
        data={
            "event_type": "family_invitation_declined",
            "invitation_id": invitation_id,
            "family_group_id": invitation["family_group_id"],
            "user_id": g.current_user["id"],
        },
    )
    return jsonify({"message": "Bạn đã từ chối lời mời."})


@app.route("/api/families/current/members/<int:member_id>/role", methods=["PATCH"])
@pin_required
def change_family_member_role(member_id: int):
    membership = get_active_family_membership(g.current_user["id"])
    if not membership:
        return json_error("Bạn chưa thuộc nhóm gia đình nào.", 404, "family_not_found")
    if membership["role"] != "admin":
        return json_error("Chỉ admin mới được đổi quyền.", 403, "not_family_admin")

    payload = require_json()
    new_role = (payload.get("role") or "").strip().lower()
    if new_role not in {"admin", "member"}:
        return json_error("Vai trò không hợp lệ.", 400, "invalid_role")

    target = fetch_one(
        """
        SELECT * FROM family_members
        WHERE id = ? AND family_group_id = ? AND status = 'active'
        """,
        (member_id, membership["family_group_id"]),
    )
    if not target:
        return json_error("Không tìm thấy thành viên cần cập nhật.", 404, "member_not_found")

    if target["role"] == "admin" and new_role == "member" and count_active_admins(membership["family_group_id"]) <= 1:
        return json_error("Nhóm phải luôn còn ít nhất một admin.", 400, "last_admin")

    get_db().execute(
        "UPDATE family_members SET role = ?, updated_at = ? WHERE id = ?",
        (new_role, utcnow_iso(), member_id),
    )
    get_db().commit()

    return jsonify({"message": "Đã cập nhật vai trò thành viên.", "family": build_family_payload(g.current_user["id"])})


@app.route("/api/families/current/members/<int:member_id>", methods=["DELETE"])
@pin_required
def remove_family_member(member_id: int):
    membership = get_active_family_membership(g.current_user["id"])
    if not membership:
        return json_error("Bạn chưa thuộc nhóm gia đình nào.", 404, "family_not_found")

    target = fetch_one(
        """
        SELECT * FROM family_members
        WHERE id = ? AND family_group_id = ? AND status = 'active'
        """,
        (member_id, membership["family_group_id"]),
    )
    if not target:
        return json_error("Không tìm thấy thành viên cần xử lý.", 404, "member_not_found")

    is_self = target["user_id"] == g.current_user["id"]
    if not is_self and membership["role"] != "admin":
        return json_error("Chỉ admin mới được xóa thành viên khác.", 403, "not_family_admin")
    if target["role"] == "admin" and count_active_admins(membership["family_group_id"]) <= 1:
        return json_error("Không thể xóa admin cuối cùng của nhóm.", 400, "last_admin")

    get_db().execute(
        "UPDATE family_members SET status = 'removed', updated_at = ? WHERE id = ?",
        (utcnow_iso(), member_id),
    )
    get_db().commit()

    message = "Bạn đã rời nhóm gia đình." if is_self else "Đã xóa thành viên khỏi nhóm."
    return jsonify({"message": message, "family": build_family_payload(g.current_user["id"])})


@app.route("/api/device-push-tokens/register", methods=["POST"])
@pin_required
def register_device_push_token():
    payload = require_json()
    push_token = (payload.get("push_token") or "").strip()
    platform = (payload.get("platform") or "").strip().lower()

    if not push_token:
        return json_error("Thiếu push token của thiết bị.", 400, "missing_push_token")
    if platform not in {"android", "ios"}:
        return json_error("Platform chỉ hỗ trợ android hoặc ios.", 400, "invalid_platform")

    existing = fetch_one(
        """
        SELECT id FROM device_push_tokens
        WHERE user_id = ? AND device_id = ? AND push_token = ?
        """,
        (g.current_user["id"], g.current_device["device_id"], push_token),
    )

    now = utcnow_iso()
    if existing:
        get_db().execute(
            """
            UPDATE device_push_tokens
            SET is_active = 1, platform = ?, updated_at = ?
            WHERE id = ?
            """,
            (platform, now, existing["id"]),
        )
    else:
        get_db().execute(
            """
            INSERT INTO device_push_tokens (user_id, device_id, platform, push_token, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (g.current_user["id"], g.current_device["device_id"], platform, push_token, now, now),
        )

    get_db().commit()
    return jsonify({"message": "Đã lưu push token cho thiết bị.", "provider": CALL_PROVIDER})


@app.route("/api/call-relationships", methods=["GET"])
@pin_required
def get_call_relationships():
    return jsonify(
        {
            "relationships": list_call_relationships(g.current_user["id"]),
            "supported_relationships": build_supported_relationships_payload(),
        }
    )


@app.route("/api/call-relationships", methods=["POST"])
@pin_required
def upsert_call_relationship():
    membership = get_active_family_membership(g.current_user["id"])
    if not membership:
        return json_error("Bạn cần tham gia nhóm gia đình trước khi cài đặt quan hệ gọi.", 404, "family_not_found")

    payload = require_json()
    relative_user_id_raw = str(payload.get("relative_user_id") or "").strip()
    relationship_key = normalize_relationship_key(payload.get("relationship_key") or "")
    priority_raw = str(payload.get("priority_order") or "1").strip()
    custom_aliases = normalize_alias_storage(payload.get("custom_aliases") or "")

    if not relative_user_id_raw.isdigit():
        return json_error("Thiếu người thân cần cài đặt.", 400, "invalid_relative_user")
    if relationship_key not in RELATIONSHIP_LABELS:
        return json_error("Quan hệ chưa hợp lệ.", 400, "invalid_relationship_key")
    if not priority_raw.isdigit() or int(priority_raw) < 1:
        return json_error("Thứ tự ưu tiên phải là số dương.", 400, "invalid_priority")

    relative_user_id = int(relative_user_id_raw)
    if relative_user_id == g.current_user["id"]:
        return json_error("Bạn không thể tự gán quan hệ gọi cho chính mình.", 400, "invalid_relative_user")

    relative_membership = fetch_family_membership_record(membership["family_group_id"], relative_user_id)
    if not relative_membership:
        return json_error("Người này không nằm trong cùng nhóm gia đình.", 404, "relative_not_in_family")

    existing = fetch_one(
        """
        SELECT id FROM family_relationships
        WHERE owner_user_id = ? AND relative_user_id = ? AND relationship_key = ?
        """,
        (g.current_user["id"], relative_user_id, relationship_key),
    )

    now = utcnow_iso()
    if existing:
        get_db().execute(
            """
            UPDATE family_relationships
            SET family_group_id = ?, priority_order = ?, custom_aliases = ?, is_active = 1, updated_at = ?
            WHERE id = ?
            """,
            (membership["family_group_id"], int(priority_raw), custom_aliases, now, existing["id"]),
        )
    else:
        get_db().execute(
            """
            INSERT INTO family_relationships (
                family_group_id, owner_user_id, relative_user_id, relationship_key, custom_aliases, priority_order, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                membership["family_group_id"],
                g.current_user["id"],
                relative_user_id,
                relationship_key,
                custom_aliases,
                int(priority_raw),
                now,
                now,
            ),
        )

    get_db().commit()
    return jsonify({"message": "Đã lưu quan hệ gọi khẩn cấp.", "relationships": list_call_relationships(g.current_user["id"])})


@app.route("/api/call-relationships/<int:relationship_id>", methods=["DELETE"])
@pin_required
def delete_call_relationship(relationship_id: int):
    row = fetch_one(
        "SELECT * FROM family_relationships WHERE id = ? AND owner_user_id = ?",
        (relationship_id, g.current_user["id"]),
    )
    if not row:
        return json_error("Không tìm thấy cấu hình quan hệ cần xóa.", 404, "relationship_not_found")

    get_db().execute(
        "UPDATE family_relationships SET is_active = 0, updated_at = ? WHERE id = ?",
        (utcnow_iso(), relationship_id),
    )
    get_db().commit()
    return jsonify({"message": "Đã xóa quan hệ gọi.", "relationships": list_call_relationships(g.current_user["id"])})


@app.route("/api/calls/voice-intent", methods=["POST"])
@pin_required
def create_call_from_voice_intent():
    payload = require_json()
    transcript_text = (payload.get("transcript_text") or "").strip()
    if not transcript_text:
        return json_error("Thiếu nội dung giọng nói đã nhận dạng.", 400, "missing_transcript")

    relationship_rows = list_call_relationship_rows(g.current_user["id"])
    intent = detect_call_intent(transcript_text, relationship_rows)
    if intent.get("type") != "call":
        return jsonify({"action": "chat", "message": "Đây chưa phải là lệnh gọi khẩn cấp."})

    if intent.get("needs_confirmation"):
        return jsonify(
            {
                "action": "confirm",
                "question": intent.get("question") or "Bác muốn gọi ai ạ?",
                "intent": intent,
            }
        )

    session_row = create_call_session_for_relationship(
        caller_user_id=g.current_user["id"],
        relationship_key=intent["relationship_key"],
        relative_user_id=intent.get("relative_user_id"),
        transcript_text=transcript_text,
        trigger_source="voice",
    )
    if not session_row:
        return json_error("Gia đình chưa cài đặt người nhận cho lệnh gọi này.", 404, "call_target_not_found")

    return jsonify(
        {
            "action": "calling",
            "message": f"Đang gọi {RELATIONSHIP_LABELS.get(intent['relationship_key'], intent['relationship_key'])} cho bác.",
            "call": build_call_session_payload(session_row["id"]),
        }
    )


@app.route("/api/calls", methods=["POST"])
@pin_required
def create_manual_call():
    payload = require_json()
    relationship_key = payload.get("relationship_key") or ""
    session_row = create_call_session_for_relationship(
        caller_user_id=g.current_user["id"],
        relationship_key=relationship_key,
        transcript_text=None,
        trigger_source="manual_button",
    )
    if not session_row:
        return json_error("Không tìm thấy người nhận phù hợp cho cuộc gọi này.", 404, "call_target_not_found")

    return jsonify({"message": "Đã tạo cuộc gọi khẩn cấp.", "call": build_call_session_payload(session_row["id"])})


@app.route("/api/calls/<int:call_session_id>", methods=["GET"])
@pin_required
def get_call_session_status(call_session_id: int):
    if not user_can_access_call_session(call_session_id, g.current_user["id"]):
        return json_error("Bạn không có quyền xem cuộc gọi này.", 403, "forbidden_call_session")

    payload = build_call_session_payload(call_session_id)
    if not payload:
        return json_error("Không tìm thấy cuộc gọi.", 404, "call_session_not_found")
    return jsonify({"call": payload})


@app.route("/api/calls/history", methods=["GET"])
@pin_required
def get_call_history():
    return jsonify({"provider": CALL_PROVIDER, "calls": list_call_history(g.current_user["id"])})


@app.route("/api/calls/<int:call_session_id>/accept", methods=["POST"])
@pin_required
def accept_call_session(call_session_id: int):
    if not user_can_access_call_session(call_session_id, g.current_user["id"]):
        return json_error("Bạn không có quyền nhận cuộc gọi này.", 403, "forbidden_call_session")

    session_row = advance_call_session_if_needed(call_session_id)
    if not session_row:
        return json_error("Không tìm thấy cuộc gọi.", 404, "call_session_not_found")
    if session_row["status"] in FINAL_CALL_STATUSES and session_row["status"] != "accepted":
        return json_error("Cuộc gọi này không còn ở trạng thái có thể nghe máy.", 409, "call_not_available")

    target_row = fetch_one(
        """
        SELECT * FROM call_session_targets
        WHERE call_session_id = ? AND target_user_id = ? AND status IN ('ringing', 'pending')
        ORDER BY priority_order ASC
        LIMIT 1
        """,
        (call_session_id, g.current_user["id"]),
    )
    if not target_row:
        return json_error("Bạn không phải người đang được gọi ở thời điểm này.", 409, "not_current_target")

    now = utcnow_iso()
    db = get_db()
    db.execute(
        """
        UPDATE call_session_targets
        SET status = 'accepted', responded_at = ?, response_reason = 'accepted', updated_at = ?
        WHERE id = ?
        """,
        (now, now, target_row["id"]),
    )
    db.execute(
        """
        UPDATE call_session_targets
        SET status = 'skipped', responded_at = ?, response_reason = 'another_target_accepted', updated_at = ?
        WHERE call_session_id = ? AND id != ? AND status IN ('pending', 'ringing')
        """,
        (now, now, call_session_id, target_row["id"]),
    )
    db.commit()

    update_call_session_status(
        call_session_id,
        status="accepted",
        accepted_by_user_id=g.current_user["id"],
        accepted_at=now,
    )
    create_call_event(call_session_id, "call_accepted", actor_user_id=g.current_user["id"])
    return jsonify({"message": "Đã nhận cuộc gọi.", "call": build_call_session_payload(call_session_id)})


@app.route("/api/calls/<int:call_session_id>/decline", methods=["POST"])
@pin_required
def decline_call_session(call_session_id: int):
    if not user_can_access_call_session(call_session_id, g.current_user["id"]):
        return json_error("Bạn không có quyền từ chối cuộc gọi này.", 403, "forbidden_call_session")

    target_row = fetch_one(
        """
        SELECT * FROM call_session_targets
        WHERE call_session_id = ? AND target_user_id = ? AND status IN ('ringing', 'pending')
        ORDER BY priority_order ASC
        LIMIT 1
        """,
        (call_session_id, g.current_user["id"]),
    )
    if not target_row:
        return json_error("Bạn không có lượt đổ chuông đang chờ.", 409, "no_pending_target")

    now = utcnow_iso()
    get_db().execute(
        """
        UPDATE call_session_targets
        SET status = 'declined', responded_at = ?, response_reason = 'declined', updated_at = ?
        WHERE id = ?
        """,
        (now, now, target_row["id"]),
    )
    get_db().commit()
    create_call_event(call_session_id, "call_declined", actor_user_id=g.current_user["id"])
    advance_call_session_if_needed(call_session_id)
    return jsonify({"message": "Đã từ chối cuộc gọi.", "call": build_call_session_payload(call_session_id)})


@app.route("/api/calls/<int:call_session_id>/end", methods=["POST"])
@pin_required
def end_call_session(call_session_id: int):
    if not user_can_access_call_session(call_session_id, g.current_user["id"]):
        return json_error("Bạn không có quyền kết thúc cuộc gọi này.", 403, "forbidden_call_session")

    session_row = fetch_call_session(call_session_id)
    if not session_row:
        return json_error("Không tìm thấy cuộc gọi.", 404, "call_session_not_found")
    if session_row["status"] in {"ended", "failed", "missed", "declined", "timeout"}:
        return jsonify({"message": "Cuộc gọi đã kết thúc trước đó.", "call": build_call_session_payload(call_session_id)})

    update_call_session_status(
        call_session_id,
        status="ended",
        ended_at=utcnow_iso(),
        end_reason="ended_by_user",
    )
    create_call_event(call_session_id, "call_ended", actor_user_id=g.current_user["id"])
    return jsonify({"message": "Đã kết thúc cuộc gọi.", "call": build_call_session_payload(call_session_id)})


@app.route("/api/calls/provider/webhook", methods=["POST"])
def call_provider_webhook():
    payload = require_json()
    call_session_id = payload.get("call_session_id")
    if call_session_id and str(call_session_id).isdigit() and fetch_call_session(int(call_session_id)):
        create_call_event(
            int(call_session_id),
            "provider_webhook",
            payload=payload,
        )
    return jsonify({"status": "ok", "provider": CALL_PROVIDER})


@app.route("/chat", methods=["POST"])
@pin_required
def chat():
    payload = require_json()
    user_text = (payload.get("message") or "").strip()

    if not user_text:
        return jsonify({"error": "Thiếu nội dung tin nhắn."}), 400

    reply = generate_reply(user_text, get_history())
    return jsonify({"reply": reply})


@app.route("/chat_stream", methods=["POST"])
@pin_required
def chat_stream():
    payload = require_json()
    user_text = (payload.get("message") or "").strip()

    if not user_text:
        return jsonify({"error": "Thiếu nội dung tin nhắn."}), 400

    history = get_history()

    @stream_with_context
    def generate():
        current_model = get_user_model(g.current_user)
        if current_model is None:
            reply = build_unavailable_message(g.current_user)
            remember_turn(history, user_text, reply)
            yield reply
            return

        prompt = build_prompt(user_text, history)
        full_text = ""

        try:
            response = current_model.generate_content(prompt, stream=True)
            for chunk in response:
                chunk_text = getattr(chunk, "text", "")
                if not chunk_text:
                    continue
                full_text += chunk_text
                yield chunk_text
        except Exception:
            full_text = (
                "Dạ, trong lúc kết nối Gemini đã có lỗi xảy ra. "
                "Bạn thử lại sau ít phút hoặc kiểm tra API key giúp tôi nhé."
            )
            yield full_text

        if not full_text.strip():
            full_text = "Dạ, tôi tạm thời chưa tạo được nội dung phản hồi."

        remember_turn(history, user_text, full_text.strip())

    return Response(generate(), mimetype="text/plain; charset=utf-8")


def extract_keywords(text: str) -> list[str]:
    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    return [word for word in words if len(word) > 1]


def search_context(question: str) -> str:
    if not knowledge_chunks:
        return ""

    keywords = extract_keywords(question)
    if not keywords:
        return "\n".join(knowledge_chunks[:MAX_CONTEXT_CHUNKS])

    scored_chunks = []
    for chunk in knowledge_chunks:
        lowered_chunk = chunk.lower()
        score = sum(1 for keyword in keywords if keyword in lowered_chunk)
        if score:
            scored_chunks.append((score, chunk))

    if not scored_chunks:
        return "\n".join(knowledge_chunks[:MAX_CONTEXT_CHUNKS])

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    top_chunks = [chunk for _, chunk in scored_chunks[:MAX_CONTEXT_CHUNKS]]
    return "\n".join(top_chunks)


def build_prompt(question: str, history: list[str]) -> str:
    history_text = "\n".join(history[-6:]) or "Chưa có lịch sử hội thoại."
    context = search_context(question) or knowledge or "Không có dữ liệu tham khảo bổ sung."

    return f"""
Bạn là một trợ lý thân thiện, ấm áp và kiên nhẫn dành cho người lớn tuổi.

Nguyên tắc trả lời:
- Dùng tiếng Việt tự nhiên, đầy đủ dấu, dễ hiểu, câu ngắn gọn.
- Có thể mở đầu bằng các cụm nhẹ nhàng như "Dạ", "À", "Vâng".
- Nếu câu hỏi chưa rõ, hỏi lại ngắn gọn.
- Không tự ý đưa ra thông tin y tế nguy hiểm như một chẩn đoán chính xác.
- Ưu tiên dùng thông tin trong phần tham khảo khi có liên quan.

Lịch sử hội thoại:
{history_text}

Thông tin tham khảo:
{context}

Người dùng:
{question}

Trả lời:
""".strip()


def get_chat_history_key() -> str:
    if g.current_user is not None:
        return f"user:{g.current_user['id']}:device:{g.current_device['device_id']}"
    chat_session_id = session.get("chat_session_id")
    if not chat_session_id:
        chat_session_id = str(uuid.uuid4())
        session["chat_session_id"] = chat_session_id
    return f"guest:{chat_session_id}"


def remember_turn(history: list[str], user_text: str, reply: str) -> None:
    history.append(f"Người dùng: {user_text}")
    history.append(f"Trợ lý: {reply}")
    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]


def get_history() -> list[str]:
    return chat_store[get_chat_history_key()]


def get_user_model(user_row: sqlite3.Row | None):
    if genai is None:
        return None

    personal_key = get_personal_gemini_api_key(user_row)
    if not personal_key:
        return None

    genai.configure(api_key=personal_key)
    return genai.GenerativeModel(MODEL_NAME)


def build_unavailable_message(user_row: sqlite3.Row | None = None) -> str:
    if genai is None:
        return (
            "Dạ, ứng dụng chưa cài thư viện google-generativeai nên tôi chưa thể kết nối Gemini. "
            "Bạn hãy cài dependencies rồi thử lại nhé."
        )

    if user_row is not None and not get_personal_gemini_api_key(user_row):
        return (
            "Dạ, để trò chuyện hoặc voice với trợ lý, bác hãy mở phần Cài đặt và thêm Gemini API key cá nhân trước nhé."
        )

    if not API_KEY:
        return (
            "Dạ, hiện chưa có GEMINI_API_KEY trong môi trường nên tôi chưa thể trả lời bằng Gemini. "
            "Bạn chỉ cần thêm API key vào file .env hoặc biến môi trường là được."
        )

    return "Dạ, hiện tôi chưa sẵn sàng để phản hồi. Bạn thử lại giúp tôi nhé."


def generate_reply(question: str, history: list[str]) -> str:
    current_model = get_user_model(g.current_user)
    if current_model is None:
        reply = build_unavailable_message(g.current_user)
        remember_turn(history, question, reply)
        return reply

    prompt = build_prompt(question, history)
    response = current_model.generate_content(prompt)
    reply = (getattr(response, "text", "") or "").strip()

    if not reply:
        reply = "Dạ, tôi chưa tạo được câu trả lời phù hợp. Bạn thử hỏi lại một chút nhé."

    remember_turn(history, question, reply)
    return reply


@app.route("/")
def index():
    return render_template("index.html", model_name=MODEL_NAME)


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "model_ready": genai is not None,
            "knowledge_loaded": bool(knowledge_chunks),
            "database_ready": DB_PATH.exists(),
        }
    )


@app.route("/api/bootstrap")
def bootstrap():
    return jsonify(build_bootstrap_payload())


@app.route("/api/auth/register", methods=["POST"])
def register():
    payload = require_json()
    full_name = (payload.get("full_name") or "").strip()
    age_raw = str(payload.get("age") or "").strip()
    email = normalize_email(payload.get("email") or "")
    phone_number = normalize_phone(payload.get("phone_number") or "")
    password = payload.get("password") or ""
    device_id = normalize_device_id(payload.get("device_id") or "")
    device_name = (payload.get("device_name") or "Thiết bị chưa đặt tên").strip()[:120]

    if not full_name:
        return json_error("Bạn chưa nhập họ tên.", 400, "invalid_full_name")
    if not age_raw.isdigit():
        return json_error("Tuổi phải là số hợp lệ.", 400, "invalid_age")

    age = int(age_raw)
    if age < 1 or age > 120:
        return json_error("Tuổi cần nằm trong khoảng hợp lý.", 400, "invalid_age")
    if not validate_email(email):
        return json_error("Email chưa đúng định dạng.", 400, "invalid_email")
    if not validate_phone(phone_number):
        return json_error("Số điện thoại chưa đúng định dạng.", 400, "invalid_phone")
    if not validate_password(password):
        return json_error("Mật khẩu cần ít nhất 6 ký tự.", 400, "invalid_password")
    if not device_id:
        return json_error("Thiếu thông tin thiết bị để ghi nhớ đăng nhập.", 400, "missing_device")
    if fetch_user_by_email(email):
        return json_error("Email này đã được dùng rồi.", 409, "email_exists")
    if fetch_user_by_phone(phone_number):
        return json_error("Số điện thoại này đã được dùng rồi.", 409, "phone_exists")

    user_row = save_user(
        full_name=full_name,
        age=age,
        email=email,
        phone_number=phone_number,
        password_hash_value=generate_password_hash(password),
    )
    login_user_session(user_row, device_id, device_name)

    return jsonify(
        {
            "message": "Tạo tài khoản thành công. Bạn hãy thiết lập PIN 4 số cho thiết bị này nhé.",
            "bootstrap": build_bootstrap_payload(),
        }
    )


@app.route("/api/auth/login", methods=["POST"])
def login():
    payload = require_json()
    identifier = (payload.get("identifier") or "").strip()
    password = payload.get("password") or ""
    device_id = normalize_device_id(payload.get("device_id") or "")
    device_name = (payload.get("device_name") or "Thiết bị chưa đặt tên").strip()[:120]

    if not identifier or not password:
        return json_error("Bạn cần nhập email hoặc số điện thoại và mật khẩu.", 400, "missing_credentials")
    if not device_id:
        return json_error("Thiếu thông tin thiết bị để đăng nhập.", 400, "missing_device")

    user_row = fetch_user_by_identifier(identifier)
    if not user_row or not check_password_hash(user_row["password_hash"], password):
        return json_error("Thông tin đăng nhập chưa đúng.", 401, "invalid_credentials")
    if not user_row["is_active"]:
        return json_error("Tài khoản này đang bị khóa.", 403, "inactive_user")

    login_user_session(user_row, device_id, device_name)
    return jsonify({"message": "Đăng nhập thành công.", "bootstrap": build_bootstrap_payload()})


@app.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    logout_user_session()
    return jsonify({"message": "Đã đăng xuất khỏi thiết bị này."})


def save_user(
    *,
    full_name: str,
    age: int,
    email: str,
    phone_number: str,
    password_hash_value: str,
) -> sqlite3.Row:
    now = utcnow_iso()
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO users (full_name, age, email, phone_number, password_hash, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (full_name, age, email, phone_number, password_hash_value, now, now),
    )
    db.commit()
    return fetch_user_by_id(cursor.lastrowid)


def fetch_user_by_id(user_id: int) -> sqlite3.Row | None:
    return fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))


def fetch_user_by_email(email: str) -> sqlite3.Row | None:
    return fetch_one("SELECT * FROM users WHERE email = ?", (normalize_email(email),))


def fetch_user_by_phone(phone_number: str) -> sqlite3.Row | None:
    return fetch_one("SELECT * FROM users WHERE phone_number = ?", (normalize_phone(phone_number),))


def fetch_user_by_identifier(identifier: str) -> sqlite3.Row | None:
    normalized = identifier.strip()
    if "@" in normalized:
        return fetch_user_by_email(normalized)
    return fetch_user_by_phone(normalized)


def fetch_device(user_id: int, device_id: str) -> sqlite3.Row | None:
    return fetch_one(
        "SELECT * FROM user_devices WHERE user_id = ? AND device_id = ?",
        (user_id, device_id),
    )


def ensure_device_session(user_id: int, device_id: str, device_name: str) -> sqlite3.Row:
    now = utcnow_iso()
    db = get_db()
    device = fetch_device(user_id, device_id)

    if device:
        db.execute(
            """
            UPDATE user_devices
            SET device_name = ?, is_revoked = 0, last_login_at = ?, last_seen_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (device_name, now, now, now, device["id"]),
        )
    else:
        db.execute(
            """
            INSERT INTO user_devices (
                user_id, device_id, device_name, last_login_at, last_seen_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, device_id, device_name, now, now, now, now),
        )

    db.commit()
    return fetch_device(user_id, device_id)


def mark_device_seen(device_row: sqlite3.Row) -> None:
    now = utcnow_iso()
    get_db().execute(
        "UPDATE user_devices SET last_seen_at = ?, updated_at = ? WHERE id = ?",
        (now, now, device_row["id"]),
    )
    get_db().commit()


def issue_pin_token(user_id: int, device_id: str) -> str:
    return pin_serializer.dumps({"user_id": user_id, "device_id": device_id})


def validate_pin_token(raw_token: str, user_id: int, device_id: str) -> bool:
    if not raw_token:
        return False

    try:
        payload = pin_serializer.loads(raw_token, max_age=PIN_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False

    return payload.get("user_id") == user_id and payload.get("device_id") == device_id


def login_user_session(user_row: sqlite3.Row, device_id: str, device_name: str) -> sqlite3.Row:
    device = ensure_device_session(user_row["id"], device_id, device_name)
    session.clear()
    session.permanent = True
    session["user_id"] = user_row["id"]
    session["device_id"] = device_id
    g.current_user = user_row
    g.current_device = device
    return device


def logout_user_session() -> None:
    user_id = session.get("user_id")
    device_id = session.get("device_id")

    if user_id and device_id:
        get_db().execute(
            "UPDATE user_devices SET is_revoked = 1, updated_at = ? WHERE user_id = ? AND device_id = ?",
            (utcnow_iso(), user_id, device_id),
        )
        get_db().commit()

    session.clear()
    g.current_user = None
    g.current_device = None


def mask_secret(value: str) -> str:
    trimmed = (value or "").strip()
    if not trimmed:
        return ""
    if len(trimmed) <= 8:
        return "*" * len(trimmed)
    return f"{trimmed[:4]}...{trimmed[-4:]}"


def get_personal_gemini_api_key(user_row: sqlite3.Row | None) -> str:
    if not user_row:
        return ""
    return (user_row["gemini_api_key"] or "").strip()


def serialize_user(user_row: sqlite3.Row) -> dict:
    personal_key = get_personal_gemini_api_key(user_row)
    return {
        "id": user_row["id"],
        "full_name": user_row["full_name"],
        "age": user_row["age"],
        "email": user_row["email"],
        "phone_number": user_row["phone_number"],
        "created_at": user_row["created_at"],
        "updated_at": user_row["updated_at"],
        "has_personal_gemini_key": bool(personal_key),
        "gemini_key_preview": mask_secret(personal_key),
    }


def get_active_family_membership(user_id: int) -> sqlite3.Row | None:
    return fetch_one(
        """
        SELECT
            fm.id AS membership_id,
            fm.family_group_id,
            fm.user_id,
            fm.role,
            fm.status,
            fg.family_name,
            fg.created_by_user_id
        FROM family_members fm
        JOIN family_groups fg ON fg.id = fm.family_group_id
        WHERE fm.user_id = ? AND fm.status = 'active'
        ORDER BY fm.id DESC
        LIMIT 1
        """,
        (user_id,),
    )


def count_active_admins(family_group_id: int) -> int:
    row = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM family_members
        WHERE family_group_id = ? AND status = 'active' AND role = 'admin'
        """,
        (family_group_id,),
    )
    return row["total"] if row else 0


def fetch_family_members(family_group_id: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT
            fm.id,
            fm.role,
            fm.status,
            fm.joined_at,
            u.id AS user_id,
            u.full_name,
            u.age,
            u.email,
            u.phone_number
        FROM family_members fm
        JOIN users u ON u.id = fm.user_id
        WHERE fm.family_group_id = ? AND fm.status = 'active'
        ORDER BY
            CASE WHEN fm.role = 'admin' THEN 0 ELSE 1 END,
            u.full_name COLLATE NOCASE ASC
        """,
        (family_group_id,),
    )

    return [
        {
            "membership_id": row["id"],
            "user_id": row["user_id"],
            "full_name": row["full_name"],
            "age": row["age"],
            "email": row["email"],
            "phone_number": row["phone_number"],
            "role": row["role"],
            "joined_at": row["joined_at"],
        }
        for row in rows
    ]


def build_family_payload(user_id: int) -> dict | None:
    membership = get_active_family_membership(user_id)
    if not membership:
        return None

    return {
        "family_group_id": membership["family_group_id"],
        "family_name": membership["family_name"],
        "role": membership["role"],
        "created_by_user_id": membership["created_by_user_id"],
        "members": fetch_family_members(membership["family_group_id"]),
    }


def list_pending_family_invitations(user_id: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT
            fi.id,
            fi.family_group_id,
            fi.status,
            fi.created_at,
            fg.family_name,
            inviter.full_name AS invited_by_name
        FROM family_invitations fi
        JOIN family_groups fg ON fg.id = fi.family_group_id
        JOIN users inviter ON inviter.id = fi.invited_by_user_id
        WHERE fi.invited_user_id = ? AND fi.status = 'pending'
        ORDER BY fi.created_at DESC
        """,
        (user_id,),
    )

    return [
        {
            "id": row["id"],
            "family_group_id": row["family_group_id"],
            "family_name": row["family_name"],
            "invited_by_name": row["invited_by_name"],
            "created_at": row["created_at"],
            "status": row["status"],
        }
        for row in rows
    ]


def require_json() -> dict:
    return request.get_json(silent=True) or {}


def build_bootstrap_payload() -> dict:
    if g.current_user is None or g.current_device is None:
        return {
            "authenticated": False,
            "user": None,
            "pin_configured": False,
            "family": None,
            "invitations": [],
        }

    return {
        "authenticated": True,
        "user": {
            "id": g.current_user["id"],
            "full_name": g.current_user["full_name"],
        },
        "pin_configured": bool(g.current_device["pin_enabled"]),
        "family": build_family_payload(g.current_user["id"]),
        "invitations": list_pending_family_invitations(g.current_user["id"]),
    }


def build_supported_relationships_payload() -> list[dict]:
    return [{"key": key, "label": label} for key, label in RELATIONSHIP_LABELS.items()]


RELATIONSHIP_LABELS = {
    "son": "con trai",
    "daughter": "con gái",
    "grandchild": "cháu",
    "wife": "vợ",
    "husband": "chồng",
    "brother": "anh/em trai",
    "sister": "chị/em gái",
    "caregiver": "người chăm sóc",
    "family_member": "người nhà",
}

RELATIONSHIP_ALIASES = {
    "con trai": "son",
    "trai": "son",
    "thang con trai": "son",
    "con gai": "daughter",
    "gai": "daughter",
    "be gai": "daughter",
    "chau": "grandchild",
    "chau noi": "grandchild",
    "chau ngoai": "grandchild",
    "vo": "wife",
    "chong": "husband",
    "anh": "brother",
    "anh trai": "brother",
    "em trai": "brother",
    "chi": "sister",
    "chi gai": "sister",
    "em gai": "sister",
    "nguoi cham soc": "caregiver",
    "bao mau": "caregiver",
    "nguoi nha": "family_member",
    "nguoi than": "family_member",
    "gia dinh": "family_member",
    "chu": "family_member",
    "bac": "family_member",
    "chu bac": "family_member",
    "co": "family_member",
    "di": "family_member",
    "cau": "family_member",
    "mo": "family_member",
    "thim": "family_member",
    "dua chau": "grandchild",
}

FINAL_CALL_STATUSES = {"accepted", "declined", "timeout", "missed", "ended", "failed"}
FINAL_CALL_TARGET_STATUSES = {"accepted", "declined", "timeout", "skipped", "missed"}


def simplify_text(value: str) -> str:
    lowered = (value or "").strip().lower()
    normalized = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_marks).strip()


def normalize_relationship_key(value: str) -> str:
    simplified = simplify_text(value)
    return RELATIONSHIP_ALIASES.get(simplified, simplified)


def split_alias_input(value: str) -> list[str]:
    raw_parts = re.split(r"[,\n;]+", value or "")
    aliases: list[str] = []
    seen: set[str] = set()

    for part in raw_parts:
        alias = " ".join((part or "").strip().split())
        simplified = simplify_text(alias)
        if not simplified or simplified in seen:
            continue
        seen.add(simplified)
        aliases.append(alias)

    return aliases


def normalize_alias_storage(value: str) -> str:
    return ", ".join(split_alias_input(value))


def serialize_call_relationship(row: sqlite3.Row) -> dict:
    alias_list = split_alias_input(row["custom_aliases"])
    return {
        "id": row["id"],
        "family_group_id": row["family_group_id"],
        "owner_user_id": row["owner_user_id"],
        "relative_user_id": row["relative_user_id"],
        "relationship_key": row["relationship_key"],
        "relationship_label": RELATIONSHIP_LABELS.get(row["relationship_key"], row["relationship_key"]),
        "custom_aliases": row["custom_aliases"] or "",
        "custom_alias_list": alias_list,
        "priority_order": row["priority_order"],
        "relative_full_name": row["relative_full_name"],
        "relative_email": row["relative_email"],
        "relative_phone_number": row["relative_phone_number"],
        "is_active": bool(row["is_active"]),
    }


def list_call_relationship_rows(owner_user_id: int) -> list[sqlite3.Row]:
    membership = get_active_family_membership(owner_user_id)
    if not membership:
        return []

    return fetch_all(
        """
        SELECT
            fr.*,
            u.full_name AS relative_full_name,
            u.email AS relative_email,
            u.phone_number AS relative_phone_number
        FROM family_relationships fr
        JOIN users u ON u.id = fr.relative_user_id
        WHERE fr.owner_user_id = ? AND fr.is_active = 1 AND fr.family_group_id = ?
        ORDER BY fr.relationship_key ASC, fr.priority_order ASC, u.full_name COLLATE NOCASE ASC
        """,
        (owner_user_id, membership["family_group_id"]),
    )


def list_call_relationships(owner_user_id: int) -> list[dict]:
    return [serialize_call_relationship(row) for row in list_call_relationship_rows(owner_user_id)]


def list_relationship_keys(owner_user_id: int) -> list[str]:
    rows = list_call_relationship_rows(owner_user_id)
    return sorted({row["relationship_key"] for row in rows})


def build_person_call_aliases(relationship_rows: list[sqlite3.Row]) -> dict[str, list[dict]]:
    alias_map: dict[str, list[dict]] = {}

    def register(alias: str, row: sqlite3.Row) -> None:
        simplified = simplify_text(alias)
        if not simplified:
            return

        entry = {
            "relationship_key": row["relationship_key"],
            "relative_user_id": row["relative_user_id"],
            "relative_full_name": row["relative_full_name"],
        }
        bucket = alias_map.setdefault(simplified, [])
        if not any(
            existing["relationship_key"] == entry["relationship_key"]
            and existing["relative_user_id"] == entry["relative_user_id"]
            for existing in bucket
        ):
            bucket.append(entry)

    for row in relationship_rows:
        register(row["relative_full_name"], row)
        for alias in split_alias_input(row["custom_aliases"]):
            register(alias, row)

    return alias_map


def build_relationship_call_aliases(relationship_rows: list[sqlite3.Row]) -> dict[str, set[str]]:
    alias_map: dict[str, set[str]] = {}
    available_keys = {row["relationship_key"] for row in relationship_rows}

    def register(alias: str, relationship_key: str) -> None:
        simplified = simplify_text(alias)
        if not simplified:
            return
        alias_map.setdefault(simplified, set()).add(relationship_key)

    for alias, relationship_key in RELATIONSHIP_ALIASES.items():
        if relationship_key in available_keys:
            register(alias, relationship_key)

    for row in relationship_rows:
        relationship_key = row["relationship_key"]
        register(RELATIONSHIP_LABELS.get(relationship_key, relationship_key), relationship_key)

    return alias_map


def fetch_family_membership_record(family_group_id: int, user_id: int) -> sqlite3.Row | None:
    return fetch_one(
        """
        SELECT * FROM family_members
        WHERE family_group_id = ? AND user_id = ? AND status = 'active'
        """,
        (family_group_id, user_id),
    )


def create_call_event(call_session_id: int, event_type: str, actor_user_id: int | None = None, payload: dict | None = None) -> None:
    get_db().execute(
        """
        INSERT INTO call_events (call_session_id, event_type, actor_user_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            call_session_id,
            event_type,
            actor_user_id,
            json.dumps(payload or {}, ensure_ascii=False),
            utcnow_iso(),
        ),
    )
    get_db().commit()


def fetch_call_session(call_session_id: int) -> sqlite3.Row | None:
    return fetch_one("SELECT * FROM call_sessions WHERE id = ?", (call_session_id,))


def fetch_call_targets(call_session_id: int) -> list[sqlite3.Row]:
    return fetch_all(
        """
        SELECT
            cst.*,
            u.full_name AS target_full_name,
            u.email AS target_email,
            u.phone_number AS target_phone_number
        FROM call_session_targets cst
        JOIN users u ON u.id = cst.target_user_id
        WHERE cst.call_session_id = ?
        ORDER BY cst.priority_order ASC, cst.id ASC
        """,
        (call_session_id,),
    )


def fetch_current_ringing_target(call_session_id: int) -> sqlite3.Row | None:
    return fetch_one(
        """
        SELECT
            cst.*,
            u.full_name AS target_full_name,
            u.email AS target_email,
            u.phone_number AS target_phone_number
        FROM call_session_targets cst
        JOIN users u ON u.id = cst.target_user_id
        WHERE cst.call_session_id = ? AND cst.status = 'ringing'
        ORDER BY cst.priority_order ASC, cst.id ASC
        LIMIT 1
        """,
        (call_session_id,),
    )


def fetch_next_pending_target(call_session_id: int) -> sqlite3.Row | None:
    return fetch_one(
        """
        SELECT
            cst.*,
            u.full_name AS target_full_name,
            u.email AS target_email,
            u.phone_number AS target_phone_number
        FROM call_session_targets cst
        JOIN users u ON u.id = cst.target_user_id
        WHERE cst.call_session_id = ? AND cst.status = 'pending'
        ORDER BY cst.priority_order ASC, cst.id ASC
        LIMIT 1
        """,
        (call_session_id,),
    )


def list_push_tokens_for_user(user_id: int) -> list[str]:
    rows = fetch_all(
        """
        SELECT push_token
        FROM device_push_tokens
        WHERE user_id = ? AND is_active = 1
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    return [row["push_token"] for row in rows]


def send_push_notification(
    *,
    target_user_id: int | None = None,
    push_tokens: list[str] | None = None,
    title: str,
    body: str,
    data: dict | None = None,
) -> None:
    firebase_app = get_firebase_push_app()
    if firebase_app is None or firebase_messaging is None:
        return

    tokens = [token for token in (push_tokens or list_push_tokens_for_user(target_user_id or 0)) if token]
    unique_tokens: list[str] = []
    for token in tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)

    if not unique_tokens:
        return

    payload_data = {
        str(key): str(value)
        for key, value in (data or {}).items()
        if value is not None
    }

    message = firebase_messaging.MulticastMessage(
        tokens=unique_tokens,
        notification=firebase_messaging.Notification(title=title, body=body),
        data=payload_data,
        android=firebase_messaging.AndroidConfig(
            priority="high",
            notification=firebase_messaging.AndroidNotification(
                sound="default",
                channel_id="emergency_calls",
            ),
        ),
        apns=firebase_messaging.APNSConfig(
            headers={"apns-priority": "10"},
            payload=firebase_messaging.APNSPayload(
                aps=firebase_messaging.Aps(
                    sound="default",
                    content_available=True,
                )
            ),
        ),
    )

    try:
        firebase_messaging.send_each_for_multicast(message, app=firebase_app)
    except Exception:
        return


def build_call_invitation_payload(call_session_id: int, target_row: sqlite3.Row) -> dict:
    session_row = fetch_call_session(call_session_id)
    caller = fetch_user_by_id(session_row["caller_user_id"]) if session_row else None
    return {
        "provider": CALL_PROVIDER,
        "call_type": "audio",
        "call_session_id": call_session_id,
        "room_id": session_row["room_id"] if session_row else None,
        "ring_timeout_seconds": CALL_RING_TIMEOUT_SECONDS,
        "caller": {
            "id": caller["id"] if caller else None,
            "full_name": caller["full_name"] if caller else "Người thân",
        },
        "target": {
            "id": target_row["target_user_id"],
            "full_name": target_row["target_full_name"],
            "relationship_key": target_row["relationship_key"],
        },
        "push_tokens": list_push_tokens_for_user(target_row["target_user_id"]),
    }


def update_call_session_status(
    call_session_id: int,
    *,
    status: str,
    accepted_by_user_id: int | None = None,
    accepted_at: str | None = None,
    ended_at: str | None = None,
    end_reason: str | None = None,
) -> None:
    session_row = fetch_call_session(call_session_id)
    if not session_row:
        return

    get_db().execute(
        """
        UPDATE call_sessions
        SET status = ?,
            accepted_by_user_id = COALESCE(?, accepted_by_user_id),
            accepted_at = COALESCE(?, accepted_at),
            ended_at = COALESCE(?, ended_at),
            end_reason = COALESCE(?, end_reason),
            updated_at = ?
        WHERE id = ?
        """,
        (status, accepted_by_user_id, accepted_at, ended_at, end_reason, utcnow_iso(), call_session_id),
    )
    get_db().commit()


def start_next_call_target(call_session_id: int) -> sqlite3.Row | None:
    session_row = fetch_call_session(call_session_id)
    if not session_row or session_row["status"] in FINAL_CALL_STATUSES:
        return session_row

    target_row = fetch_next_pending_target(call_session_id)
    if not target_row:
        final_status = "missed"
        update_call_session_status(call_session_id, status=final_status, ended_at=utcnow_iso(), end_reason="no_target_answered")
        create_call_event(call_session_id, "session_completed_without_answer", payload={"status": final_status})
        return fetch_call_session(call_session_id)

    now = utcnow_iso()
    get_db().execute(
        """
        UPDATE call_session_targets
        SET status = 'ringing', rung_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, target_row["id"]),
    )
    get_db().execute(
        """
        UPDATE call_sessions
        SET status = 'ringing', started_at = COALESCE(started_at, ?), updated_at = ?
        WHERE id = ?
        """,
        (now, now, call_session_id),
    )
    get_db().commit()

    create_call_event(
        call_session_id,
        "target_ringing",
        payload=build_call_invitation_payload(call_session_id, target_row),
    )
    session_payload = build_call_session_payload(call_session_id)
    caller_row = fetch_user_by_id(session_row["caller_user_id"]) if session_row else None
    send_push_notification(
        target_user_id=target_row["target_user_id"],
        title="Cuoc goi khan cap",
        body=f"{caller_row['full_name'] if caller_row else 'Nguoi than'} dang goi ban.",
        data={
            "event_type": "incoming_call",
            "call_session_id": call_session_id,
            "room_id": session_payload["room_id"] if session_payload else None,
            "relationship_key": target_row["relationship_key"],
            "caller_name": caller_row["full_name"] if caller_row else None,
        },
    )
    return fetch_call_session(call_session_id)


def advance_call_session_if_needed(call_session_id: int) -> sqlite3.Row | None:
    session_row = fetch_call_session(call_session_id)
    if not session_row or session_row["status"] in FINAL_CALL_STATUSES:
        return session_row

    current_target = fetch_current_ringing_target(call_session_id)
    if current_target:
        rung_at = parse_iso_datetime(current_target["rung_at"])
        if rung_at and (utcnow() - rung_at).total_seconds() >= CALL_RING_TIMEOUT_SECONDS:
            now = utcnow_iso()
            get_db().execute(
                """
                UPDATE call_session_targets
                SET status = 'timeout', responded_at = ?, response_reason = 'ring_timeout', updated_at = ?
                WHERE id = ?
                """,
                (now, now, current_target["id"]),
            )
            get_db().commit()
            create_call_event(
                call_session_id,
                "target_timeout",
                payload={
                    "target_user_id": current_target["target_user_id"],
                    "priority_order": current_target["priority_order"],
                },
            )
            return start_next_call_target(call_session_id)
        return session_row

    return start_next_call_target(call_session_id)


def user_can_access_call_session(call_session_id: int, user_id: int) -> bool:
    row = fetch_one(
        """
        SELECT cs.id
        FROM call_sessions cs
        LEFT JOIN call_session_targets cst ON cst.call_session_id = cs.id
        WHERE cs.id = ? AND (cs.caller_user_id = ? OR cst.target_user_id = ?)
        LIMIT 1
        """,
        (call_session_id, user_id, user_id),
    )
    return row is not None


def build_call_session_payload(call_session_id: int) -> dict | None:
    session_row = advance_call_session_if_needed(call_session_id)
    if not session_row:
        return None

    caller = fetch_user_by_id(session_row["caller_user_id"])
    accepted_by = fetch_user_by_id(session_row["accepted_by_user_id"]) if session_row["accepted_by_user_id"] else None
    targets = fetch_call_targets(call_session_id)
    current_target = next((target for target in targets if target["status"] == "ringing"), None)

    return {
        "call_session_id": session_row["id"],
        "room_id": session_row["room_id"],
        "provider": CALL_PROVIDER,
        "status": session_row["status"],
        "trigger_source": session_row["trigger_source"],
        "relationship_key": session_row["relationship_key"],
        "relationship_label": RELATIONSHIP_LABELS.get(session_row["relationship_key"], session_row["relationship_key"]),
        "ring_timeout_seconds": CALL_RING_TIMEOUT_SECONDS,
        "caller": {
            "id": caller["id"] if caller else None,
            "full_name": caller["full_name"] if caller else "Người thân",
        },
        "accepted_by": {
            "id": accepted_by["id"],
            "full_name": accepted_by["full_name"],
        } if accepted_by else None,
        "current_target": {
            "id": current_target["target_user_id"],
            "full_name": current_target["target_full_name"],
            "relationship_key": current_target["relationship_key"],
            "priority_order": current_target["priority_order"],
            "push_tokens": list_push_tokens_for_user(current_target["target_user_id"]),
        } if current_target else None,
        "targets": [
            {
                "target_user_id": target["target_user_id"],
                "full_name": target["target_full_name"],
                "relationship_key": target["relationship_key"],
                "priority_order": target["priority_order"],
                "status": target["status"],
                "rung_at": target["rung_at"],
                "responded_at": target["responded_at"],
                "response_reason": target["response_reason"],
            }
            for target in targets
        ],
        "transcript_text": session_row["transcript_text"],
        "detected_intent": session_row["detected_intent"],
        "started_at": session_row["started_at"],
        "accepted_at": session_row["accepted_at"],
        "ended_at": session_row["ended_at"],
        "end_reason": session_row["end_reason"],
        "created_at": session_row["created_at"],
        "updated_at": session_row["updated_at"],
    }


def list_call_history(user_id: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT DISTINCT cs.*
        FROM call_sessions cs
        LEFT JOIN call_session_targets cst ON cst.call_session_id = cs.id
        WHERE cs.caller_user_id = ? OR cst.target_user_id = ?
        ORDER BY cs.created_at DESC, cs.id DESC
        LIMIT 30
        """,
        (user_id, user_id),
    )
    return [build_call_session_payload(row["id"]) for row in rows]


def get_call_target_candidates(
    owner_user_id: int,
    relationship_key: str,
    relative_user_id: int | None = None,
) -> list[sqlite3.Row]:
    normalized_key = normalize_relationship_key(relationship_key)
    membership = get_active_family_membership(owner_user_id)
    if not membership:
        return []

    if relative_user_id is not None:
        rows = fetch_all(
            """
            SELECT
                fr.*,
                u.full_name AS relative_full_name,
                u.email AS relative_email,
                u.phone_number AS relative_phone_number
            FROM family_relationships fr
            JOIN users u ON u.id = fr.relative_user_id
            WHERE fr.owner_user_id = ?
              AND fr.family_group_id = ?
              AND fr.is_active = 1
              AND fr.relationship_key = ?
              AND fr.relative_user_id = ?
            ORDER BY fr.priority_order ASC, fr.id ASC
            LIMIT 1
            """,
            (owner_user_id, membership["family_group_id"], normalized_key, relative_user_id),
        )
    else:
        rows = fetch_all(
            """
            SELECT
                fr.*,
                u.full_name AS relative_full_name,
                u.email AS relative_email,
                u.phone_number AS relative_phone_number
            FROM family_relationships fr
            JOIN users u ON u.id = fr.relative_user_id
            WHERE fr.owner_user_id = ?
              AND fr.family_group_id = ?
              AND fr.is_active = 1
              AND fr.relationship_key = ?
            ORDER BY fr.priority_order ASC, fr.id ASC
            LIMIT ?
            """,
            (owner_user_id, membership["family_group_id"], normalized_key, CALL_MAX_TARGETS),
        )

    return rows


def create_call_session_for_relationship(
    *,
    caller_user_id: int,
    relationship_key: str,
    relative_user_id: int | None = None,
    transcript_text: str | None,
    trigger_source: str,
) -> sqlite3.Row | None:
    relationship_key = normalize_relationship_key(relationship_key)
    targets = get_call_target_candidates(caller_user_id, relationship_key, relative_user_id)
    if not targets:
        return None

    now = utcnow_iso()
    room_id = str(uuid.uuid4())
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO call_sessions (
            room_id, initiated_by_user_id, caller_user_id, trigger_source, transcript_text,
            detected_intent, relationship_key, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'call', ?, 'created', ?, ?)
        """,
        (room_id, caller_user_id, caller_user_id, trigger_source, transcript_text, relationship_key, now, now),
    )
    call_session_id = cursor.lastrowid

    for row in targets:
        db.execute(
            """
            INSERT INTO call_session_targets (
                call_session_id, target_user_id, relationship_key, priority_order, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                call_session_id,
                row["relative_user_id"],
                relationship_key,
                row["priority_order"],
                now,
                now,
            ),
        )

    db.commit()
    create_call_event(
        call_session_id,
        "session_created",
        actor_user_id=caller_user_id,
        payload={
            "relationship_key": relationship_key,
            "target_user_ids": [row["relative_user_id"] for row in targets],
            "provider": CALL_PROVIDER,
        },
    )
    return advance_call_session_if_needed(call_session_id)


def detect_call_intent(text: str, relationship_rows: list[sqlite3.Row]) -> dict:
    simplified = simplify_text(text)
    if not simplified:
        return {"type": "chat"}

    call_patterns = [
        r"(^| )goi( |$)",
        r"(^| )goi cho( |$)",
        r"(^| )hay goi( |$)",
        r"(^| )giup toi goi( |$)",
        r"(^| )lien lac( |$)",
        r"(^| )call( |$)",
    ]
    if "goi y" in simplified or not any(re.search(pattern, simplified) for pattern in call_patterns):
        return {"type": "chat"}

    available_relationship_keys = sorted({row["relationship_key"] for row in relationship_rows})
    person_alias_map = build_person_call_aliases(relationship_rows)
    matched_people = []
    for alias in sorted(person_alias_map.keys(), key=len, reverse=True):
        if alias in simplified:
            matched_people.extend(person_alias_map[alias])

    unique_people: list[dict] = []
    seen_people: set[tuple[str, int]] = set()
    for entry in matched_people:
        marker = (entry["relationship_key"], entry["relative_user_id"])
        if marker in seen_people:
            continue
        seen_people.add(marker)
        unique_people.append(entry)

    if len(unique_people) == 1:
        return {
            "type": "call",
            "relationship_key": unique_people[0]["relationship_key"],
            "relative_user_id": unique_people[0]["relative_user_id"],
            "confidence": 0.98,
            "needs_confirmation": False,
        }

    if len(unique_people) > 1:
        names = [entry["relative_full_name"] for entry in unique_people[:3]]
        return {
            "type": "call",
            "relationship_key": None,
            "confidence": 0.45,
            "needs_confirmation": True,
            "question": f"Bác muốn gọi {', '.join(names)} ạ?",
        }

    alias_map = build_relationship_call_aliases(relationship_rows)
    matched_keys = []
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        if alias in simplified:
            matched_keys.extend(sorted(alias_map[alias]))

    unique_keys = []
    for key in matched_keys:
        if key not in unique_keys:
            unique_keys.append(key)

    if len(unique_keys) == 1:
        return {
            "type": "call",
            "relationship_key": unique_keys[0],
            "confidence": 0.95,
            "needs_confirmation": False,
        }

    if len(unique_keys) > 1:
        labels = [RELATIONSHIP_LABELS.get(key, key) for key in unique_keys]
        return {
            "type": "call",
            "relationship_key": None,
            "confidence": 0.4,
            "needs_confirmation": True,
            "question": f"Bác muốn gọi {', '.join(labels)} ạ?",
        }

    if len(available_relationship_keys) == 1:
        only_key = available_relationship_keys[0]
        return {
            "type": "call",
            "relationship_key": only_key,
            "confidence": 0.55,
            "needs_confirmation": False,
        }

    if available_relationship_keys:
        labels = [RELATIONSHIP_LABELS.get(key, key) for key in available_relationship_keys[:3]]
        return {
            "type": "call",
            "relationship_key": None,
            "confidence": 0.35,
            "needs_confirmation": True,
            "question": f"Bác muốn gọi {', '.join(labels)} ạ?",
        }

    return {
        "type": "call",
        "relationship_key": None,
        "confidence": 0.1,
        "needs_confirmation": True,
        "question": "Gia đình chưa cài đặt người nhận cuộc gọi khẩn cấp này.",
    }


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
