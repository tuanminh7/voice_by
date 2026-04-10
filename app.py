import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, Response, g, has_request_context, jsonify, render_template, request, session, stream_with_context, url_for
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
CALL_RING_TIMEOUT_SECONDS = int(os.getenv("CALL_RING_TIMEOUT_SECONDS", "30"))
CALL_MAX_TARGETS = int(os.getenv("CALL_MAX_TARGETS", "3"))
FIREBASE_SERVICE_ACCOUNT_JSON = (os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "") or "").strip()
ANDROID_APP_DOWNLOAD_URL = (os.getenv("ANDROID_APP_DOWNLOAD_URL", "") or "").strip()
ANDROID_APK_STATIC_PATH = BASE_DIR / "static" / "downloads" / "ut-nguyen-android-release.apk"
ELDER_MIN_AGE = int(os.getenv("ELDER_MIN_AGE", "60"))
EMOTION_ALERT_THRESHOLD = int(os.getenv("EMOTION_ALERT_THRESHOLD", "45"))
EMOTION_CRITICAL_THRESHOLD = int(os.getenv("EMOTION_CRITICAL_THRESHOLD", "25"))
EMOTION_ALERT_COOLDOWN_MINUTES = int(os.getenv("EMOTION_ALERT_COOLDOWN_MINUTES", "180"))
APP_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Ho_Chi_Minh"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=180)
app.json.ensure_ascii = False

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
API_KEYS_RAW = (os.getenv("GEMINI_API_KEYS", "") or "").strip()
GEMINI_API_KEY_POOL = tuple(
    dict.fromkeys(
        key.strip()
        for key in [*re.split(r"[\n,;]+", API_KEYS_RAW), API_KEY]
        if (key or "").strip()
    )
)
GEMINI_GENERATION_CONFIG = {
    "temperature": 0.35,
    "candidate_count": 1,
    "max_output_tokens": 384,
}
GEMINI_KEY_CURSOR = 0
GEMINI_KEY_CURSOR_LOCK = threading.Lock()
LIVE_WEATHER_CACHE_TTL_SECONDS = int(os.getenv("LIVE_WEATHER_CACHE_TTL_SECONDS", "300"))
LIVE_WEATHER_CACHE: dict[str, dict] = {}
WEATHER_GEOCODE_CACHE_TTL_SECONDS = int(os.getenv("WEATHER_GEOCODE_CACHE_TTL_SECONDS", "86400"))
WEATHER_GEOCODE_CACHE: dict[str, dict] = {}
WEATHER_LOCATIONS = {
    "ha noi": {
        "label": "Ha Noi",
        "latitude": 21.0285,
        "longitude": 105.8542,
        "timezone": "Asia/Ho_Chi_Minh",
    },
}
WEATHER_LOCATION_ALIASES = {
    "hanoi": "ha noi",
    "hn": "ha noi",
    "ha noi": "ha noi",
    "tphcm": "ho chi minh city",
    "tp hcm": "ho chi minh city",
    "hcm": "ho chi minh city",
    "sai gon": "ho chi minh city",
    "saigon": "ho chi minh city",
}

model = None
if genai and GEMINI_API_KEY_POOL:
    genai.configure(api_key=GEMINI_API_KEY_POOL[0])
    model = genai.GenerativeModel(MODEL_NAME)

knowledge = KNOWLEDGE_PATH.read_text(encoding="utf-8") if KNOWLEDGE_PATH.exists() else ""
knowledge_chunks = [line.strip() for line in knowledge.splitlines() if line.strip()]
chat_store = defaultdict(list)
pin_serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="device-pin-token")
firebase_push_app = None
firebase_push_init_attempted = False


def utcnow() -> datetime:
    return datetime.utcnow()


def now_in_app_timezone() -> datetime:
    return datetime.now(APP_TIMEZONE)


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


def _truncate_log_value(value, *, limit: int = 160):
    if value is None:
        return None
    if isinstance(value, str):
        compact = value.replace("\n", " ").replace("\r", " ").strip()
        return compact if len(compact) <= limit else f"{compact[:limit]}..."
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return [_truncate_log_value(item, limit=limit) for item in items[:6]]
    if isinstance(value, dict):
        return {
            str(key): _truncate_log_value(item, limit=limit)
            for key, item in list(value.items())[:12]
        }
    return _truncate_log_value(str(value), limit=limit)



def log_mobile_diag(event: str, *, level: str = "info", **fields) -> None:
    in_request = has_request_context()
    payload = {
        "event": event,
        "path": request.path if in_request else None,
        "method": request.method if in_request else None,
        "user_id": g.current_user["id"] if in_request and getattr(g, "current_user", None) else None,
        "device_id": g.current_device["device_id"] if in_request and getattr(g, "current_device", None) else None,
        "client_source": ((request.headers.get("X-Client-Source", "") or "").strip() or None) if in_request else None,
        "client_platform": ((request.headers.get("X-Client-Platform", "") or "").strip() or None) if in_request else None,
    }
    payload.update({key: _truncate_log_value(value) for key, value in fields.items() if value is not None})
    message = "MOBILE_DIAG " + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    getattr(app.logger, level, app.logger.info)(message)


def voice_json_response(action: str, message: str, **payload):
    call_payload = payload.get("call") if isinstance(payload.get("call"), dict) else None
    chat_message = payload.get("chat_message") if isinstance(payload.get("chat_message"), dict) else None
    intent_payload = payload.get("intent") if isinstance(payload.get("intent"), dict) else None
    log_mobile_diag(
        "voice_intent_result",
        action=action,
        message_preview=message[:160],
        question_preview=payload.get("question"),
        intent_type=intent_payload.get("type") if intent_payload else None,
        call_session_id=call_payload.get("call_session_id") if call_payload else None,
        chat_message_id=chat_message.get("id") if chat_message else None,
        emotion_logged=bool(payload.get("emotion_signal")),
        payload_keys=sorted(payload.keys()),
    )
    return jsonify({"action": action, "message": message, **payload})


def build_auth_diag_context() -> dict:
    current_user = getattr(g, "current_user", None)
    current_device = getattr(g, "current_device", None)
    return {
        "session_user_id": session.get("user_id"),
        "session_device_id": session.get("device_id"),
        "auth_user_id": current_user["id"] if current_user else None,
        "auth_device_id": current_device["device_id"] if current_device else None,
        "pin_token_present": bool((request.headers.get("X-PIN-Token", "") or "").strip()),
    }


def has_server_gemini_key_pool() -> bool:
    return bool(GEMINI_API_KEY_POOL)


def get_rotating_gemini_api_keys() -> list[str]:
    if not GEMINI_API_KEY_POOL:
        return []

    global GEMINI_KEY_CURSOR
    with GEMINI_KEY_CURSOR_LOCK:
        start_index = GEMINI_KEY_CURSOR % len(GEMINI_API_KEY_POOL)
        GEMINI_KEY_CURSOR = (GEMINI_KEY_CURSOR + 1) % len(GEMINI_API_KEY_POOL)

    return list(GEMINI_API_KEY_POOL[start_index:]) + list(GEMINI_API_KEY_POOL[:start_index])


def build_gemini_model(api_key: str):
    if genai is None or not api_key:
        return None

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        MODEL_NAME,
        generation_config=GEMINI_GENERATION_CONFIG,
    )


def is_retryable_gemini_error(error: Exception) -> bool:
    text = simplify_text(str(error))
    retryable_patterns = (
        "429",
        "rate limit",
        "quota",
        "resource exhausted",
        "deadline exceeded",
        "temporarily unavailable",
        "service unavailable",
        "internal",
        "timeout",
    )
    return any(pattern in text for pattern in retryable_patterns)


def get_gemini_unavailable_reason(user_row: sqlite3.Row | None) -> str:
    if genai is None:
        return "sdk_missing"
    if user_row is None:
        return "missing_authenticated_user"
    if not has_server_gemini_key_pool():
        return "missing_server_key_pool"
    return "unknown"


def build_gemini_diag_context(user_row: sqlite3.Row | None) -> dict:
    personal_key = get_personal_gemini_api_key(user_row)
    return {
        **build_auth_diag_context(),
        "gemini_sdk_available": genai is not None,
        "env_gemini_key_present": bool(API_KEY),
        "gemini_key_pool_size": len(GEMINI_API_KEY_POOL),
        "has_personal_gemini_key": bool(personal_key),
        "personal_gemini_key_preview": mask_secret(personal_key),
        "user_row_present": user_row is not None,
        "user_updated_at": user_row["updated_at"] if user_row else None,
    }


@app.before_request
def log_native_client_request() -> None:
    client_source = (request.headers.get("X-Client-Source", "") or "").strip()
    if not client_source or not request.path.startswith("/api/"):
        return

    app.logger.info(
        "API request tu client=%s platform=%s path=%s method=%s",
        client_source,
        (request.headers.get("X-Client-Platform", "") or "").strip(),
        request.path,
        request.method,
    )


@app.after_request
def log_mobile_api_errors(response):
    client_source = (request.headers.get("X-Client-Source", "") or "").strip()
    if not client_source or not request.path.startswith("/api/") or response.status_code < 400:
        return response

    payload = response.get_json(silent=True) or {}
    log_mobile_diag(
        "api_response_error",
        level="warning",
        status_code=response.status_code,
        error=payload.get("error"),
        error_code=payload.get("code"),
    )
    return response


