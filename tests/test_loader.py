import json

import pytest

from agent_contract.loader import (
    LoadError,
    expand_paths,
    from_canonical,
    from_langchain,
    from_openai_chat,
    is_empty,
    iter_records,
    load_traces,
    normalize_record,
)


def test_is_empty_matrix():
    assert is_empty(None)
    assert is_empty("")
    assert is_empty("  ")
    assert is_empty("null")
    assert is_empty("{}")
    assert is_empty("[]")
    assert is_empty([])
    assert is_empty({})
    assert not is_empty("0")
    assert not is_empty(0)
    assert not is_empty(False)
    assert not is_empty([1])


def test_openai_chat_pairs_tool_results():
    record = {
        "model": "m",
        "messages": [
            {"role": "system", "content": "be nice"},
            {"role": "user", "content": "refund?"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "1", "function": {"name": "search_docs", "arguments": '{"q":"refund"}'}},
            ]},
            {"role": "tool", "content": '{"items":[],"total":0}'},
            {"role": "assistant", "content": "Within 7 days."},
        ],
    }
    trace = from_openai_chat(record)
    assert trace is not None
    assert trace.input == "refund?"
    assert trace.output == "Within 7 days."
    assert trace.tool_names() == ["search_docs"]
    call = trace.tool_calls()[0]
    assert call.args == {"q": "refund"}
    assert call.result == {"items": [], "total": 0}
    assert trace.meta["model"] == "m"


def test_langchain_pairs():
    record = {
        "inputs": {"input": "warranty?"},
        "outputs": {"output": "24 months"},
        "intermediate_steps": [({"tool": "read_file", "tool_input": {"path": "docs/w.md"}}, "ok")],
    }
    trace = from_langchain(record)
    assert trace.input == "warranty?"
    assert trace.output == "24 months"
    assert trace.tool_calls()[0].name == "read_file"
    assert trace.tool_calls()[0].result == "ok"


def test_canonical_keeps_unknown_steps_as_messages():
    record = {"id": "x", "input": "q", "output": "a",
              "steps": [{"type": "tool_call", "name": "t", "arguments": '{"a":1}', "result": None},
                        {"type": "error", "text": "boom"},
                        {"type": "whatever", "content": "hello"}]}
    trace = from_canonical(record)
    assert trace.id == "x"
    assert trace.steps[0].kind == "tool"
    assert trace.steps[0].args == {"a": 1}
    assert trace.steps[1].kind == "error"
    assert trace.steps[2].kind == "message"
    assert trace.steps[2].text == "hello"


def test_normalize_falls_back_to_bare_pair():
    trace = normalize_record({"input": "q", "output": "a"})
    assert trace is not None
    assert trace.steps == []
    assert trace.input == "q"
    assert normalize_record({"nothing": 1}) is None


def test_iter_records_supports_json_array(tmp_path):
    path = tmp_path / "arr.json"
    path.write_text(json.dumps([{"input": "a", "output": "b"}]), encoding="utf-8")
    rows = list(iter_records(path))
    assert rows == [{"input": "a", "output": "b"}]


def test_iter_records_reports_line_number(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"input":"a"}\n{broken\n', encoding="utf-8")
    with pytest.raises(LoadError) as exc:
        list(iter_records(path))
    assert ":2:" in str(exc.value)


def test_expand_paths_dedupes_and_sorts(tmp_path):
    (tmp_path / "a.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "b.jsonl").write_text("", encoding="utf-8")
    files = expand_paths([str(tmp_path), str(tmp_path / "a.jsonl")])
    assert [f.name for f in files] == ["a.jsonl", "b.jsonl"]


def test_expand_paths_missing():
    with pytest.raises(LoadError):
        expand_paths(["does/not/exist.jsonl"])


def test_load_traces_counts(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        '{"input":"q","output":"a"}\n{"junk":true}\n{"messages":[{"role":"user","content":"hi"},'
        '{"role":"assistant","content":"yo"}]}\n',
        encoding="utf-8",
    )
    traces, stats = load_traces([str(path)])
    assert stats["traces"] == 2
    assert stats["skipped"] == 1
    assert stats["files"] == 1


def test_load_examples_roundtrip(baseline_rows, tmp_path):
    path = tmp_path / "b.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in baseline_rows), encoding="utf-8")
    traces, stats = load_traces([str(path)])
    assert stats["traces"] == 40
    assert traces[0].tool_names() == ["search_docs", "read_file", "get_order"]