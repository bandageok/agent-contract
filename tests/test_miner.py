from agent_contract.miner import (
    MineOptions,
    mine,
    mine_action,
    mine_drift,
    mine_shape,
    percentile,
    summarize_mining,
)
from agent_contract.miner import _Builder
from agent_contract.model import RED, AMBER

from helpers import make_tool, make_trace


def kinds(contract):
    return [a.kind for a in contract.assertions]


def test_percentile_edges():
    assert percentile([], 0.5) == 0.0
    assert percentile([7], 0.9) == 7.0
    assert percentile([0, 10], 0.5) == 5.0
    assert percentile(list(range(11)), 0.95) > 9


def test_shape_not_empty_is_generated_when_always_non_empty(simple_traces):
    b = _Builder()
    mine_shape(simple_traces, MineOptions(min_support=3), b)
    not_empty = [a for a in b.items if a.kind == "shape.tool_result_not_empty"]
    assert {a.params["tool"] for a in not_empty} == {"search_docs", "read_file"}
    assert all(a.evidence for a in not_empty)
    assert all(a.severity == RED for a in not_empty)


def test_shape_not_empty_skipped_when_often_empty():
    traces = []
    for i in range(10):
        result = None if i % 2 else {"items": [1]}
        traces.append(make_trace(i, "q", "a", [make_tool("search_docs", result)]))
    b = _Builder()
    mine_shape(traces, MineOptions(min_support=3), b)
    assert [a for a in b.items if a.kind == "shape.tool_result_not_empty"] == []


def test_shape_tolerance_when_rarely_empty():
    traces = []
    for i in range(40):
        result = None if i == 0 else {"items": [1]}
        traces.append(make_trace(i, "q", "a", [make_tool("search_docs", result)]))
    b = _Builder()
    mine_shape(traces, MineOptions(min_support=3), b)
    found = [a for a in b.items if a.kind == "shape.tool_result_not_empty"]
    assert len(found) == 1
    assert found[0].params.get("tolerance")


def test_shape_field_and_len_range():
    traces = []
    for i in range(10):
        traces.append(make_trace(i, "q", "a", [
            make_tool("get_order", {"id": "1", "total": i}),
            make_tool("list_items", [1] * (3 + i % 3)),
        ]))
    b = _Builder()
    mine_shape(traces, MineOptions(min_support=3), b)
    fields = {a.params["field"] for a in b.items if a.kind == "shape.result_has_field"}
    assert fields == {"id", "total"}
    ranges = [a for a in b.items if a.kind == "shape.result_len_range"]
    assert len(ranges) == 1
    assert ranges[0].params["min"] <= 3 <= ranges[0].params["max"]


def test_min_support_blocks_thin_evidence():
    traces = [make_trace(1, "q", "a", [make_tool("rare", {"x": 1})])]
    b = _Builder()
    mine_shape(traces, MineOptions(min_support=5), b)
    assert b.items == []


def test_action_tool_allowed_and_pairs(simple_traces):
    b = _Builder()
    mine_action(simple_traces, MineOptions(min_support=3), b)
    kinds_found = [a.kind for a in b.items]
    assert "action.tool_allowed" in kinds_found
    assert "action.tool_pair_allowed" in kinds_found
    allowed = next(a for a in b.items if a.kind == "action.tool_allowed")
    assert set(allowed.params["tools"]) == {"search_docs", "read_file"}
    assert allowed.severity == AMBER


def test_action_path_within_root(simple_traces):
    b = _Builder()
    mine_action(simple_traces, MineOptions(min_support=3), b)
    path_rules = [a for a in b.items if a.kind == "action.path_within_root"]
    assert len(path_rules) == 1
    assert path_rules[0].params["root"] == "docs"
    assert path_rules[0].params["arg"] == "path"


def test_action_max_calls(simple_traces):
    b = _Builder()
    mine_action(simple_traces, MineOptions(min_support=3), b)
    max_rules = [a for a in b.items if a.kind == "action.max_calls"]
    assert len(max_rules) == 2
    assert all(a.params["max"] >= 1 for a in max_rules)


def test_action_disabled():
    traces = [make_trace(i, "q", "a", [make_tool("t", {})]) for i in range(10)]
    b = _Builder()
    mine_action(traces, MineOptions(min_support=3, include_action=False), b)
    assert b.items == []


def test_drift_captures_every_input(simple_traces):
    b = _Builder()
    store = {}
    mine_drift(simple_traces, MineOptions(min_support=2), b, store)
    assert len(store) == 3, "every distinct input must be captured, not sampled"
    assert len(b.items) == 1 and b.items[0].kind == "drift.batch"
    assert b.items[0].params["inputs"] == 3
    assert all(v["output"] for v in store.values())
    assert any("duration:7days" in v["facts"] for v in store.values())


def test_drift_skips_traces_without_output():
    traces = [make_trace(1, "q", ""), make_trace(2, "q2", "answer")]
    b = _Builder()
    store = {}
    mine_drift(traces, MineOptions(), b, store)
    assert len(store) == 1
    assert b.items[0].params["inputs"] == 1


def test_drift_keeps_first_answer_per_input():
    traces = [make_trace(1, "same", "first"), make_trace(2, "same", "second")]
    store = {}
    mine_drift(traces, MineOptions(), _Builder(), store)
    assert len(store) == 1
    assert list(store.values())[0]["output"] == "first"


def test_drift_disabled():
    b = _Builder()
    mine_drift([make_trace(1, "q", "a")], MineOptions(include_drift=False), b, {})
    assert b.items == []


def test_mine_end_to_end_and_summary(simple_traces):
    contract = mine(simple_traces, MineOptions(min_support=3), source={"x": 1})
    assert contract.assertions
    assert contract.generated_at.endswith("Z")
    assert contract.source["trace_count"] == len(simple_traces)
    assert [a.id for a in contract.assertions] == [
        "A%d" % i for i in range(1, len(contract.assertions) + 1)]
    assert all(a.evidence for a in contract.assertions)
    assert summarize_mining(contract)["drift"] > 0
    # round-trips through the on-disk shape without losing anything
    from agent_contract.model import Contract
    same = Contract.from_dict(contract.to_dict())
    assert [a.to_dict() for a in same.assertions] == [a.to_dict() for a in contract.assertions]

def test_shape_key_count_range():
    traces = [make_trace(i, "q", "a", [make_tool("g", {"a": 1, "b": 2})]) for i in range(10)]
    b = _Builder()
    mine_shape(traces, MineOptions(min_support=3), b)
    rule = [a for a in b.items if a.kind == "shape.result_key_count"][0]
    assert rule.params == {"tool": "g", "min": 2, "max": 2}
    assert rule.evidence
