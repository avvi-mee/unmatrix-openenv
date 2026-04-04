"""Architecture review grader: keyword-match fraction score."""


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


def _keyword_match_fraction(flag: dict, bug: dict) -> float:
    kws = bug.get("expected_keywords", [])
    if not kws:
        return 1.0
    desc = flag.get("description", "").lower()
    return sum(1 for k in kws if k.lower() in desc) / len(kws)


def compute_score(flags: list[dict], ground_truth: list[dict]) -> float:
    if not ground_truth:
        return 0.0
    total = len(ground_truth)
    matched: set[tuple] = set()
    total_kw_fraction = 0.0
    for flag in flags:
        is_tp, bug = is_true_positive(flag, ground_truth)
        if is_tp:
            key = (bug["file"], bug["line"])
            if key not in matched:
                matched.add(key)
                total_kw_fraction += _keyword_match_fraction(flag, bug)
    return min(1.0, total_kw_fraction / total)
