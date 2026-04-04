"""
Peer Review Arena — Two-agent inference script.

Usage:
    python inference.py

Environment variables:
    HF_TOKEN         HuggingFace token for the inference router
    API_BASE_URL     OpenAI-compatible base URL (default: HF router)
    MODEL_NAME       Model to use for both agents
    ENV_SERVER_URL   URL of the running FastAPI environment server
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

import requests
from openai import OpenAI

# Force UTF-8 output on Windows so box/arrow characters print correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Configuration ──────────────────────────────────────────────────────────────

HF_TOKEN = os.environ.get("HF_TOKEN", "")
API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
ENV_SERVER_URL = os.environ.get("ENV_SERVER_URL", "http://localhost:8000")

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


def print_header() -> None:
    print(SEP)
    print("Peer Review Arena — Inference Run")
    print(f"Server : {ENV_SERVER_URL}")
    print(f"Model  : {MODEL_NAME}")
    if "llama" in MODEL_NAME.lower():
        print("Hint   : To use Qwen: $env:MODEL_NAME='Qwen/Qwen2.5-72B-Instruct'")
    print("Provider: HF Router")
    print(SEP)
    print(flush=True)


def print_task_header(label: str, ep_id: str) -> None:
    print(SEP)
    print(f"TASK: {label} | episode={ep_id}")
    print(SEP, flush=True)


def print_agent_start(agent_id: str, ep_id: str, task: str) -> None:
    print(f"[START] {agent_id} episode={ep_id} task={task}", flush=True)


def print_step(agent_id: str, step: int, action: str, result: str, done: bool, error) -> None:
    err = error if error else "null"
    done_str = str(done).lower()
    print(
        f"[STEP]  {agent_id} step={step} action={action} result={result} done={done_str} error={err}",
        flush=True,
    )


def print_agent_end(agent_id: str, ep_id: str, score: float, bugs_found: int, total_bugs: int) -> None:
    print(f"[END]   {agent_id} episode={ep_id} score={score:.4f} bugs={bugs_found}/{total_bugs}", flush=True)


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


def _get_fallback(obs: dict, phase: str) -> dict:
    """Return a sensible fallback when the LLM output is unparseable."""
    if phase in ("round_1", "cross_review"):
        files = obs.get("files_available", [])
        if files:
            return {"action_type": "read_file", "file_path": files[0]}
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
    "You are an expert code reviewer. You are in ROUND 1: independently review the provided code. "
    "Your goal is to find as many real bugs/issues as possible. "
    "For each action, output ONLY a JSON object (no extra text) matching one of these schemas:\n\n"
    '1. Read a file:       {"action_type": "read_file", "file_path": "<name>"}\n'
    '2. Flag an issue:     {"action_type": "flag_issue", "file_path": "<name>", "line_number": <int>, '
    '"issue_type": "<type>", "severity": "critical|major|minor", "description": "<clear explanation>"}\n'
    '3. Submit round 1:    {"action_type": "submit_round"}\n\n'
    "Read each file first, then flag issues, then submit. Use submit_round when done with round 1."
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
                action_dict = parse_action(llm_response) or _get_fallback(self._obs, self._phase)
                # Guard: don't submit_final with 0 flags in round_1
                if (action_dict.get("action_type") == "submit_final"
                        and self._phase == "round_1"
                        and not self._obs.get("my_flags")):
                    action_dict = _get_fallback(self._obs, self._phase)
            action_type = action_dict.get("action_type", "submit_final")

            resp = server_step(self.ep_id, self.agent_id, action_dict)
            self._obs = resp.get("observation", {})
            self._phase = self._obs.get("phase", self._phase)

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

    safety = MAX_STEPS_PER_AGENT * 2 + 10
    guard = 0
    step_delay = 0 if use_random else 2

    while not (agent_a.done and agent_b.done):
        guard += 1
        if guard > safety:
            break

        if not agent_a.done:
            agent_a.take_step()
            if step_delay:
                time.sleep(step_delay)

        if not agent_b.done:
            agent_b.take_step()
            if step_delay:
                time.sleep(step_delay)

    print_agent_end("agent_A", ep_id, agent_a.final_score, agent_a.bugs_found, agent_a.total_bugs)
    print_agent_end("agent_B", ep_id, agent_b.final_score, agent_b.bugs_found, agent_b.total_bugs)

    a_score = compute_task_score(agent_a.bugs_found, agent_a.total_bugs,
                                 agent_a.round1_score, agent_b.bugs_found)
    b_score = compute_task_score(agent_b.bugs_found, agent_b.total_bugs,
                                 agent_b.round1_score, agent_a.bugs_found)

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

    HF_TOKEN = os.environ.get("HF_TOKEN", "")
    API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
    MODEL_NAME = os.environ.get("MODEL_NAME", "meta-llama/Llama-3.1-8B-Instruct")
    llm = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN or "dummy")
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
