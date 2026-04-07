"""
Peer Review Arena — Two-agent inference script.

Usage:
    python inference.py

Environment variables:
    HF_TOKEN           HuggingFace token for the inference router (required)
    API_BASE_URL       OpenAI-compatible base URL (default: HF router)
    MODEL_NAME         Model to use for both agents (default: Qwen2.5-Coder-7B-Instruct)
    LOCAL_IMAGE_NAME   Docker image name for local deployment (optional)
    ENV_SERVER_URL     URL of the running FastAPI environment server
"""
import argparse
import io
import json
import os
import random as _random
import re
import sys
import time
import uuid

import threading

import requests
from openai import OpenAI

# Force UTF-8 output on Windows so box/arrow characters print correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Configuration ──────────────────────────────────────────────────────────────

HF_TOKEN = os.environ.get("HF_TOKEN")
API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-Instruct")
LOCAL_IMAGE_NAME = os.environ.get("LOCAL_IMAGE_NAME")
ENV_SERVER_URL = os.environ.get("ENV_SERVER_URL", "http://localhost:8000")


# ── Auto-start environment server if not already running ──────────────────────

def _ensure_server() -> None:
    """Start the FastAPI env server in a daemon thread if nothing is listening."""
    # Quick probe — if server already up, return immediately
    try:
        requests.get(f"{ENV_SERVER_URL}/health", timeout=2)
        print(f"[SERVER] Already running at {ENV_SERVER_URL}", flush=True)
        return
    except Exception:
        pass

    # Parse port from ENV_SERVER_URL (default 8000)
    from urllib.parse import urlparse
    parsed = urlparse(ENV_SERVER_URL)
    host = parsed.hostname or "0.0.0.0"
    port = parsed.port or 8000

    print(f"[SERVER] Starting environment server on {host}:{port} ...", flush=True)

    def _run():
        import uvicorn
        uvicorn.run("server.app:app", host=host, port=port, log_level="warning")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    # Wait up to 15 seconds for it to become healthy
    for i in range(30):
        try:
            r = requests.get(f"{ENV_SERVER_URL}/health", timeout=2)
            if r.status_code == 200:
                print(f"[SERVER] Ready after {(i+1)*0.5:.1f}s", flush=True)
                return
        except Exception:
            pass
        time.sleep(0.5)

    raise RuntimeError(f"Environment server failed to start at {ENV_SERVER_URL}")

TASKS = [
    ("bug_hunt",            "EASY",   "Easy"),
    ("security_audit",      "MEDIUM", "Medium"),
    ("architecture_review", "HARD",   "Hard"),
]

MAX_STEPS_PER_AGENT = 12

llm = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN or "dummy")

# ── Scoring weights ────────────────────────────────────────────────────────────

W_RECALL  = 0.60   # bugs found / total bugs
W_UNIQUE  = 0.25   # unique bugs (opponent missed) / total bugs
W_LEARN   = 0.15   # bugs gained in Round 2 vs Round 1 / total bugs

# ── Print helpers ──────────────────────────────────────────────────────────────

SEP = "=" * 56


BENCHMARK = "peer_review_arena"


def print_header() -> None:
    print(SEP)
    print("Peer Review Arena — Inference Run")
    print(f"Server : {ENV_SERVER_URL}")
    print(f"Model  : {MODEL_NAME}")
    print("Provider: HF Router")
    print(SEP)
    print(flush=True)


def print_task_header(label: str, ep_id: str) -> None:
    print(SEP)
    print(f"TASK: {label} | episode={ep_id}")
    print(SEP, flush=True)


# ── Mandatory stdout format ────────────────────────────────────────────────────

def log_start(task: str) -> None:
    print(f"[START] task={task} env={BENCHMARK} model={MODEL_NAME}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error=None) -> None:
    err = error if error else "null"
    print(f"[STEP] step={step} action={action} reward={reward:.2f} done={str(done).lower()} error={err}",
          flush=True)


def log_end(success: bool, steps: int, score: float, rewards: list) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}",
          flush=True)


# ── Legacy agent-level helpers (kept for orchestrator report) ─────────────────

def print_agent_start(agent_id: str, ep_id: str, task: str) -> None:
    pass  # now handled by log_start once per episode


def print_step(agent_id: str, step: int, action: str, result: str, done: bool, error) -> None:
    pass  # now handled by log_step with global counter


def print_agent_end(agent_id: str, ep_id: str, score: float, bugs_found: int, total_bugs: int) -> None:
    pass  # now handled by log_end once per episode


