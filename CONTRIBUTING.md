# Contributing

Small project, small rules. Three of them actually matter.

## 1. No new runtime dependencies

Everything ships in the standard library. A new dependency in `[project.dependencies]` is a
conversation, not a commit. `dev` and `yaml` extras are fine.

Reason: the tool has to run in a locked-down CI container with no network. That property is the
product; a convenient dependency can quietly kill it.

## 2. Every assertion needs evidence

If you add an assertion kind, `mine` must produce it from observed history and print how many
observations justified it. An assertion nobody can trace back to data is a guess, and guesses get
the whole report switched off.

## 3. No model calls in the check path

`run` must stay deterministic, offline and free. Embedding-based comparison is out; token-set
similarity, regexes and counting are in.

## Getting set up

```bash
git clone https://github.com/bandageok/agent-contract
cd agent-contract
uv venv && uv pip install -e ".[dev]"     # or: python -m venv .venv && pip install -e ".[dev]"
pytest -q --cov=agent_contract
```

Python 3.9+ must work — CI runs 3.9, 3.12 and 3.13.

## Adding an assertion kind

Three files, in this order. See [docs/extending.md](docs/extending.md) for a worked example.

**`src/agent_contract/miner.py`** — decide when the assertion is justified:

```python
b.add(
    "shape.result_has_key",              # kind
    "%s result always carries `%s`" % (tool, key),   # title, shown in the report
    {"tool": tool, "field": key},        # params, must be JSON-serialisable
    "%d/%d results carried `%s`" % (n, total, key),  # evidence, never omit
    severity=RED,                        # RED blocks, AMBER warns
)
```

**`src/agent_contract/runner.py`** — implement the evaluator:

```python
def eval_result_has_key(a: Assertion, traces: List[Trace],
                        baseline: Optional[Dict[str, Any]] = None) -> Finding:
    ...
    return _finding(a, RED, "message", samples, checked=n)
```

Return `_finding(..., skipped=len(traces))` when the target set cannot be judged — a green result
from zero coverage is the bug this project exists to prevent.

**Register it** at the bottom of `runner.py`:

```python
EVALUATORS = {..., "shape.result_has_key": eval_result_has_key}
```

Then add tests to `tests/test_runner.py` (one per status, at minimum RED and GREEN) and a
`tests/test_miner.py` case proving the assertion is only emitted when the evidence is real.

## Adding a trace format

`src/agent_contract/loader.py` has one adapter per shape, each returning `Trace | None`. Add a
function, then place it in the `adapter` tuple in `normalize_record`, most specific first. Never
drop unknown keys — they go into `trace.meta`.

## Pull requests

- One logical change per PR.
- Tests included; CI must be green.
- If you changed behaviour, say what the old behaviour was and why it was wrong.
- No reformatting of untouched files.

## Reporting a false positive

The most valuable bug report this project can receive. Include:

1. your `contract.json` assertion (redact inputs),
2. the target trace that tripped it,
3. what the *correct* verdict was.

False positives are how a gate dies. They get fixed first.