def init_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        age INTEGER NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone_number TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        care_role_key TEXT NOT NULL DEFAULT '',
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

    CREATE TABLE IF NOT EXISTS emotion_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        source TEXT NOT NULL,
        message_text TEXT NOT NULL,
        emotion_label TEXT NOT NULL,
        emotion_score INTEGER NOT NULL,
        risk_level TEXT NOT NULL,
        alert_sent INTEGER NOT NULL DEFAULT 0,
        detected_keywords TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(family_group_id) REFERENCES family_groups(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS family_chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_group_id INTEGER NOT NULL,
        sender_user_id INTEGER NOT NULL,
        recipient_user_id INTEGER NOT NULL,
        message_text TEXT NOT NULL,
        read_at TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(family_group_id) REFERENCES family_groups(id) ON DELETE CASCADE,
        FOREIGN KEY(sender_user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(recipient_user_id) REFERENCES users(id) ON DELETE CASCADE
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
    if "care_role_key" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN care_role_key TEXT NOT NULL DEFAULT ''")

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
    global firebase_push_app, firebase_push_init_attempted

    if firebase_push_app is not None:
        return firebase_push_app
    if firebase_push_init_attempted:
        return None

    firebase_push_init_attempted = True

    if firebase_admin is None or firebase_credentials is None or firebase_messaging is None:
        app.logger.warning("Firebase Admin SDK chưa sẵn sàng, push notification sẽ bị tắt.")
        return None
    if not FIREBASE_SERVICE_ACCOUNT_JSON:
        app.logger.warning("Thiếu FIREBASE_SERVICE_ACCOUNT_JSON, push notification sẽ bị tắt.")
        return None

    try:
        service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        credential = firebase_credentials.Certificate(service_account_info)
        firebase_push_app = firebase_admin.initialize_app(credential, name="push-app")
    except Exception:
        app.logger.exception("Khoi tao Firebase push app that bai.")
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
            log_mobile_diag("auth_required_blocked", level="warning")
            return json_error("Bạn cần đăng nhập trước.", 401, "auth_required")
        return view_func(*args, **kwargs)

    return wrapped


def pin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if g.current_user is None or g.current_device is None:
            log_mobile_diag("auth_required_blocked", level="warning")
            return json_error("Bạn cần đăng nhập trước.", 401, "auth_required")

        if not g.current_device["pin_enabled"]:
            log_mobile_diag("pin_not_configured", level="warning")
            return json_error("Thiết bị này chưa thiết lập PIN 4 số.", 403, "pin_not_configured")

        pin_token = request.headers.get("X-PIN-Token", "").strip()
        if not validate_pin_token(pin_token, g.current_user["id"], g.current_device["device_id"]):
            log_mobile_diag("pin_required_blocked", level="warning", pin_token_present=bool(pin_token))
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
    family_payload = build_family_payload(g.current_user["id"])
    log_mobile_diag(
        "me_profile_state",
        family_group_id=family_payload["family_group_id"] if family_payload else None,
        **build_gemini_diag_context(g.current_user),
    )
    return jsonify(
        {
            "user": serialize_user(g.current_user),
            "family": family_payload,
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
    raw_care_role_key = payload.get("care_role_key")
    care_role_key = normalize_relationship_key(raw_care_role_key or "")

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
    if raw_care_role_key is not None and care_role_key and care_role_key not in RELATIONSHIP_LABELS:
        return json_error("Vai vế gia đình chưa hợp lệ.", 400, "invalid_care_role")

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
        SET full_name = ?, age = ?, email = ?, phone_number = ?, care_role_key = ?, updated_at = ?
        WHERE id = ?
        """,
        (full_name, age, email, phone_number, care_role_key, now, g.current_user["id"]),
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
        return json_error("Ban can nhap Gemini API key truoc khi luu.", 400, "missing_gemini_api_key")

    get_db().execute(
        "UPDATE users SET gemini_api_key = ?, updated_at = ? WHERE id = ?",
        (api_key, utcnow_iso(), g.current_user["id"]),
    )
    get_db().commit()
    g.current_user = fetch_user_by_id(g.current_user["id"])
    log_mobile_diag(
        "gemini_key_saved",
        submitted_key_length=len(api_key),
        **build_gemini_diag_context(g.current_user),
    )
    return jsonify({"message": "Da luu Gemini API key ca nhan.", "user": serialize_user(g.current_user)})


@app.route("/api/me/gemini-key", methods=["DELETE"])
@pin_required
def clear_gemini_key():
    get_db().execute(
        "UPDATE users SET gemini_api_key = '', updated_at = ? WHERE id = ?",
        (utcnow_iso(), g.current_user["id"]),
    )
    get_db().commit()
    g.current_user = fetch_user_by_id(g.current_user["id"])
    log_mobile_diag("gemini_key_cleared", **build_gemini_diag_context(g.current_user))
    return jsonify({"message": "Da xoa Gemini API key ca nhan.", "user": serialize_user(g.current_user)})


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
        return json_error("Thiáº¿u push token cá»§a thiáº¿t bá»‹.", 400, "missing_push_token")
    if platform not in {"android", "ios"}:
        return json_error("Platform chá»‰ há»— trá»£ android hoáº·c ios.", 400, "invalid_platform")

    now = utcnow_iso()
    db = get_db()
    db.execute(
        """
        UPDATE device_push_tokens
        SET is_active = 0, updated_at = ?
        WHERE is_active = 1
          AND (device_id = ? OR push_token = ?)
          AND NOT (user_id = ? AND device_id = ? AND push_token = ?)
        """,
        (now, g.current_device["device_id"], push_token, g.current_user["id"], g.current_device["device_id"], push_token),
    )

    existing = fetch_one(
        """
        SELECT id FROM device_push_tokens
        WHERE user_id = ? AND device_id = ? AND push_token = ?
        """,
        (g.current_user["id"], g.current_device["device_id"], push_token),
    )

    if existing:
        db.execute(
            """
            UPDATE device_push_tokens
            SET is_active = 1, platform = ?, updated_at = ?
            WHERE id = ?
            """,
            (platform, now, existing["id"]),
        )
    else:
        db.execute(
            """
            INSERT INTO device_push_tokens (user_id, device_id, platform, push_token, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (g.current_user["id"], g.current_device["device_id"], platform, push_token, now, now),
        )

    db.commit()
    log_mobile_diag("push_token_registered", token_suffix=push_token[-12:], platform=platform)
    return jsonify({"message": "ÄÃ£ lÆ°u push token cho thiáº¿t bá»‹.", "provider": CALL_PROVIDER})


@app.route("/api/device-push-tokens/unregister", methods=["POST"])
@pin_required
def unregister_device_push_token():
    payload = request.get_json(silent=True) or {}
    push_token = (payload.get("push_token") or "").strip()
    now = utcnow_iso()

    if push_token:
        get_db().execute(
            """
            UPDATE device_push_tokens
            SET is_active = 0, updated_at = ?
            WHERE user_id = ? AND device_id = ? AND push_token = ?
            """,
            (now, g.current_user["id"], g.current_device["device_id"], push_token),
        )
    else:
        get_db().execute(
            """
            UPDATE device_push_tokens
            SET is_active = 0, updated_at = ?
            WHERE user_id = ? AND device_id = ?
            """,
            (now, g.current_user["id"], g.current_device["device_id"]),
        )

    get_db().commit()
    log_mobile_diag("push_token_unregistered", token_suffix=push_token[-12:] if push_token else None, cleared_all=not bool(push_token))
    return jsonify({"message": "ÄÃ£ gá»¡ push token cho thiáº¿t bá»‹.", "provider": CALL_PROVIDER})


@app.route("/api/emotions/dashboard", methods=["GET"])
@pin_required
def get_emotion_dashboard():
    membership = get_active_family_membership(g.current_user["id"])
    if not membership:
        return json_error("Bạn chưa thuộc nhóm gia đình nào.", 404, "family_not_found")
    if membership["role"] != "admin":
        return json_error("Chỉ admin mới được xem bảng giám sát cảm xúc.", 403, "not_family_admin")

    return jsonify({"dashboard": build_emotion_dashboard_payload(g.current_user["id"])})


@app.route("/api/family-chat/threads", methods=["GET"])
@pin_required
def get_family_chat_threads():
    return jsonify({"threads": list_family_chat_threads(g.current_user["id"])})


@app.route("/api/family-chat/messages", methods=["GET"])
@pin_required
def get_family_chat_messages():
    partner_user_id_raw = (request.args.get("partner_user_id") or "").strip()
    if not partner_user_id_raw.isdigit():
        return json_error("Thiếu người nhận hội thoại.", 400, "invalid_partner_user_id")

    partner_user_id = int(partner_user_id_raw)
    rows = list_family_chat_messages(g.current_user["id"], partner_user_id)
    if rows is None:
        return json_error("Người này không thuộc cùng gia đình.", 404, "chat_partner_not_found")
    return jsonify({"messages": rows, "partner_user_id": partner_user_id})


@app.route("/api/family-chat/messages", methods=["POST"])
@pin_required
def send_family_chat_message():
    payload = require_json()
    recipient_user_id_raw = str(payload.get("recipient_user_id") or "").strip()
    message_text = (payload.get("message_text") or "").strip()

    if not recipient_user_id_raw.isdigit():
        return json_error("Thiếu người nhận tin nhắn.", 400, "invalid_recipient_user_id")
    if not message_text:
        return json_error("Tin nhắn không được để trống.", 400, "invalid_message_text")

    message_payload = create_family_chat_message(
        g.current_user["id"],
        int(recipient_user_id_raw),
        message_text,
    )
    if message_payload is None:
        return json_error("Không thể nhắn tin cho người này trong gia đình.", 404, "chat_partner_not_found")

    log_mobile_diag("family_chat_sent", recipient_user_id=int(recipient_user_id_raw), message_id=message_payload["id"], message_preview=message_text[:120])
    return jsonify({"message": "Đã gửi tin nhắn.", "chat_message": message_payload})


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


def get_pending_voice_call_intent() -> dict | None:
    payload = session.get(PENDING_VOICE_CALL_SESSION_KEY)
    if not isinstance(payload, dict):
        return None
    return payload


def clear_pending_voice_call_intent() -> None:
    session.pop(PENDING_VOICE_CALL_SESSION_KEY, None)
    session.modified = True


def save_pending_voice_call_intent(
    *,
    relationship_key: str,
    relative_user_id: int | None,
    transcript_text: str,
    target_label: str,
) -> None:
    session[PENDING_VOICE_CALL_SESSION_KEY] = {
        "relationship_key": relationship_key,
        "relative_user_id": relative_user_id,
        "transcript_text": transcript_text,
        "target_label": target_label,
        "created_at": utcnow_iso(),
    }
    session.modified = True


def is_voice_confirmation_reply(text: str) -> bool:
    simplified = simplify_text(text)
    confirmation_phrases = (
        "xac nhan",
        "dong y",
        "duoc",
        "duoc roi",
        "ok",
        "ok roi",
        "goi di",
        "goi ngay",
        "dung roi",
        "phai",
    )
    return any(
        simplified == phrase
        or simplified.startswith(f"{phrase} ")
        or simplified.endswith(f" {phrase}")
        for phrase in confirmation_phrases
    )


def is_voice_cancel_reply(text: str) -> bool:
    simplified = simplify_text(text)
    cancel_phrases = (
        "huy",
        "huy bo",
        "thoi",
        "dung lai",
        "khong goi",
        "khong can",
        "khong dong y",
        "bo qua",
    )
    return any(
        simplified == phrase
        or simplified.startswith(f"{phrase} ")
        or simplified.endswith(f" {phrase}")
        for phrase in cancel_phrases
    )


def describe_call_target(
    relationship_key: str,
    relationship_rows: list[sqlite3.Row],
    *,
    relative_user_id: int | None = None,
) -> str:
    relationship_label = RELATIONSHIP_LABELS.get(relationship_key, relationship_key)
    if relative_user_id is None:
        return relationship_label

    for row in relationship_rows:
        if row["relationship_key"] != relationship_key or row["relative_user_id"] != relative_user_id:
            continue
        full_name = (row["relative_full_name"] or "").strip()
        if full_name:
            return f"{full_name} ({relationship_label})"
        break

    return relationship_label


def build_voice_confirmation_message(user_row: sqlite3.Row, target_label: str) -> str:
    user_title = get_user_voice_title(user_row)
    return f"{user_title} muốn gọi {target_label}. Nếu đúng, {get_user_voice_reference(user_row)} hãy nói 'xác nhận'."


@app.route("/api/calls/voice-intent", methods=["POST"])
@pin_required
def create_call_from_voice_intent():
    payload = require_json()
    transcript_text = (payload.get("transcript_text") or "").strip()
    raw_realtime_call_ready = payload.get("realtime_call_ready")
    if raw_realtime_call_ready is None:
        realtime_call_ready = True
    elif isinstance(raw_realtime_call_ready, str):
        realtime_call_ready = raw_realtime_call_ready.strip().lower() in {"1", "true", "yes", "on"}
    else:
        realtime_call_ready = bool(raw_realtime_call_ready)
    if not transcript_text:
        return json_error("Thiếu nội dung giọng nói đã nhận dạng.", 400, "missing_transcript")

    relationship_rows = list_call_relationship_rows(g.current_user["id"])
    pending_intent = get_pending_voice_call_intent()
    family_chat_intent = detect_family_chat_intent(transcript_text, g.current_user["id"])
    intent = detect_call_intent(transcript_text, relationship_rows)
    log_mobile_diag(
        "voice_intent_received",
        transcript_preview=transcript_text[:120],
        realtime_call_ready=realtime_call_ready,
        pending_intent_present=bool(pending_intent),
        call_intent_type=intent.get("type"),
        family_chat_intent_type=family_chat_intent.get("type"),
        **build_gemini_diag_context(g.current_user),
    )

    if pending_intent and (intent.get("type") == "call" or family_chat_intent.get("type") == "family_chat"):
        clear_pending_voice_call_intent()
        pending_intent = None

    if family_chat_intent.get("type") == "family_chat":
        if family_chat_intent.get("needs_confirmation"):
            return voice_json_response(
                "chat",
                family_chat_intent.get("question")
                or f"{get_user_voice_title(g.current_user)} noi lai giup minh nguoi nhan nhe.",
            )

        message_payload = create_family_chat_message(
            g.current_user["id"],
            family_chat_intent["recipient_user_id"],
            family_chat_intent["message_text"],
        )
        if not message_payload:
            return json_error("Không thể nhắn tin cho người này trong gia đình.", 404, "chat_partner_not_found")

        ack_message = (
            f"{get_assistant_self_reference(g.current_user).capitalize()} da nhan giup "
            f"{get_user_voice_reference(g.current_user)} cho {family_chat_intent['target_label']} roi nhe: "
            f"\"{family_chat_intent['message_text']}\""
        )
        remember_turn(get_history(), transcript_text, ack_message)
        return voice_json_response(
            "chat",
            ack_message,
            chat_message=message_payload,
        )

    if not realtime_call_ready and intent.get("type") == "call":
        clear_pending_voice_call_intent()
        log_mobile_diag(
            "voice_intent_result",
            action="chat",
            outcome="realtime_not_ready",
            transcript_preview=transcript_text[:120],
        )
        return jsonify(
            {
                "action": "chat",
                "message": (
                    "Bản app hiện tại chưa có cấu hình gọi thoại realtime nên chưa thể gọi hoặc nghe máy. "
                    "Bạn hãy build lại APK với ZEGO_APP_ID và ZEGO_APP_SIGN rồi thử lại nhé."
                ),
            }
        )

    if pending_intent and is_voice_confirmation_reply(transcript_text):
        session_row = create_call_session_for_relationship(
            caller_user_id=g.current_user["id"],
            relationship_key=pending_intent["relationship_key"],
            relative_user_id=pending_intent.get("relative_user_id"),
            transcript_text=pending_intent.get("transcript_text") or transcript_text,
            trigger_source="voice",
        )
        clear_pending_voice_call_intent()
        if not session_row:
            return json_error("Gia đình chưa cài đặt người nhận cho lệnh gọi này.", 404, "call_target_not_found")

        log_mobile_diag(
            "voice_intent_result",
            action="calling",
            outcome="call_created",
            transcript_preview=transcript_text[:120],
            call_session_id=session_row["id"],
        )
        return jsonify(
            {
                "action": "calling",
                "message": f"Đang gọi {pending_intent['target_label']} cho {get_user_voice_title(g.current_user).lower()}.",
                "call": build_call_session_payload(session_row["id"]),
            }
        )

    if pending_intent and is_voice_cancel_reply(transcript_text):
        clear_pending_voice_call_intent()
        log_mobile_diag(
            "voice_intent_result",
            action="chat",
            outcome="call_cancelled",
            transcript_preview=transcript_text[:120],
        )
        return jsonify(
            {
                "action": "chat",
                "message": (
                    f"Đã hủy yêu cầu gọi. Mình tiếp tục trò chuyện với "
                    f"{get_user_voice_reference(g.current_user)} nhé."
                ),
            }
        )

    if intent.get("type") != "call":
        if pending_intent:
            reminder_message = build_voice_confirmation_message(
                g.current_user,
                pending_intent["target_label"],
            )
            log_mobile_diag(
                "voice_intent_result",
                action="confirm",
                outcome="pending_call_reminder",
                transcript_preview=transcript_text[:120],
                question_preview=reminder_message,
            )
            return jsonify(
                {
                    "action": "confirm",
                    "message": reminder_message,
                    "question": reminder_message,
                }
            )

        reply = generate_reply(transcript_text, get_history())
        emotion_signal = maybe_log_emotion_signal(
            g.current_user,
            transcript_text,
            source="assistant_voice",
        )
        log_mobile_diag(
            "voice_intent_result",
            action="chat",
            outcome="assistant_reply",
            transcript_preview=transcript_text[:120],
            reply_preview=reply[:160],
            emotion_logged=bool(emotion_signal),
        )
        return jsonify(
            {
                "action": "chat",
                "message": reply,
                "emotion_signal": emotion_signal,
            }
        )

    if intent.get("needs_confirmation") or not intent.get("relationship_key"):
        clear_pending_voice_call_intent()
        question = intent.get("question") or f"{get_user_voice_title(g.current_user)} muốn gọi ai ạ?"
        log_mobile_diag(
            "voice_intent_result",
            action="confirm",
            outcome="call_needs_confirmation",
            transcript_preview=transcript_text[:120],
            question_preview=question,
            intent_type=intent.get("type"),
        )
        return jsonify(
            {
                "action": "confirm",
                "message": question,
                "question": question,
                "intent": intent,
            }
        )

    target_label = describe_call_target(
        intent["relationship_key"],
        relationship_rows,
        relative_user_id=intent.get("relative_user_id"),
    )
    save_pending_voice_call_intent(
        relationship_key=intent["relationship_key"],
        relative_user_id=intent.get("relative_user_id"),
        transcript_text=transcript_text,
        target_label=target_label,
    )
    confirmation_message = build_voice_confirmation_message(
        g.current_user,
        target_label,
    )
    log_mobile_diag(
        "voice_intent_result",
        action="confirm",
        outcome="call_confirmation_ready",
        transcript_preview=transcript_text[:120],
        question_preview=confirmation_message,
        relationship_key=intent.get("relationship_key"),
        relative_user_id=intent.get("relative_user_id"),
    )
    return jsonify(
        {
            "action": "confirm",
            "message": confirmation_message,
            "question": confirmation_message,
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

    log_mobile_diag("manual_call_created", relationship_key=relationship_key, call_session_id=session_row["id"])
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
    log_mobile_diag("call_accepted", call_session_id=call_session_id, target_user_id=g.current_user["id"])
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
    log_mobile_diag("call_declined", call_session_id=call_session_id, target_user_id=g.current_user["id"])
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
    log_mobile_diag("call_ended", call_session_id=call_session_id, actor_user_id=g.current_user["id"], previous_status=session_row["status"])
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
    emotion_signal = maybe_log_emotion_signal(g.current_user, user_text, source="assistant_chat")
    return jsonify({"reply": reply, "emotion_signal": emotion_signal})


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
        realtime_reply = build_realtime_reply(user_text, g.current_user)
        if realtime_reply is not None:
            remember_turn(history, user_text, realtime_reply)
            yield realtime_reply
            return

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
        maybe_log_emotion_signal(g.current_user, user_text, source="assistant_chat")

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


def format_vietnamese_weekday(value: datetime) -> str:
    return {
        0: "Thu hai",
        1: "Thu ba",
        2: "Thu tu",
        3: "Thu nam",
        4: "Thu sau",
        5: "Thu bay",
        6: "Chu nhat",
    }[value.weekday()]


def format_live_datetime(value: datetime) -> str:
    return (
        f"{value.strftime('%H:%M')} ngay {value.strftime('%d/%m/%Y')} "
        f"({format_vietnamese_weekday(value)})"
    )


def is_current_time_question(text: str) -> bool:
    simplified = simplify_text(text)
    patterns = (
        "may gio",
        "bao nhieu gio",
        "gio hien tai",
        "bay gio la may gio",
        "hom nay may gio",
    )
    return any(pattern in simplified for pattern in patterns)


def is_current_date_question(text: str) -> bool:
    simplified = simplify_text(text)
    patterns = (
        "hom nay la ngay may",
        "hom nay thu may",
        "ngay hom nay",
        "ngay may",
        "thu may",
    )
    return any(pattern in simplified for pattern in patterns)


def is_weather_question(text: str) -> bool:
    simplified = simplify_text(text)
    weather_patterns = (
        "thoi tiet",
        "du bao",
        "nhiet do",
        "bao nhieu do",
        "do c",
        "do celsius",
        "mua hay nang",
        "co mua khong",
        "dang mua khong",
        "co nang khong",
    )
    return any(pattern in simplified for pattern in weather_patterns)


def normalize_weather_location_query(value: str) -> str:
    simplified = simplify_text(value)
    replacements = (
        "noi cho toi biet",
        "noi cho minh biet",
        "cho toi biet",
        "cho minh biet",
        "noi giup toi",
        "noi giup minh",
        "doc giup toi",
        "doc giup minh",
        "du bao thoi tiet",
        "thoi tiet hien tai",
        "thoi tiet",
        "nhiet do",
        "bao nhieu do celsius",
        "bao nhieu do c",
        "bao nhieu do",
        "do celsius",
        "do c",
        "dang mua hay nang",
        "mua hay nang",
        "co mua khong",
        "dang mua khong",
        "co nang khong",
        "hien tai",
        "luc nay",
        "bay gio",
        "hom nay",
        "ngay mai",
        "ra sao",
        "the nao",
        "cho toi biet",
        "giup toi",
        "xem giup",
        "xem dum",
        "xem ho",
        "xem",
        "voi",
    )
    cleaned = simplified
    for phrase in replacements:
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned)

    for prefix in ("o ", "tai "):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    if cleaned.startswith("cua "):
        cleaned = cleaned[len("cua "):].strip()

    cleaned = re.sub(r"[^a-z0-9 ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return WEATHER_LOCATION_ALIASES.get(cleaned, cleaned)


def extract_weather_location_query(text: str) -> str | None:
    simplified = simplify_text(text)
    if not is_weather_question(simplified):
        return None

    explicit_weather_matches = list(
        re.finditer(
            r"\b(?:thoi tiet|du bao thoi tiet|nhiet do)(?:\s+(?:cua|o|tai))?\s+([a-z0-9 ]+)",
            simplified,
        )
    )
    for match in reversed(explicit_weather_matches):
        candidate = normalize_weather_location_query(match.group(1))
        if candidate:
            return candidate

    explicit_matches = list(re.finditer(r"\b(?:o|tai)\s+([a-z0-9 ]+)", simplified))
    for match in reversed(explicit_matches):
        candidate = normalize_weather_location_query(match.group(1))
        if candidate:
            return candidate

    candidate = normalize_weather_location_query(simplified)
    return candidate or None


def resolve_weather_location(location_query: str) -> dict | None:
    normalized_query = normalize_weather_location_query(location_query)
    if not normalized_query:
        return None

    static_location = WEATHER_LOCATIONS.get(normalized_query)
    if static_location:
        return static_location

    now_ts = now_in_app_timezone().timestamp()
    cached = WEATHER_GEOCODE_CACHE.get(normalized_query)
    if cached and now_ts - cached.get("fetched_at", 0) < WEATHER_GEOCODE_CACHE_TTL_SECONDS:
        return cached["payload"]

    params = urllib_parse.urlencode(
        {
            "name": normalized_query,
            "count": 1,
            "language": "vi",
            "format": "json",
        }
    )
    url = f"https://geocoding-api.open-meteo.com/v1/search?{params}"
    try:
        with urllib_request.urlopen(url, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, urllib_error.URLError, urllib_error.HTTPError, json.JSONDecodeError) as error:
        log_mobile_diag(
            "weather_geocode_failed",
            level="warning",
            location_query=normalized_query,
            error=str(error),
        )
        return None

    rows = payload.get("results") or []
    if not rows:
        log_mobile_diag(
            "weather_geocode_not_found",
            level="warning",
            location_query=normalized_query,
        )
        return None

    row = rows[0]
    parts = [row.get("name"), row.get("admin1"), row.get("country")]
    label_parts = []
    for part in parts:
        if part and part not in label_parts:
            label_parts.append(part)

    location_payload = {
        "label": ", ".join(label_parts) or normalized_query.title(),
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "timezone": row.get("timezone") or "auto",
    }
    WEATHER_GEOCODE_CACHE[normalized_query] = {
        "fetched_at": now_ts,
        "payload": location_payload,
    }
    log_mobile_diag(
        "weather_geocode_succeeded",
        location_query=normalized_query,
        weather_label=location_payload["label"],
    )
    return location_payload


def describe_weather_condition(
    weather_code: int | None,
    *,
    is_day: int | None = None,
    precipitation: float | None = None,
    rain: float | None = None,
    showers: float | None = None,
) -> str:
    wet_amount = max(
        float(precipitation or 0),
        float(rain or 0),
        float(showers or 0),
    )
    if wet_amount >= 0.1:
        return "dang mua"
    if weather_code is None:
        return "thoi tiet kha on dinh"

    if weather_code == 0:
        return "dang nang" if is_day else "troi quang"
    if weather_code in {1, 2}:
        return "troi it may"
    if weather_code == 3:
        return "troi nhieu may"
    if weather_code in {45, 48}:
        return "co suong mu"
    if weather_code in {51, 53, 55, 56, 57}:
        return "co mua phun"
    if weather_code in {61, 63, 65, 66, 67}:
        return "dang mua"
    if weather_code in {71, 73, 75, 77, 85, 86}:
        return "co tuyet"
    if weather_code in {80, 81, 82}:
        return "co mua rao"
    if weather_code in {95, 96, 99}:
        return "co giong"
    return "thoi tiet dang thay doi"


def get_live_weather_snapshot(location_query: str) -> dict | None:
    location = resolve_weather_location(location_query)
    if not location:
        return None

    now_ts = now_in_app_timezone().timestamp()
    cache_key = simplify_text(location_query)
    cached = LIVE_WEATHER_CACHE.get(cache_key)
    if cached and now_ts - cached.get("fetched_at", 0) < LIVE_WEATHER_CACHE_TTL_SECONDS:
        return cached["payload"]

    query = urllib_parse.urlencode(
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": (
                "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,is_day,precipitation,rain,showers,cloud_cover,wind_speed_10m"
            ),
            "timezone": location.get("timezone") or "auto",
            "forecast_days": 1,
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{query}"

    try:
        with urllib_request.urlopen(url, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, urllib_error.URLError, urllib_error.HTTPError, json.JSONDecodeError) as error:
        log_mobile_diag(
            "weather_lookup_failed",
            level="warning",
            location_query=location_query,
            weather_label=location.get("label"),
            error=str(error),
        )
        return None

    current = payload.get("current") or {}
    temperature = current.get("temperature_2m")
    apparent_temperature = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    observed_at = current.get("time")
    weather_code = current.get("weather_code")
    is_day = current.get("is_day")
    precipitation = current.get("precipitation")
    rain = current.get("rain")
    showers = current.get("showers")
    cloud_cover = current.get("cloud_cover")
    wind_speed = current.get("wind_speed_10m")
    if temperature is None:
        return None

    weather_payload = {
        "label": location["label"],
        "temperature_c": float(temperature),
        "apparent_temperature_c": float(apparent_temperature) if apparent_temperature is not None else None,
        "humidity_percent": int(humidity) if humidity is not None else None,
        "observed_at": observed_at or "",
        "weather_code": int(weather_code) if weather_code is not None else None,
        "is_day": int(is_day) if is_day is not None else None,
        "precipitation_mm": float(precipitation) if precipitation is not None else None,
        "rain_mm": float(rain) if rain is not None else None,
        "showers_mm": float(showers) if showers is not None else None,
        "cloud_cover_percent": int(cloud_cover) if cloud_cover is not None else None,
        "wind_speed_kmh": float(wind_speed) if wind_speed is not None else None,
    }
    weather_payload["condition"] = describe_weather_condition(
        weather_payload["weather_code"],
        is_day=weather_payload["is_day"],
        precipitation=weather_payload["precipitation_mm"],
        rain=weather_payload["rain_mm"],
        showers=weather_payload["showers_mm"],
    )
    LIVE_WEATHER_CACHE[cache_key] = {
        "fetched_at": now_ts,
        "payload": weather_payload,
    }
    log_mobile_diag(
        "weather_lookup_succeeded",
        location_query=location_query,
        weather_label=weather_payload["label"],
        condition=weather_payload["condition"],
        temperature_c=weather_payload["temperature_c"],
        precipitation_mm=weather_payload["precipitation_mm"],
    )
    return weather_payload


def build_live_context(question: str) -> str:
    now_value = now_in_app_timezone()
    lines = [
        f"- Thời gian hiện tại tại Việt Nam: {format_live_datetime(now_value)}.",
    ]

    weather_location_query = extract_weather_location_query(question)
    if weather_location_query:
        weather = get_live_weather_snapshot(weather_location_query)
        if weather:
            weather_line = (
                f"- Thời tiết trực tiếp tại {weather['label']}: "
                f"{weather['condition']}, {weather['temperature_c']:.1f} độ C"
            )
            if weather.get("apparent_temperature_c") is not None:
                weather_line += f", cảm nhận {weather['apparent_temperature_c']:.1f} độ C"
            if weather.get("humidity_percent") is not None:
                weather_line += f", độ ẩm {weather['humidity_percent']}%"
            if weather.get("wind_speed_kmh") is not None:
                weather_line += f", gió {weather['wind_speed_kmh']:.1f} km/h"
            if weather.get("observed_at"):
                weather_line += f", cập nhật lúc {weather['observed_at']}"
            weather_line += "."
            lines.append(weather_line)
        else:
            lines.append("- Chưa lấy được dữ liệu thời tiết trực tiếp lúc này.")

    return "\n".join(lines)


def build_realtime_reply(question: str, user_row: sqlite3.Row | None) -> str | None:
    user_title = get_user_voice_title(user_row)
    user_reference = user_title.lower()
    now_value = now_in_app_timezone()

    if is_current_time_question(question) or is_current_date_question(question):
        return (
            f"Dạ {user_reference}, bây giờ là {now_value.strftime('%H:%M')}, "
            f"{format_vietnamese_weekday(now_value)}, ngày {now_value.strftime('%d/%m/%Y')}."
        )

    weather_location_query = extract_weather_location_query(question)
    if weather_location_query:
        weather = get_live_weather_snapshot(weather_location_query)
        if weather:
            reply = (
                f"Dạ {user_reference}, lúc này ở {weather['label']} {weather['condition']}, "
                f"nhiệt độ khoảng {weather['temperature_c']:.1f} độ C"
            )
            if weather.get("apparent_temperature_c") is not None:
                reply += f", cảm nhận {weather['apparent_temperature_c']:.1f} độ C"
            if weather.get("humidity_percent") is not None:
                reply += f", độ ẩm {weather['humidity_percent']}%"
            if weather.get("wind_speed_kmh") is not None:
                reply += f", gió {weather['wind_speed_kmh']:.1f} km/h"
            reply += "."
            return reply
        return (
            f"Dạ {user_reference}, hiện mình chưa lấy được thời tiết trực tiếp "
            f"cho địa điểm {weather_location_query} lúc này."
        )

    return None


def build_prompt(question: str, history: list[str]) -> str:
    user_title = get_user_voice_title(g.current_user)
    assistant_self = get_assistant_self_reference(g.current_user)
    history_text = "\n".join(history[-6:]) or "Chưa có lịch sử hội thoại."
    context = search_context(question) or knowledge or "Không có dữ liệu tham khảo bổ sung."
    live_context = build_live_context(question)

    return f"""
Bạn là một trợ lý thân thiện, ấm áp và kiên nhẫn cho gia đình.

Nguyên tắc trả lời:
- Dùng tiếng Việt tự nhiên, đầy đủ dấu, dễ hiểu, câu ngắn gọn.
- Có thể mở đầu bằng các cụm nhẹ nhàng như "Dạ", "À", "Vâng".
- Nếu câu hỏi chưa rõ, hỏi lại ngắn gọn.
- Không tự ý đưa ra thông tin y tế nguy hiểm như một chẩn đoán chính xác.
- Ưu tiên dùng thông tin trong phần tham khảo khi có liên quan.
- Xưng hô với người dùng là "{user_title.lower()}". Nếu cần tự xưng, hãy dùng "{assistant_self}".
- Tuyệt đối không gọi người dùng là "bà", "bác" hoặc "cháu" nếu vai trò đang lưu không phải như vậy.
- Nếu người dùng hỏi thông tin thay đổi theo thời gian như giờ hiện tại, ngày hiện tại, thời tiết hoặc nhiệt độ, hãy ưu tiên dùng Live context.
- Khi cần trả lời chi tiết, hãy chia ý rõ ràng và đi thẳng vào câu hỏi.

Live context:
{live_context}

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
    del user_row
    if genai is None:
        return None

    api_keys = get_rotating_gemini_api_keys()
    if not api_keys:
        return None

    return build_gemini_model(api_keys[0])


def build_unavailable_message(user_row: sqlite3.Row | None = None) -> str:
    log_mobile_diag(
        "gemini_unavailable",
        level="warning",
        reason=get_gemini_unavailable_reason(user_row),
        **build_gemini_diag_context(user_row),
    )
    if genai is None:
        return (
            "Dạ, ứng dụng chưa cài thư viện google-generativeai nên tôi chưa thể kết nối Gemini. "
            "Bạn hãy cài dependencies rồi thử lại nhé."
        )

    if not has_server_gemini_key_pool():
        return (
            "Dạ, hệ thống chưa được cấu hình Gemini API key trên server nên tôi chưa thể trả lời AI."
        )

    return "Dạ, hiện tôi chưa sẵn sàng để phản hồi. Bạn thử lại giúp tôi nhé."


def generate_reply(question: str, history: list[str]) -> str:
    realtime_reply = build_realtime_reply(question, g.current_user)
    if realtime_reply is not None:
        log_mobile_diag(
            "assistant_reply_generated",
            source="realtime",
            question_preview=question[:120],
            reply_preview=realtime_reply[:160],
        )
        remember_turn(history, question, realtime_reply)
        return realtime_reply

    api_keys = get_rotating_gemini_api_keys()
    if not api_keys:
        log_mobile_diag(
            "gemini_reply_fallback",
            level="warning",
            question_preview=question[:120],
            history_size=len(history),
            reason=get_gemini_unavailable_reason(g.current_user),
            **build_gemini_diag_context(g.current_user),
        )
        reply = build_unavailable_message(g.current_user)
        remember_turn(history, question, reply)
        return reply

    prompt = build_prompt(question, history)
    last_error: Exception | None = None
    for api_key in api_keys:
        current_model = build_gemini_model(api_key)
        if current_model is None:
            continue
        try:
            response = current_model.generate_content(prompt)
            reply = (getattr(response, "text", "") or "").strip()
            if reply:
                log_mobile_diag(
                    "assistant_reply_generated",
                    source="gemini",
                    question_preview=question[:120],
                    reply_preview=reply[:160],
                )
                remember_turn(history, question, reply)
                return reply
        except Exception as error:
            last_error = error
            if not is_retryable_gemini_error(error):
                break
            continue

    log_mobile_diag(
        "gemini_reply_failed",
        level="error",
        question_preview=question[:120],
        history_size=len(history),
        error=str(last_error) if last_error is not None else "empty_reply",
        attempted_key_count=len(api_keys),
        **build_gemini_diag_context(g.current_user),
    )
    reply = (
        "Dạ, trong lúc kết nối trợ lý đã có lỗi xảy ra. "
        "Bạn thử lại sau ít phút giúp mình nhé."
    )
    if last_error is None:
        reply = "Dạ, tôi chưa tạo được câu trả lời phù hợp. Bạn thử hỏi lại một chút nhé."

    remember_turn(history, question, reply)
    return reply


def get_android_download_url() -> str | None:
    if ANDROID_APP_DOWNLOAD_URL:
        return ANDROID_APP_DOWNLOAD_URL
    if ANDROID_APK_STATIC_PATH.exists():
        return url_for("static", filename="downloads/ut-nguyen-android-release.apk")
    return None


@app.route("/")
def index():
    android_download_url = get_android_download_url()
    return render_template(
        "index.html",
        model_name=MODEL_NAME,
        android_download_url=android_download_url,
        android_download_ready=bool(android_download_url),
    )


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
    care_role_key = normalize_relationship_key(payload.get("care_role_key") or "")
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
    if care_role_key and care_role_key not in RELATIONSHIP_LABELS:
        return json_error("Vai vế gia đình chưa hợp lệ.", 400, "invalid_care_role")
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
        care_role_key=care_role_key,
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
    care_role_key: str = "",
) -> sqlite3.Row:
    now = utcnow_iso()
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO users (full_name, age, email, phone_number, password_hash, care_role_key, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (full_name, age, email, phone_number, password_hash_value, care_role_key, now, now),
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
        now = utcnow_iso()
        db = get_db()
        db.execute(
            "UPDATE user_devices SET is_revoked = 1, updated_at = ? WHERE user_id = ? AND device_id = ?",
            (now, user_id, device_id),
        )
        db.execute(
            "UPDATE device_push_tokens SET is_active = 0, updated_at = ? WHERE user_id = ? AND device_id = ?",
            (now, user_id, device_id),
        )
        db.commit()

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
    care_role_key = (user_row["care_role_key"] or "").strip()
    return {
        "id": user_row["id"],
        "full_name": user_row["full_name"],
        "age": user_row["age"],
        "email": user_row["email"],
        "phone_number": user_row["phone_number"],
        "care_role_key": care_role_key,
        "care_role_label": RELATIONSHIP_LABELS.get(care_role_key, ""),
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


ELDER_RELATIONSHIP_KEYS = {"grandfather", "grandmother"}
EMOTION_KEYWORD_WEIGHTS = {
    "buon": 18,
    "chan": 15,
    "co don": 24,
    "tuyet vong": 35,
    "met moi": 12,
    "lo lang": 14,
    "so hai": 14,
    "that vong": 18,
    "khoc": 18,
    "toi te": 18,
    "bat luc": 20,
    "tui than": 20,
    "tram": 20,
    "khong ai quan tam": 28,
    "khong co ai": 22,
    "vo nghia": 28,
}
EMOTION_CRITICAL_PATTERNS = {
    "muon chet": 80,
    "khong muon song": 85,
    "chan song": 70,
    "khong muon tiep tuc": 65,
    "muon bien mat": 70,
}
EMOTION_POSITIVE_KEYWORDS = {
    "vui": 10,
    "on": 6,
    "tot": 6,
    "hanh phuc": 12,
    "yen tam": 10,
    "thoai mai": 10,
}


RELATIONSHIP_LABELS = {
    "father": "ba",
    "mother": "me",
    "son": "con trai",
    "daughter": "con gái",
    "grandchild": "cháu",
    "grandfather": "ông",
    "grandmother": "bà",
    "wife": "vợ",
    "husband": "chồng",
    "brother": "anh/em trai",
    "sister": "chị/em gái",
    "caregiver": "người chăm sóc",
    "family_member": "người nhà",
}

RELATIONSHIP_EXACT_ALIASES = {
    "ba": "father",
    "bo": "father",
    "bố": "father",
    "cha": "father",
    "me": "mother",
    "mẹ": "mother",
    "má": "mother",
    "bà": "grandmother",
    "bà nội": "grandmother",
    "bà ngoại": "grandmother",
}

RELATIONSHIP_ALIASES = {
    "ba": "father",
    "bo": "father",
    "cha": "father",
    "me": "mother",
    "ma": "mother",
    "con trai": "son",
    "trai": "son",
    "thang con trai": "son",
    "con gai": "daughter",
    "gai": "daughter",
    "be gai": "daughter",
    "chau": "grandchild",
    "chau noi": "grandchild",
    "chau ngoai": "grandchild",
    "ong": "grandfather",
    "ong noi": "grandfather",
    "ong ngoai": "grandfather",
    "ba noi": "grandmother",
    "ba ngoai": "grandmother",
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
PENDING_VOICE_CALL_SESSION_KEY = "pending_voice_call_intent"


def simplify_text(value: str) -> str:
    lowered = (value or "").strip().lower()
    normalized = unicodedata.normalize("NFD", lowered)
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    without_marks = without_marks.replace("đ", "d").replace("Đ", "d")
    return re.sub(r"\s+", " ", without_marks).strip()


def normalize_relationship_key(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in RELATIONSHIP_EXACT_ALIASES:
        return RELATIONSHIP_EXACT_ALIASES[lowered]

    simplified = simplify_text(value)
    return RELATIONSHIP_ALIASES.get(simplified, simplified)


def extract_voice_message_command(text: str) -> dict | None:
    normalized_text = " ".join((text or "").strip().split())
    if not normalized_text:
        return None

    remaining_text = normalized_text
    lowered_remaining = remaining_text.lower()

    for prefix in (
        "bạn ",
        "ban ",
        "icare ",
        "bot ",
        "trợ lý ",
        "tro ly ",
    ):
        if lowered_remaining.startswith(prefix):
            remaining_text = remaining_text[len(prefix):].lstrip()
            lowered_remaining = remaining_text.lower()
            break

    for prefix in (
        "hãy ",
        "hay ",
        "giúp ",
        "giup ",
        "vui lòng ",
        "vui long ",
    ):
        if lowered_remaining.startswith(prefix):
            remaining_text = remaining_text[len(prefix):].lstrip()
            lowered_remaining = remaining_text.lower()
            break

    command_prefix = None
    for prefix in (
        "gửi tin nhắn cho ",
        "gui tin nhan cho ",
        "gửi lời nhắn cho ",
        "gui loi nhan cho ",
        "nhắn cho ",
        "nhan cho ",
        "nhắn giúp ",
        "nhan giup ",
        "bảo ",
        "bao ",
        "nói với ",
        "noi voi ",
        "nhắc ",
        "nhac ",
    ):
        if lowered_remaining.startswith(prefix):
            command_prefix = prefix
            break

    if command_prefix is None:
        return None

    remaining_text = remaining_text[len(command_prefix):].strip()
    lowered_remaining = remaining_text.lower()

    separator_index = -1
    separator_text = None
    for separator in (
        " nội dung là ",
        " noi dung la ",
        " rằng ",
        " rang ",
        " là ",
        " la ",
    ):
        separator_index = lowered_remaining.find(separator)
        if separator_index >= 0:
            separator_text = separator
            break

    if separator_index < 0 or separator_text is None:
        return None

    target_hint = remaining_text[:separator_index].strip(" ,:;.!?-")
    message_text = remaining_text[separator_index + len(separator_text):].strip()
    message_text = message_text.strip("\"'“”")
    if target_hint and message_text:
        return {
            "target_hint": target_hint,
            "message_text": message_text,
        }

    return None



def extract_voice_message_command_without_separator(text: str, owner_user_id: int) -> dict | None:
    normalized_text = " ".join((text or "").strip().split())
    if not normalized_text:
        return None

    original_tokens = normalized_text.split()
    simplified_tokens = simplify_text(normalized_text).split()
    if len(original_tokens) != len(simplified_tokens):
        return None

    def consume_prefix(prefix_tokens: list[str]) -> bool:
        nonlocal original_tokens, simplified_tokens
        if simplified_tokens[: len(prefix_tokens)] != prefix_tokens:
            return False
        original_tokens = original_tokens[len(prefix_tokens) :]
        simplified_tokens = simplified_tokens[len(prefix_tokens) :]
        return True

    for prefix_tokens in (
        ["ban"],
        ["icare"],
        ["bot"],
        ["tro", "ly"],
    ):
        if consume_prefix(prefix_tokens):
            break

    for prefix_tokens in (
        ["hay"],
        ["giup"],
        ["vui", "long"],
    ):
        if consume_prefix(prefix_tokens):
            break

    command_detected = False
    for prefix_tokens in (
        ["gui", "tin", "nhan", "cho"],
        ["gui", "loi", "nhan", "cho"],
        ["nhan", "cho"],
        ["nhan", "giup"],
        ["bao"],
        ["noi", "voi"],
        ["nhac"],
    ):
        if consume_prefix(prefix_tokens):
            command_detected = True
            break

    if not command_detected or len(original_tokens) < 2:
        return None

    filler_tokens = {"bac", "ong", "ba", "a", "ah", "nhe", "nha", "oi", "voi"}
    best_match = None
    candidates = list_voice_message_target_candidates(owner_user_id)
    for candidate in candidates:
        alias_candidates = [candidate["full_name"], *candidate["custom_aliases"]]
        if candidate.get("care_role_key"):
            alias_candidates.extend(iter_relationship_aliases(candidate["care_role_key"]))
        for relationship_key in candidate.get("relationship_keys") or []:
            alias_candidates.extend(iter_relationship_aliases(relationship_key))

        seen_aliases: set[str] = set()
        for alias in alias_candidates:
            simplified_alias = clean_voice_target_hint(alias)
            if not simplified_alias or simplified_alias in seen_aliases:
                continue
            seen_aliases.add(simplified_alias)

            alias_tokens = simplified_alias.split()
            if not alias_tokens or simplified_tokens[: len(alias_tokens)] != alias_tokens:
                continue

            consumed_count = len(alias_tokens)
            while consumed_count < len(simplified_tokens) - 1 and simplified_tokens[consumed_count] in filler_tokens:
                consumed_count += 1

            message_tokens = original_tokens[consumed_count:]
            if not message_tokens:
                continue

            match = {
                "target_hint": " ".join(original_tokens[:consumed_count]).strip(" ,:;.!?-"),
                "message_text": " ".join(message_tokens).strip().strip("\"'"),
                "consumed_count": consumed_count,
                "alias_length": len(alias_tokens),
            }
            if not match["message_text"]:
                continue

            if best_match is None or (
                match["alias_length"] > best_match["alias_length"]
                or (
                    match["alias_length"] == best_match["alias_length"]
                    and match["consumed_count"] < best_match["consumed_count"]
                )
            ):
                best_match = match

    if not best_match:
        return None

    return {
        "target_hint": best_match["target_hint"],
        "message_text": best_match["message_text"],
    }

def clean_voice_target_hint(value: str) -> str:
    simplified = simplify_text(value)
    simplified = re.sub(r"\b(cua toi|toi|oi|nhe|nha|dum|dum nhe|giup toi)\b", " ", simplified)
    return re.sub(r"\s+", " ", simplified).strip()


def list_voice_message_target_candidates(owner_user_id: int) -> list[dict]:
    membership = get_active_family_membership(owner_user_id)
    if not membership:
        return []

    rows = fetch_all(
        """
        SELECT
            fm.user_id,
            u.full_name,
            u.care_role_key,
            fr.relationship_key,
            fr.custom_aliases
        FROM family_members fm
        JOIN users u ON u.id = fm.user_id
        LEFT JOIN family_relationships fr
          ON fr.family_group_id = fm.family_group_id
         AND fr.owner_user_id = ?
         AND fr.relative_user_id = fm.user_id
         AND fr.is_active = 1
        WHERE fm.family_group_id = ?
          AND fm.status = 'active'
          AND fm.user_id != ?
        ORDER BY u.full_name COLLATE NOCASE ASC, fr.priority_order ASC, fr.id ASC
        """,
        (owner_user_id, membership["family_group_id"], owner_user_id),
    )

    candidates: dict[int, dict] = {}
    for row in rows:
        user_id = row["user_id"]
        candidate = candidates.setdefault(
            user_id,
            {
                "user_id": user_id,
                "full_name": (row["full_name"] or "").strip(),
                "care_role_key": "",
                "relationship_keys": set(),
                "custom_aliases": set(),
            },
        )

        care_role_key = normalize_relationship_key(row["care_role_key"] or "")
        if care_role_key in RELATIONSHIP_LABELS:
            candidate["care_role_key"] = care_role_key

        relationship_key = normalize_relationship_key(row["relationship_key"] or "")
        if relationship_key in RELATIONSHIP_LABELS:
            candidate["relationship_keys"].add(relationship_key)

        for alias in split_alias_input(row["custom_aliases"] or ""):
            candidate["custom_aliases"].add(alias)

    return [
        {
            **candidate,
            "relationship_keys": sorted(candidate["relationship_keys"]),
            "custom_aliases": sorted(candidate["custom_aliases"]),
        }
        for candidate in candidates.values()
    ]


def iter_relationship_aliases(relationship_key: str) -> list[str]:
    aliases = [RELATIONSHIP_LABELS.get(relationship_key, relationship_key)]
    for alias, mapped_key in RELATIONSHIP_ALIASES.items():
        if mapped_key == relationship_key:
            aliases.append(alias)

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        simplified = simplify_text(alias)
        if not simplified or simplified in seen:
            continue
        seen.add(simplified)
        deduped.append(alias)
    return deduped


def alias_matches_hint(alias: str, target_hint: str) -> bool:
    simplified_alias = simplify_text(alias)
    simplified_hint = clean_voice_target_hint(target_hint)
    if not simplified_alias or not simplified_hint:
        return False
    if simplified_alias == simplified_hint:
        return True
    if len(simplified_alias) >= 4 and simplified_alias in simplified_hint:
        return True
    if len(simplified_hint) >= 4 and simplified_hint in simplified_alias:
        return True
    return False


def describe_voice_message_target(candidate: dict) -> str:
    full_name = (candidate.get("full_name") or "").strip() or "người thân"
    relationship_keys = candidate.get("relationship_keys") or []
    primary_role_key = relationship_keys[0] if relationship_keys else (candidate.get("care_role_key") or "")
    relationship_label = RELATIONSHIP_LABELS.get(primary_role_key, "")
    if relationship_label:
        return f"{full_name} ({relationship_label})"
    return full_name


def resolve_voice_message_target(owner_user_id: int, target_hint: str) -> dict:
    candidates = list_voice_message_target_candidates(owner_user_id)
    current_user = getattr(g, "current_user", None)
    if not candidates:
        return {
            "status": "no_family_targets",
            "question": f"Gia dinh cua {get_user_voice_reference(current_user)} chua co nguoi than nao de nhan tin.",
        }

    name_matches: list[dict] = []
    role_matches: list[dict] = []

    for candidate in candidates:
        aliases = [candidate["full_name"], *candidate["custom_aliases"]]
        if any(alias_matches_hint(alias, target_hint) for alias in aliases):
            name_matches.append(candidate)
            continue

        role_aliases: list[str] = []
        if candidate.get("care_role_key"):
            role_aliases.extend(iter_relationship_aliases(candidate["care_role_key"]))
        for relationship_key in candidate.get("relationship_keys") or []:
            role_aliases.extend(iter_relationship_aliases(relationship_key))

        if any(alias_matches_hint(alias, target_hint) for alias in role_aliases):
            role_matches.append(candidate)

    if len(name_matches) == 1:
        target = name_matches[0]
        return {
            "status": "resolved",
            "candidate": target,
            "target_label": describe_voice_message_target(target),
        }

    if len(name_matches) > 1:
        names = [candidate["full_name"] for candidate in name_matches[:3]]
        return {
            "status": "ambiguous",
            "question": (
                f"{get_user_voice_title(current_user)} muon nhan cho {', '.join(names)} a? "
                f"{get_user_voice_title(current_user)} noi lai day du giup {get_assistant_self_reference(current_user)} nhe."
            ),
        }

    if len(role_matches) == 1:
        target = role_matches[0]
        return {
            "status": "resolved",
            "candidate": target,
            "target_label": describe_voice_message_target(target),
        }

    if len(role_matches) > 1:
        names = [candidate["full_name"] for candidate in role_matches[:3]]
        return {
            "status": "ambiguous",
            "question": (
                f"{get_assistant_self_reference(current_user).capitalize()} thay co nhieu nguoi phu hop: {', '.join(names)}. "
                f"{get_user_voice_title(current_user)} noi lai ro hon giup {get_assistant_self_reference(current_user)} nhe."
            ),
        }

    sample_names = [candidate["full_name"] for candidate in candidates[:3] if candidate.get("full_name")]
    if sample_names:
        return {
            "status": "not_found",
            "question": (
                f"{get_assistant_self_reference(current_user).capitalize()} chua xac dinh dung nguoi nhan. "
                f"{get_user_voice_title(current_user)} co the noi theo mau: nhan cho {sample_names[0]} la ..."
            ),
        }

    return {
        "status": "not_found",
        "question": (
            f"{get_assistant_self_reference(current_user).capitalize()} chua xac dinh dung nguoi nhan. "
            f"{get_user_voice_title(current_user)} noi lai giup {get_assistant_self_reference(current_user)} nhe."
        ),
    }


def detect_family_chat_intent(text: str, owner_user_id: int) -> dict:
    command = extract_voice_message_command(text)
    if command is None:
        command = extract_voice_message_command_without_separator(text, owner_user_id)
    if command is None:
        return {"type": "chat"}

    target_resolution = resolve_voice_message_target(owner_user_id, command["target_hint"])
    if target_resolution["status"] != "resolved":
        return {
            "type": "family_chat",
            "needs_confirmation": True,
            "question": target_resolution["question"],
            "message_text": command["message_text"],
        }

    candidate = target_resolution["candidate"]
    return {
        "type": "family_chat",
        "needs_confirmation": False,
        "recipient_user_id": candidate["user_id"],
        "recipient_full_name": candidate["full_name"],
        "target_label": target_resolution["target_label"],
        "message_text": command["message_text"],
    }


def get_user_care_role_key(user_row: sqlite3.Row | None) -> str | None:
    if user_row is None:
        return None

    saved_role_key = normalize_relationship_key(user_row["care_role_key"] or "")
    if saved_role_key in RELATIONSHIP_LABELS:
        return saved_role_key

    membership = get_active_family_membership(user_row["id"])
    if membership:
        relationship_row = fetch_one(
            """
            SELECT relationship_key
            FROM family_relationships
            WHERE family_group_id = ?
              AND relative_user_id = ?
              AND is_active = 1
              AND relationship_key IN ('mother', 'father', 'grandmother', 'grandfather')
            ORDER BY CASE relationship_key
                WHEN 'mother' THEN 0
                WHEN 'father' THEN 1
                WHEN 'grandmother' THEN 2
                WHEN 'grandfather' THEN 3
                ELSE 4
            END ASC, priority_order ASC, id ASC
            LIMIT 1
            """,
            (membership["family_group_id"], user_row["id"]),
        )
        if relationship_row is not None:
            return relationship_row["relationship_key"]

    if int(user_row["age"] or 0) >= ELDER_MIN_AGE:
        return "elder"

    return None


def get_user_voice_title(user_row: sqlite3.Row | None) -> str:
    role_key = get_user_care_role_key(user_row)
    return {
        "grandfather": "Ông",
        "grandmother": "Bà",
    }.get(role_key, "Bạn")


def get_assistant_self_reference(user_row: sqlite3.Row | None) -> str:
    role_key = get_user_care_role_key(user_row)
    return {
        "grandfather": "chau",
        "grandmother": "chau",
    }.get(role_key, "minh")


def get_user_voice_reference(user_row: sqlite3.Row | None) -> str:
    return get_user_voice_title(user_row).lower()


def analyze_emotion_signal(message_text: str) -> dict:
    simplified = simplify_text(message_text)
    score = 100
    detected_keywords: list[str] = []

    for phrase, penalty in EMOTION_CRITICAL_PATTERNS.items():
        if phrase in simplified:
            score -= penalty
            detected_keywords.append(phrase)

    for phrase, penalty in EMOTION_KEYWORD_WEIGHTS.items():
        if phrase in simplified:
            score -= penalty
            detected_keywords.append(phrase)

    for phrase, bonus in EMOTION_POSITIVE_KEYWORDS.items():
        if phrase in simplified:
            score += bonus

    score = max(0, min(100, score))

    if score <= EMOTION_CRITICAL_THRESHOLD:
        return {
            "emotion_label": "rat_buon",
            "risk_level": "critical",
            "emotion_score": score,
            "detected_keywords": detected_keywords,
        }
    if score <= EMOTION_ALERT_THRESHOLD:
        return {
            "emotion_label": "buon_chan",
            "risk_level": "warning",
            "emotion_score": score,
            "detected_keywords": detected_keywords,
        }
    if score <= 70:
        return {
            "emotion_label": "giam_nhe",
            "risk_level": "watch",
            "emotion_score": score,
            "detected_keywords": detected_keywords,
        }

    return {
        "emotion_label": "on_dinh",
        "risk_level": "stable",
        "emotion_score": score,
        "detected_keywords": detected_keywords,
    }


def fetch_monitored_elders(family_group_id: int) -> list[sqlite3.Row]:
    return fetch_all(
        """
        SELECT DISTINCT
            fm.user_id,
            u.full_name,
            u.age,
            u.email,
            u.phone_number,
            CASE
                WHEN EXISTS(
                    SELECT 1
                    FROM family_relationships fr
                    WHERE fr.family_group_id = fm.family_group_id
                      AND fr.relative_user_id = fm.user_id
                      AND fr.is_active = 1
                      AND fr.relationship_key = 'grandfather'
                ) THEN 'ong'
                WHEN EXISTS(
                    SELECT 1
                    FROM family_relationships fr
                    WHERE fr.family_group_id = fm.family_group_id
                      AND fr.relative_user_id = fm.user_id
                      AND fr.is_active = 1
                      AND fr.relationship_key = 'grandmother'
                ) THEN 'ba'
                ELSE 'nguoi_cao_tuoi'
            END AS care_role_key
        FROM family_members fm
        JOIN users u ON u.id = fm.user_id
        WHERE fm.family_group_id = ?
          AND fm.status = 'active'
          AND (
              u.age >= ?
              OR EXISTS(
                    SELECT 1
                    FROM family_relationships fr
                    WHERE fr.family_group_id = fm.family_group_id
                      AND fr.relative_user_id = fm.user_id
                      AND fr.is_active = 1
                      AND fr.relationship_key IN ('grandfather', 'grandmother')
                )
          )
        ORDER BY u.age DESC, u.full_name COLLATE NOCASE ASC
        """,
        (family_group_id, ELDER_MIN_AGE),
    )


def is_monitored_elder(user_id: int, family_group_id: int) -> bool:
    return any(row["user_id"] == user_id for row in fetch_monitored_elders(family_group_id))


def emotion_role_label(care_role_key: str) -> str:
    return {
        "grandfather": "Ong",
        "grandmother": "Ba",
        "father": "Ba",
        "mother": "Me",
        "elder": "Nguoi cao tuoi",
    }.get(care_role_key, "Người được theo dõi")


def get_family_admin_user_ids(family_group_id: int, *, exclude_user_id: int | None = None) -> list[int]:
    rows = fetch_all(
        """
        SELECT user_id
        FROM family_members
        WHERE family_group_id = ? AND status = 'active' AND role = 'admin'
        ORDER BY id ASC
        """,
        (family_group_id,),
    )
    user_ids = [row["user_id"] for row in rows]
    if exclude_user_id is not None:
        user_ids = [user_id for user_id in user_ids if user_id != exclude_user_id]
    return user_ids


def has_recent_emotion_alert(user_id: int) -> bool:
    threshold = (utcnow() - timedelta(minutes=EMOTION_ALERT_COOLDOWN_MINUTES)).isoformat(timespec="seconds")
    row = fetch_one(
        """
        SELECT id
        FROM emotion_logs
        WHERE user_id = ? AND alert_sent = 1 AND created_at >= ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id, threshold),
    )
    return row is not None


def maybe_log_emotion_signal(user_row: sqlite3.Row | None, message_text: str, *, source: str = "assistant_chat") -> dict | None:
    if user_row is None or not message_text.strip():
        return None

    membership = get_active_family_membership(user_row["id"])
    if not membership:
        return None
    if not is_monitored_elder(user_row["id"], membership["family_group_id"]):
        return None

    analysis = analyze_emotion_signal(message_text)
    now = utcnow_iso()
    cursor = get_db().execute(
        """
        INSERT INTO emotion_logs (
            family_group_id, user_id, source, message_text, emotion_label,
            emotion_score, risk_level, alert_sent, detected_keywords, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            membership["family_group_id"],
            user_row["id"],
            source,
            message_text.strip(),
            analysis["emotion_label"],
            analysis["emotion_score"],
            analysis["risk_level"],
            ", ".join(analysis["detected_keywords"]),
            now,
        ),
    )
    emotion_log_id = cursor.lastrowid

    should_alert = analysis["emotion_score"] <= EMOTION_ALERT_THRESHOLD and not has_recent_emotion_alert(user_row["id"])
    if should_alert:
        admin_user_ids = get_family_admin_user_ids(
            membership["family_group_id"],
            exclude_user_id=user_row["id"],
        )
        for admin_user_id in admin_user_ids:
            send_push_notification(
                target_user_id=admin_user_id,
                title="Icare canh bao cam xuc",
                body=(
                    f"{user_row['full_name']} dang co dau hieu buon/chan. "
                    f"Diem cam xuc hien tai: {analysis['emotion_score']}/100."
                ),
                data={
                    "event_type": "emotion_alert",
                    "emotion_log_id": emotion_log_id,
                    "user_id": user_row["id"],
                    "emotion_score": analysis["emotion_score"],
                    "risk_level": analysis["risk_level"],
                },
            )

        get_db().execute(
            "UPDATE emotion_logs SET alert_sent = 1 WHERE id = ?",
            (emotion_log_id,),
        )

    get_db().commit()
    return {
        **analysis,
        "emotion_log_id": emotion_log_id,
        "alert_sent": should_alert,
        "created_at": now,
    }


def serialize_emotion_log(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "full_name": row["full_name"],
        "age": row["age"],
        "message_text": row["message_text"],
        "emotion_label": row["emotion_label"],
        "emotion_score": row["emotion_score"],
        "risk_level": row["risk_level"],
        "alert_sent": bool(row["alert_sent"]),
        "detected_keywords": split_alias_input(row["detected_keywords"]),
        "created_at": row["created_at"],
    }


def fetch_recent_emotion_logs_for_user(user_id: int, limit: int = 6) -> list[dict]:
    rows = fetch_all(
        """
        SELECT el.*, u.full_name, u.age
        FROM emotion_logs el
        JOIN users u ON u.id = el.user_id
        WHERE el.user_id = ?
        ORDER BY el.created_at DESC, el.id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    return [serialize_emotion_log(row) for row in rows]


def build_emotion_trend(user_id: int, days: int = 7) -> list[dict]:
    threshold = (utcnow() - timedelta(days=days - 1)).date().isoformat()
    rows = fetch_all(
        """
        SELECT substr(created_at, 1, 10) AS day, AVG(emotion_score) AS avg_score, COUNT(*) AS total
        FROM emotion_logs
        WHERE user_id = ? AND substr(created_at, 1, 10) >= ?
        GROUP BY substr(created_at, 1, 10)
        ORDER BY day ASC
        """,
        (user_id, threshold),
    )
    return [
        {
            "date": row["day"],
            "average_score": int(round(row["avg_score"] or 0)),
            "entry_count": row["total"],
        }
        for row in rows
    ]


def build_emotion_dashboard_payload(user_id: int) -> dict | None:
    membership = get_active_family_membership(user_id)
    if not membership:
        return None

    elder_rows = fetch_monitored_elders(membership["family_group_id"])
    elders_payload: list[dict] = []
    average_scores: list[int] = []
    critical_count = 0
    warning_count = 0

    for elder_row in elder_rows:
        recent_entries = fetch_recent_emotion_logs_for_user(elder_row["user_id"])
        latest_entry = recent_entries[0] if recent_entries else None
        trend = build_emotion_trend(elder_row["user_id"])
        avg_score = (
            int(round(sum(entry["emotion_score"] for entry in recent_entries) / len(recent_entries)))
            if recent_entries
            else 100
        )
        average_scores.append(avg_score)
        if latest_entry and latest_entry["risk_level"] == "critical":
            critical_count += 1
        elif latest_entry and latest_entry["risk_level"] in {"warning", "watch"}:
            warning_count += 1

        elders_payload.append(
            {
                "user_id": elder_row["user_id"],
                "full_name": elder_row["full_name"],
                "age": elder_row["age"],
                "care_role_key": elder_row["care_role_key"],
                "care_role_label": emotion_role_label(elder_row["care_role_key"]),
                "latest_score": latest_entry["emotion_score"] if latest_entry else 100,
                "latest_label": latest_entry["emotion_label"] if latest_entry else "on_dinh",
                "latest_risk_level": latest_entry["risk_level"] if latest_entry else "stable",
                "latest_message": latest_entry["message_text"] if latest_entry else "",
                "latest_created_at": latest_entry["created_at"] if latest_entry else None,
                "recent_entries": recent_entries,
                "trend": trend,
                "average_score_7d": avg_score,
            }
        )

    return {
        "family_group_id": membership["family_group_id"],
        "generated_at": utcnow_iso(),
        "summary": {
            "elder_count": len(elders_payload),
            "average_score": int(round(sum(average_scores) / len(average_scores))) if average_scores else 100,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "stable_count": max(0, len(elders_payload) - critical_count - warning_count),
        },
        "elders": elders_payload,
    }


def validate_same_family_chat_membership(user_id: int, partner_user_id: int) -> tuple[sqlite3.Row | None, sqlite3.Row | None]:
    membership = get_active_family_membership(user_id)
    if not membership:
        return None, None
    partner_membership = fetch_family_membership_record(membership["family_group_id"], partner_user_id)
    if not partner_membership:
        return membership, None
    return membership, partner_membership


def serialize_family_chat_message(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "family_group_id": row["family_group_id"],
        "sender_user_id": row["sender_user_id"],
        "sender_full_name": row["sender_full_name"],
        "recipient_user_id": row["recipient_user_id"],
        "recipient_full_name": row["recipient_full_name"],
        "message_text": row["message_text"],
        "read_at": row["read_at"],
        "created_at": row["created_at"],
    }


def list_family_chat_threads(user_id: int) -> list[dict]:
    membership = get_active_family_membership(user_id)
    if not membership:
        return []

    threads: list[dict] = []
    for member in fetch_family_members(membership["family_group_id"]):
        if member["user_id"] == user_id:
            continue

        last_message = fetch_one(
            """
            SELECT
                m.*,
                sender.full_name AS sender_full_name,
                recipient.full_name AS recipient_full_name
            FROM family_chat_messages m
            JOIN users sender ON sender.id = m.sender_user_id
            JOIN users recipient ON recipient.id = m.recipient_user_id
            WHERE m.family_group_id = ?
              AND (
                    (m.sender_user_id = ? AND m.recipient_user_id = ?)
                 OR (m.sender_user_id = ? AND m.recipient_user_id = ?)
              )
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT 1
            """,
            (
                membership["family_group_id"],
                user_id,
                member["user_id"],
                member["user_id"],
                user_id,
            ),
        )
        unread_row = fetch_one(
            """
            SELECT COUNT(*) AS total
            FROM family_chat_messages
            WHERE family_group_id = ?
              AND sender_user_id = ?
              AND recipient_user_id = ?
              AND read_at IS NULL
            """,
            (membership["family_group_id"], member["user_id"], user_id),
        )
        threads.append(
            {
                "partner_user_id": member["user_id"],
                "partner_full_name": member["full_name"],
                "partner_role": member["role"],
                "last_message": serialize_family_chat_message(last_message) if last_message else None,
                "unread_count": unread_row["total"] if unread_row else 0,
            }
        )

    threads.sort(
        key=lambda item: (
            item["last_message"]["created_at"] if item["last_message"] else "",
            item["partner_full_name"].lower(),
        ),
        reverse=True,
    )
    return threads


def list_family_chat_messages(user_id: int, partner_user_id: int, *, limit: int = 80) -> list[dict] | None:
    membership, partner_membership = validate_same_family_chat_membership(user_id, partner_user_id)
    if membership is None or partner_membership is None:
        return None

    now = utcnow_iso()
    get_db().execute(
        """
        UPDATE family_chat_messages
        SET read_at = ?
        WHERE family_group_id = ?
          AND sender_user_id = ?
          AND recipient_user_id = ?
          AND read_at IS NULL
        """,
        (now, membership["family_group_id"], partner_user_id, user_id),
    )
    get_db().commit()

    rows = fetch_all(
        """
        SELECT
            m.*,
            sender.full_name AS sender_full_name,
            recipient.full_name AS recipient_full_name
        FROM family_chat_messages m
        JOIN users sender ON sender.id = m.sender_user_id
        JOIN users recipient ON recipient.id = m.recipient_user_id
        WHERE m.family_group_id = ?
          AND (
                (m.sender_user_id = ? AND m.recipient_user_id = ?)
             OR (m.sender_user_id = ? AND m.recipient_user_id = ?)
          )
        ORDER BY m.created_at ASC, m.id ASC
        LIMIT ?
        """,
        (
            membership["family_group_id"],
            user_id,
            partner_user_id,
            partner_user_id,
            user_id,
            limit,
        ),
    )
    return [serialize_family_chat_message(row) for row in rows]


def create_family_chat_message(sender_user_id: int, recipient_user_id: int, message_text: str) -> dict | None:
    membership, partner_membership = validate_same_family_chat_membership(sender_user_id, recipient_user_id)
    if membership is None or partner_membership is None:
        log_mobile_diag(
            "family_chat_blocked",
            level="warning",
            sender_user_id=sender_user_id,
            recipient_user_id=recipient_user_id,
            sender_has_family=membership is not None,
            sender_family_group_id=membership["family_group_id"] if membership else None,
            recipient_in_same_family=partner_membership is not None,
        )
        return None

    sender = fetch_user_by_id(sender_user_id)
    recipient = fetch_user_by_id(recipient_user_id)
    now = utcnow_iso()
    cursor = get_db().execute(
        """
        INSERT INTO family_chat_messages (
            family_group_id, sender_user_id, recipient_user_id, message_text, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (membership["family_group_id"], sender_user_id, recipient_user_id, message_text.strip(), now),
    )
    get_db().commit()

    payload = {
        "id": cursor.lastrowid,
        "family_group_id": membership["family_group_id"],
        "sender_user_id": sender_user_id,
        "sender_full_name": sender["full_name"] if sender else "Nguoi nha",
        "recipient_user_id": recipient_user_id,
        "recipient_full_name": recipient["full_name"] if recipient else "Nguoi nha",
        "message_text": message_text.strip(),
        "read_at": None,
        "created_at": now,
    }

    send_push_notification(
        target_user_id=recipient_user_id,
        title="Icare co tin nhan moi",
        body=f"{payload['sender_full_name']}: {payload['message_text'][:80]}",
        data={
            "event_type": "family_chat_message",
            "message_id": payload["id"],
            "sender_user_id": sender_user_id,
            "recipient_user_id": recipient_user_id,
        },
        channel_id="family_chat",
    )
    log_mobile_diag("family_chat_push_enqueued", sender_user_id=sender_user_id, recipient_user_id=recipient_user_id, message_id=payload["id"], message_preview=message_text[:120])
    return payload


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


def deactivate_push_tokens(push_tokens: list[str]) -> None:
    unique_tokens = [token for token in dict.fromkeys(push_tokens) if token]
    if not unique_tokens:
        return

    placeholders = ", ".join("?" for _ in unique_tokens)
    params = [utcnow_iso(), *unique_tokens]
    get_db().execute(
        f"""
        UPDATE device_push_tokens
        SET is_active = 0, updated_at = ?
        WHERE push_token IN ({placeholders})
        """,
        params,
    )
    get_db().commit()


def send_push_notification(
    *,
    target_user_id: int | None = None,
    push_tokens: list[str] | None = None,
    title: str,
    body: str,
    data: dict | None = None,
    channel_id: str = "icare_updates",
) -> None:
    firebase_app = get_firebase_push_app()
    if firebase_app is None or firebase_messaging is None:
        app.logger.info("Bo qua gui push vi Firebase push app chua san sang.")
        return

    tokens = [token for token in (push_tokens or list_push_tokens_for_user(target_user_id or 0)) if token]
    unique_tokens: list[str] = []
    for token in tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)

    if not unique_tokens:
        app.logger.info("Khong tim thay push token dang hoat dong cho user_id=%s.", target_user_id)
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
                channel_id=channel_id,
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
        result = firebase_messaging.send_each_for_multicast(message, app=firebase_app)
        if result.failure_count:
            failed_tokens = []
            inactive_tokens = []
            for index, response in enumerate(result.responses):
                if response.success:
                    continue
                error_text = str(response.exception)
                if "NotRegistered" in error_text or "Unregistered" in error_text:
                    inactive_tokens.append(unique_tokens[index])
                failed_tokens.append(
                    {
                        "token_suffix": unique_tokens[index][-12:] if len(unique_tokens[index]) > 12 else unique_tokens[index],
                        "error": error_text,
                    }
                )
            if inactive_tokens:
                deactivate_push_tokens(inactive_tokens)
            app.logger.warning(
                "Gui FCM xong nhung co loi: success=%s failure=%s details=%s",
                result.success_count,
                result.failure_count,
                failed_tokens,
            )
    except Exception:
        app.logger.exception("Gui push notification that bai cho user_id=%s.", target_user_id)
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

    log_mobile_diag("call_target_ringing", call_session_id=call_session_id, target_user_id=target_row["target_user_id"], priority_order=target_row["priority_order"], push_token_count=len(list_push_tokens_for_user(target_row["target_user_id"])))
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
        channel_id="incoming_calls",
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
            log_mobile_diag("call_target_timeout", call_session_id=call_session_id, target_user_id=current_target["target_user_id"], priority_order=current_target["priority_order"])
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

    generic_call_phrases = [
        "giup toi goi",
        "hay goi",
        "goi cho",
        "lien lac",
        "call",
        "goi",
    ]
    remaining_target_hint = simplified
    for phrase in generic_call_phrases:
        if remaining_target_hint.startswith(phrase):
            remaining_target_hint = remaining_target_hint[len(phrase):].strip()
            break

    is_generic_call_request = not remaining_target_hint

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
            "question": f"{get_user_voice_title(g.current_user)} muốn gọi {', '.join(names)} ạ?",
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
            "question": f"{get_user_voice_title(g.current_user)} muốn gọi {', '.join(labels)} ạ?",
        }

    if len(available_relationship_keys) == 1 and is_generic_call_request:
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
            "question": (
                f"Mình chưa khớp đúng người {get_user_voice_reference(g.current_user)} muốn gọi. "
                f"Hiện gia đình đang cấu hình: {', '.join(labels)}."
            ),
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
