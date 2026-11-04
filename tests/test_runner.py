from agent_contract.model import AMBER, GREEN, RED, Assertion, Contract, Trace
from agent_contract.runner import (
    eval_facts_preserved,
    eval_max_calls,
    eval_path_within_root,
    eval_result_has_field,
    eval_result_len_range,
    eval_similarity,
    eval_tool_allowed,
    eval_tool_pair_allowed,
    eval_tool_result_not_empty,
    inside_root,
    run_contract,
)

from helpers import make_tool, make_trace


def A(kind, **params):
    return Assertion(id="A1", kind=kind, title="t", params=params, evidence="e")


def test_inside_root_boundaries():
    assert inside_root("docs/policies/a.md", "docs")
    assert inside_root("docs/a.md", "docs/")
    assert inside_root("./docs/a.md", "docs")
    assert inside_root("docs\\a.md", "docs")
    assert not inside_root("docs2/a.md", "docs")
    assert not inside_root("../secrets/key.pem", "docs")
    assert not inside_root("/etc/passwd", "docs")
    assert inside_root("C:\\repo\\docs\\a.md", "C:/repo/docs")
    assert inside_root("anything", "")


def test_tool_result_not_empty_red_and_green():
    bad = [make_trace(1, "q", "a", [make_tool("s", None)])]
    good = [make_trace(1, "q", "a", [make_tool("s", {"x": 1})])]
    rule = A("shape.tool_result_not_empty", tool="s")
    assert eval_tool_result_not_empty(rule, bad).status == RED
    assert eval_tool_result_not_empty(rule, good).status == GREEN
    empty = [make_trace(1, "q", "a", [])]
    got = eval_tool_result_not_empty(rule, empty)
    assert got.status == GREEN and got.skipped == 1


def test_tool_result_not_empty_amber_within_tolerance():
    traces = [make_trace(i, "q", "a", [make_tool("s", None if i == 0 else {"x": 1})])
              for i in range(20)]
    rule = A("shape.tool_result_not_empty", tool="s", tolerance=0.1)
    assert eval_tool_result_not_empty(rule, traces).status == AMBER


def test_result_has_field():
    rule = A("shape.result_has_field", tool="g", field="total")
    ok = [make_trace(1, "q", "a", [make_tool("g", {"total": 1})])]
    bad = [make_trace(1, "q", "a", [make_tool("g", {"id": 1})])]
    assert eval_result_has_field(rule, ok).status == GREEN
    assert eval_result_has_field(rule, bad).status == RED
    assert eval_result_has_field(rule, [make_trace(1, "q", "a", [])]).status == GREEN


def test_result_len_range():
    rule = A("shape.result_len_range", tool="l", min=2, max=4)
    ok = [make_trace(1, "q", "a", [make_tool("l", [1, 2, 3])])]
    amber = [make_trace(1, "q", "a", [make_tool("l", [1] * 9)])]
    red = [make_trace(1, "q", "a", [make_tool("l", [])])]
    assert eval_result_len_range(rule, ok).status == GREEN
    assert eval_result_len_range(rule, amber).status == AMBER
    assert eval_result_len_range(rule, red).status == RED


def test_tool_allowed():
    rule = A("action.tool_allowed", tools=["a", "b"])
    ok = [make_trace(1, "q", "a", [make_tool("a", {}), make_tool("b", {})])]
    novel = [make_trace(1, "q", "a", [make_tool("a", {}), make_tool("c", {})])]
    assert eval_tool_allowed(rule, ok).status == GREEN
    got = eval_tool_allowed(rule, novel)
    assert got.status == AMBER
    assert got.samples[0]["tool"] == "c"


def test_tool_pair_allowed():
    rule = A("action.tool_pair_allowed", pairs=[["a", "b"]])
    ok = [make_trace(1, "q", "a", [make_tool("a", {}), make_tool("b", {})])]
    novel = [make_trace(1, "q", "a", [make_tool("b", {}), make_tool("a", {})])]
    assert eval_tool_pair_allowed(rule, ok).status == GREEN
    assert eval_tool_pair_allowed(rule, novel).status == AMBER


