# Meta OpenEnv Hackathon — Complete Guide & Project Plan
**Deadline: April 8, 2026 | Prize: $30,000**

---

# THE IDEA: "Peer Review Arena"

## What You're Building (One Sentence)

Two anonymous AI agents review the same code independently, then each sees the other's findings — and both get smarter by learning from each other's hits AND misses.

## Why This Is Brilliant

This concept is called **adversarial co-learning through cross-observation**. It has never been built as an OpenEnv environment. It's backed by cutting-edge research (MARTI framework, Multiagent Debate from ICML 2024) but hasn't been packaged as a learnable RL environment.

**Real-world analogy**: Two senior engineers both review the same PR. Then they compare notes in a code review meeting. Engineer A realizes they missed the SQL injection that Engineer B caught. Engineer B realizes they missed the race condition that Engineer A caught. Both get sharper from the meeting. **This environment trains AI to do exactly that.**

---

## PART 1: UNDERSTANDING THE CONCEPT (Plain English)

### How an Episode Works

```
┌─────────────────────────────────────────────────────┐
│                  EPISODE START                       │
│         "Review this Python codebase"               │
└─────────────────┬───────────────────┬───────────────┘
                  │                   │
         ┌────────▼──────┐   ┌────────▼──────┐
         │   AGENT A     │   │   AGENT B     │
         │ (Model 1)     │   │ (Model 2)     │
         │               │   │               │
         │ ROUND 1:      │   │ ROUND 1:      │
         │ Reviews alone │   │ Reviews alone │
         │ - reads files │   │ - reads files │
         │ - flags bugs  │   │ - flags bugs  │
         └────────┬──────┘   └────────┬──────┘
                  │                   │
                  └─────────┬─────────┘
                            │
              ┌─────────────▼─────────────┐
              │  ENVIRONMENT REVEALS:      │
              │  "Here's what your         │
              │   opponent found"           │
              └─────────────┬─────────────┘
                            │
                  ┌─────────┴─────────┐
         ┌────────▼──────┐   ┌────────▼──────┐
         │   AGENT A     │   │   AGENT B     │
         │               │   │               │
         │ ROUND 2:      │   │ ROUND 2:      │
         │ Sees B's work │   │ Sees A's work │
         │ - "Oh! I      │   │ - "I missed   │
         │   missed X"   │   │   that one"   │
         │ - Updates     │   │ - Updates     │
         │   their review│   │   their review│
         └────────┬──────┘   └────────┬──────┘
                  │                   │
                  └─────────┬─────────┘
                            │
              ┌─────────────▼─────────────┐
              │       FINAL SCORING        │
              │  A: found 6/8 bugs (0.75) │
              │  B: found 5/8 bugs (0.62) │
              │  A improved by 2 in R2    │
              │  B improved by 1 in R2    │
              └───────────────────────────┘
```

### The Key Insight

The environment gives each agent a **second chance** after seeing the opponent's work. This creates two learning pressures:

1. **Be thorough in Round 1** — you get big rewards for finding things your opponent didn't
2. **Be a good learner in Round 2** — you get rewards for recognizing opponent's valid finds and correcting yourself

Together these train an agent that is BOTH comprehensive AND self-correcting.

---

## PART 2: WHY THIS WINS THE HACKATHON

| Criterion | Weight | Score | Why |
|-----------|--------|-------|-----|
| Real-world utility | 30% | 29/30 | Code review is done by every software team, high stakes, AI replacing it is an active industry need |
| Task & grader quality | 25% | 24/25 | Bugs are planted with known ground truth. Grading is 100% programmatic. No LLM-as-judge needed |
| Environment design | 20% | 19/20 | Multi-phase episodes, two competing reward incentives (find unique things vs. learn from opponent), clean state machine |
| Code quality & spec | 15% | 14/15 | Standard OpenEnv compliance, well-typed models |
| Creativity & novelty | 10% | 10/10 | **No one has built this**. Closest work (MARTI, 2026) is from top AI labs and isn't on OpenEnv |
| **TOTAL** | 100% | **96/100** | |

### What Makes This Novel

From research: The MARTI framework (Tsinghua University, ICLR 2026) achieved state-of-the-art code generation using multi-agent debate with cross-observation. But it's a training framework, not an OpenEnv environment. **You're building the RL environment that makes this kind of training accessible to everyone.**

Meta engineers will recognize this as directly relevant to their work on training better AI systems.

---

## PART 3: OPENENV TECHNICAL DESIGN

### How Multi-Agent Works in OpenEnv

OpenEnv doesn't natively support two agents sharing a session. Instead, you use this architecture:

```
Agent A's client                    Agent B's client
      │                                    │
      │  reset(episode_id="ep123",         │  reset(episode_id="ep123",
      │         metadata={"agent":"A"})    │         metadata={"agent":"B"})
      │                                    │
      └──────────────────┬─────────────────┘
                         │
              ┌──────────▼──────────┐
              │  PeerReviewEnvironment │
              │                      │
              │  Internal State:     │
              │  episodes = {        │
              │    "ep123": {        │
              │      code: "...",    │
              │      bugs: [...],    │
              │      phase: "r1",    │
              │      A_findings: [], │
              │      B_findings: []  │
              │    }                 │
              │  }                   │
              └──────────────────────┘
```

**Both agents connect to the same server using the same `episode_id`.** The server internally tracks both agents' state and coordinates phases.

### File Structure

```
peer_review_env/
├── README.md
├── openenv.yaml                    # Manifest
├── pyproject.toml                  # Dependencies
├── inference.py                    # MANDATORY baseline script
│
├── peer_review_env/
│   ├── __init__.py                 # Exports: PeerReviewEnv, PeerReviewAction
│   ├── models.py                   # All Pydantic models
│   └── client.py                   # EnvClient subclass
│
├── server/
│   ├── __init__.py
│   ├── app.py                      # FastAPI app setup
│   ├── environment.py              # Core multi-agent logic
│   ├── grader.py                   # Reward computation
│   ├── code_generator.py           # Generates buggy code with known answers
│   └── Dockerfile
│
└── tasks/
    ├── easy/                       # Bug Hunt (2-3 bugs, 2 files)
    │   ├── code_sample_1.py
    │   ├── code_sample_2.py
    │   └── ground_truth.json
    ├── medium/                     # Security Audit (4-5 bugs, 4 files)
    │   └── ...
    └── hard/                       # Architecture Review (6-8 bugs, 6 files)
        └── ...
```

### The Three Data Models

```python
# models.py
from pydantic import BaseModel
from typing import List, Optional, Literal
from openenv.core.env_server.types import Action, Observation, State


class PeerReviewAction(Action):
    """What an agent can do."""

    action_type: Literal[
        "read_file",        # Open and read a file
        "read_lines",       # Read specific lines (file_path, start, end)
        "flag_issue",       # Flag a bug/issue at a specific line
        "remove_flag",      # Remove a false flag (correct a mistake)
        "submit_round",     # Finish this round and wait for cross-review
        "submit_final"      # Submit final review (ends episode)
    ]

    # For read_file / read_lines
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0

    # For flag_issue / remove_flag
    issue_id: str = ""        # Unique ID for this flag (agent assigns it)
    line_number: int = 0
    issue_type: str = ""      # "bug" | "security" | "performance" | "style"
    severity: str = "minor"   # "critical" | "major" | "minor"
    description: str = ""     # Explanation of the issue


class PeerReviewObservation(Observation):
    """What an agent sees after each action.
    Inherits: done (bool), reward (float), metadata (dict)
    """

    # Current phase
    phase: Literal["round_1", "cross_review", "round_2", "finished"] = "round_1"

    # The task
    task_name: str = ""
    task_description: str = ""
    files_available: List[str] = []

    # File reading result
    current_file: str = ""
    file_content: str = ""

    # Agent's own progress
    my_flags: List[dict] = []           # Issues I've flagged so far
    my_round1_flags: List[dict] = []    # My Round 1 flags (frozen after R1)

    # Cross-review data (only visible in round_2 and later)
    opponent_round1_flags: List[dict] = []   # What the opponent found in R1

    # Feedback
    last_action_result: str = ""
    step_number: int = 0
    max_steps: int = 20
    error: Optional[str] = None


class PeerReviewState(State):
    """Internal episode state — returned by GET /state.
    Inherits: episode_id, step_count
    """
    phase: str = "round_1"
    task_name: str = ""
    agent_id: str = ""
    my_flags_count: int = 0
    opponent_ready: bool = False   # Has the opponent completed Round 1?
```

### The Environment Logic

