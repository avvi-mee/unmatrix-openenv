from server.data_gen.bug_generator import generate


def load(seed: int = 42) -> dict:
    data = generate(seed)
    data.setdefault("max_steps", 20)
    data.setdefault("task_type", "bug_hunt")
    return data
