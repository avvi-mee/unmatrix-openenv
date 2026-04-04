"""Security audit grader: severity-weighted TP score."""

SEVERITY_WEIGHTS = {
    "critical": 0.40,
    "major": 0.35,
    "minor": 0.25,
}


def is_true_positive(flag: dict, ground_truth: list[dict]) -> tuple[bool, dict | None]:
    for bug in ground_truth:
        same_file = flag.get("file_path", "") == bug["file"]
        close_line = abs(flag.get("line_number", 0) - bug["line"]) <= 8
        desc = flag.get("description", "").lower()
        kws = bug.get("expected_keywords", [])
        kw_ok = (sum(1 for k in kws if k.lower() in desc) / len(kws) >= 0.30) if kws else True
        if same_file and close_line and kw_ok:
            return True, bug
    return False, None


def compute_score(flags: list[dict], ground_truth: list[dict]) -> float:
    if not ground_truth:
        return 0.0
    total_weight = sum(SEVERITY_WEIGHTS.get(bug.get("severity", "minor"), 0.25) for bug in ground_truth)
    if total_weight == 0:
        return 0.0
    matched: set[tuple] = set()
    matched_weight = 0.0
    for flag in flags:
        is_tp, bug = is_true_positive(flag, ground_truth)
        if is_tp:
            key = (bug["file"], bug["line"])
            if key not in matched:
                matched.add(key)
                matched_weight += SEVERITY_WEIGHTS.get(bug.get("severity", "minor"), 0.25)
    return min(1.0, matched_weight / total_weight)