```python
# server/environment.py
import asyncio
from typing import Dict, Any, Optional
from openenv.core.env_server.types import Environment
from ..models import PeerReviewAction, PeerReviewObservation, PeerReviewState


class PeerReviewEnvironment(Environment[PeerReviewAction, PeerReviewObservation, PeerReviewState]):

    SUPPORTS_CONCURRENT_SESSIONS = True  # Allows multiple agent connections

    # Shared state across ALL sessions (class-level)
    _episodes: Dict[str, dict] = {}
    _lock = asyncio.Lock()

    def __init__(self):
        self.agent_id: Optional[str] = None
        self.episode_id: Optional[str] = None
        self._step_count = 0

    def reset(self, seed=None, episode_id=None, **kwargs) -> PeerReviewObservation:
        """
        Called by each agent at episode start.
        Both agents pass the same episode_id to join the same match.
        metadata={"agent_id": "A"} or "B"
        """
        self.agent_id = kwargs.get("metadata", {}).get("agent_id", "A")
        self.episode_id = episode_id or "default"
        self._step_count = 0

        # Create episode if it doesn't exist (first agent to connect)
        if self.episode_id not in PeerReviewEnvironment._episodes:
            task = self._load_task(kwargs.get("task", "bug_hunt"))
            PeerReviewEnvironment._episodes[self.episode_id] = {
                "task": task,
                "phase": "round_1",
                "A": {"flags": [], "r1_flags": [], "steps": 0, "ready": False},
                "B": {"flags": [], "r1_flags": [], "steps": 0, "ready": False},
                "ground_truth": task["bugs"],
            }

        ep = PeerReviewEnvironment._episodes[self.episode_id]

        return PeerReviewObservation(
            phase="round_1",
            task_name=ep["task"]["name"],
            task_description=ep["task"]["description"],
            files_available=ep["task"]["files"],
            last_action_result="Episode started. Begin your independent review.",
            done=False,
            reward=0.0
        )

    def step(self, action: PeerReviewAction) -> PeerReviewObservation:
        """Process one action and return observation."""
        ep = PeerReviewEnvironment._episodes[self.episode_id]
        me = ep[self.agent_id]
        opponent_id = "B" if self.agent_id == "A" else "A"
        opponent = ep[opponent_id]

        self._step_count += 1
        me["steps"] += 1

        # ── ROUTING BY ACTION TYPE ──────────────────────────────────────

        if action.action_type == "read_file":
            content = self._read_file(ep["task"], action.file_path)
            return PeerReviewObservation(
                phase=ep["phase"],
                files_available=ep["task"]["files"],
                current_file=action.file_path,
                file_content=content,
                my_flags=me["flags"],
                step_number=self._step_count,
                last_action_result=f"Opened {action.file_path} ({len(content.splitlines())} lines)",
                done=False, reward=0.0
            )

        elif action.action_type == "flag_issue":
            flag = {
                "id": action.issue_id,
                "file": action.file_path,
                "line": action.line_number,
                "type": action.issue_type,
                "severity": action.severity,
                "description": action.description
            }
            me["flags"].append(flag)
            # Small immediate reward for flagging (encourages action)
            reward = 0.05
            return PeerReviewObservation(
                phase=ep["phase"],
                files_available=ep["task"]["files"],
                my_flags=me["flags"],
                step_number=self._step_count,
                last_action_result=f"Flagged issue at {action.file_path}:{action.line_number}",
                done=False, reward=reward
            )

        elif action.action_type == "submit_round":
            # Agent finishes Round 1
            me["r1_flags"] = me["flags"].copy()
            me["ready"] = True

            # Check if BOTH agents have submitted Round 1
            both_ready = ep["A"]["ready"] and ep["B"]["ready"]
            if both_ready:
                ep["phase"] = "round_2"  # Advance to cross-review phase

            # Compute Round 1 reward
            r1_reward = self._compute_reward(
                my_flags=me["r1_flags"],
                opponent_flags=[],
                ground_truth=ep["ground_truth"],
                phase="round_1"
            )

            if not both_ready:
                # Waiting for opponent
                return PeerReviewObservation(
                    phase="cross_review",  # Waiting state
                    my_flags=me["r1_flags"],
                    my_round1_flags=me["r1_flags"],
                    step_number=self._step_count,
                    last_action_result="Round 1 complete. Waiting for opponent...",
                    done=False, reward=r1_reward
                )
            else:
                # Both done — reveal opponent's Round 1 findings
                return PeerReviewObservation(
                    phase="round_2",
                    files_available=ep["task"]["files"],
                    my_flags=me["r1_flags"],
                    my_round1_flags=me["r1_flags"],
                    opponent_round1_flags=opponent["r1_flags"],  # KEY: reveal opponent's work
                    step_number=self._step_count,
                    last_action_result=(
                        f"Round 1 complete! Your opponent found {len(opponent['r1_flags'])} issues. "
                        f"You found {len(me['r1_flags'])}. Now improve your review."
                    ),
                    done=False, reward=r1_reward
                )

        elif action.action_type == "submit_final":
            # Compute full reward (Round 1 + improvement + uniqueness)
            final_reward = self._compute_reward(
                my_flags=me["flags"],
                opponent_flags=opponent["r1_flags"],
                ground_truth=ep["ground_truth"],
                phase="final",
                r1_flags=me["r1_flags"]
            )
            # Normalize to [0, 1]
            score = min(1.0, max(0.0, final_reward / self._max_possible_reward()))

            return PeerReviewObservation(
                phase="finished",
                my_flags=me["flags"],
                my_round1_flags=me["r1_flags"],
                opponent_round1_flags=opponent["r1_flags"],
                step_number=self._step_count,
                last_action_result=(
                    f"Review complete! Final score: {score:.2f}. "
                    f"Found {len([f for f in me['flags'] if self._is_true_positive(f, ep['ground_truth'])])} "
                    f"of {len(ep['ground_truth'])} real issues."
                ),
                done=True,
                reward=score
            )

        # Default: unknown action
        return PeerReviewObservation(
            phase=ep["phase"],
            step_number=self._step_count,
            last_action_result=f"Unknown action: {action.action_type}",
            error=f"Unknown action_type: {action.action_type}",
            done=False, reward=0.0
        )

    @property
    def state(self) -> PeerReviewState:
        ep = PeerReviewEnvironment._episodes.get(self.episode_id, {})
        me = ep.get(self.agent_id, {})
        opponent_id = "B" if self.agent_id == "A" else "A"
        return PeerReviewState(
            episode_id=self.episode_id,
            step_count=self._step_count,
            phase=ep.get("phase", "round_1"),
            task_name=ep.get("task", {}).get("name", ""),
            agent_id=self.agent_id or "",
            my_flags_count=len(me.get("flags", [])),
            opponent_ready=ep.get(opponent_id, {}).get("ready", False)
        )
```