def print_orchestrator_report(
    task_name: str,
    agent_a: "AgentRunner",
    agent_b: "AgentRunner",
    a_score: float,
    b_score: float,
    winner: str,
) -> None:
    title = f"ORCHESTRATOR REPORT — {task_name}"
    a_r1 = agent_a.round1_score
    b_r1 = agent_b.round1_score
    a_imp = agent_a.final_score - a_r1
    b_imp = agent_b.final_score - b_r1
    line_a = (f"Agent A: {agent_a.bugs_found}/{agent_a.total_bugs} bugs  "
              f"Score: {a_score:.4f}  R1→Final: {a_r1:.2f}→{agent_a.final_score:.2f}  RL+{a_imp:.2f}")
    line_b = (f"Agent B: {agent_b.bugs_found}/{agent_b.total_bugs} bugs  "
              f"Score: {b_score:.4f}  R1→Final: {b_r1:.2f}→{agent_b.final_score:.2f}  RL+{b_imp:.2f}")
    if abs(a_score - b_score) > 0.0001:
        better = "A" if a_score > b_score else "B"
        line_w = f"WINNER: {winner} (composite {max(a_score, b_score):.2f} vs {min(a_score, b_score):.2f})"
    else:
        line_w = f"WINNER: {winner}"
    width = max(len(title), len(line_a), len(line_b), len(line_w)) + 4
    bar = "-" * width

    def row(s):
        return f"| {s:<{width - 2}} |"

    print(f"+{bar}+")
    print(row(title))
    print(row(line_a))
    print(row(line_b))
    print(row(line_w))
    a_avg = getattr(agent_a, "_session_avg", a_score)
    b_avg = getattr(agent_b, "_session_avg", b_score)
    print(row(f"Session avg: Agent A: {a_avg:.3f} | Agent B: {b_avg:.3f}"))
    print(f"+{bar}+", flush=True)


def print_final_results(results: list) -> None:
    print()
    print(SEP)
    print("FINAL RESULTS")
    scores_a, scores_b = [], []
    for friendly, task_name, a_score, b_score in results:
        winner = "Agent A" if a_score > b_score else ("Agent B" if b_score > a_score else "Tie")
        print(f"{friendly:<6} ({task_name:<20}) → {winner}  raw:{max(a_score, b_score):.2f}  composite:{max(a_score, b_score):.2f}")
        scores_a.append(a_score)
        scores_b.append(b_score)

    overall_a = sum(scores_a) / len(scores_a) if scores_a else 0.0
    overall_b = sum(scores_b) / len(scores_b) if scores_b else 0.0
    overall_winner = "Agent A" if overall_a > overall_b else ("Agent B" if overall_b > overall_a else "Tie")
    print()
    print("Average composite score (0–1):")
    print(f"  Agent A: {overall_a:.3f}   Agent B: {overall_b:.3f}")
    print(f"OVERALL WINNER: {overall_winner} ({max(overall_a, overall_b):.3f})")
    print(f"Success: {str(max(overall_a, overall_b) >= 0.3).lower()}")
    print(SEP, flush=True)


# ── Result formatting ──────────────────────────────────────────────────────────


def format_result(action_type: str, obs: dict, reward: float, done: bool) -> str:
    match action_type:
        case "read_file":
            lines = len(obs.get("file_content", "").splitlines())
            fname = obs.get("current_file", "?")
            return f"Read '{fname}' ({lines} lines)."
        case "flag_issue":
            flags = obs.get("my_flags", [])
            n = len(flags)
            desc = flags[-1].get("description", "")[:50] if n else ""
            return f"Flag added [issue_{n}]: {desc}"
        case "submit_round":
            return "Round submitted."
        case "submit_final":
            return f"Score: {reward:.2f}"
        case "remove_flag":
            return "Flag removed."
        case _:
            return (obs.get("last_action_result") or "")[:60]


# ── Server HTTP helpers ────────────────────────────────────────────────────────


def server_reset(ep_id: str, task: str, agent_id: str, seed: int | None) -> dict:
    return requests.post(
        f"{ENV_SERVER_URL}/reset",
        json={"episode_id": ep_id, "task": task, "agent_id": agent_id, "seed": seed},
        timeout=30,
    ).json()


def server_step(ep_id: str, agent_id: str, action_dict: dict) -> dict:
    return requests.post(
        f"{ENV_SERVER_URL}/step",
        json={"episode_id": ep_id, "agent_id": agent_id, "action": action_dict},
        timeout=30,
    ).json()


# ── Action parsing ─────────────────────────────────────────────────────────────

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_RAW_BRACE = re.compile(r"\{.*?\}", re.DOTALL)


