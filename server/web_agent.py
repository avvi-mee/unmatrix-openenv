"""Server-side random agent for the web UI.

Extracted from inference.py's random agent logic so the browser can drive
agent actions via /api/auto-step without needing an LLM.
"""
import random as _random

import server.environment as env_module
from server.models import PeerReviewAction

# ── Random agent constants (mirrored from inference.py) ───────────────────────

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
_RAND_SEVS = ["critical", "major", "minor"]
_RAND_SWEIGHTS = [0.2, 0.5, 0.3]


def _build_file_flags(fname: str, content: str, rng: _random.Random) -> list[dict]:
    """Create flags at every-12-line intervals, keeping 40-90% for variety."""
    max_line = max(len(content.splitlines()), 10)
    candidates = list(range(5, max_line + 1, 12))
    if not candidates:
        candidates = [5]
    n_keep = max(1, int(len(candidates) * rng.uniform(0.4, 0.9)))
    chosen = sorted(rng.sample(candidates, min(n_keep, len(candidates))))
    desc_base = "Potential issue: " + ", ".join(_RAND_KEYWORDS) + " detected"
    return [
        {
            "action_type": "flag_issue",
            "file_path": fname,
            "line_number": ln,
            "issue_type": rng.choice(_RAND_TYPES),
            "severity": rng.choices(_RAND_SEVS, weights=_RAND_SWEIGHTS)[0],
            "description": desc_base,
        }
        for ln in chosen
    ]


def _random_action(obs: dict, phase: str, rng: _random.Random, state: dict) -> dict:
    """Stateful random action picker. `state` is a per-agent mutable dict."""
    files = obs.get("files_available", [])

    if phase == "round_1":
        content = obs.get("file_content", "")
        last_file = state.get("last_read_file")
        if content and last_file and last_file not in state.get("flags_built", set()):
            state.setdefault("flags_built", set()).add(last_file)
            state.setdefault("flag_queue", []).extend(
                _build_file_flags(last_file, content, rng)
            )

        q = state.get("flag_queue", [])
        if q:
            return q.pop(0)

        read_set = state.get("read", set())
        unread = [f for f in files if f not in read_set]
        if unread:
            fname = unread[0]
            state.setdefault("read", set()).add(fname)
            state["last_read_file"] = fname
            return {"action_type": "read_file", "file_path": fname}

        return {"action_type": "submit_round"}

    # round_2 / cross_review — adopt some opponent flags then finish
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
            "file_path": f.get("file_path", ""),
            "line_number": f.get("line_number", 1),
            "issue_type": f.get("issue_type", "logic_error"),
            "severity": f.get("severity", "minor"),
            "description": f.get("description", "adopted from opponent"),
        }

    return {"action_type": "submit_final"}


# ── Per-agent context cache ───────────────────────────────────────────────────

_agent_contexts: dict[str, dict] = {}  # keyed by "episode_id:agent_id"


def auto_step(episode_id: str, agent_id: str = "B") -> dict:
    """Run one random-agent step for the given agent. Returns EnvResponse dict."""
    key = f"{episode_id}:{agent_id}"

    if key not in _agent_contexts:
        # First call — build initial obs from environment state
        internal_id = env_module._internal_id(agent_id)
        with env_module._lock:
            ep = env_module._episodes[episode_id]
            obs = env_module._base_obs(ep, internal_id)
            phase = ep["phase"]
        seed = hash(key) & 0xFFFFFF
        _agent_contexts[key] = {
            "rng": _random.Random(seed),
            "state": {},
            "last_obs": obs.model_dump(),
            "phase": phase,
        }

    ctx = _agent_contexts[key]
    action_dict = _random_action(ctx["last_obs"], ctx["phase"], ctx["rng"], ctx["state"])

    # Build PeerReviewAction from the dict
    action = PeerReviewAction(**{
        k: v for k, v in action_dict.items() if k != "action_type" or True
    })

    result = env_module.step(episode_id, agent_id, action)
    result_dict = result.model_dump()

    # Cache new observation
    ctx["last_obs"] = result_dict.get("observation", {})
    ctx["phase"] = ctx["last_obs"].get("phase", ctx["phase"])

    return result_dict


def reset_agent_state(episode_id: str) -> None:
    """Clear all cached agent contexts for this episode."""
    keys_to_remove = [k for k in _agent_contexts if k.startswith(f"{episode_id}:")]
    for k in keys_to_remove:
        del _agent_contexts[k]