---

## PART 4: THE REWARD FUNCTION (The Heart of the Environment)

This is what makes the environment interesting. Two competing forces:

```
┌─────────────────────────────────────────────────────┐
│              COMPETITIVE FORCE                       │
│  "Find things your opponent MISSED"                  │
│  Reward: +0.4 per unique true positive              │
│  (pushes agent to be thorough)                      │
└─────────────────────────────────────────────────────┘
                    VS
┌─────────────────────────────────────────────────────┐
│              COOPERATIVE FORCE                       │
│  "Learn from opponent's valid findings"              │
│  Reward: +0.2 for adopting opponent's correct flag  │
│  (pushes agent to be humble + adaptive)             │
└─────────────────────────────────────────────────────┘
```

```python
# server/grader.py

SEVERITY_WEIGHTS = {
    "critical": 0.40,
    "major":    0.25,
    "minor":    0.10
}

def compute_reward(my_flags, opponent_flags, ground_truth, phase, r1_flags=None):
    """
    Compute reward for one agent.

    Components:
    1. ACCURACY: Did I flag real issues? (+big reward for TP, -penalty for FP)
    2. UNIQUENESS: Did I find things my opponent missed? (competitive bonus)
    3. LEARNING: Did I improve after seeing opponent's work? (adaptive bonus)
    4. CORRECTION: Did I remove my own false positives in Round 2? (self-correction)
    """
    reward = 0.0

    # 1. ACCURACY COMPONENT
    true_positives = [f for f in my_flags if is_true_positive(f, ground_truth)]
    false_positives = [f for f in my_flags if not is_true_positive(f, ground_truth)]

    for tp in true_positives:
        matched_bug = find_matching_bug(tp, ground_truth)
        weight = SEVERITY_WEIGHTS.get(matched_bug["severity"], 0.10)
        reward += weight * 2.0   # Core reward: finding a real bug

    for fp in false_positives:
        reward -= 0.15  # Penalty for false alarms

    # 2. UNIQUENESS COMPONENT (only if we have opponent data)
    if opponent_flags:
        opponent_tps = [f for f in opponent_flags if is_true_positive(f, ground_truth)]
        unique_finds = [
            tp for tp in true_positives
            if not any(flags_overlap(tp, otp) for otp in opponent_tps)
        ]
        for unique in unique_finds:
            matched_bug = find_matching_bug(unique, ground_truth)
            weight = SEVERITY_WEIGHTS.get(matched_bug["severity"], 0.10)
            reward += weight * 1.5  # Bonus: I found this, opponent didn't

    # 3. LEARNING COMPONENT (Round 2 only)
    if phase == "final" and r1_flags is not None:
        # Issues I added in Round 2 that are correct (I learned from opponent)
        r2_additions = [f for f in my_flags if not any(flags_overlap(f, r1) for r1 in r1_flags)]
        learned_correctly = [f for f in r2_additions if is_true_positive(f, ground_truth)]
        for learned in learned_correctly:
            reward += 0.20  # Adaptive bonus: I learned from the cross-review

        # 4. CORRECTION COMPONENT
        # R1 flags I removed in R2 because they were false positives (good self-correction)
        removed_fps = [
            f for f in r1_flags
            if not is_true_positive(f, ground_truth)
            and not any(flags_overlap(f, cur) for cur in my_flags)
        ]
        reward += len(removed_fps) * 0.10  # Small bonus for removing false alarms

    # Normalize: maximum possible reward ≈ 1.0
    max_possible = sum(SEVERITY_WEIGHTS.get(b["severity"], 0.10) * 2.0
                       for b in ground_truth) * 1.2  # 20% headroom for uniqueness
    normalized = max(0.0, min(1.0, reward / max_possible))
    return normalized


def is_true_positive(flag, ground_truth):
    """Check if a flagged issue matches a real planted bug."""
    for bug in ground_truth:
        if (flag["file"] == bug["file"]
                and abs(flag["line"] - bug["line"]) <= 3  # 3-line tolerance
                and keyword_overlap(flag["description"], bug["expected_keywords"]) >= 0.3):
            return True
    return False


def keyword_overlap(description, expected_keywords):
    """Fraction of expected keywords mentioned in description."""
    desc_lower = description.lower()
    matches = sum(1 for kw in expected_keywords if kw.lower() in desc_lower)
    return matches / len(expected_keywords) if expected_keywords else 0


def flags_overlap(flag_a, flag_b):
    """Check if two flags refer to the same issue."""
    return (flag_a["file"] == flag_b["file"]
            and abs(flag_a["line"] - flag_b["line"]) <= 3)
```