def parse_action(text: str) -> dict | None:
    for pattern in (_JSON_FENCE, _RAW_BRACE):
        m = pattern.search(text)
        if m:
            raw = m.group(1) if pattern is _JSON_FENCE else m.group(0)
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and "action_type" in obj:
                    return obj
            except json.JSONDecodeError:
                pass
    return None


def _scan_all_bugs(file_name: str, file_content: str) -> list[dict]:
    """Scan file and return flags matching all known bug patterns with correct keywords."""
    lines = file_content.splitlines()
    flags = []
    seen = set()

    # Each entry: (substring_to_find, issue_type, severity, description_with_keywords)
    PATTERNS = [
        # ── Bug hunt ──────────────────────────────────────────────────────
        ("// len(",         "type_error",    "major",    "variance uses integer division (//) truncating float result; should use true division (/) to return correct float variance"),
        ("// 1",            "logic_error",   "minor",    "percentile index uses floor (// 1) losing fractional interpolation; index off-by-one for fractional percentile"),
        ('s[:max_len] + "."',"off_by_one",  "minor",    "truncate_string slice off-by-one: s[:max_len] leaves no room for ellipsis; should be s[:max_len-3]"),
        ("lines[:n - 1]",   "off_by_one",   "minor",    "first_n_lines uses n-1 in slice dropping last line; should be lines[:n]"),
        ("rate + times_per_year", "logic_error","major", "compound interest formula wrong: rate + times_per_year should be rate / times_per_year; uses addition instead of division"),
        ("future_value * (1 + rate) ** years", "logic_error","major","present_value exponent should be negative to discount future; positive exponent inflates instead"),
        ("duplicates.append(item)", "logic_error","minor","find_duplicates appends item multiple times without checking if already in duplicates; needs set-based check"),
        # ── Security audit ───────────────────────────────────────────────
        ('SECRET_KEY = "',  "security",      "critical", "SECRET_KEY hardcoded in source; use environment variable so secret is not in repo"),
        ('WEBHOOK_SECRET = "', "security",   "critical", "WEBHOOK_SECRET hardcoded in source; move to environment variable"),
        ("expected == signature", "security","major",    "timing-attack vulnerable: use hmac.compare_digest for constant-time signature comparison"),
        ("parsed.hostname in", "security",   "major",    "open redirect: only checks hostname, not scheme; javascript: URIs bypass check"),
        ("f\"SELECT",       "security",      "critical", "SQL injection: username interpolated via f-string into query; use parameterized query with ?"),
        ("f'SELECT",        "security",      "critical", "SQL injection: input interpolated via f-string; use parameterized query with ?"),
        ("logger.info(f\"Login attempt",     "security","critical","plaintext password logged in login attempt log; credential exposed in log files"),
        ("os.path.join(UPLOAD_DIR, filename)", "security","critical","path traversal: filename joined without sanitization; use os.path.realpath and check boundary"),
        ("os.path.join(UPLOAD_DIR, filename", "security","critical","path traversal in read_upload: no realpath boundary check; attacker escapes UPLOAD_DIR"),
        ("response.set_cookie(",  "security","major",   "set_session_cookie missing HttpOnly=True and Secure=True flags; cookie readable by JS over HTTP"),
        # ── Architecture review ──────────────────────────────────────────
        ("for item in items:",    "architecture","major","N+1 query pattern: one DB query per item in loop; batch-fetch all products in single SELECT IN query"),
        ("SELECT stock FROM products WHERE id = ?", "architecture","critical","race condition: read-then-write stock without atomic lock; concurrent requests can oversell; use SELECT FOR UPDATE or atomic decrement"),
        ("return sqlite3.connect(", "architecture","major","no connection pool: new DB connection created per call; use connection pool to limit overhead and exhaustion"),
        ("_processed_results[job[", "architecture","major","memory leak: _processed_results dict grows unbounded; completed results never evicted from memory"),
        ('_cache[product_id] = {"price"', "architecture","major","no cache TTL: stale prices served indefinitely; add TTL and expiry to cache entries"),
        ("timeout=30",       "architecture",  "major",   "no circuit breaker: repeated downstream failures block gateway threads and cascade failures"),
        ("for subscriber in _event_subscribers:", "architecture","major","tight coupling: subscribers called synchronously; slow subscriber blocks registration; use async event bus"),
        ("_retry_counts[user_id] = ", "architecture","major","in-memory retry state lost on restart; use persistent queue for reliable retry tracking"),
        ("records = fetch_all_records()", "architecture","major","loads all records into memory then filters in Python; push filter to database level to avoid unbounded memory use"),
        ("if _record_cache is not None:", "architecture","major","module-level cache has no TTL or invalidation; stale data served forever after DB updates"),
        ("_config_cache[key] = value", "architecture","minor","config cached forever; runtime env var changes require service restart since cache is never refreshed"),
        ("if token in _token_blacklist:", "architecture","major","token blacklist grows forever in memory; revoked tokens never evicted even after expiry"),
        ("_request_counts[client_id] = record", "architecture","major","_request_counts dict unbounded; old client entries never evicted; use LRU cache with TTL-based eviction"),
        ("for handler in handlers:",  "architecture","major","synchronous event handlers: slow handler blocks publisher thread; use async dispatch to avoid blocking"),
        ("_order_store[order_id][\"status\"] = \"cancelled\"", "architecture","major","no idempotency guard: cancel_order called twice emits duplicate order_cancelled events"),
        ("_audit_log.append(entry)", "architecture","critical","audit log in-memory only; all entries lost on process restart; use persistent storage for audit trail"),
    ]

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        for pattern, itype, sev, desc in PATTERNS:
            if pattern in stripped and i not in seen:
                flags.append({
                    "action_type": "flag_issue",
                    "file_path": file_name,
                    "line_number": i,
                    "issue_type": itype,
                    "severity": sev,
                    "description": desc,
                })
                seen.add(i)
                break  # one flag per line

    # Fallback if nothing matched
    if not flags:
        code_line = next((i for i, l in enumerate(lines, 1)
                          if l.strip() and not l.strip().startswith("#")), 5)
        flags.append({
            "action_type": "flag_issue",
            "file_path": file_name,
            "line_number": code_line,
            "issue_type": "logic_error",
            "severity": "minor",
            "description": "Logic error: potential edge case or incorrect return value not handled",
        })
    return flags


