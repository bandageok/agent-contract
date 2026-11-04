# agent-contract

**Mine what "correct" looked like from your own traces — then catch the moment a model swap, a prompt edit or a dependency bump quietly changes it.**

[![ci](https://github.com/bandageok/agent-contract/actions/workflows/ci.yml/badge.svg)](https://github.com/bandageok/agent-contract/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## The problem

Your agent ran fine for three months. You upgraded the model. Nothing crashed, no exception, exit code 0 — and for six days it has been quoting a 3-day refund window instead of 7.

That is a **silent failure**: the shape is right, the tone is right, the facts are wrong. Traditional software throws when it breaks. An LLM app returns something that looks reasonable. The stronger the model, the more plausible the mistake.

Nobody has CI for this. So teams sample 20 conversations by hand, or ship and hope.

`agent-contract` closes that gap in two commands.

## Quickstart

```bash
pip install "agent-contract @ git+https://github.com/bandageok/agent-contract"

# 1. learn the contract from traces that already worked
agent-contract mine --traces examples/traces-baseline.jsonl -o contract.json

# 2. run it against a batch produced by the new model / prompt / dependency
agent-contract run --contract contract.json --target examples/traces-candidate.jsonl
```

That is the whole loop. `contract.json` goes in git and gets reviewed like code; `contract.baseline.jsonl` sits next to it and holds the reference answers every replay is compared against. Commit both.

## What it looks like

The bundled example: 40 baseline traces, 40 candidate traces, four deliberate drifts.

```
agent-contract · 20 assertions · 40 target traces

RED   A10  shape.tool_result_not_empty  search_docs never returns an empty result
      2/40 calls returned an empty result (5.0%)
      └ trace=c-018, tool=search_docs, reason=empty result
RED   A16  action.path_within_root      read_file keeps `path` inside docs
      1/40 `path` values escaped `docs`
      └ trace=c-012, path=../secrets/key.pem, allowed=docs
RED   A20  drift.batch                  answers to the baseline inputs stay the same
      5/40 matched answers drifted
      └ trace=c-001, input=What is the refund window for international orders?,
        why=facts lost, detail=['duration:7days']
AMBER A14  action.tool_allowed          only tools seen in the baseline are called
      new tool(s) surfaced: escalate_to_human
AMBER A15  action.tool_pair_allowed     tool call order matches the baseline
      2 new transition(s): read_file -> escalate_to_human

3 red · 2 amber · 15 green  →  FAIL
```

Exit code is `1` when there is a red, so it drops straight into CI.

No scores. A score gets optimised; a traffic light gets acted on.

## How it works

`mine` reads traces that worked and writes assertions with **evidence**. An assertion with no history behind it is a guess, and guesses are why people switch linters off.

| Kind | Catches | Example |
|---|---|---|
| `shape.tool_result_not_empty` | empty payloads | `search_docs` returned `[]` and the agent carried on |
| `shape.result_not_degenerate` | successful-looking but zeroed payloads | `{"content_chars": 0, "bytes": 0}` |
| `shape.result_has_field` / `result_len_range` | missing fields, length blowups | a field silently dropped by a serialiser |
| `action.tool_allowed` / `tool_pair_allowed` | new tools, changed call order | an escalation path appeared |
| `action.path_within_root` | files touched outside the workspace | reading `../secrets/key.pem` |
| `action.max_calls` | runaway loops | the same tool called 12 times |
| `drift.batch` | any answer drifting from the baseline — facts changed, numbers moved, or the text rewritten | "7 days" became "3 days"; `830 lines` became `277 lines`; a policy paragraph rewritten |

`run` reports three states:

- **green** — unchanged
- **amber** — behaviour moved but stayed in bounds (one extra retry, a new tool)
- **red** — an assertion from history is now violated

## Trace formats

Point `--traces` at files, directories or globs. Every record is normalised; unknown keys are kept in `meta`.

**Documented shape**

```json
{"id": "t-1", "input": "refund window?", "output": "7 days",
 "steps": [{"kind": "tool", "name": "search_docs", "args": {"q": "refund"}, "result": {"items": [], "total": 0}}]}
```

**OpenAI chat** — `{"messages": [...]}` with `tool_calls` and `role: "tool"` replies is paired automatically.

**LangChain** — `{"inputs": ..., "outputs": ..., "intermediate_steps": [...]}`.

A bare `{"input": ..., "output": ...}` pair still works for drift checks.

> Drift assertions compare answers to the **same input**, so the target batch should replay the prompts from the baseline. When fewer than half of the drift assertions find a matching input, the report says so instead of showing a wall of green.

## GitHub Actions

```yaml
- uses: bandageok/agent-contract@main
  with:
    contract: contract.json
    target: traces/candidate/*.jsonl
    fail-on: red
```

The rendered markdown report is appended to the job summary, so a reviewer sees which behaviour moved without opening the logs.

## Validated on real data

The fixture set above was too clean. Run against 60 real files — paths containing spaces and apostrophes, every input distinct, sizes from 0 to 54 KB — the tool reported **all green on a batch with three deliberate regressions**. Five defects fell out:

| Defect | Fix |
|---|---|
| `{"content_chars": 0, "bytes": 0}` counted as a non-empty result | `is_degenerate()` + `shape.result_not_degenerate` |
| relative paths share no common prefix, so path assertions were never emitted — exactly the tool that needed protecting | allowed-directory fallback in `action.path_within_root` |
| a drift that only moves numbers scored 0.87 similarity, well above the 0.55 floor | number extraction added to the drift comparison |
| the unit list missed `lines`, `characters`, `tokens`, `entries` | fact patterns extended |
| drift covered a **sample** of inputs (`max_drift=25` of 60), so a file that actually changed was never checked | the whole baseline goes into a sidecar and every replayed input is compared |

The last one is the important one. Sampling the thing that decides pass/fail is how a gate becomes decorative.

After the fixes, the same batch reports **3 red** instead of 0, and a self-comparison (baseline vs baseline) still reports **0 red** — no false positives.

The strongest check was unscripted: with a baseline in place, one real file was edited by a single byte. The next run reported exactly one input — `summarise file: .research/raw/hn_2.json, why=facts lost` — and 55 others green.

Performance on 5 000 traces: `mine` 0.4 s, `run` 0.8 s.

You can reproduce the real-data pass yourself:

```bash
python tools/collect_fs.py /path/to/a/messy/directory /tmp/fs
agent-contract mine --traces /tmp/fs/fs-baseline.jsonl -o /tmp/fs/contract.json
agent-contract run  --contract /tmp/fs/contract.json --target /tmp/fs/fs-candidate.jsonl
```

## Design choices

**Zero runtime dependencies.** Standard library only. It runs in a locked-down CI container, on a laptop, offline.

**No model calls.** Comparison is token-set similarity plus fact and number extraction, not embeddings. A gate that needs an API key and costs money per run is a gate people disable.

**Local only.** Traces never leave the machine. There is no account, no upload, no telemetry.

**Evidence or nothing.** Every mined assertion prints how many observations justified it.

**Deterministic output.** Assertion ids and ordering are stable, so a re-mine produces a reviewable diff instead of a rewrite.

**Boring verdicts.** Three states, no percentages.

## What it does not do

- It does not make your agent smarter, and it does not fix hallucinations. It detects **change**, not badness on day one.
- It is not an observability platform. It reads traces; it does not store or visualise them.
- It does not write your test cases. It infers them — which is the point, but the inference can be wrong, so review the contract once before trusting the gate.

## Status

`0.1.0` — the loop works end to end, covered by tests (88% of statements), and has been validated against real filesystem data. Interfaces may change before `1.0`.

Roadmap: a replay harness (so you never hand-assemble the candidate batch), HTML report, baseline pinning per branch, and a `--from-logs` adapter for plain application logs.

Before `1.0` the two open questions are: how the sidecar should scale past ~50k inputs, and whether token-set similarity is enough for non-English answers. Neither is settled — the tool is honest about what it has actually been run against.

## License

MIT