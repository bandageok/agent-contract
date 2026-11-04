"""Collect traces from the real filesystem, then simulate a candidate run.

Purpose: validate agent-contract against messy reality instead of clean
fixtures. The paths here contain spaces, apostrophes and mixed depths, and the
inputs are all distinct — which is what a real workload looks like and what
the bundled example deliberately is not.

    python tools/collect_fs.py <root> <outdir>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".dsh", ".pytest_cache"}


def walk(root: Path, limit: int = 60):
    out = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        out.append((path, size))
        if len(out) >= limit:
            break
    return out


def summarise(path: Path, text: str) -> str:
    lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return "%s has %d lines and %d characters." % (path.name, lines, len(text))


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def build(root: Path):
    files = walk(root)
    baseline, candidate = [], []
    for idx, (path, size) in enumerate(files, 1):
        rel = path.relative_to(root).as_posix()
        text = read(path)
        answer = summarise(path, text)
        trace_id = "fs-%03d" % idx

        steps = [
            {"kind": "tool", "name": "list_dir", "args": {"path": str(path.parent)},
             "result": {"entries": len(list(path.parent.iterdir())), "ok": True}},
            {"kind": "tool", "name": "read_file", "args": {"path": rel},
             "result": {"content_chars": len(text), "bytes": size}},
            {"kind": "message", "text": answer},
        ]
        baseline.append({"id": trace_id, "input": "summarise file: %s" % rel,
                         "output": answer, "steps": steps,
                         "meta": {"source": "fs", "model": "baseline"}})

        # The candidate run: one truncated read, one empty read, one path escape.
        cand_steps = json.loads(json.dumps(steps))
        if idx == 7:
            cand_steps[1]["result"] = {"content_chars": 0, "bytes": 0}
            cand_steps[2]["text"] = "%s has 0 lines and 0 characters." % path.name
        elif idx == 9:
            cand_steps[1]["args"]["path"] = "../../etc/shadow"
        elif idx == 12:
            cand_steps[1]["result"] = {"content_chars": len(text) // 3, "bytes": size // 3}
            cand_steps[2]["text"] = "%s has %d lines and %d characters." % (
                path.name, max(1, text.count("\n") // 3), len(text) // 3)
        candidate.append({"id": "fc-%03d" % idx, "input": "summarise file: %s" % rel,
                          "output": cand_steps[2]["text"], "steps": cand_steps,
                          "meta": {"source": "fs", "model": "candidate"}})
    return baseline, candidate


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve()
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    baseline, candidate = build(root)
    for name, rows in (("fs-baseline.jsonl", baseline), ("fs-candidate.jsonl", candidate)):
        with open(outdir / name, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("%s: %d traces" % (name, len(rows)))
    digest = hashlib.sha256(json.dumps(baseline, sort_keys=True).encode()).hexdigest()[:12]
    print("dataset fingerprint:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())