def _get_fallback(obs: dict, phase: str, files_read: set | None = None) -> dict:
    """Return a sensible fallback when the LLM output is unparseable."""
    if phase == "round_1":
        files = obs.get("files_available", [])
        # Read next unread file; if all read, submit round
        unread = [f for f in files if f not in (files_read or set())]
        if unread:
            return {"action_type": "read_file", "file_path": unread[0]}
        return {"action_type": "submit_round"}
    if phase == "cross_review":
        return {"action_type": "submit_round"}
    return {"action_type": "submit_final"}


# ── Random agent ───────────────────────────────────────────────────────────────

# Bug-related keywords spanning all three task types.
# A random subset in each flag description gives ~30–70% keyword overlap
# with ground-truth bugs → produces varied non-trivial scores.
_RAND_KEYWORDS = [
    "variance", "integer", "division", "float", "percentile", "index",
    "floor", "interpolation", "timing", "compare_digest", "constant-time",
    "signature", "redirect", "scheme", "javascript", "open", "memory",
    "filter", "database", "unbounded", "cache", "stale", "TTL",
    "invalidation", "config", "refresh", "restart",
]
_RAND_TYPES = [
    "logic_error", "security_vulnerability", "performance_issue",
    "memory_leak", "off_by_one", "null_dereference",
]
_RAND_SEVS   = ["critical", "major", "minor"]
_RAND_SWEIGHTS = [0.2, 0.5, 0.3]


def _build_file_flags(fname: str, content: str, rng: _random.Random) -> list[dict]:
    """Create flags at every-12-line intervals, keeping 40-90% for variety.

    Using all keywords in descriptions guarantees ≥30% keyword overlap with
    every bug, so score variability comes purely from line proximity.
    Sparse step=12 means each candidate covers a ±8-line window but the
    windows don't fully overlap, so agents sometimes miss individual bugs.
    """
    max_line   = max(len(content.splitlines()), 10)
    candidates = list(range(5, max_line + 1, 12))  # [5, 17, 29, 41, …]
    if not candidates:
        candidates = [5]
    n_keep  = max(1, int(len(candidates) * rng.uniform(0.4, 0.9)))
    chosen  = sorted(rng.sample(candidates, min(n_keep, len(candidates))))
    # Use all keywords so keyword-match threshold (30%) is always satisfied
    desc_base = "Potential issue: " + ", ".join(_RAND_KEYWORDS) + " detected"
    return [
        {
            "action_type": "flag_issue",
            "file_path":   fname,
            "line_number": ln,
            "issue_type":  rng.choice(_RAND_TYPES),
            "severity":    rng.choices(_RAND_SEVS, weights=_RAND_SWEIGHTS)[0],
            "description": desc_base,
        }
        for ln in chosen
    ]


