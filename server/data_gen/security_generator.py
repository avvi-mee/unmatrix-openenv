import random

TEMPLATES = [
    {
        "filename": "auth.py",
        "code": """\
\"\"\"Authentication module.\"\"\"
import hmac
import hashlib
import datetime

# Bug: hardcoded secret key in source code
SECRET_KEY = "super_secret_key_12345"
JWT_ALGORITHM = "HS256"


def generate_token(user_id: int, role: str) -> str:
    \"\"\"Generate a simple HMAC token.\"\"\"
    payload = f"{user_id}:{role}:{datetime.datetime.utcnow().isoformat()}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_token(token: str) -> dict | None:
    \"\"\"Verify token and return payload dict.\"\"\"
    try:
        payload_str, signature = token.rsplit(".", 1)
        expected = hmac.new(SECRET_KEY.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
        # Bug: JWT expiry is never checked; expired tokens remain valid forever
        if hmac.compare_digest(expected, signature):
            parts = payload_str.split(":")
            return {"user_id": int(parts[0]), "role": parts[1]}
    except Exception:
        return None
    return None


def get_user_resource(user_id: int, resource_owner_id: int, resource: dict) -> dict | None:
    \"\"\"Return resource if requester is owner.\"\"\"
    # Bug: IDOR — only checks user_id == resource_owner_id but no role/permission check,
    # also does not verify the resource_owner_id from the database; trusts client-supplied value
    if user_id == resource_owner_id:
        return resource
    return None


def hash_password(password: str) -> str:
    \"\"\"Hash password with SHA-256.\"\"\"
    return hashlib.sha256(password.encode()).hexdigest()
""",
        "bugs": [
            {
                "file": "auth.py",
                "line": 6,
                "severity": "critical",
                "type": "hardcoded_secret",
                "description": "SECRET_KEY is hardcoded in source; anyone with repo access can forge tokens. Must use environment variable.",
                "expected_keywords": ["hardcoded", "secret", "environment", "variable"]
            },
            {
                "file": "auth.py",
                "line": 24,
                "severity": "major",
                "type": "missing_expiry_check",
                "description": "verify_token never checks token expiry/timestamp; tokens are valid indefinitely after issuance",
                "expected_keywords": ["expiry", "expired", "timestamp", "JWT"]
            },
            {
                "file": "auth.py",
                "line": 31,
                "severity": "major",
                "type": "idor",
                "description": "get_user_resource trusts client-supplied resource_owner_id without server-side lookup; enables IDOR by passing any owner ID",
                "expected_keywords": ["IDOR", "authorization", "lookup", "server-side"]
            }
        ]
    },
    {
        "filename": "db_api.py",
        "code": """\
\"\"\"Database access layer with logging.\"\"\"
import sqlite3
import logging

logger = logging.getLogger(__name__)
DB_PATH = "app.db"


def get_user_by_username(username: str) -> dict | None:
    \"\"\"Fetch user record by username.\"\"\"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Bug: SQL injection — username interpolated directly into query string
    query = f"SELECT id, username, email, password_hash FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "email": row[2], "password_hash": row[3]}
    return None


def log_login_attempt(username: str, password: str, success: bool) -> None:
    \"\"\"Log login attempt for audit trail.\"\"\"
    # Bug: plaintext password logged; PII/credential exposure in log files
    logger.info(f"Login attempt: user={username} password={password} success={success}")


def create_user(username: str, email: str, password_hash: str) -> int:
    \"\"\"Insert new user, return new row id.\"\"\"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (username, email, password_hash)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id
""",
        "bugs": [
            {
                "file": "db_api.py",
                "line": 13,
                "severity": "critical",
                "type": "sql_injection",
                "description": "get_user_by_username interpolates username directly into SQL query using f-string; allows SQL injection. Use parameterized query with ?.",
                "expected_keywords": ["SQL", "injection", "parameterized", "f-string"]
            },
            {
                "file": "db_api.py",
                "line": 23,
                "severity": "critical",
                "type": "pii_logging",
                "description": "log_login_attempt logs plaintext password in log message; credentials exposed in log files and monitoring systems",
                "expected_keywords": ["password", "logging", "plaintext", "credential"]
            }
        ]
    },
    {
        "filename": "payment.py",
        "code": """\
\"\"\"Payment processing utilities.\"\"\"
import hmac
import hashlib
from urllib.parse import urlparse


WEBHOOK_SECRET = "wh_secret_abc"
ALLOWED_REDIRECT_DOMAINS = ["example.com", "app.example.com"]


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    \"\"\"Verify incoming webhook payload signature.\"\"\"
    expected = hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    # Bug: plain string comparison instead of hmac.compare_digest; timing attack possible
    return expected == signature


def process_refund(order_id: int, amount: float, currency: str) -> dict:
    \"\"\"Initiate refund for an order.\"\"\"
    if amount <= 0:
        raise ValueError("Refund amount must be positive")
    return {"status": "initiated", "order_id": order_id, "amount": amount, "currency": currency}


def redirect_after_payment(return_url: str) -> str:
    \"\"\"Validate and return safe redirect URL after payment.\"\"\"
    parsed = urlparse(return_url)
    # Bug: open redirect — only checks if domain is in allowed list but does not
    # enforce scheme, so javascript: or data: URIs with matching hostname bypass check
    if parsed.hostname in ALLOWED_REDIRECT_DOMAINS:
        return return_url
    return "https://example.com/payment/cancelled"


def mask_card_number(card_number: str) -> str:
    \"\"\"Return masked card number showing only last 4 digits.\"\"\"
    digits_only = "".join(c for c in card_number if c.isdigit())
    return "*" * (len(digits_only) - 4) + digits_only[-4:]
""",
        "bugs": [
            {
                "file": "payment.py",
                "line": 14,
                "severity": "major",
                "type": "timing_attack",
                "description": "verify_webhook_signature uses == comparison which is timing-attack vulnerable; must use hmac.compare_digest for constant-time comparison",
                "expected_keywords": ["timing", "compare_digest", "constant-time", "signature"]
            },
            {
                "file": "payment.py",
                "line": 26,
                "severity": "major",
                "type": "open_redirect",
                "description": "redirect_after_payment only validates hostname but not scheme; javascript: URIs or data: URIs with a valid hostname bypass the check enabling open redirect / XSS",
                "expected_keywords": ["redirect", "scheme", "javascript", "open"]
            }
        ]
    },
    {
        "filename": "file_handler.py",
        "code": """\
\"\"\"Secure file handler for user uploads.\"\"\"
import os
import shutil

UPLOAD_DIR = "/var/uploads"
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".png", ".jpg"}


def save_upload(filename: str, data: bytes) -> str:
    \"\"\"Save uploaded file, return saved path.\"\"\"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension {ext} not allowed")
    # Bug: path traversal — filename not sanitized; '../../../etc/passwd' would escape UPLOAD_DIR
    dest = os.path.join(UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def read_upload(filename: str) -> bytes:
    \"\"\"Read a previously uploaded file.\"\"\"
    # Bug: path traversal — no check that resolved path stays within UPLOAD_DIR
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "rb") as f:
        return f.read()


def delete_upload(filename: str) -> bool:
    \"\"\"Delete an uploaded file. Returns True on success.\"\"\"
    path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def list_uploads() -> list[str]:
    \"\"\"List all uploaded filenames.\"\"\"
    return os.listdir(UPLOAD_DIR)
""",
        "bugs": [
            {
                "file": "file_handler.py",
                "line": 14,
                "severity": "critical",
                "type": "path_traversal",
                "description": "save_upload joins filename directly to UPLOAD_DIR without sanitization; path traversal like '../../../etc/passwd' escapes intended directory",
                "expected_keywords": ["path", "traversal", "sanitize", "realpath"]
            },
            {
                "file": "file_handler.py",
                "line": 22,
                "severity": "critical",
                "type": "path_traversal",
                "description": "read_upload constructs path without verifying it stays within UPLOAD_DIR; use os.path.realpath and check startswith(UPLOAD_DIR)",
                "expected_keywords": ["path", "traversal", "realpath", "boundary"]
            }
        ]
    },
    {
        "filename": "session.py",
        "code": """\
\"\"\"Session management utilities.\"\"\"
import os
import hashlib
import datetime


SESSION_DURATION_HOURS = 24


def create_session_id() -> str:
    \"\"\"Generate a cryptographically random session ID.\"\"\"
    return hashlib.sha256(os.urandom(32)).hexdigest()


def set_session_cookie(response, session_id: str, user_id: int) -> None:
    \"\"\"Attach session cookie to HTTP response.\"\"\"
    expires = datetime.datetime.utcnow() + datetime.timedelta(hours=SESSION_DURATION_HOURS)
    # Bug: missing HttpOnly and Secure flags; cookie accessible via JS and sent over HTTP
    response.set_cookie(
        key="session_id",
        value=session_id,
        expires=expires.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        samesite="Lax",
    )


def invalidate_session(session_store: dict, session_id: str) -> bool:
    \"\"\"Remove session from store.\"\"\"
    if session_id in session_store:
        del session_store[session_id]
        return True
    return False


def get_session_user(session_store: dict, session_id: str) -> int | None:
    \"\"\"Return user_id for valid session, or None.\"\"\"
    session = session_store.get(session_id)
    if not session:
        return None
    # Bug: expiry is never checked; sessions remain valid past their expiration time
    return session.get("user_id")
""",
        "bugs": [
            {
                "file": "session.py",
                "line": 19,
                "severity": "major",
                "type": "insecure_cookie",
                "description": "set_session_cookie missing HttpOnly=True and Secure=True flags; cookie readable by JavaScript and transmittable over plain HTTP",
                "expected_keywords": ["HttpOnly", "Secure", "cookie", "flag"]
            },
            {
                "file": "session.py",
                "line": 38,
                "severity": "major",
                "type": "missing_expiry_check",
                "description": "get_session_user never checks session expiry timestamp; expired sessions remain valid indefinitely",
                "expected_keywords": ["expiry", "expired", "timestamp", "session"]
            }
        ]
    }
]


def generate(seed: int = 42) -> dict:
    random.seed(seed)
    t = TEMPLATES[seed % len(TEMPLATES)]
    return {
        "name": "security_audit",
        "description": (
            "Audit this module for security vulnerabilities. "
            "Flag each issue with file, line, severity (critical/major/minor), and a clear description "
            "explaining the vulnerability and recommended fix."
        ),
        "files": [t["filename"]],
        "content": {t["filename"]: t["code"]},
        "bugs": t["bugs"],
        "task_type": "security_audit",
    }
