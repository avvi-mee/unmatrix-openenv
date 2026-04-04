"""Phase state machine for Peer Review Arena."""
import threading

from server.models import (
    ActionType,
    EnvResponse,
    PeerReviewAction,
    PeerReviewObservation,
    StateResponse,
)
from server.tasks import task1_bug_hunt, task2_security_audit, task3_architecture_review
from server.graders import grader1, grader2, grader3

# ── Task / grader registries ──────────────────────────────────────────────────

TASK_LOADERS = {
    "bug_hunt": task1_bug_hunt.load,
    "security_audit": task2_security_audit.load,
    "architecture_review": task3_architecture_review.load,
}

GRADERS = {
    "bug_hunt": grader1.compute_score,
    "security_audit": grader2.compute_score,
    "architecture_review": grader3.compute_score,
}

GRADER_MODULES = {
    "bug_hunt": grader1,
    "security_audit": grader2,
    "architecture_review": grader3,
}


def _count_matched_bugs(flags: list, bugs: list, grader_mod) -> int:
    """Exact count of unique bugs matched by flags using the grader's is_true_positive."""
    matched: set[tuple] = set()
    for flag in flags:
        _, bug = grader_mod.is_true_positive(flag, bugs)
        if bug:
            matched.add((bug["file"], bug["line"]))
    return len(matched)

# ── Global state ──────────────────────────────────────────────────────────────

_episodes: dict[str, dict] = {}
_lock = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────


def _internal_id(agent_id: str) -> str:
    """Normalise agent_id to 'A' or 'B'."""
    clean = agent_id.replace("agent_", "").upper()
    if clean not in ("A", "B"):
        raise ValueError(f"agent_id must be 'A' or 'B' (got '{agent_id}')")
    return clean


def _other_id(internal_id: str) -> str:
    return "B" if internal_id == "A" else "A"


def _base_obs(ep: dict, internal_id: str) -> PeerReviewObservation:
    task = ep["task"]
    me = ep[internal_id]
    other = ep[_other_id(internal_id)]
    opp_flags: list[dict] = []
    if ep["phase"] in ("round_2", "finished"):
        opp_flags = list(other.get("r1_flags", []))
    return PeerReviewObservation(
        phase=ep["phase"],
        task_name=task["name"],
        task_description=task["description"],
        files_available=list(task["files"]),
        current_file="",
        file_content="",
        my_flags=list(me["flags"]),
        my_round1_flags=list(me.get("r1_flags", [])),
        opponent_round1_flags=opp_flags,
        last_action_result="",
        step_number=me["step_count"],
        max_steps=task.get("max_steps", 20),
    )


def _ok(ep: dict, internal_id: str, result: str, reward: float = 0.0, done: bool = False,
        info: dict | None = None) -> EnvResponse:
    obs = _base_obs(ep, internal_id)
    obs.last_action_result = result
    return EnvResponse(observation=obs, done=done, reward=reward, info=info or {})


def _err(ep: dict, internal_id: str, error: str) -> EnvResponse:
    obs = _base_obs(ep, internal_id)
    obs.error = error
    obs.last_action_result = f"ERROR: {error}"
    return EnvResponse(observation=obs, done=False, reward=0.0)


# ── Action handlers ───────────────────────────────────────────────────────────


def _read_file(ep: dict, internal_id: str, action: PeerReviewAction) -> EnvResponse:
    task = ep["task"]
    path = action.file_path.strip()
    content = task["content"].get(path)
    if content is None:
        # Try basename match
        for fname, fcontent in task["content"].items():
            if fname.endswith(path) or path.endswith(fname):
                content = fcontent
                path = fname
                break
    if content is None:
        return _err(ep, internal_id, f"File not found: {action.file_path}")
    obs = _base_obs(ep, internal_id)
    obs.current_file = path
    numbered = "\n".join(f"{i+1:3}: {line}" for i, line in enumerate(content.splitlines()))
    obs.file_content = numbered
    obs.last_action_result = f"Read {len(content)} chars from {path}"
    return EnvResponse(observation=obs, done=False, reward=0.0)


def _flag_issue(ep: dict, internal_id: str, action: PeerReviewAction) -> EnvResponse:
    me = ep[internal_id]
    flag = {
        "file_path": action.file_path,
        "line_number": action.line_number,
        "issue_type": action.issue_type,
        "severity": action.severity,
        "description": action.description,
        "issue_id": action.issue_id or f"flag_{len(me['flags'])}",
    }
    me["flags"].append(flag)
    return _ok(ep, internal_id, f"Flagged issue at {action.file_path}:{action.line_number}", reward=0.05)


def _remove_flag(ep: dict, internal_id: str, action: PeerReviewAction) -> EnvResponse:
    me = ep[internal_id]
    before = len(me["flags"])
    me["flags"] = [f for f in me["flags"] if f.get("issue_id") != action.issue_id]
    removed = before - len(me["flags"])
    return _ok(ep, internal_id, f"Removed {removed} flag(s) with id '{action.issue_id}'")


def _submit_round(ep: dict, internal_id: str) -> EnvResponse:
    me = ep[internal_id]
    other_id = _other_id(internal_id)
    other = ep[other_id]
    task = ep["task"]

    me["r1_flags"] = list(me["flags"])
    me["ready"] = True

    grader = GRADERS.get(task["name"], grader1.compute_score)
    r1_score = grader(me["flags"], task.get("bugs", []))
    me["r1_score"] = r1_score

    if other["ready"] or other["done"]:
        ep["phase"] = "round_2"
        obs = _base_obs(ep, internal_id)
        obs.opponent_round1_flags = list(other.get("r1_flags", []))
        obs.last_action_result = "Round 1 submitted. Both agents ready — round 2 begins!"
        return EnvResponse(observation=obs, done=False, reward=0.0,
                           info={"phase_transition": "round_2", "round1_score": r1_score})
    else:
        ep["phase"] = "cross_review"
        obs = _base_obs(ep, internal_id)
        obs.last_action_result = "Round 1 submitted. Waiting for opponent to submit round 1."
        return EnvResponse(observation=obs, done=False, reward=0.0,
                           info={"waiting_for_opponent": True, "round1_score": r1_score})


