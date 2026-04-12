---
title: Peer Review Arena
emoji: "\U0001F50D"
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Peer Review Arena

**Two AI agents review the same code, then learn from each other's findings.**

An OpenEnv-compliant reinforcement learning environment where two anonymous AI agents independently review a codebase for bugs, security vulnerabilities, or architectural flaws. After their independent review, the environment reveals each agent's findings to the other — and both get a second chance to improve. Agents that learn from cross-review earn higher rewards.

## Why This Matters

Code review is one of the most critical and time-consuming engineering tasks. This environment trains AI agents to review code the way the best engineers do — not just finding obvious bugs, but learning from peer observations to catch what they missed the first time.

**Real-world analogy:** Two senior engineers both review the same PR. Then they compare notes. Engineer A realizes they missed the SQL injection that Engineer B caught. Engineer B realizes they missed the race condition that Engineer A caught. Both get sharper from the meeting. *This environment trains AI to do exactly that.*

**Research foundation:** Built on the Multiagent Debate paradigm (Du et al., ICML 2024) and cross-observation learning from the MARTI framework (Tsinghua University, ICLR 2026) — but packaged as an interactive OpenEnv environment accessible to anyone. See [RESEARCH.md](RESEARCH.md) for the full academic context.

## Live Demo

**[Try it on HuggingFace Spaces](https://huggingface.co/spaces/avvi-mee/peer-review-arena)**

- **Watch Mode** — Spectate two AI agents reviewing code in real time. See their flags appear, phases transition, and scores reveal at the end.
- **Play Mode** — Take the role of Agent B and compete head-to-head against the AI. Can you find more bugs than the machine?

No setup required — just open the link and pick a task.

## Key Innovation

**Adversarial co-learning through cross-observation** creates two competing training pressures:

| Pressure | Mechanism | Effect |
|----------|-----------|--------|
| **Competitive** | Find things your opponent missed | Pushes thoroughness |
| **Cooperative** | Learn from opponent's valid findings | Pushes humility and adaptiveness |

Together, these train an agent that is BOTH comprehensive AND self-correcting — the hallmark of expert human reviewers.

## Architecture

```
+-----------------------------------------------------+
|            Interactive Web UI (index.html)           |
|   Lobby  →  Match (code viewer + flags)  →  Score   |
|        Watch Mode  |  Play Mode  |  /api/* routes    |
+-----------------------------------------------------+
|                   FastAPI Server                     |
|  /reset  /step  /state  /health  |  web_agent.py    |
+-----------------------------------------------------+
|              environment.py (state machine)          |
|   round_1 -> cross_review -> round_2 -> finished    |
+--------------+--------------+-----------------------+
|  data_gen/   |   tasks/     |   graders/            |
|  bug         |  task1       |  grader1 (TP/total)   |
|  security    |  task2       |  grader2 (severity-w) |
|  architecture|  task3       |  grader3 (kw-match)   |
+--------------+--------------+-----------------------+
```

Both agents connect to the same server using the same `episode_id`. The server internally tracks both agents' state and coordinates phase transitions using a thread-safe lock.

## Interactive Web UI

The environment ships with a fully interactive browser frontend — zero extra dependencies, single HTML file, no build step.

**Three screens:**

| Screen | What it does |
|--------|-------------|
| **Lobby** | Pick a task (bug hunt / security audit / architecture review) and mode (Watch or Play) |
| **Match** | Dark-theme code viewer with line-numbered gutter, real-time flag markers, split-panel agent comparison, phase transition overlays, and a flag dialog for Play Mode |
| **Scoreboard** | Final scores for both agents, ground truth reveal showing all planted bugs, per-flag TP/FP breakdown |

**Key features:**
- GitHub-style dark code viewer with syntax-aware gutter markers (green = TP, red = FP)
- Real-time phase transition overlays ("Cross Review" / "Round 2" / "Finished")
- Play Mode flag dialog: click a line to flag it, pick severity, describe the issue
- Ground truth reveal at the end shows every planted bug so you can learn from what you missed
- Fully self-contained: `server/static/index.html` + `server/web_agent.py` (server-side random agent)

## Phase Flow

| Phase | Description |
|-------|-------------|
| `round_1` | Both agents independently read files and flag issues |
| `cross_review` | Waiting for both agents to submit round 1 |
| `round_2` | Agents see each other's round 1 flags and can refine their review |
| `finished` | Both agents submitted final answers; graded scores returned |

### Detailed Episode Flow

```
Agent A                              Agent B
  |                                    |
  |  reset(episode_id, agent_id="A")   |  reset(episode_id, agent_id="B")
  |                                    |
  |  ROUND 1: Independent review       |  ROUND 1: Independent review
  |  - read_file("auth.py")           |  - read_file("config.py")
  |  - flag_issue(line=31, ...)        |  - flag_issue(line=3, ...)
  |  - submit_round                    |  - submit_round
  |                                    |
  +------------ BOTH SUBMITTED --------+
  |                                    |
  |  Environment reveals:              |
  |  "Here's what your opponent found" |
  |                                    |
  |  ROUND 2: Cross-review             |  ROUND 2: Cross-review
  |  - Sees B's findings               |  - Sees A's findings
  |  - Flags missed issues             |  - Flags missed issues
  |  - submit_final                    |  - submit_final
  |                                    |
  |  reward = graded score [0, 1]      |  reward = graded score [0, 1]
```

## Supported Tasks

| Task | Difficulty | Generator | Grader | Expected Score |
|------|-----------|-----------|--------|----------------|
| `bug_hunt` | Easy | 5 Python templates with logic/type/control-flow bugs | TP count / total bugs | ~0.70 |
| `security_audit` | Medium | 5 security vulnerability templates across auth/IDOR/injection | Severity-weighted TP score | ~0.45 |
| `architecture_review` | Hard | 5 multi-file microservice anti-pattern templates | Keyword-match fraction | ~0.25 |

**Difficulty rationale:**
- **Easy (bug_hunt):** Bugs are localized, syntactically visible, and in single files. Most LLMs catch obvious errors.
- **Medium (security_audit):** Vulnerabilities span multiple files and require understanding code flow. IDOR and timing attacks require reasoning about *what should be there*, not just what's wrong.
- **Hard (architecture_review):** Issues require distributed systems knowledge. An N+1 query only emerges when tracing call paths across files. Race conditions look correct until you reason about concurrency.

## API Reference

### POST /reset
```json
{
  "episode_id": "my_episode",
  "task": "bug_hunt",
  "agent_id": "A",
  "seed": 42
}
```

### POST /step
```json
{
  "episode_id": "my_episode",
  "agent_id": "A",
  "action": {
    "action_type": "flag_issue",
    "file_path": "utils.py",
    "line_number": 7,
    "severity": "major",
    "description": "Off-by-one error in slice operation"
  }
}
```

Available `action_type` values: `read_file`, `flag_issue`, `remove_flag`, `submit_round`, `submit_final`

### GET /state
```
GET /state?episode_id=my_episode&agent_id=A
```

### GET /health
```json
{"status": "ok", "service": "peer_review_arena"}
```

## Reward Structure

| Action | Reward |
|--------|--------|
| `read_file` | 0.0 |
| `flag_issue` | 0.05 (encourages exploration) |
| `remove_flag` | 0.0 |
| `submit_round` | 0.0 |
| `submit_final` | Graded score [0.0, 1.0] |

**Design philosophy:** Small per-flag rewards (0.05) encourage agents to actively explore rather than immediately submitting. The terminal graded reward is the true learning signal — it measures how many real bugs the agent found, weighted by the task-specific grader. This two-tier structure (shaping rewards + terminal evaluation) follows standard RL practice for sparse-reward environments.

## Grading Philosophy

Three different graders serve three different evaluation goals:

| Grader | Task | Algorithm | Rationale |
|--------|------|-----------|-----------|
| grader1 | `bug_hunt` | TP count / total bugs | All bugs are equal — completeness is what matters |
| grader2 | `security_audit` | Severity-weighted TP score (critical=0.40, major=0.35, minor=0.25) | Critical vulnerabilities matter far more than style nits |
| grader3 | `architecture_review` | Keyword-match fraction per bug | Partial credit for depth — identifying "N+1 query" is worth more than a vague "performance issue" |

**Shared matching criteria across all graders:**
- **Line proximity:** Flag must be within 8 lines of the planted bug
- **Keyword overlap:** Flag description must match >= 30% of expected keywords
- **File match:** Flag must reference the correct file
- **Deduplication:** Multiple flags on the same bug count once

The 8-line tolerance accounts for agents flagging a function header vs. the specific buggy line. The 30% keyword threshold ensures agents demonstrate genuine understanding, not just line-number guessing.

## Setup

### Local Development

```bash
pip install -r requirements.txt

# Start server (local dev uses port 8000)
PYTHONPATH=. uvicorn server.app:app --port 8000 --workers 1

# Run inference baseline
export HF_TOKEN=hf_...
export ENV_SERVER_URL=http://localhost:8000
python inference.py
```

### PowerShell (Windows)

```powershell
.\run.ps1
```

### Docker

```bash
docker build -t peer-review-arena .
docker run -p 7860:7860 peer-review-arena
```

> **Port note:** The Docker container and OpenEnv deployment listen on port **7860** (configured in Dockerfile and openenv.yaml). For local development without Docker, `uvicorn` defaults to port **8000**. Make sure your `ENV_SERVER_URL` matches whichever you're running.

## Expected Baseline Output

```
[START] task=bug_hunt env=peer_review_arena model=Qwen/Qwen2.5-Coder-7B-Instruct
[STEP] step=1 agent=agent_A action=read_file result=read_file reward=0.00 done=false error=null
[STEP] step=1 agent=agent_B action=read_file result=read_file reward=0.00 done=false error=null
...
[STEP] step=N agent=agent_A action=submit_final result=submit_final reward=0.50 done=true error=null
[STEP] step=N agent=agent_B action=submit_final result=submit_final reward=0.50 done=true error=null
[END] success=true steps=N score=0.50 rewards=0.00,0.05,...,0.50
```

The inference script supports `--random` mode for testing without an LLM:
```bash
python inference.py --random --seed 42
```

## Composite Scoring (Inference)

The inference script computes a composite score per agent:

```
score = 0.60 * recall + 0.25 * uniqueness + 0.15 * learning
```

| Component | Weight | Definition |
|-----------|--------|------------|
| **Recall** | 0.60 | bugs_found / total_bugs |
| **Uniqueness** | 0.25 | Bugs found that opponent missed / total_bugs |
| **Learning** | 0.15 | Bugs gained in Round 2 vs Round 1 / total_bugs |

This rewards agents that are thorough (recall), find things others miss (uniqueness), AND improve after cross-review (learning).

## openenv.yaml Compliance

- `spec_version: 1` (integer)
- `name: peer_review_arena` (matches `env=` in [START])
- `app: server.app:app`
- `port: 7860`
- `runtime: fastapi`

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Docker container unreachable | Port mismatch | Use `-p 7860:7860` (container listens on 7860, not 8000) |
| `KeyError: 'episode_id'` on /step | Forgot to call /reset first | Always POST /reset before /step for each episode |
| Agent gets "waiting" responses | Opponent hasn't submitted round 1 | Both agents must `submit_round` before round 2 begins |
| Score is 0.0 | Flags don't match ground truth | Check file path, line proximity (within 8 lines), and keyword overlap (>= 30%) |
| `openenv validate` fails on port | openenv.yaml port != actual | Ensure openenv.yaml says `port: 7860` |
| Inference script hangs | LLM API unreachable or slow | Check HF_TOKEN is set; use `--random` for testing without LLM |
| Windows encoding errors | UTF-8 not default on Windows | The inference script auto-wraps stdout in UTF-8; ensure Python 3.10+ |
| `/reset` returns 422 | Missing required fields | Send `{"episode_id": "...", "task": "bug_hunt", "agent_id": "A"}` |

## Future Work

- **N-agent scaling:** Extend from 2 to N agents with tournament-style matchmaking and Elo ratings
- **Adaptive difficulty:** Dynamically adjust bug count and subtlety based on agent performance
- **Real codebases:** Replace generated templates with real open-source code + known CVEs
- **Heterogeneous models:** Pit different model families against each other to study cross-model learning
- **Persistent learning:** Track agent improvement across episodes, not just within a single episode

## License

MIT

## Credits

Built by **Team Unmatrix** for the [Meta OpenEnv Hackathon](https://huggingface.co/spaces/open-env/hackathon). Research foundations from Du et al. (ICML 2024) and the MARTI framework (ICLR 2026).
