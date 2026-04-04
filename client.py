"""OpenEnv client for Peer Review Arena."""
from openenv.core import EnvClient
from models import Action, Observation, StateResponse


class PeerReviewArenaClient(EnvClient[Action, Observation, StateResponse]):
    """Client for the Peer Review Arena multi-agent code review environment."""

    action_type = Action
    observation_type = Observation
    state_type = StateResponse
