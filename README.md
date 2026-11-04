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

That is the whole loop. `contract.json` goes in git and gets reviewed like code.

## What it looks like

Running the bundled example (40 baseline traces, 40 candidate traces, four deliberate drifts):

```
agent-contract · 31 assertions · 40 target traces

RED   A8   shape.tool_result_not_empty  search_docs never returns an empty result
      2/40 calls returned an empty result (5.0%)
      └ trace=c-018, tool=search_docs, reason=empty result
RED   A13  action.path_within_root      read_file keeps `path` inside docs
      1/40 `path` values escaped `docs`
      └ trace=c-012, path=../secrets/key.pem, root=docs
RED   A27  drift.facts_preserved        answer for `What is the refund window for internation…` keeps its facts
      fact(s) disappeared from 5/5 answers: duration:7days
      └ trace=c-001, dropped=['duration:7days']
AMBER A11  action.tool_allowed          only tools seen in the baseline are called
      new tool(s) surfaced: escalate_to_human
AMBER A12  action.tool_pair_allowed     tool call order matches the baseline
      2 new transition(s): escalate_to_human -> get_order; read_file -> escalate_to_human

3 red · 2 amber · 26 green  →  FAIL
```

Exit code is `1` when there is a red, so it drops straight into CI.

No scores. A score gets optimised; a traffic light gets acted on.

## How it works

`mine` reads traces that worked and writes assertions with **evidence**. An assertion that has no history behind it is a guess, and guesses are why people switch linters off.

| Kind | Catches | Example |
|---|---|---|
| `shape` | empty results, missing fields, length blowups | `search_docs` returned `[]` and the agent carried on |
| `action` | tool set, call order, path containment, call counts | read a file outside the repo |
| `drift` | facts that changed, answers that moved | "7 days" became "3 days" |

`run` re-evaluates every assertion against a new batch and reports three states:

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

> Drift assertions compare answers to the **same input**, so the target batch should replay the prompts from the baseline. That is usually a loop over your golden set.

## GitHub Actions

```yaml
- uses: bandageok/agent-contract@main
  with:
    contract: contract.json
    target: traces/candidate/*.jsonl
    fail-on: red
```

The rendered markdown report is appended to the job summary, so a reviewer sees which behaviour moved without opening the logs.

## Design choices

**Zero runtime dependencies.** Standard library only. It runs in a locked-down CI container, on a laptop, offline.

**No model calls.** Comparison is token-set similarity plus fact extraction, not embeddings. A gate that needs an API key and costs money per run is a gate people disable.

**Local only.** Traces never leave the machine. There is no account, no upload, no telemetry.

**Evidence or nothing.** Every mined assertion prints how many observations justified it.

**Deterministic output.** Assertion ids and ordering are stable, so a re-mine produces a reviewable diff instead of a rewrite.

**Boring verdicts.** Three states, no percentages.

## What it does not do

- It does not make your agent smarter, and it does not fix hallucinations. It detects **change**, not badness on day one.
- It is not an observability platform. It reads traces; it does not store or visualise them.
- It does not write your test cases. It infers them — which is the point, but the inference can be wrong, so review the contract once before trusting the gate.

## Status

`0.1.0` — the loop works end to end and is covered by tests (90% of statements). Interfaces may change before `1.0`.

Roadmap: replay harness for input-matched batches, HTML report, baseline pinning per branch, and a `--from-logs` adapter for plain application logs.

## License

MIT