from server.data_gen.architecture_generator import generate


def load(seed: int = 42) -> dict:
    data = generate(seed)
    data.setdefault("max_steps", 20)
    data.setdefault("task_type", "architecture_review")
    return data
