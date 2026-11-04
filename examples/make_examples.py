"""Generate the demo trace sets.

Two batches of the same 8 support questions: a baseline that "worked", and a
candidate from a model swap that quietly changed four things. Used by the
README walkthrough, the test suite and the demo recording.

    python examples/make_examples.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
random.seed(7)

QA = [
    {
        "q": "What is the refund window for international orders?",
        "a": "International orders can be refunded within 7 days of delivery.",
        "doc": "docs/policies/refund.md",
        "snippet": "International refunds: 7 days from delivery.",
        "order": {"id": "ORD-1041", "status": "delivered", "total": 84},
    },
    {
        "q": "How long does standard shipping take?",
        "a": "Standard shipping takes 5 days for domestic addresses.",
        "doc": "docs/shipping/standard.md",
        "snippet": "Standard: 5 days domestic, 9 days international.",
        "order": {"id": "ORD-1042", "status": "in_transit", "total": 32},
    },
    {
        "q": "Do you ship to Canada?",
        "a": "Yes. Canada shipping costs 12 USD flat and takes 9 days.",
        "doc": "docs/shipping/international.md",
        "snippet": "Canada: flat 12 USD, 9 days.",
        "order": {"id": "ORD-1043", "status": "delivered", "total": 12},
    },
    {
        "q": "What is the warranty period?",
        "a": "Every device carries a 24 month warranty from the delivery date.",
        "doc": "docs/policies/warranty.md",
        "snippet": "Warranty: 24 months from delivery.",
        "order": {"id": "ORD-1044", "status": "delivered", "total": 240},
    },
    {
        "q": "Can I change my shipping address after ordering?",
        "a": "You can change the address within 2 hours of placing the order.",
        "doc": "docs/policies/address.md",
        "snippet": "Address changes: allowed within 2 hours.",
        "order": {"id": "ORD-1045", "status": "processing", "total": 55},
    },
    {
        "q": "What payment methods do you accept?",
        "a": "We accept 4 payment methods: card, PayPal, bank transfer and Alipay.",
        "doc": "docs/policies/payment.md",
        "snippet": "Payments: card, PayPal, bank transfer, Alipay.",
        "order": {"id": "ORD-1046", "status": "delivered", "total": 18},
    },
    {
        "q": "How do I return a damaged item?",
        "a": "Report a damaged item within 30 days and we cover the return shipping.",
        "doc": "docs/policies/returns.md",
        "snippet": "Damaged items: report within 30 days, shipping covered.",
        "order": {"id": "ORD-1047", "status": "delivered", "total": 99},
    },
    {
        "q": "Is there a restocking fee?",
        "a": "A 15 percent restocking fee applies to opened items only.",
        "doc": "docs/policies/returns.md",
        "snippet": "Restocking: 15 percent, opened items only.",
        "order": {"id": "ORD-1048", "status": "delivered", "total": 67},
    },
]

REPEATS = 5


def trace(qa, idx, model, *, empty_search=False, bad_path=False,
          escalate=False, answer=None, tool_order=None):
    seq = tool_order or ["search_docs", "read_file", "get_order"]
    steps = []
    for name in seq:
        if name == "search_docs":
            steps.append({
                "kind": "tool",
                "name": "search_docs",
                "args": {"query": qa["q"][:60], "top_k": 3},
                "result": [] if empty_search else {
                    "items": [{"doc": qa["doc"], "snippet": qa["snippet"]}],
                    "total": 1,
                },
            })
        elif name == "read_file":
            steps.append({
                "kind": "tool",
                "name": "read_file",
                "args": {"path": "../secrets/key.pem" if bad_path else qa["doc"]},
                "result": {"content": qa["snippet"], "bytes": len(qa["snippet"])},
            })
        elif name == "get_order":
            steps.append({
                "kind": "tool",
                "name": "get_order",
                "args": {"order_id": qa["order"]["id"]},
                "result": dict(qa["order"]),
            })
        elif name == "escalate_to_human":
            steps.append({
                "kind": "tool",
                "name": "escalate_to_human",
                "args": {"reason": "low_confidence"},
                "result": {"ticket": "T-%d" % idx, "queued": True},
            })
    steps.append({"kind": "message", "text": answer or qa["a"]})
    return {
        "id": "%s-%03d" % ("b" if model == "baseline" else "c", idx),
        "input": qa["q"],
        "output": answer or qa["a"],
        "steps": steps,
        "meta": {"model": "support-v1" if model == "baseline" else "support-v2-candidate"},
    }


def build_baseline():
    rows = []
    idx = 1
    for _ in range(REPEATS):
        for qa in QA:
            rows.append(trace(qa, idx, "baseline"))
            idx += 1
    return rows


def build_target():
    """Four quiet changes: empty search, an escaped path, a changed fact, a new tool."""
    rows = []
    idx = 1
    for rep in range(REPEATS):
        for pos, qa in enumerate(QA):
            kwargs = {}
            if rep == 2 and pos == 1:
                kwargs["empty_search"] = True
            if rep == 3 and pos == 2:
                kwargs["empty_search"] = True
            if rep == 1 and pos == 3:
                kwargs["bad_path"] = True
            if rep == 4 and pos == 5:
                kwargs["escalate"] = True
                kwargs["tool_order"] = ["search_docs", "read_file", "escalate_to_human", "get_order"]
            if pos == 0:
                # the silent one: 7 days became 3 days, same tone, same shape
                kwargs["answer"] = "International orders can be refunded within 3 days of delivery."
            rows.append(trace(qa, idx, "target", **kwargs))
            idx += 1
    return rows


def write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("%s: %d traces" % (path, len(rows)))


if __name__ == "__main__":
    write(HERE / "traces-baseline.jsonl", build_baseline())
    write(HERE / "traces-candidate.jsonl", build_target())