import random

TEMPLATES = [
    {
        "files": ["order_service.py", "inventory.py", "database.py", "worker.py", "cache.py"],
        "code": {
            "order_service.py": """\
\"\"\"Order service — processes customer orders.\"\"\"
from database import get_db_connection
from inventory import get_item_stock
from cache import get_cached_price


def create_order(user_id: int, items: list[dict]) -> dict:
    \"\"\"Create order: validate stock, compute total, persist.\"\"\"
    conn = get_db_connection()
    total = 0.0
    order_items = []
    # Arch issue: N+1 query — one DB call per item instead of batch SELECT
    for item in items:
        stock = get_item_stock(item["product_id"])
        if stock < item["quantity"]:
            raise ValueError(f"Insufficient stock for product {item['product_id']}")
        price = get_cached_price(item["product_id"])
        total += price * item["quantity"]
        order_items.append({"product_id": item["product_id"], "qty": item["quantity"], "price": price})
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (user_id, total) VALUES (?, ?)", (user_id, total))
    order_id = cursor.lastrowid
    conn.commit()
    return {"order_id": order_id, "total": total, "items": order_items}
""",
            "inventory.py": """\
\"\"\"Inventory service — manages stock levels.\"\"\"
from database import get_db_connection

_stock_cache = {}


def get_item_stock(product_id: int) -> int:
    \"\"\"Return current stock level for a product.\"\"\"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    return row[0] if row else 0


def decrement_stock(product_id: int, quantity: int) -> bool:
    \"\"\"Decrement stock. Returns False if insufficient.\"\"\"
    conn = get_db_connection()
    cursor = conn.cursor()
    # Arch issue: race condition — read-then-write without locking; concurrent decrements can oversell
    cursor.execute("SELECT stock FROM products WHERE id = ?", (product_id,))
    row = cursor.fetchone()
    if not row or row[0] < quantity:
        return False
    cursor.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
    conn.commit()
    return True
""",
            "database.py": """\
\"\"\"Database connection factory.\"\"\"
import sqlite3

DB_PATH = "app.db"


def get_db_connection():
    \"\"\"Return a new database connection.\"\"\"
    # Arch issue: no connection pool — new connection created on every call
    return sqlite3.connect(DB_PATH)
""",
            "worker.py": """\
\"\"\"Background worker — processes queued jobs.\"\"\"
import threading
import time

_job_queue = []
_processed_results = {}


def enqueue_job(job_id: str, payload: dict) -> None:
    \"\"\"Add job to in-process queue.\"\"\"
    _job_queue.append({"id": job_id, "payload": payload})


def process_jobs() -> None:
    \"\"\"Process all queued jobs synchronously.\"\"\"
    while _job_queue:
        job = _job_queue.pop(0)
        result = _execute_job(job["payload"])
        # Arch issue: results stored in unbounded in-memory dict — memory leak over time
        _processed_results[job["id"]] = result


def _execute_job(payload: dict) -> dict:
    time.sleep(0.01)
    return {"status": "done", "data": payload}


def get_result(job_id: str) -> dict | None:
    return _processed_results.get(job_id)
""",
            "cache.py": """\
\"\"\"Simple in-memory cache for product prices.\"\"\"
import time

_cache = {}


def get_cached_price(product_id: int) -> float:
    \"\"\"Return cached price or fetch from DB.\"\"\"
    entry = _cache.get(product_id)
    # Arch issue: no TTL — stale prices served indefinitely after product price update
    if entry is not None:
        return entry["price"]
    price = _fetch_price_from_db(product_id)
    _cache[product_id] = {"price": price}
    return price


def invalidate(product_id: int) -> None:
    \"\"\"Remove product from cache.\"\"\"
    _cache.pop(product_id, None)


def _fetch_price_from_db(product_id: int) -> float:
    return 9.99
"""
        },
        "bugs": [
            {
                "file": "order_service.py",
                "line": 13,
                "severity": "major",
                "type": "n_plus_1_query",
                "description": "create_order issues one DB query per item in the loop (N+1 pattern); should batch-fetch all product stock in a single SELECT IN query",
                "expected_keywords": ["N+1", "batch", "query", "loop"]
            },
            {
                "file": "inventory.py",
                "line": 20,
                "severity": "critical",
                "type": "race_condition",
                "description": "decrement_stock reads stock then writes without atomic locking; concurrent requests can both read sufficient stock and oversell",
                "expected_keywords": ["race", "condition", "atomic", "lock"]
            },
            {
                "file": "database.py",
                "line": 8,
                "severity": "major",
                "type": "no_connection_pool",
                "description": "get_db_connection creates a new connection on every call with no pooling; use a connection pool to limit overhead and exhaustion",
                "expected_keywords": ["connection", "pool", "overhead", "exhaustion"]
            },
            {
                "file": "worker.py",
                "line": 19,
                "severity": "major",
                "type": "memory_leak",
                "description": "_processed_results dict grows without bound; completed job results are never evicted causing memory leak",
                "expected_keywords": ["memory", "leak", "evict", "unbounded"]
            },
            {
                "file": "cache.py",
                "line": 10,
                "severity": "major",
                "type": "no_cache_ttl",
                "description": "get_cached_price has no TTL; stale prices persist indefinitely after DB updates unless invalidate() is explicitly called",
                "expected_keywords": ["TTL", "stale", "expiry", "cache"]
            }
        ]
    },
    {
        "files": ["api_gateway.py", "user_service.py", "notification_service.py"],
        "code": {
            "api_gateway.py": """\
\"\"\"API gateway — routes requests to backend services.\"\"\"
import requests as http_requests

SERVICE_URLS = {
    "users": "http://user-service:8001",
    "notifications": "http://notification-service:8002",
}

# Arch issue: no circuit breaker — failed downstream calls block gateway indefinitely
def proxy_request(service: str, path: str, method: str = "GET", data: dict = None) -> dict:
    \"\"\"Forward request to a downstream service.\"\"\"
    url = SERVICE_URLS.get(service)
    if not url:
        raise ValueError(f"Unknown service: {service}")
    resp = http_requests.request(method, f"{url}{path}", json=data, timeout=30)
    return resp.json()


def get_user_profile(user_id: int) -> dict:
    \"\"\"Fetch user profile via user-service.\"\"\"
    return proxy_request("users", f"/users/{user_id}")


def send_notification(user_id: int, message: str) -> dict:
    \"\"\"Send notification via notification-service.\"\"\"
    return proxy_request("notifications", "/send", "POST", {"user_id": user_id, "message": message})
""",
            "user_service.py": """\
\"\"\"User service — manages user accounts.\"\"\"

_users_db = {}
_event_subscribers = []


def register_user(user_id: int, name: str, email: str) -> dict:
    \"\"\"Register a new user.\"\"\"
    if user_id in _users_db:
        raise ValueError(f"User {user_id} already exists")
    user = {"id": user_id, "name": name, "email": email}
    _users_db[user_id] = user
    # Arch issue: tight coupling — directly calls all subscribers synchronously
    for subscriber in _event_subscribers:
        subscriber("user_registered", user)
    return user


def subscribe(callback) -> None:
    \"\"\"Subscribe to user events.\"\"\"
    _event_subscribers.append(callback)


def get_user(user_id: int) -> dict | None:
    return _users_db.get(user_id)
""",
            "notification_service.py": """\
\"\"\"Notification service — sends messages to users.\"\"\"
import time

_retry_counts = {}
MAX_RETRIES = 3


def send_notification(user_id: int, message: str) -> bool:
    \"\"\"Attempt to deliver a notification.\"\"\"
    retries = _retry_counts.get(user_id, 0)
    if retries >= MAX_RETRIES:
        return False
    success = _deliver(user_id, message)
    if not success:
        # Arch issue: retry counter stored in memory — lost on service restart; use persistent queue
        _retry_counts[user_id] = retries + 1
    else:
        _retry_counts.pop(user_id, None)
    return success


def _deliver(user_id: int, message: str) -> bool:
    time.sleep(0.05)
    return True
"""
        },
        "bugs": [
            {
                "file": "api_gateway.py",
                "line": 9,
                "severity": "major",
                "type": "no_circuit_breaker",
                "description": "proxy_request has no circuit breaker pattern; repeated failures to a downstream service will block all gateway threads and cascade failures",
                "expected_keywords": ["circuit", "breaker", "cascade", "timeout"]
            },
            {
                "file": "user_service.py",
                "line": 14,
                "severity": "major",
                "type": "tight_coupling",
                "description": "register_user directly invokes all subscribers synchronously; a slow/failing subscriber blocks user registration. Use async event bus instead.",
                "expected_keywords": ["coupling", "subscriber", "async", "event"]
            },
            {
                "file": "notification_service.py",
                "line": 14,
                "severity": "major",
                "type": "in_memory_state",
                "description": "_retry_counts stored in-memory only; lost on restart. Failed notifications will reset retry counter after crash, potentially exceeding MAX_RETRIES limits.",
                "expected_keywords": ["in-memory", "persistent", "restart", "retry"]
            }
        ]
    },
    {
        "files": ["report_service.py", "data_pipeline.py", "config_service.py"],
        "code": {
            "report_service.py": """\
\"\"\"Report generation service.\"\"\"
from data_pipeline import fetch_all_records
import csv
import io


def generate_csv_report(filters: dict) -> str:
    \"\"\"Generate CSV report for filtered records.\"\"\"
    # Arch issue: loads ALL records into memory then filters; should filter at DB level
    records = fetch_all_records()
    filtered = [r for r in records if all(r.get(k) == v for k, v in filters.items())]
    output = io.StringIO()
    if not filtered:
        return ""
    writer = csv.DictWriter(output, fieldnames=filtered[0].keys())
    writer.writeheader()
    writer.writerows(filtered)
    return output.getvalue()


def export_report(report_data: str, format: str = "csv") -> bytes:
    \"\"\"Encode report for export.\"\"\"
    return report_data.encode("utf-8")
""",
            "data_pipeline.py": """\
\"\"\"Data pipeline — fetches and transforms records.\"\"\"

_record_cache = None


def fetch_all_records() -> list[dict]:
    \"\"\"Fetch all records, using cache if available.\"\"\"
    global _record_cache
    # Arch issue: module-level mutable cache with no invalidation or TTL
    if _record_cache is not None:
        return _record_cache
    _record_cache = _load_from_db()
    return _record_cache


def transform_record(record: dict) -> dict:
    \"\"\"Apply field transformations.\"\"\"
    return {k: str(v).strip() for k, v in record.items()}


def _load_from_db() -> list[dict]:
    return [{"id": i, "value": i * 10, "status": "active"} for i in range(1000)]
""",
            "config_service.py": """\
\"\"\"Configuration service — loads app settings.\"\"\"
import os

_config_cache = {}


def get_config(key: str, default=None):
    \"\"\"Return config value from cache or environment.\"\"\"
    if key in _config_cache:
        return _config_cache[key]
    value = os.environ.get(key, default)
    # Arch issue: config cached forever; changes to env vars require service restart
    _config_cache[key] = value
    return value


def set_config(key: str, value) -> None:
    \"\"\"Override a config value at runtime.\"\"\"
    _config_cache[key] = value


def clear_cache() -> None:
    \"\"\"Clear all cached config.\"\"\"
    _config_cache.clear()
"""
        },
        "bugs": [
            {
                "file": "report_service.py",
                "line": 9,
                "severity": "major",
                "type": "inefficient_data_loading",
                "description": "generate_csv_report fetches ALL records then filters in Python; filter should be pushed to DB level to avoid loading unbounded data into memory",
                "expected_keywords": ["memory", "filter", "database", "unbounded"]
            },
            {
                "file": "data_pipeline.py",
                "line": 8,
                "severity": "major",
                "type": "stale_cache",
                "description": "_record_cache module-level variable has no TTL or invalidation; stale data served forever after DB updates",
                "expected_keywords": ["cache", "stale", "TTL", "invalidation"]
            },
            {
                "file": "config_service.py",
                "line": 11,
                "severity": "minor",
                "type": "config_not_refreshable",
                "description": "get_config caches env vars indefinitely; runtime config changes require service restart since cache is never refreshed",
                "expected_keywords": ["config", "cache", "refresh", "restart"]
            }
        ]
    },
    {
        "files": ["auth_middleware.py", "rate_limiter.py", "session_store.py"],
        "code": {
            "auth_middleware.py": """\
\"\"\"Authentication middleware for request pipeline.\"\"\"
import time

_token_blacklist = set()


def authenticate_request(headers: dict) -> dict | None:
    \"\"\"Extract and validate bearer token from headers.\"\"\"
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    # Arch issue: blacklist grows forever in memory — no eviction of expired tokens
    if token in _token_blacklist:
        return None
    return _parse_token(token)


def revoke_token(token: str) -> None:
    \"\"\"Add token to revocation blacklist.\"\"\"
    _token_blacklist.add(token)


def _parse_token(token: str) -> dict | None:
    if not token:
        return None
    return {"user_id": 1, "role": "user"}
""",
            "rate_limiter.py": """\
\"\"\"In-memory rate limiter.\"\"\"
import time
import threading

_request_counts = {}
_lock = threading.Lock()
WINDOW_SECONDS = 60
MAX_REQUESTS = 100


def is_allowed(client_id: str) -> bool:
    \"\"\"Return True if client is within rate limit.\"\"\"
    now = time.time()
    with _lock:
        record = _request_counts.get(client_id, {"count": 0, "window_start": now})
        if now - record["window_start"] > WINDOW_SECONDS:
            record = {"count": 0, "window_start": now}
        record["count"] += 1
        _request_counts[client_id] = record
        # Arch issue: no eviction of old client records — dict grows without bound
        return record["count"] <= MAX_REQUESTS
""",
            "session_store.py": """\
\"\"\"In-process session store.\"\"\"
import time
import threading

_sessions = {}
_lock = threading.Lock()
SESSION_TTL = 3600


def create_session(session_id: str, user_id: int) -> None:
    \"\"\"Create a new session entry.\"\"\"
    with _lock:
        _sessions[session_id] = {
            "user_id": user_id,
            "created_at": time.time(),
        }


def get_session(session_id: str) -> dict | None:
    \"\"\"Retrieve session by ID. Returns None if expired or missing.\"\"\"
    with _lock:
        session = _sessions.get(session_id)
        if session is None:
            return None
        if time.time() - session["created_at"] > SESSION_TTL:
            del _sessions[session_id]
            return None
        return session


def delete_session(session_id: str) -> None:
    with _lock:
        _sessions.pop(session_id, None)
"""
        },
        "bugs": [
            {
                "file": "auth_middleware.py",
                "line": 13,
                "severity": "major",
                "type": "unbounded_blacklist",
                "description": "_token_blacklist set in authenticate_request grows forever; revoked tokens are never evicted even after expiry, causing memory growth",
                "expected_keywords": ["blacklist", "eviction", "memory", "expiry"]
            },
            {
                "file": "rate_limiter.py",
                "line": 19,
                "severity": "major",
                "type": "unbounded_dict",
                "description": "_request_counts dict in rate_limiter grows without bound; old client entries are never cleaned up. Should use LRU cache or TTL-based eviction.",
                "expected_keywords": ["eviction", "unbounded", "LRU", "memory"]
            }
        ]
    },
    {
        "files": ["event_bus.py", "order_processor.py", "audit_log.py"],
        "code": {
            "event_bus.py": """\
\"\"\"Simple synchronous event bus.\"\"\"
import threading

_handlers = {}
_lock = threading.Lock()


def subscribe(event_type: str, handler) -> None:
    \"\"\"Subscribe handler to an event type.\"\"\"
    with _lock:
        if event_type not in _handlers:
            _handlers[event_type] = []
        _handlers[event_type].append(handler)


def publish(event_type: str, payload: dict) -> None:
    \"\"\"Publish event to all subscribed handlers.\"\"\"
    with _lock:
        handlers = list(_handlers.get(event_type, []))
    # Arch issue: handlers called synchronously; slow handler blocks publisher thread
    for handler in handlers:
        handler(payload)


def unsubscribe_all(event_type: str) -> None:
    with _lock:
        _handlers.pop(event_type, None)
""",
            "order_processor.py": """\
\"\"\"Order processor — handles order lifecycle events.\"\"\"
from event_bus import subscribe, publish
import time

_order_store = {}


def process_payment(order_id: str, amount: float) -> bool:
    \"\"\"Simulate payment processing and emit events.\"\"\"
    time.sleep(0.1)
    success = amount > 0
    if success:
        _order_store[order_id] = {"status": "paid", "amount": amount}
        publish("order_paid", {"order_id": order_id, "amount": amount})
    else:
        publish("order_failed", {"order_id": order_id})
    return success


def cancel_order(order_id: str) -> bool:
    \"\"\"Cancel order if it exists.\"\"\"
    # Arch issue: no idempotency check — cancelling same order_id twice emits duplicate events
    if order_id in _order_store:
        _order_store[order_id]["status"] = "cancelled"
        publish("order_cancelled", {"order_id": order_id})
        return True
    return False


def get_order(order_id: str) -> dict | None:
    return _order_store.get(order_id)
""",
            "audit_log.py": """\
\"\"\"Audit logging service.\"\"\"
import datetime
import json

_audit_log = []


def log_event(event_type: str, payload: dict, user_id: int = 0) -> None:
    \"\"\"Append audit entry to in-memory log.\"\"\"
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "payload": payload,
    }
    # Arch issue: audit log in-memory only — all entries lost on process restart
    _audit_log.append(entry)


def get_recent_events(limit: int = 100) -> list[dict]:
    \"\"\"Return most recent audit events.\"\"\"
    return _audit_log[-limit:]


def export_log() -> str:
    \"\"\"Export entire audit log as JSON string.\"\"\"
    return json.dumps(_audit_log, indent=2)
"""
        },
        "bugs": [
            {
                "file": "event_bus.py",
                "line": 18,
                "severity": "major",
                "type": "synchronous_handlers",
                "description": "publish calls all handlers synchronously; a slow or failing handler blocks the publishing thread and cascades latency to unrelated events",
                "expected_keywords": ["synchronous", "async", "handler", "blocking"]
            },
            {
                "file": "order_processor.py",
                "line": 23,
                "severity": "major",
                "type": "missing_idempotency",
                "description": "cancel_order has no idempotency guard; calling it twice on same order emits duplicate order_cancelled events causing downstream double-processing",
                "expected_keywords": ["idempotency", "duplicate", "event", "guard"]
            },
            {
                "file": "audit_log.py",
                "line": 16,
                "severity": "critical",
                "type": "volatile_audit_log",
                "description": "_audit_log stored in-memory only; all audit records are lost when the process restarts, violating audit trail requirements",
                "expected_keywords": ["persistent", "audit", "memory", "restart"]
            }
        ]
    }
]


def generate(seed: int = 42) -> dict:
    random.seed(seed)
    t = TEMPLATES[seed % len(TEMPLATES)]
    return {
        "name": "architecture_review",
        "description": (
            "Review this multi-file service for architectural issues. "
            "Flag each problem with file, line, severity, and a description including the anti-pattern name "
            "and recommended improvement."
        ),
        "files": t["files"],
        "content": t["code"],
        "bugs": t["bugs"],
        "task_type": "architecture_review",
    }
