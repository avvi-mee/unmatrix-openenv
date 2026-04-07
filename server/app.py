"""FastAPI application for Peer Review Arena."""
import os
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

import server.environment as env_module
import server.web_agent as web_agent
from server.models import EnvResponse, ResetRequest, StateResponse, StepRequest

app = FastAPI(title="Peer Review Arena", version="1.0.0")

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "done": False, "reward": 0.0,
                 "observation": {}, "info": {}},
    )


@app.get("/")
def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html_path = os.path.join(_STATIC_DIR, "index.html")
        if os.path.exists(html_path):
            return FileResponse(html_path, media_type="text/html")
    return {
        "name": "Peer Review Arena",
        "description": "Two AI agents independently review code, then learn from each other's findings.",
        "status": "running",
        "endpoints": {
            "GET  /health": "Health check",
            "POST /reset": "Start a new episode",
            "POST /step": "Submit an action",
            "GET  /state": "Get episode state",
        },
        "tasks": ["bug_hunt", "security_audit", "architecture_review"],
        "agents": ["A", "B"],
        "phases": ["round_1", "cross_review", "round_2", "finished"],
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "peer_review_arena"}


@app.post("/reset", response_model=EnvResponse)
def reset(req: Optional[ResetRequest] = Body(default=None)):
    if req is None:
        req = ResetRequest()
    try:
        web_agent.reset_agent_state(req.episode_id)
        return env_module.reset(req.episode_id, req.task, req.agent_id, req.seed)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/step", response_model=EnvResponse)
def step(req: StepRequest):
    try:
        return env_module.step(req.episode_id, req.agent_id, req.action)
    except KeyError:
        raise HTTPException(status_code=404, detail="Episode not found. Call /reset first.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/state", response_model=StateResponse)
def state(episode_id: str = "default", agent_id: str = "A"):
    try:
        return env_module.get_state(episode_id, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Web UI API endpoints ─────────────────────────────────────────────────────


@app.post("/api/auto-step")
def api_auto_step(body: dict = Body(...)):
    episode_id = body.get("episode_id", "default")
    agent_id = body.get("agent_id", "B")
    try:
        return web_agent.auto_step(episode_id, agent_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Episode not found. Call /reset first.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reveal-bugs")
def api_reveal_bugs(body: dict = Body(...)):
    episode_id = body.get("episode_id", "default")
    with env_module._lock:
        ep = env_module._episodes.get(episode_id)
        if ep is None:
            raise HTTPException(status_code=404, detail="Episode not found.")
        if ep["phase"] != "finished":
            raise HTTPException(status_code=400, detail="Match not finished yet.")
        bugs = ep["task"].get("bugs", [])
        files = ep["task"].get("content", {})
    return {
        "bugs": bugs,
        "files": {name: content for name, content in files.items()},
    }


def main():
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, workers=1)


if __name__ == "__main__":
    main()
