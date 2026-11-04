import json
from pathlib import Path

import pytest

from helpers import make_tool, make_trace  # noqa: F401  (re-exported for tests)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def baseline_rows():
    text = (EXAMPLES / "traces-baseline.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture
def candidate_rows():
    text = (EXAMPLES / "traces-candidate.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture
def simple_traces():
    """12 traces: 3 questions repeated 4 times, tools that never return empty."""
    traces = []
    questions = ["refund window?", "shipping time?", "warranty period?"]
    answers = [
        "Refunds are allowed within 7 days.",
        "Shipping takes 5 days.",
        "Warranty is 24 months.",
    ]
    idx = 1
    for _ in range(4):
        for q, a in zip(questions, answers):
            traces.append(make_trace(
                idx, q, a,
                [make_tool("search_docs", {"items": [{"id": idx}], "total": 1}, query=q),
                 make_tool("read_file", {"content": "x", "bytes": 1}, path="docs/policy.md")],
            ))
            idx += 1
    return traces