def _submit_final(ep: dict, internal_id: str) -> EnvResponse:
    me = ep[internal_id]
    other_id = _other_id(internal_id)
    other = ep[other_id]
    task = ep["task"]

    # Auto-complete round 1 submission if agent skipped submit_round
    if not me["ready"]:
        me["r1_flags"] = list(me["flags"])
        me["ready"] = True

    grader = GRADERS.get(task["name"], grader1.compute_score)
    score = grader(me["flags"], task.get("bugs", []))
    score = max(0.0, min(1.0, float(score)))

    me["done"] = True
    if other["done"]:
        ep["phase"] = "finished"

    all_bugs = task.get("bugs", [])
    total_bugs = len(all_bugs)
    grader_mod = GRADER_MODULES.get(task["name"], grader1)
    bugs_found = _count_matched_bugs(me["flags"], all_bugs, grader_mod)

    obs = _base_obs(ep, internal_id)
    obs.last_action_result = f"Final submission scored {score:.3f}"
    return EnvResponse(
        observation=obs,
        done=True,
        reward=score,
        info={
            "final_score": score,
            "flags_submitted": len(me["flags"]),
            "bugs_found": bugs_found,
            "total_bugs": total_bugs,
            "round1_score": me.get("r1_score", 0.0),
        },
    )


def _waiting_obs(ep: dict, internal_id: str) -> EnvResponse:
    obs = _base_obs(ep, internal_id)
    obs.last_action_result = "Waiting for opponent. Dummy action processed."
    return EnvResponse(observation=obs, done=False, reward=0.0,
                       info={"waiting": True})


# ── Public API ────────────────────────────────────────────────────────────────


def reset(episode_id: str, task: str, agent_id: str, seed: int | None = None) -> EnvResponse:
    internal_id = _internal_id(agent_id)
    loader = TASK_LOADERS.get(task)
    if loader is None:
        raise ValueError(f"Unknown task '{task}'. Valid: {list(TASK_LOADERS)}")

    with _lock:
        if episode_id not in _episodes:
            effective_seed = seed if seed is not None else hash(episode_id) & 0xFFFFFF
            task_data = loader(effective_seed)
            task_data["max_steps"] = task_data.get("max_steps", 20)
            _episodes[episode_id] = {
                "task": task_data,
                "phase": "round_1",
                "task_name": task_data["name"],
                "A": {"flags": [], "r1_flags": [], "ready": False, "done": False, "step_count": 0},
                "B": {"flags": [], "r1_flags": [], "ready": False, "done": False, "step_count": 0},
            }
        ep = _episodes[episode_id]
        # Re-init this agent's state (allows reconnect)
        ep[internal_id] = {"flags": [], "r1_flags": [], "ready": False, "done": False, "step_count": 0}

    obs = _base_obs(ep, internal_id)
    obs.last_action_result = f"Episode '{episode_id}' ready for agent {internal_id}."
    return EnvResponse(observation=obs, done=False, reward=0.0,
                       info={
                           "episode_id": episode_id,
                           "agent_id": internal_id,
                           "total_bugs": len(ep["task"].get("bugs", [])),
                       })


def step(episode_id: str, agent_id: str, action: PeerReviewAction) -> EnvResponse:
    internal_id = _internal_id(agent_id)
    other_id = _other_id(internal_id)

    with _lock:
        ep = _episodes[episode_id]   # KeyError → propagates → HTTP 404
        me = ep[internal_id]
        other = ep[other_id]
        me["step_count"] += 1

        # Guard: already done
        if me["done"]:
            obs = _base_obs(ep, internal_id)
            obs.last_action_result = "Episode already finished for this agent."
            return EnvResponse(observation=obs, done=True, reward=0.0)

        # Guard: waiting in cross_review for opponent
        if ep["phase"] == "cross_review" and me["ready"] and not other["ready"]:
            return _waiting_obs(ep, internal_id)

        match action.action_type:
            case ActionType.read_file:
                return _read_file(ep, internal_id, action)
            case ActionType.flag_issue:
                return _flag_issue(ep, internal_id, action)
            case ActionType.remove_flag:
                return _remove_flag(ep, internal_id, action)
            case ActionType.submit_round:
                return _submit_round(ep, internal_id)
            case ActionType.submit_final:
                return _submit_final(ep, internal_id)
            case _:
                return _err(ep, internal_id, f"Unknown action_type: {action.action_type}")


def get_state(episode_id: str, agent_id: str) -> StateResponse:
    internal_id = _internal_id(agent_id)
    other_id = _other_id(internal_id)
    with _lock:
        ep = _episodes.get(episode_id)
        if ep is None:
            return StateResponse(episode_id=episode_id, agent_id=agent_id)
        me = ep[internal_id]
        other = ep[other_id]
        return StateResponse(
            episode_id=episode_id,
            agent_id=internal_id,
            phase=ep["phase"],
            task_name=ep["task_name"],
            step_count=me["step_count"],
            my_flags_count=len(me["flags"]),
            opponent_ready=other["ready"],
        )
