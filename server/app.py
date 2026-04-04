"""FastAPI application for Peer Review Arena."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

import server.environment as env_module
from server.models import EnvResponse, ResetRequest, StateResponse, StepRequest

app = FastAPI(title="Peer Review Arena", version="1.0.0")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "done": False, "reward": 0.0,
                 "observation": {}, "info": {}},
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "peer_review_arena"}


@app.post("/reset", response_model=EnvResponse)
def reset(req: ResetRequest):
    try:
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


def main():
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860, workers=1)


if __name__ == "__main__":
    main()