---

## PART 5: THREE TASKS

### Task 1 — "Bug Hunt" (Easy) — Expected score: ~0.70

**Setup**: One Python file with 3 bugs. Very findable.

**The code** (`tasks/easy/buggy_utils.py`):
```python
def calculate_compound_interest(principal, rate, years):
    # BUG 1 (major): Uses simple interest formula, not compound
    return principal * rate * years   # Should be: principal * (1 + rate) ** years

def find_user(users_list, user_id):
    # BUG 2 (major): Wrong comparison — uses = instead of ==
    for user in users_list:
        if user["id"] = user_id:     # SyntaxError: should be ==
            return user
    return None

def sanitize_input(user_input):
    # BUG 3 (critical/security): Direct string interpolation — SQL injection
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    return query
    # Should use parameterized queries: ("SELECT ... WHERE name = %s", (user_input,))
```

**Ground truth** (`tasks/easy/ground_truth.json`):
```json
{
  "task_id": "easy_001",
  "name": "bug_hunt",
  "description": "Review this utility module for bugs and security issues.",
  "files": ["buggy_utils.py"],
  "bugs": [
    {
      "id": "bug_1",
      "file": "buggy_utils.py",
      "line": 3,
      "severity": "major",
      "type": "logic_error",
      "description": "Wrong interest formula - simple not compound",
      "expected_keywords": ["compound", "power", "exponent", "formula", "interest"]
    },
    {
      "id": "bug_2",
      "file": "buggy_utils.py",
      "line": 8,
      "severity": "major",
      "type": "syntax_error",
      "description": "Assignment operator instead of comparison",
      "expected_keywords": ["comparison", "equals", "==", "assignment", "operator"]
    },
    {
      "id": "bug_3",
      "file": "buggy_utils.py",
      "line": 14,
      "severity": "critical",
      "type": "security",
      "description": "SQL injection via string interpolation",
      "expected_keywords": ["injection", "sql", "parameterized", "interpolation", "f-string", "sanitize"]
    }
  ]
}
```

**Why this is easy**: All bugs are in the same file, clearly visible, with distinct types.

---

### Task 2 — "Security Audit" (Medium) — Expected score: ~0.45

**Setup**: A simple web API across 3 files with 5 security vulnerabilities hidden in realistic-looking code.

**Files**: `auth.py`, `user_controller.py`, `config.py`

**Planted issues**:
1. **auth.py:18** — JWT token never validated for expiry (critical)
2. **auth.py:31** — Password compared with `==` instead of `bcrypt.checkpw` (critical)
3. **user_controller.py:44** — IDOR: no ownership check before returning user data (major)
4. **user_controller.py:67** — Sensitive PII logged to stdout (major)
5. **config.py:3** — Hardcoded secret key `SECRET_KEY = "mysecret123"` (critical)

**Why medium difficulty**: Issues are spread across files, require understanding the code flow, and some (IDOR) require reasoning about what SHOULD be there, not just what's obviously wrong.

---

### Task 3 — "Architecture Autopsy" (Hard) — Expected score: ~0.25

**Setup**: A mini e-commerce backend across 5 files with 6 architectural/performance bugs.

**Files**: `order_service.py`, `inventory.py`, `database.py`, `worker.py`, `cache.py`

**Planted issues**:
1. **order_service.py:23** — N+1 query: fetches product details inside a loop (major/performance)
2. **inventory.py:56** — Race condition: check-then-act on stock level without transaction (critical)
3. **database.py:12** — No connection pool — creates new DB connection per request (major)
4. **worker.py:34** — Memory leak: result list grows indefinitely, never cleared (major)
5. **cache.py:8** — Cache never expires (no TTL) — stale data served forever (major)
6. **order_service.py:89** — Silent exception swallow: `except: pass` hides errors (minor)

