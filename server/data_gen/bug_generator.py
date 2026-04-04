import random

TEMPLATES = [
    {
        "filename": "finance.py",
        "code": """\
\"\"\"Finance utility module for interest calculations.\"\"\"
import math


def compound_interest(principal, rate, times_per_year, years):
    \"\"\"Calculate compound interest.\"\"\"
    # Bug: uses addition instead of multiplication for growth factor
    amount = principal * (1 + rate + times_per_year) ** (times_per_year * years)
    return round(amount - principal, 2)


def simple_interest(principal, rate, years):
    \"\"\"Calculate simple interest.\"\"\"
    return round(principal * rate * years, 2)


def present_value(future_value, rate, years):
    \"\"\"Calculate present value given future value.\"\"\"
    if rate <= 0:
        raise ValueError("Rate must be positive")
    # Bug: exponent sign is wrong; should be negative power
    pv = future_value * (1 + rate) ** years
    return round(pv, 2)


def annuity_payment(principal, annual_rate, num_payments):
    \"\"\"Calculate fixed annuity payment.\"\"\"
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return round(principal / num_payments, 2)
    numerator = principal * monthly_rate * (1 + monthly_rate) ** num_payments
    denominator = (1 + monthly_rate) ** num_payments - 1
    return round(numerator / denominator, 2)


def effective_annual_rate(nominal_rate, compounding_periods):
    \"\"\"Convert nominal rate to effective annual rate.\"\"\"
    return round((1 + nominal_rate / compounding_periods) ** compounding_periods - 1, 6)
""",
        "bugs": [
            {
                "file": "finance.py",
                "line": 7,
                "severity": "major",
                "type": "logic_error",
                "description": "compound_interest uses addition instead of division: formula should be (1 + rate/times_per_year) not (1 + rate + times_per_year)",
                "expected_keywords": ["compound", "formula", "division", "rate"]
            },
            {
                "file": "finance.py",
                "line": 18,
                "severity": "major",
                "type": "logic_error",
                "description": "present_value exponent should be negative to discount future value back; positive exponent inflates instead of discounts",
                "expected_keywords": ["present", "exponent", "negative", "discount"]
            }
        ]
    },
    {
        "filename": "text_processor.py",
        "code": """\
\"\"\"Text processing utilities.\"\"\"


def truncate_string(s, max_len):
    \"\"\"Truncate string to max_len characters, adding ellipsis if truncated.\"\"\"
    if len(s) <= max_len:
        return s
    # Bug: off-by-one; slice should be s[:max_len-3] to leave room for '...'
    return s[:max_len] + "..."


def count_words(text):
    \"\"\"Count number of words in text.\"\"\"
    if not text or not text.strip():
        return 0
    return len(text.split())


def extract_emails(text):
    \"\"\"Extract email-like tokens from text.\"\"\"
    tokens = text.split()
    return [t for t in tokens if "@" in t and "." in t]


def pad_center(s, width, fillchar=" "):
    \"\"\"Center string in a field of given width.\"\"\"
    if len(s) >= width:
        return s
    total_padding = width - len(s)
    left_pad = total_padding // 2
    right_pad = total_padding - left_pad
    return fillchar * left_pad + s + fillchar * right_pad


def first_n_lines(text, n):
    \"\"\"Return first n lines of a multiline string.\"\"\"
    lines = text.splitlines()
    # Bug: should slice lines[:n], not lines[:n-1] — last line dropped
    return "\\n".join(lines[:n - 1])


def reverse_words(text):
    \"\"\"Reverse the order of words in text.\"\"\"
    return " ".join(text.split()[::-1])
""",
        "bugs": [
            {
                "file": "text_processor.py",
                "line": 8,
                "severity": "minor",
                "type": "off_by_one",
                "description": "truncate_string slice is off-by-one: s[:max_len] leaves no room for ellipsis; should be s[:max_len-3] to stay within max_len total",
                "expected_keywords": ["truncate", "slice", "ellipsis", "off-by-one"]
            },
            {
                "file": "text_processor.py",
                "line": 37,
                "severity": "minor",
                "type": "off_by_one",
                "description": "first_n_lines uses n-1 in slice which drops the last requested line; should be lines[:n]",
                "expected_keywords": ["lines", "slice", "off-by-one", "n-1"]
            }
        ]
    },
    {
        "filename": "statistics_utils.py",
        "code": """\
\"\"\"Basic statistics utilities.\"\"\"


def mean(values):
    \"\"\"Compute arithmetic mean.\"\"\"
    if not values:
        return 0.0
    return sum(values) / len(values)


def variance(values):
    \"\"\"Compute population variance.\"\"\"
    if len(values) < 2:
        return 0.0
    m = mean(values)
    # Bug: integer division used; should be / len(values) for float result
    return sum((x - m) ** 2 for x in values) // len(values)


def std_dev(values):
    \"\"\"Compute population standard deviation.\"\"\"
    return variance(values) ** 0.5


def median(values):
    \"\"\"Compute median of a list.\"\"\"
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return sorted_vals[mid]


def percentile(values, p):
    \"\"\"Compute p-th percentile (0-100).\"\"\"
    if not values or not (0 <= p <= 100):
        raise ValueError("Invalid input")
    sorted_vals = sorted(values)
    # Bug: index computed with integer division loses fractional index
    idx = (p / 100) * len(sorted_vals) // 1
    idx = int(min(idx, len(sorted_vals) - 1))
    return sorted_vals[idx]
""",
        "bugs": [
            {
                "file": "statistics_utils.py",
                "line": 15,
                "severity": "major",
                "type": "type_error",
                "description": "variance uses integer division (//) which truncates the result; should use true division (/) to return float variance",
                "expected_keywords": ["variance", "integer", "division", "float"]
            },
            {
                "file": "statistics_utils.py",
                "line": 37,
                "severity": "minor",
                "type": "logic_error",
                "description": "percentile index uses // 1 for floor which may map p=100 to out-of-bounds; fractional index interpolation is lost",
                "expected_keywords": ["percentile", "index", "floor", "interpolation"]
            }
        ]
    },
    {
        "filename": "search_utils.py",
        "code": """\
\"\"\"Search and filtering utilities.\"\"\"


def linear_search(items, target):
    \"\"\"Return index of target in items, or -1 if not found.\"\"\"
    for i, item in enumerate(items):
        if item == target:
            return i
    # Bug: missing return -1; function returns None when not found
    pass


def binary_search(sorted_items, target):
    \"\"\"Return index of target in sorted list, or -1 if not found.\"\"\"
    lo, hi = 0, len(sorted_items) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if sorted_items[mid] == target:
            return mid
        elif sorted_items[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def filter_range(items, low, high):
    \"\"\"Return items in range [low, high].\"\"\"
    return [x for x in items if low <= x <= high]


def find_duplicates(items):
    \"\"\"Return list of duplicate values.\"\"\"
    seen = set()
    duplicates = []
    for item in items:
        if item in seen:
            # Bug: appends item even if already in duplicates list
            duplicates.append(item)
        seen.add(item)
    return duplicates


def top_n(items, n):
    \"\"\"Return top n largest items in descending order.\"\"\"
    return sorted(items, reverse=True)[:n]
""",
        "bugs": [
            {
                "file": "search_utils.py",
                "line": 10,
                "severity": "major",
                "type": "missing_return",
                "description": "linear_search missing return -1 at end of function; returns None instead of -1 when target not found",
                "expected_keywords": ["return", "missing", "None", "-1"]
            },
            {
                "file": "search_utils.py",
                "line": 34,
                "severity": "minor",
                "type": "logic_error",
                "description": "find_duplicates appends duplicate items multiple times if they appear more than twice; should check if item not already in duplicates before appending",
                "expected_keywords": ["duplicate", "append", "set", "check"]
            }
        ]
    },
    {
        "filename": "file_utils.py",
        "code": """\
\"\"\"File I/O utilities.\"\"\"
import os


def read_lines(filepath):
    \"\"\"Read all lines from a file, stripping newlines.\"\"\"
    # Bug: file handle never closed; should use 'with' context manager
    f = open(filepath, "r", encoding="utf-8")
    lines = [line.rstrip("\\n") for line in f.readlines()]
    return lines


def write_lines(filepath, lines):
    \"\"\"Write list of strings to file, one per line.\"\"\"
    with open(filepath, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\\n")


def count_lines(filepath):
    \"\"\"Count number of non-empty lines in a file.\"\"\"
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def safe_read(filepath, default=""):
    \"\"\"Read file contents, returning default on error.\"\"\"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    # Bug: catches Exception instead of specific OSError/IOError
    except Exception:
        return default


def append_line(filepath, line):
    \"\"\"Append a single line to a file.\"\"\"
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(line + "\\n")
""",
        "bugs": [
            {
                "file": "file_utils.py",
                "line": 6,
                "severity": "major",
                "type": "resource_leak",
                "description": "read_lines opens file without context manager; file handle is never closed causing resource leak",
                "expected_keywords": ["file", "context", "manager", "closed", "with"]
            },
            {
                "file": "file_utils.py",
                "line": 33,
                "severity": "minor",
                "type": "broad_exception",
                "description": "safe_read catches bare Exception which hides unexpected errors; should catch specific OSError or FileNotFoundError",
                "expected_keywords": ["exception", "specific", "OSError", "broad"]
            }
        ]
    }
]


def generate(seed: int = 42) -> dict:
    random.seed(seed)
    t = TEMPLATES[seed % len(TEMPLATES)]
    return {
        "name": "bug_hunt",
        "description": (
            "Review the provided Python module for bugs. "
            "Flag each issue with the file name, line number, severity, and a clear description."
        ),
        "files": [t["filename"]],
        "content": {t["filename"]: t["code"]},
        "bugs": t["bugs"],
        "task_type": "bug_hunt",
    }