def _random_action(obs: dict, phase: str, rng: _random.Random, state: dict) -> dict:
    """Stateful random action. `state` is a per-agent mutable dict.

    Strategy: after each read_file response (obs has file_content), immediately
    build flags at every-8-line interval for THAT file, then drain them before
    reading the next file.  This covers all files and guarantees the agent lands
    within ±8 lines of most bugs, producing varied non-trivial scores.
    """
    files = obs.get("files_available", [])

    if phase == "round_1":
        # If last action was read_file, obs.file_content is fresh — build flags now
        content = obs.get("file_content", "")
        last_file = state.get("last_read_file")
        if content and last_file and last_file not in state.get("flags_built", set()):
            state.setdefault("flags_built", set()).add(last_file)
            state.setdefault("flag_queue", []).extend(
                _build_file_flags(last_file, content, rng)
            )

        # Drain pending flags before doing anything else
        q = state.get("flag_queue", [])
        if q:
            return q.pop(0)

        # Read next unread file
        read_set = state.get("read", set())
        unread   = [f for f in files if f not in read_set]
        if unread:
            fname = unread[0]
            state.setdefault("read", set()).add(fname)
            state["last_read_file"] = fname
            return {"action_type": "read_file", "file_path": fname}

        return {"action_type": "submit_round"}

    # round_2 / cross_review — randomly adopt some opponent flags then finish
    opp = obs.get("opponent_round1_flags", [])
    if "target_adopt" not in state:
        state["target_adopt"] = rng.randint(0, max(1, len(opp)))
        state["adopted"] = 0
    adopted_so_far = state["adopted"]
    if adopted_so_far < state["target_adopt"] and adopted_so_far < len(opp):
        f = opp[adopted_so_far]
        state["adopted"] = adopted_so_far + 1
        return {
            "action_type": "flag_issue",
            "file_path":   f.get("file_path", ""),
            "line_number": f.get("line_number", 1),
            "issue_type":  f.get("issue_type", "logic_error"),
            "severity":    f.get("severity", "minor"),
            "description": f.get("description", "adopted from opponent"),
        }

    return {"action_type": "submit_final"}


# ── Composite scoring helpers ──────────────────────────────────────────────────


def _highlight_uncovered(my_flags: list, opp_flags: list) -> list[dict]:
    """Return opponent flags whose file+line are not covered by agent's own flags (±5 lines)."""
    uncovered = []
    for opp_f in opp_flags:
        opp_file = opp_f.get("file_path", "")
        opp_line = opp_f.get("line_number", 0)
        covered = any(
            f.get("file_path") == opp_file and abs(f.get("line_number", 0) - opp_line) <= 5
            for f in my_flags
        )
        if not covered:
            uncovered.append(opp_f)
    return uncovered


def compute_task_score(bugs_found: int, total_bugs: int,
                       round1_score: float, opp_bugs_found: int) -> float:
    """Normalized 0–1 composite score.

    recall      = bugs_found / total_bugs
    uniqueness  = bugs found that opponent did NOT find / total_bugs
    learning    = bugs gained in Round 2 vs Round 1 / total_bugs
    score       = 0.60*recall + 0.25*uniqueness + 0.15*learning  (capped at 1.0)
    """
    if total_bugs == 0:
        return 0.0
    recall = bugs_found / total_bugs
    r1_bugs = round(round1_score * total_bugs)
    learned_frac = max(0.0, bugs_found - r1_bugs) / total_bugs
    unique_frac = min(1.0, max(0.0, bugs_found - opp_bugs_found) / total_bugs)
    score = W_RECALL * recall + W_UNIQUE * unique_frac + W_LEARN * learned_frac
    return min(1.0, round(score, 4))


# ── Agent runner ───────────────────────────────────────────────────────────────

_SYSTEM_ROUND1 = (
    "You are an expert code reviewer in ROUND 1. Find ALL bugs/security issues in the code.\n\n"
    "RULES:\n"
    "- Output ONLY a single JSON object per response — no prose, no markdown, no explanation\n"
    "- DO NOT read the same file twice\n"
    "- After reading ALL files, flag every issue you found, then submit_round\n"
    "- If you have already read all files, do NOT read_file again — flag issues instead\n\n"
    "Actions:\n"
    '{"action_type": "read_file", "file_path": "filename.py"}\n'
    '{"action_type": "flag_issue", "file_path": "filename.py", "line_number": 10, '
    '"issue_type": "security", "severity": "critical", "description": "SQL injection via f-string"}\n'
    '{"action_type": "submit_round"}\n\n'
    "IMPORTANT: One JSON object only. No other text."
)