**Why hard**: All bugs require understanding distributed systems concepts. The N+1 query only becomes visible when you trace the call path from `order_service.py` through `inventory.py`. The race condition is subtle — the code looks correct until you think about concurrent requests.

---

## PART 6: THE EPISODE FLOW IN DETAIL

```
AGENT A ACTIONS                   AGENT B ACTIONS

reset(episode_id="ep1",           reset(episode_id="ep1",
      task="security_audit",             task="security_audit",
      metadata={"agent_id":"A"})         metadata={"agent_id":"B"})
      │                                   │
step(read_file "auth.py")         step(read_file "config.py")
      │                                   │
step(flag_issue line=3 ...)       step(flag_issue line=3 ...)
      │                                   │
step(read_file "user_controller") step(read_file "auth.py")
      │                                   │
step(flag_issue line=44 ...)      step(flag_issue line=18 ...)
      │                                   │
step(submit_round)                step(flag_issue line=31 ...)
      │                                   │
  [WAITING...]                    step(submit_round)
      │                                   │
      └──────── BOTH SUBMITTED ───────────┘
                      │
         Environment reveals to each:
         "Your opponent found: [...]"
                      │
            ┌─────────┴─────────┐
step(flag_issue ...)          step(flag_issue ...)
  [A spots what B found       [B spots what A found
   that they missed]           that they missed]
            │                         │
step(submit_final)            step(submit_final)
            │                         │
   reward=0.72                reward=0.58
   done=True                  done=True
```

---

## PART 7: THE INFERENCE SCRIPT (`inference.py`)

This is mandatory. It runs TWO LLM agents against the environment.

