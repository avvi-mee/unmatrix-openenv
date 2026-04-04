---
title: Peer Review Arena
emoji: 🔍
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Peer Review Arena

An OpenEnv-compliant reinforcement learning environment where two anonymous AI agents independently review the same codebase, then see each other's findings and improve.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Server                     │
│  /reset  /step  /state  /health                     │
├─────────────────────────────────────────────────────┤
│              environment.py (state machine)          │
│   round_1 → cross_review → round_2 → finished       │
├──────────────┬──────────────┬───────────────────────┤
│  data_gen/   │   tasks/     │   graders/            │
│  bug         │  task1       │  grader1 (TP/total)   │
│  security    │  task2       │  grader2 (severity-w) │
│  architecture│  task3       │  grader3 (kw-match)   │
└──────────────┴──────────────┴───────────────────────┘
```

## Phases

| Phase | Description |
|-------|-------------|
| `round_1` | Both agents independently read files and flag issues |
| `cross_review` | Waiting for both agents to submit round 1 |
| `round_2` | Agents see each other's flags and can refine |
| `finished` | Both agents submitted final answers |

## Supported Tasks

| Task | Generator | Grader |
|------|-----------|--------|
| `bug_hunt` | 5 Python file templates with logic/type/control-flow bugs | TP count / total bugs |
| `security_audit` | 5 security vulnerability templates | Severity-weighted TP score |
| `architecture_review` | 5 multi-file microservice anti-pattern templates | Keyword-match fraction |

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

## Setup

### Local Development

```bash
pip install -r requirements.txt

# Start server
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
docker run -p 8000:8000 peer-review-arena
```

## Expected Baseline Output

```
[START] task=bug_hunt env=peer_review_arena model=meta-llama/Llama-3.1-8B-Instruct
[STEP] step=1 agent=agent_A action=read_file result=read_file reward=0.00 done=false error=null
[STEP] step=1 agent=agent_B action=read_file result=read_file reward=0.00 done=false error=null
...
[STEP] step=N agent=agent_A action=submit_final result=submit_final reward=0.50 done=true error=null
[STEP] step=N agent=agent_B action=submit_final result=submit_final reward=0.50 done=true error=null
[END] success=true steps=N score=0.50 rewards=0.00,0.05,...,0.50
```

## openenv.yaml Compliance

- `spec_version: 1` (integer)
- `name: peer_review_arena` (matches `env=` in [START])
- `app: server.app:app`
- `port: 8000`
- `runtime: fastapi`