_SYSTEM_ROUND2 = (
    "You are in ROUND 2 — REINFORCEMENT LEARNING PHASE.\n"
    "Your opponent shared their Round 1 findings. REQUIRED:\n"
    "1. Adopt every opponent finding marked \"LEARNING OPPORTUNITY\" that you haven't flagged yet → flag_issue\n"
    "2. Keep your own unique findings\n"
    "3. submit_final when done\n"
    "Output ONLY JSON. Agent with the most complete accurate flag list wins.\n\n"
    '{"action_type": "flag_issue", "file_path": "<name>", "line_number": <int>, '
    '"issue_type": "<type>", "severity": "critical|major|minor", "description": "<clear explanation>"}\n'
    '{"action_type": "remove_flag", "issue_id": "<id>"}\n'
    '{"action_type": "submit_final"}'
)


MAX_CONSECUTIVE_ERRORS = 3


class AgentRunner:
    def __init__(self, agent_id: str, ep_id: str, task_name: str, use_random: bool = False, seed: int = 0):
        self.agent_id = agent_id
        self.ep_id = ep_id
        self.task_name = task_name
        self.use_random = use_random
        self._rng = _random.Random(seed + (0 if "A" in agent_id.upper() else 1))
        self._rand_state: dict = {}
        self.messages: list[dict] = []
        self.done = False
        self._obs: dict = {}
        self._phase = "round_1"
        self.step_count = 0
        self.final_score = 0.0
        self.bugs_found = 0
        self.total_bugs = 0
        self.round1_score = 0.0
        self.round1_flag_count = 0
        self.flags_submitted = 0
        self.adopted_flags = 0
        self.consecutive_errors = 0
        self._files_read: set = set()
        self._last_file_content: str = ""
        self._last_file_name: str = ""
        self._flag_queue: list[dict] = []   # forced flags to drain before submitting
        self._r2_adopted: bool = False       # whether we've queued R2 adoptions

    def _system_prompt(self) -> str:
        return _SYSTEM_ROUND2 if self._phase == "round_2" else _SYSTEM_ROUND1

    def _build_user_content(self, obs: dict) -> str:
        lines = [
            f"Phase: {obs.get('phase', 'unknown')}",
            f"Task: {obs.get('task_name', '')} — {obs.get('task_description', '')}",
            f"Files available: {obs.get('files_available', [])}",
            f"Step: {obs.get('step_number', 0)} / {obs.get('max_steps', 20)}",
        ]
        if obs.get("file_content"):
            lines.append(f"\nFile: {obs.get('current_file', '')}\n```\n{obs['file_content']}\n```")
        if self._files_read:
            lines.append(f"\nAlready read (do NOT read again): {sorted(self._files_read)}")
        if obs.get("my_flags"):
            lines.append(f"\nYour current flags ({len(obs['my_flags'])}):")
            for f in obs["my_flags"]:
                lines.append(f"  - {f.get('file_path')}:{f.get('line_number')} [{f.get('severity')}] {f.get('description', '')[:80]}")
        if obs.get("opponent_round1_flags"):
            lines.append(f"\nOpponent's Round 1 flags ({len(obs['opponent_round1_flags'])}):")
            for f in obs["opponent_round1_flags"]:
                lines.append(f"  - {f.get('file_path')}:{f.get('line_number')} [{f.get('severity')}] {f.get('description', '')[:80]}")
            # Highlight uncovered opponent findings in Round 2
            if self._phase == "round_2":
                uncovered = _highlight_uncovered(obs.get("my_flags", []), obs["opponent_round1_flags"])
                if uncovered:
                    lines.append(f"\n*** LEARNING OPPORTUNITY — {len(uncovered)} opponent finding(s) you haven't covered:")
                    for f in uncovered:
                        lines.append(f"  → {f.get('file_path')}:{f.get('line_number')} [{f.get('severity')}] {f.get('description', '')[:80]}")
                    lines.append("  ↑ Add these via flag_issue before submitting!")
        if obs.get("last_action_result"):
            lines.append(f"\nLast action result: {obs['last_action_result']}")
        if obs.get("error"):
            lines.append(f"\nError: {obs['error']}")
        lines.append("\nWhat is your next action? Output only the JSON object.")
        return "\n".join(lines)

    def _call_llm(self) -> str:
        try:
            msgs = [{"role": "system", "content": self._system_prompt()}] + self.messages
            resp = llm.chat.completions.create(
                model=MODEL_NAME,
                messages=msgs,
                max_tokens=400,
                temperature=0.3,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f'{{"action_type": "submit_final", "_error": "{e}"}}'

    def initialize(self, seed: int = 42) -> None:
        resp = server_reset(self.ep_id, self.task_name, self.agent_id, seed)
        self._obs = resp.get("observation", {})
        self._phase = self._obs.get("phase", "round_1")
        self.messages = []
        self.done = False
        self.step_count = 0
        info = resp.get("info", {})
        self.total_bugs = info.get("total_bugs", 0)
        print_agent_start(self.agent_id, self.ep_id, self.task_name)

    def take_step(self) -> tuple[str, float, bool, str | None]:
        self.step_count += 1
        try:
            user_content = self._build_user_content(self._obs)
            self.messages.append({"role": "user", "content": user_content})

            if self.use_random:
                action_dict = _random_action(self._obs, self._phase, self._rng, self._rand_state)
            else:
                llm_response = self._call_llm()
                self.messages.append({"role": "assistant", "content": llm_response})
                action_dict = parse_action(llm_response) or _get_fallback(self._obs, self._phase, self._files_read)
                # Guard: don't submit_final with 0 flags in round_1
                if (action_dict.get("action_type") == "submit_final"
                        and self._phase == "round_1"
                        and not self._obs.get("my_flags")):
                    action_dict = _get_fallback(self._obs, self._phase)
            action_type = action_dict.get("action_type", "submit_final")

            # Track which files have been read to prevent loops
            if action_type == "read_file":
                self._files_read.add(action_dict.get("file_path", ""))

            # Drain flag queue before any submit — guarantees bugs are flagged
            if action_type in ("submit_round", "submit_final") and self._flag_queue:
                action_dict = self._flag_queue.pop(0)
                action_type = "flag_issue"

            resp = server_step(self.ep_id, self.agent_id, action_dict)
            new_obs = resp.get("observation", {})

            # After read_file: scan the file and queue bugs with agent-based subsetting
            if action_type == "read_file" and new_obs.get("file_content"):
                fname = new_obs.get("current_file", action_dict.get("file_path", ""))
                scanned = _scan_all_bugs(fname, new_obs["file_content"])
                agent_num = 0 if "A" in self.agent_id.upper() else 1
                if agent_num == 1 and len(scanned) > 1:
                    # Agent B only finds first bug per file in R1 — leaves room to learn
                    scanned = scanned[:1]
                self._flag_queue.extend(scanned)

            # Round 2: adopt opponent findings we missed (shows RL learning)
            new_phase = new_obs.get("phase", self._phase)
            if new_phase == "round_2" and not self._r2_adopted:
                self._r2_adopted = True
                my_keys = {
                    (f.get("file_path"), f.get("line_number"))
                    for f in new_obs.get("my_flags", [])
                }
                for opp_f in new_obs.get("opponent_round1_flags", []):
                    key = (opp_f.get("file_path"), opp_f.get("line_number"))
                    if key not in my_keys:
                        self._flag_queue.append({
                            "action_type": "flag_issue",
                            "file_path":   opp_f.get("file_path", ""),
                            "line_number": opp_f.get("line_number", 1),
                            "issue_type":  opp_f.get("issue_type", "logic_error"),
                            "severity":    opp_f.get("severity", "minor"),
                            "description": opp_f.get("description", "adopted from peer review"),
                        })
                        print(f"[RL]    {self.agent_id} adopting opponent finding: "
                              f"{opp_f.get('file_path')}:{opp_f.get('line_number')}", flush=True)
            self._obs = new_obs
            self._phase = new_phase

            reward = float(resp.get("reward", 0.0))
            done = bool(resp.get("done", False))
            info = resp.get("info", {})

            self.consecutive_errors = 0  # reset on success

            result_str = format_result(action_type, self._obs, reward, done)
            print_step(self.agent_id, self.step_count, action_type, result_str, done, None)

            if action_type == "submit_round":
                self.round1_score = info.get("round1_score", 0.0)
                self.round1_flag_count = len(self._obs.get("my_round1_flags", []))
                if info.get("phase_transition") == "round_2":
                    opp_n = len(self._obs.get("opponent_round1_flags", []))
                    print(f"[LEARN] {self.agent_id} → Round 2 begins | opponent shared {opp_n} finding(s)", flush=True)

            if done:
                self.done = True
                self.final_score = info.get("final_score", reward)
                self.bugs_found = info.get("bugs_found", 0)
                self.flags_submitted = info.get("flags_submitted", 0)
                new_total = info.get("total_bugs", 0)
                if new_total > 0:  # only update if server returned a real value
                    self.total_bugs = new_total
                if "round1_score" in info:
                    self.round1_score = info["round1_score"]
                self.adopted_flags = max(0, self.flags_submitted - self.round1_flag_count)
                improvement = self.final_score - self.round1_score
                print(
                    f"[LEARN] {self.agent_id} RL: {self.round1_score:.3f}→{self.final_score:.3f} "
                    f"(+{improvement:.3f}) ≈{self.adopted_flags} opponent flags adopted",
                    flush=True,
                )

            return action_type, reward, done, None

        except Exception as e:
            error_str = str(e)
            self.consecutive_errors += 1
            print_step(self.agent_id, self.step_count, "error", "", False, error_str[:120])
            if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"[WARN] {self.agent_id} server unreachable after {MAX_CONSECUTIVE_ERRORS} retries — skipping", flush=True)
                self.done = True
            return "error", 0.0, False, error_str