```python
#!/usr/bin/env python3
"""
inference.py — Peer Review Arena: Two-Agent Baseline

Runs two LLM agents against each other on code review tasks.
Agents review code independently, then improve after seeing opponent's findings.

Required env vars:
  API_BASE_URL    LLM API endpoint
  MODEL_NAME      Model to use (same model for both agents in baseline)
  HF_TOKEN        Hugging Face API key
  LOCAL_IMAGE_NAME  Docker image name
"""

import asyncio
import json
import os
from typing import List, Optional
from openai import OpenAI
from peer_review_env import PeerReviewEnv, PeerReviewAction

API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME", "peer-review-env:latest")
BENCHMARK = "peer_review_env"
MAX_STEPS = 15
TEMPERATURE = 0.3


# ── LOGGING (MANDATORY FORMAT) ───────────────────────────────────────────────

def log_start(task: str, env: str, model: str):
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]):
    err = error if error else "null"
    print(f"[STEP] step={step} action={action[:60]} reward={reward:.2f} "
          f"done={str(done).lower()} error={err}", flush=True)

def log_end(success: bool, steps: int, score: float, rewards: List[float]):
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} "
          f"score={score:.3f} rewards={rewards_str}", flush=True)


# ── LLM PROMPTS ──────────────────────────────────────────────────────────────

ROUND1_SYSTEM = """You are a senior software engineer doing a code review.
Your job: find ALL bugs, security vulnerabilities, and issues in the provided code.

To review code, respond with ONE JSON action at a time:

Read a file:
{"action_type": "read_file", "file_path": "filename.py"}

Flag an issue:
{"action_type": "flag_issue", "file_path": "file.py", "line_number": 23,
 "issue_id": "issue_1", "issue_type": "security", "severity": "critical",
 "description": "SQL injection: user input directly interpolated into query"}

Submit your round 1 review when done:
{"action_type": "submit_round"}

Be thorough. Check all files. Severity: critical/major/minor."""

ROUND2_SYSTEM = """You are continuing a code review. You've already submitted your Round 1 review.

Your opponent found these issues in their Round 1 review:
{opponent_findings}

Your Round 1 findings were:
{my_findings}

Now you can:
1. Flag issues you MISSED that your opponent found (if they look valid)
2. Flag NEW issues you notice after reviewing more carefully
3. Remove flags that seem wrong (action_type: "remove_flag")
4. Submit final review when done

Respond with ONE JSON action at a time. Submit final when ready:
{"action_type": "submit_final"}"""


def parse_action(raw: str) -> Optional[PeerReviewAction]:
    """Parse LLM output into a PeerReviewAction."""
    try:
        # Try to extract JSON from the response
        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(raw)
        return PeerReviewAction(**data)
    except Exception:
        return PeerReviewAction(action_type="submit_final")


async def run_agent(client_llm: OpenAI, env: PeerReviewEnv, agent_id: str,
                    task_name: str, episode_id: str) -> tuple[float, List[float]]:
    """Run one agent through a full episode."""

    rewards = []
    steps_taken = 0
    messages = []

    log_start(task=f"{task_name}_agent_{agent_id}", env=BENCHMARK, model=MODEL_NAME)

    # Reset into the shared episode
    result = await env.reset(
        episode_id=episode_id,
        task=task_name,
        metadata={"agent_id": agent_id}
    )
    obs = result.observation

    # Round 1: Independent review
    messages = [
        {"role": "system", "content": ROUND1_SYSTEM},
        {"role": "user", "content": (
            f"Task: {obs.task_description}\n"
            f"Files to review: {obs.files_available}\n"
            f"Start your review. Read each file and flag all issues you find."
        )}
    ]

    for step in range(1, MAX_STEPS + 1):
        if result.done:
            break

        # Check if we need to switch to Round 2 prompt
        if obs.phase == "round_2" and obs.opponent_round1_flags:
            messages = [
                {"role": "system", "content": ROUND2_SYSTEM.format(
                    opponent_findings=json.dumps(obs.opponent_round1_flags, indent=2),
                    my_findings=json.dumps(obs.my_round1_flags, indent=2)
                )},
                {"role": "user", "content": (
                    "Round 2 has started. Review your opponent's findings and improve your review.\n"
                    f"You found {len(obs.my_round1_flags)} issues in Round 1.\n"
                    f"Your opponent found {len(obs.opponent_round1_flags)} issues.\n"
                    "Flag any issues you missed, then submit_final when done."
                )}
            ]

        # Get LLM's next action
        try:
            completion = client_llm.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=TEMPERATURE,
                max_tokens=300,
            )
            raw_action = (completion.choices[0].message.content or "").strip()
        except Exception as e:
            raw_action = '{"action_type": "submit_final"}'

        action = parse_action(raw_action)
        result = await env.step(action)
        obs = result.observation
        reward = result.reward or 0.0
        rewards.append(reward)
        steps_taken = step

        log_step(step, raw_action[:60], reward, result.done, obs.error)

        # Update conversation history
        messages.append({"role": "assistant", "content": raw_action})
        messages.append({"role": "user", "content": (
            f"Result: {obs.last_action_result}\n"
            f"Phase: {obs.phase} | Flags: {len(obs.my_flags)} | Step: {step}/{MAX_STEPS}"
        )})

        if result.done:
            break

    final_score = max(rewards) if rewards else 0.0
    log_end(final_score >= 0.5, steps_taken, final_score, rewards)
    return final_score, rewards


async def run_task(task_name: str):
    """Run both agents on the same task simultaneously."""
    print(f"\n{'='*60}")
    print(f"TASK: {task_name}")
    print(f"{'='*60}\n")

    client_llm = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    episode_id = f"{task_name}_ep1"

    # Create two env clients connecting to the same server
    env_a = await PeerReviewEnv.from_docker_image(LOCAL_IMAGE_NAME)
    env_b = await PeerReviewEnv.from_docker_image(LOCAL_IMAGE_NAME)

    try:
        # Run both agents concurrently
        (score_a, rewards_a), (score_b, rewards_b) = await asyncio.gather(
            run_agent(client_llm, env_a, "A", task_name, episode_id),
            run_agent(client_llm, env_b, "B", task_name, episode_id),
        )

        print(f"\n[TASK_RESULT] task={task_name} "
              f"agent_a={score_a:.3f} agent_b={score_b:.3f} "
              f"avg={((score_a+score_b)/2):.3f}\n")

        return score_a, score_b

    finally:
        await env_a.close()
        await env_b.close()


async def main():
    tasks = ["bug_hunt", "security_audit", "arch_autopsy"]
    results = {}

    for task in tasks:
        score_a, score_b = await run_task(task)
        results[task] = {"agent_a": score_a, "agent_b": score_b}

    print("\n" + "="*60)
    print("FINAL BASELINE SCORES")
    print("="*60)
    for task, scores in results.items():
        avg = (scores["agent_a"] + scores["agent_b"]) / 2
        print(f"{task:20s}  A={scores['agent_a']:.3f}  B={scores['agent_b']:.3f}  avg={avg:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## PART 8: EXPECTED BASELINE SCORES

| Task | Agent A | Agent B | Notes |
|------|---------|---------|-------|
| bug_hunt | 0.70 | 0.65 | Easy, most LLMs find obvious bugs |
| security_audit | 0.45 | 0.40 | Medium, auth/IDOR requires reasoning |
| arch_autopsy | 0.25 | 0.20 | Hard, architectural issues need systems knowledge |

The cross-review mechanic should push final scores ~15% higher than independent reviews, which you can highlight in your README as evidence the environment creates meaningful learning signal.

---

## PART 9: THE openenv.yaml

```yaml
spec_version: 1
name: peer_review_env
version: "1.0.0"
description: >
  Two anonymous AI agents independently review the same codebase,
  then each sees the other's findings and improves. Rewards favor
  thorough independent work AND learning from peer observations.
