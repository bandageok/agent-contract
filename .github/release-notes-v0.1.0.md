**Catch the model swap that changed your answers without changing your code.**

Two commands, no model calls, no API key, standard library only.

```bash
agent-contract mine --traces traces/ -o contract.json
agent-contract run  --contract contract.json --target traces-candidate/
```

### What's in it

- **`mine`** — reads traces you already log and writes assertions with evidence:
  tool results not empty, tool results not zeroed, required fields present, paths
  inside the workspace, call counts bounded, and a full-answer drift comparison.
- **`run`** — replays the same inputs and reports 🔴 red / 🟡 amber / 🟢 green.
  Exit code `1` on red.
- **Baseline sidecar** — every baseline answer is captured, not sampled. A file
  that changed will be examined.
- **Three trace formats** — the documented shape, OpenAI chat, LangChain. Unknown
  keys are preserved in `meta`.
- **GitHub Action** — `uses: bandageok/agent-contract@main`, report lands in the
  job summary.

### Numbers

| | |
|---|---|
| Runtime dependencies | 0 |
| Test suite | 61 tests, 88% statements |
| Python | 3.9 – 3.13 |
| 5 000 traces | `mine` 0.4 s, `run` 0.8 s |
| Self-comparison (baseline vs baseline) | 0 red — no false positives |

### What it has actually been run against

The bundled example is synthetic. The tool was also run against 60 real files
(paths with spaces and apostrophes, distinct inputs, 0–54 KB), which is how five
defects were found — including drift that only sampled 25 of 60 inputs, and so
never examined the file that had changed.

A single byte appended to one real file produced exactly one red, naming that
file, with 55 others green.

### Known limits

- It detects **change**, not badness on day one.
- The target batch must replay the baseline's inputs; low coverage is reported
  rather than shown as green.
- Token-set similarity is untested on non-English answers.
- The sidecar is a flat file; scaling past ~50k inputs is an open question.

### Install

```bash
pip install "agent-contract @ git+https://github.com/bandageok/agent-contract@v0.1.0"
```

Full walkthrough: [README](https://github.com/bandageok/agent-contract#readme) · [中文](https://github.com/bandageok/agent-contract/blob/main/README.zh-CN.md) · [architecture](https://github.com/bandageok/agent-contract/blob/main/docs/architecture.png)