# Extending agent-contract: a worked example

Adding one assertion kind, end to end, in about 40 lines. We will add
`shape.result_key_count` — "this tool's result always has between 2 and 6 keys" — which catches a
serialiser that starts dropping fields.

## Step 1 — decide when it is justified (`miner.py`)

Inside `mine_shape`, after the field loop:

```python
if dict_results and len(dict_results) / total >= 0.9:
    counts = [len(_as_dict(s.result) or {}) for s in dict_results]
    lo = int(math.floor(percentile(counts, 0.05)))
    hi = int(math.ceil(percentile(counts, 0.95)))
    if lo >= 1:
        b.add(
            "shape.result_key_count",
            "%s result always has %d..%d keys" % (tool, lo, hi),
            {"tool": tool, "min": lo, "max": hi},
            "%d results, p05=%d p95=%d keys" % (len(counts), lo, hi),
        )
```

Two rules encoded here:

- `lo >= 1` — if the tool sometimes returns a legitimately empty object, this assertion is noise.
- the evidence string carries the percentiles, so a reviewer can check the claim without rerunning.

## Step 2 — evaluate it (`runner.py`)

```python
def eval_result_key_count(a: Assertion, traces: List[Trace],
                          baseline: Optional[Dict[str, Any]] = None) -> Finding:
    tool = a.params.get("tool", "")
    lo, hi = int(a.params.get("min", 0)), int(a.params.get("max", 0))
    calls = [(t, s) for t, s in _calls_for(traces, tool) if isinstance(s.result, dict)]
    if not calls:
        return _finding(a, GREEN, "no dict results for %s" % tool, skipped=len(traces))
    bad = [(t, len(s.result or {})) for t, s in calls
           if not (lo <= len(s.result or {}) <= hi)]
    if not bad:
        return _finding(a, GREEN, "%s: %d results kept %d..%d keys" % (tool, len(calls), lo, hi),
                        checked=len(calls))
    samples = [{"trace": t.id, "tool": tool, "keys": n} for t, n in bad[:MAX_SAMPLES]]
    return _finding(a, RED, "%d/%d results outside %d..%d keys"
                    % (len(bad), len(calls), lo, hi), samples, checked=len(calls))
```

## Step 3 — register it

```python
EVALUATORS: Dict[str, Callable[..., Finding]] = {
    ...
    "shape.result_key_count": eval_result_key_count,
}
```

## Step 4 — test both halves

`tests/test_miner.py`:

```python
def test_shape_key_count_range():
    traces = [make_trace(i, "q", "a", [make_tool("g", {"a": 1, "b": 2})]) for i in range(10)]
    b = _Builder()
    mine_shape(traces, MineOptions(min_support=3), b)
    rule = [a for a in b.items if a.kind == "shape.result_key_count"][0]
    assert rule.params == {"tool": "g", "min": 2, "max": 2}
    assert rule.evidence
```

`tests/test_runner.py`:

```python
def test_result_key_count_status():
    from agent_contract.runner import eval_result_key_count
    rule = A("shape.result_key_count", tool="g", min=2, max=3)
    ok = [make_trace(1, "q", "a", [make_tool("g", {"a": 1, "b": 2})])]
    bad = [make_trace(1, "q", "a", [make_tool("g", {"a": 1})])]
    assert eval_result_key_count(rule, ok).status == GREEN
    assert eval_result_key_count(rule, bad).status == RED
```

## Step 5 — check it on real data

Fixtures are too clean; that is how four blind spots survived a passing test suite. Run against
something messy before opening the PR:

```bash
python tools/collect_fs.py /path/to/a/messy/directory /tmp/fs
agent-contract mine --traces /tmp/fs/fs-baseline.jsonl -o /tmp/fs/contract.json
agent-contract run  --contract /tmp/fs/contract.json --target /tmp/fs/fs-candidate.jsonl
```

If your new assertion never fires on real data, it is either useless or the threshold is wrong.
Both are worth knowing before merge.

## Conventions worth copying

| Rule | Why |
|---|---|
| return `skipped=` when the target set cannot be judged | a green from zero coverage is the bug this tool exists to prevent |
| cap `samples` at `MAX_SAMPLES` | a report with 400 lines does not get read |
| never raise inside an evaluator | `run_contract` catches, but a silent AMBER hides real breakage |
| put the number in the message | "3/40" is actionable, "some results failed" is not |