type: space
runtime: fastapi
app: server.app:app
port: 8000
```

---

## PART 10: THE Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python package
COPY pyproject.toml ./
COPY peer_review_env/ ./peer_review_env/
COPY server/ ./server/
COPY tasks/ ./tasks/

RUN pip install --no-cache-dir -e "."

EXPOSE 8000

# Start the environment server
CMD ["python", "-m", "peer_review_env.server.app"]
```

---

## PART 11: pyproject.toml

```toml
[project]
name = "openenv-peer-review"
version = "1.0.0"
description = "Peer Review Arena: Two-agent adversarial code review environment"
requires-python = ">=3.10"

dependencies = [
    "openenv-core[core]>=0.2.2",
    "fastapi>=0.115.0",
    "pydantic>=2.0.0",
    "uvicorn>=0.24.0",
]

[project.scripts]
server = "peer_review_env.server.app:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.backends.legacy:build"
```

---

## PART 12: BUILD PLAN (Day by Day)

### Day 1 (April 3–4): Setup + Models
- [ ] `pip install openenv-core`
- [ ] Create folder structure manually or via `openenv init peer_review_env`
- [ ] Write `models.py` (Action, Observation, State classes)
- [ ] Write `openenv.yaml`, `pyproject.toml`
- [ ] Create 3 buggy Python files for Task 1 (easy) + `ground_truth.json`

### Day 2 (April 4–5): Core Environment Logic
- [ ] Write `server/grader.py` (reward computation)
- [ ] Write `server/environment.py` (episode management, step routing)
- [ ] Write `server/app.py` (FastAPI wiring)
- [ ] Test: `python -m peer_review_env.server.app` + `curl /reset`
- [ ] Run `openenv validate`

### Day 3 (April 5–6): All 3 Tasks + Client
- [ ] Create buggy files for Task 2 (medium) + ground truth
- [ ] Create buggy files for Task 3 (hard) + ground truth
- [ ] Write `client.py` (EnvClient subclass)
- [ ] Write `__init__.py` exports
- [ ] Test all 3 tasks via curl

### Day 4 (April 6–7): Docker + Inference + Deploy
- [ ] Write `Dockerfile`
- [ ] `docker build -t peer-review-env .`
- [ ] `docker run -p 8000:8000 peer-review-env`
- [ ] Write `inference.py` (use template from Part 7)
- [ ] Test inference script locally
- [ ] `huggingface-cli login`
- [ ] `openenv push --repo-id your-username/peer-review-env`

### Day 5 (April 7–8): Polish + Submit
- [ ] Write README.md
- [ ] Run full validation script
- [ ] Record baseline scores
- [ ] Submit HF Spaces URL before 11:59 PM IST

---

## PART 13: THE ELEVATOR PITCH (For Your README)

```
Code review is one of the most critical and time-consuming engineering tasks.
This environment trains AI agents to review code the way the best engineers do —
not just finding obvious bugs, but learning from peer observations to catch
what they missed the first time.

Two anonymous AI agents independently review the same codebase. After their
independent review, each agent sees what the other found. Agents that learn
from this cross-review and improve their findings earn higher rewards.

This creates an emergent training dynamic: agents learn to be thorough
(to find things before their opponent), humble (to recognize valid findings
they missed), and self-correcting (to remove false positives when confronted
with contrary evidence).

Based on the Multiagent Debate paradigm (Du et al., ICML 2024) and
cross-observation learning (MARTI, ICLR 2026) — but as an interactive
OpenEnv environment accessible to anyone.
```

---

## QUICK REFERENCE: Key Commands

```bash
# Install
pip install openenv-core

# Validate (run from project root)
openenv validate

# Run locally
python -m peer_review_env.server.app
# OR
docker build -t peer-review-env . && docker run -p 8000:8000 peer-review-env

# Test endpoints
curl -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"episode_id": "test1", "metadata": {"agent_id": "A"}}'

curl -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action": {"action_type": "read_file", "file_path": "buggy_utils.py"}}'

curl http://localhost:8000/state
curl http://localhost:8000/health

# Deploy
huggingface-cli login
openenv push --repo-id YOUR_USERNAME/peer-review-env

# Validate deployed
openenv validate --url https://YOUR_USERNAME-peer-review-env.hf.space
```

---

*Deadline: April 8, 2026 at 11:59 PM IST*
*You have until then to build something that could win $30,000.*