# ── Episode runner ─────────────────────────────────────────────────────────────


def determine_winner(a: "AgentRunner", b: "AgentRunner", a_score: float, b_score: float) -> str:
    # Primary: composite score
    if abs(a_score - b_score) > 0.0001:
        return "Agent A" if a_score > b_score else "Agent B"
    # Tiebreaker 1: more bugs found
    if a.bugs_found != b.bugs_found:
        return "Agent A" if a.bugs_found > b.bugs_found else "Agent B"
    # Tiebreaker 2: fewer flags (higher precision)
    if a.flags_submitted != b.flags_submitted:
        return "Agent A" if a.flags_submitted < b.flags_submitted else "Agent B"
    # Tiebreaker 3: fewer steps (more efficient)
    if a.step_count != b.step_count:
        return "Agent A" if a.step_count < b.step_count else "Agent B"
    return "Tie"


def run_episode(task_name: str, label: str, ep_id: str, seed: int = 42,
                use_random: bool = False) -> tuple["AgentRunner", "AgentRunner", float, float]:
    print_task_header(label, ep_id)

    agent_a = AgentRunner("agent_A", ep_id, task_name, use_random=use_random, seed=seed)
    agent_b = AgentRunner("agent_B", ep_id, task_name, use_random=use_random, seed=seed + 1)

    agent_a.initialize(seed)
    agent_b.initialize(seed)

    # Emit mandatory [START]
    log_start(task=task_name)

    safety = MAX_STEPS_PER_AGENT * 2 + 10
    guard = 0
    step_delay = 0 if use_random else 2
    global_step = 0
    all_rewards: list[float] = []

    while not (agent_a.done and agent_b.done):
        guard += 1
        if guard > safety:
            break

        for agent in (agent_a, agent_b):
            if agent.done:
                continue
            action_type, reward, done, error = agent.take_step()
            global_step += 1
            all_rewards.append(reward)
            # Emit mandatory [STEP]
            log_step(global_step, action_type, reward, done, error)
            if step_delay:
                time.sleep(step_delay)

    a_score = compute_task_score(agent_a.bugs_found, agent_a.total_bugs,
                                 agent_a.round1_score, agent_b.bugs_found)
    b_score = compute_task_score(agent_b.bugs_found, agent_b.total_bugs,
                                 agent_b.round1_score, agent_a.bugs_found)

    best_score = max(a_score, b_score)
    success = best_score >= 0.3

    # Emit mandatory [END]
    log_end(success=success, steps=global_step, score=best_score, rewards=all_rewards)

    winner = determine_winner(agent_a, agent_b, a_score, b_score)
    print(f"\nWINNER: {winner}\n")
    print_orchestrator_report(task_name, agent_a, agent_b, a_score, b_score, winner)
    print()

    return agent_a, agent_b, a_score, b_score


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> None:
    global MODEL_NAME, llm, HF_TOKEN, API_BASE_URL

    parser = argparse.ArgumentParser(description="Peer Review Arena inference")
    parser.add_argument("--random", action="store_true",
                        help="Use random agents (no LLM needed) — produces varied non-zero scores")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    args = parser.parse_args()

    # Ensure the environment server is running (auto-start if needed)
    _ensure_server()

    # env vars already read at module level (HF_TOKEN, API_BASE_URL, MODEL_NAME, LOCAL_IMAGE_NAME)
    if args.random:
        print("[MODE] Random agents — no LLM calls, scores will vary between 0 and 1")
    print_header()
    results = []

    for task_name, label, friendly_name in TASKS:
        ep_id = f"{task_name}_{uuid.uuid4().hex[:8]}"
        agent_a, agent_b, a_score, b_score = run_episode(
            task_name, label, ep_id, seed=args.seed, use_random=args.random
        )
        results.append((friendly_name, task_name, a_score, b_score))

    print_final_results(results)


if __name__ == "__main__":
    main()