def test_path_within_root():
    rule = A("action.path_within_root", tool="read_file", arg="path", root="docs")
    ok = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="docs/a.md")])]
    bad = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="../secrets/key.pem")])]
    assert eval_path_within_root(rule, ok).status == GREEN
    got = eval_path_within_root(rule, bad)
    assert got.status == RED
    assert got.samples[0]["path"] == "../secrets/key.pem"


def test_path_within_root_glob_whitelist_allows_matching_path():
    rule = A("action.path_within_root", tool="read_file", arg="path", root="docs",
             allowed_patterns=["data/*.csv"])
    traces = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="data/report.csv")])]
    assert eval_path_within_root(rule, traces).status == GREEN


def test_path_within_root_glob_whitelist_rejects_non_matching_path():
    rule = A("action.path_within_root", tool="read_file", arg="path", root="docs",
             allowed_patterns=["data/*.csv"])
    traces = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="data/report.json")])]
    assert eval_path_within_root(rule, traces).status == RED


def test_path_within_root_glob_whitelist_recursive_pattern():
    rule = A("action.path_within_root", tool="read_file", arg="path", root="docs",
             allowed_patterns=["docs/**"])
    traces = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="docs/a/b.md")])]
    assert eval_path_within_root(rule, traces).status == GREEN


def test_path_within_root_handles_lists():
    rule = A("action.path_within_root", tool="cp", arg="paths", root="docs")
    traces = [make_trace(1, "q", "a", [make_tool("cp", {}, paths=["docs/a", "/etc/passwd"])])]
    assert eval_path_within_root(rule, traces).status == RED


def test_max_calls_amber_and_red():
    rule = A("action.max_calls", tool="s", max=2, hard_max=4)
    ok = [make_trace(1, "q", "a", [make_tool("s", {})] * 2)]
    amber = [make_trace(1, "q", "a", [make_tool("s", {})] * 3)]
    red = [make_trace(1, "q", "a", [make_tool("s", {})] * 6)]
    assert eval_max_calls(rule, ok).status == GREEN
    assert eval_max_calls(rule, amber).status == AMBER
    assert eval_max_calls(rule, red).status == RED


def test_facts_preserved():
    rule = A("drift.facts_preserved", input="refund?", input_key="refund",
             facts=["duration:7days"])
    ok = [make_trace(1, "refund?", "within 7 days")]
    bad = [make_trace(1, "refund?", "within 3 days")]
    assert eval_facts_preserved(rule, ok).status == GREEN
    got = eval_facts_preserved(rule, bad)
    assert got.status == RED
    assert "duration:7days" in got.message
    assert eval_facts_preserved(rule, [make_trace(2, "other", "x")]).skipped == 1


def test_facts_added_is_amber():
    rule = A("drift.facts_preserved", input="refund?", input_key="refund",
             facts=["duration:7days"])
    traces = [make_trace(1, "refund?", "within 7 days, or 30 days for EU")]
    assert eval_facts_preserved(rule, traces).status == AMBER


def test_similarity_thresholds():
    baseline = "International orders can be refunded within 7 days of delivery."
    rule = A("drift.similarity", input="refund?", input_key="refund",
             baseline_output=baseline, min_ratio=0.55)
    assert eval_similarity(rule, [make_trace(1, "refund?", baseline)]).status == GREEN
    amber = "International orders can be refunded within 7 days of the delivery date, subject to review."
    assert eval_similarity(rule, [make_trace(1, "refund?", amber)]).status in (GREEN, AMBER)
    red = "Totally unrelated answer about shipping to Mars."
    assert eval_similarity(rule, [make_trace(1, "refund?", red)]).status == RED


def test_similarity_no_coverage():
    rule = A("drift.similarity", input="refund?", input_key="refund",
             baseline_output="x y z", min_ratio=0.5)
    got = eval_similarity(rule, [make_trace(1, "different", "x")])
    assert got.status == GREEN and got.skipped == 1


