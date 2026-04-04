from enum import Enum
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    read_file = "read_file"
    flag_issue = "flag_issue"
    remove_flag = "remove_flag"
    submit_round = "submit_round"
    submit_final = "submit_final"


class PeerReviewAction(BaseModel):
    action_type: ActionType = ActionType.submit_final
    file_path: str = ""
    line_number: int = 0
    issue_id: str = ""
    issue_type: str = ""
    severity: str = "minor"
    description: str = ""


class PeerReviewObservation(BaseModel):
    phase: str = "round_1"
    task_name: str = ""
    task_description: str = ""
    files_available: list[str] = Field(default_factory=list)
    current_file: str = ""
    file_content: str = ""
    my_flags: list[dict] = Field(default_factory=list)
    my_round1_flags: list[dict] = Field(default_factory=list)
    opponent_round1_flags: list[dict] = Field(default_factory=list)
    last_action_result: str = ""
    step_number: int = 0
    max_steps: int = 20
    error: str | None = None


class ResetRequest(BaseModel):
    episode_id: str = "default"
    task: str = "bug_hunt"
    agent_id: str = "A"
    seed: int | None = None


class StepRequest(BaseModel):
    episode_id: str = "default"
    agent_id: str = "A"
    action: PeerReviewAction


class EnvResponse(BaseModel):
    observation: PeerReviewObservation
    done: bool = False
    reward: float = 0.0
    info: dict = Field(default_factory=dict)


class StateResponse(BaseModel):
    episode_id: str = ""
    agent_id: str = ""
    phase: str = "round_1"
    task_name: str = ""
    step_count: int = 0
    my_flags_count: int = 0
    opponent_ready: bool = False