def test_run_contract_handles_unknown_kind():
    contract = Contract.from_dict({"assertions": [
        {"id": "A1", "kind": "made.up", "title": "x", "params": {}, "evidence": "e"},
        {"id": "A2", "kind": "action.tool_allowed", "title": "y",
         "params": {"tools": ["a"]}, "evidence": "e"},
    ]})
    traces = [make_trace(1, "q", "a", [make_tool("a", {})])]
    report = run_contract(contract, traces)
    assert len(report.findings) == 2
    assert report.counts()[GREEN] == 2
    assert report.stats["traces"] == 1
    assert report.failed() is False


def test_report_aggregates():
    contract = Contract.from_dict({"assertions": [
        {"id": "A1", "kind": "shape.tool_result_not_empty", "title": "x",
         "params": {"tool": "s"}, "evidence": "e"},
    ]})
    report = run_contract(contract, [make_trace(1, "q", "a", [make_tool("s", None)])])
    assert report.failed() is True
    assert report.worst() == RED
    assert report.counts() == {RED: 1, AMBER: 0, GREEN: 0}


def test_disabled_assertions_are_skipped():
    contract = Contract.from_dict({"assertions": [
        {"id": "A1", "kind": "action.tool_allowed", "title": "x",
         "params": {"tools": []}, "evidence": "e", "enabled": False},
    ]})
    report = run_contract(contract, [make_trace(1, "q", "a", [])])
    assert report.findings == []

def test_result_not_degenerate():
    from agent_contract.runner import eval_result_not_degenerate
    rule = A("shape.result_not_degenerate", tool="read_file")
    ok = [make_trace(1, "q", "a", [make_tool("read_file", {"chars": 12, "bytes": 12})])]
    bad = [make_trace(1, "q", "a", [make_tool("read_file", {"chars": 0, "bytes": 0})])]
    assert eval_result_not_degenerate(rule, ok).status == GREEN
    got = eval_result_not_degenerate(rule, bad)
    assert got.status == RED
    assert got.samples[0]["result"] == {"chars": 0, "bytes": 0}


def test_path_allowed_dirs_fallback():
    rule = A("action.path_within_root", tool="read_file", arg="path",
             allowed_dirs=[".research/raw", "docs"])
    ok = [make_trace(1, "q", "a", [make_tool("read_file", {}, path=".research/raw/a.json")])]
    sibling = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="docs/x/y.md")])]
    bad = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="../../etc/shadow")])]
    bare = [make_trace(1, "q", "a", [make_tool("read_file", {}, path="a.md")])]
    assert eval_path_within_root(rule, ok).status == GREEN
    assert eval_path_within_root(rule, sibling).status == GREEN
    assert eval_path_within_root(rule, bare).status == GREEN
    assert eval_path_within_root(rule, bad).status == RED


def test_numbers_preserved():
    from agent_contract.runner import eval_numbers_preserved
    rule = A("drift.numbers_preserved", input="file?", input_key="file",
             numbers=[830.0, 54405.0])
    same = [make_trace(1, "file?", "a.json has 830 lines and 54405 characters.")]
    all_moved = [make_trace(1, "file?", "a.json has 277 lines and 18135 characters.")]
    dropped = [make_trace(1, "file?", "a.json has 830 lines.")]
    gained = [make_trace(1, "file?", "a.json has 830 lines and 54405 characters in 3 parts.")]
    assert eval_numbers_preserved(rule, same).status == GREEN
    assert eval_numbers_preserved(rule, all_moved).status == RED
    assert eval_numbers_preserved(rule, dropped).status == RED
    assert eval_numbers_preserved(rule, gained).status == AMBER
    assert eval_numbers_preserved(rule, [make_trace(2, "other", "x")]).skipped == 1


def test_low_drift_coverage_is_reported():
    contract = Contract.from_dict({"assertions": [
        {"id": "A1", "kind": "drift.similarity", "title": "x",
         "params": {"input": "a", "input_key": "a", "baseline_output": "hello world",
                    "min_ratio": 0.5}, "evidence": "e"},
    ]})
    report = run_contract(contract, [make_trace(1, "totally different", "hello")])
    assert report.stats["drift_coverage"] == 0.0
    assert report.stats["uncovered"] == ["A1"]
    assert report.counts()[GREEN] == 1  # green, but the warning tells the truth
