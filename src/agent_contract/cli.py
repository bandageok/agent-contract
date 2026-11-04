"""Command line surface.

Two verbs, and that is the whole product: mine a contract from history, run
it against a new batch of traces.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .loader import LoadError, load_traces
from .miner import MineOptions, mine, summarize_mining
from .model import Contract, Report
from .report import render, summary_line
from .runner import run_contract

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_ERROR = 2


def _use_color(args) -> bool:
    if getattr(args, "no_color", False):
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _dump_contract(contract: Contract, path: str, fmt: str) -> str:
    data = contract.to_dict()
    suffix = Path(path).suffix.lower()
    if fmt == "auto":
        fmt = "yaml" if suffix in {".yaml", ".yml"} else "json"
    if fmt == "yaml":
        try:
            import yaml  # type: ignore
        except ImportError:
            raise SystemExit(
                "yaml output needs PyYAML: pip install 'agent-contract[yaml]' "
                "— or write JSON by using a .json path")
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    if path == "-":
        return text
    target = Path(path)
    if target.parent and str(target.parent) not in {"", "."}:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return text


def _load_contract(path: str) -> Contract:
    text = Path(path).read_text(encoding="utf-8")
    if path.lower().endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except ImportError:
            raise SystemExit("reading YAML needs PyYAML: pip install 'agent-contract[yaml]'")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("%s: contract must be an object" % path)
    return Contract.from_dict(data)


def cmd_mine(args) -> int:
    try:
        traces, stats = load_traces(args.traces)
    except LoadError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    if not traces:
        print("error: no traces could be normalised from %s" % ", ".join(args.traces),
              file=sys.stderr)
        return EXIT_ERROR

    opts = MineOptions(
        min_support=args.min_support,
        similarity_floor=args.similarity_floor,
        max_drift=args.max_drift,
        include_drift=not args.no_drift,
        include_action=not args.no_action,
    )
    contract = mine(traces, opts, source={"traces": stats})
    text = _dump_contract(contract, args.out, args.format)

    if not args.quiet:
        by_kind = summarize_mining(contract)
        print("mined %d assertions from %d traces (%s)"
              % (len(contract.assertions), len(traces),
                 ", ".join("%s=%d" % kv for kv in sorted(by_kind.items())) or "none"))
        print("  traces: %d files, %d skipped records" % (stats["files"], stats["skipped"]))
        if args.out == "-":
            print("")
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
        else:
            print("  written: %s" % args.out)
        if len(contract.assertions) == 0:
            print("  warning: nothing minable — needs at least %d traces with shared inputs "
                  "or tool calls" % args.min_support, file=sys.stderr)
    return EXIT_OK


def cmd_run(args) -> int:
    try:
        contract = _load_contract(args.contract)
    except (OSError, ValueError) as exc:
        print("error: cannot read contract: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    try:
        traces, stats = load_traces(args.target)
    except LoadError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    report: Report = run_contract(contract, traces)
    out = render(report, args.format, color=_use_color(args), verbose=not args.quiet)

    if args.output:
        Path(args.output).write_text(out + "\n", encoding="utf-8")
    print(out)

    counts = report.counts()
    if args.fail_on == "never":
        return EXIT_OK
    if args.fail_on == "amber":
        return EXIT_FAIL if (counts["red"] or counts["amber"]) else EXIT_OK
    return EXIT_FAIL if counts["red"] else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-contract",
        description="Mine behavioural contracts from agent traces and catch silent failures "
                    "on every model swap, prompt edit or dependency bump.")
    p.add_argument("--version", action="version", version="agent-contract %s" % __version__)
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("mine", help="learn a contract from traces that already worked")
    m.add_argument("--traces", nargs="+", required=True,
                   help="trace files, directories or globs (jsonl/json)")
    m.add_argument("-o", "--out", default="contract.json",
                   help="output path, or - for stdout (default: contract.json)")
    m.add_argument("--format", choices=["auto", "json", "yaml"], default="auto")
    m.add_argument("--min-support", type=int, default=5,
                   help="minimum observations before an assertion is justified (default: 5)")
    m.add_argument("--similarity-floor", type=float, default=0.55,
                   help="minimum token-set similarity for drift checks (default: 0.55)")
    m.add_argument("--max-drift", type=int, default=25,
                   help="cap on per-input drift assertions (default: 25)")
    m.add_argument("--no-drift", action="store_true", help="skip semantic drift assertions")
    m.add_argument("--no-action", action="store_true", help="skip tool/action assertions")
    m.add_argument("-q", "--quiet", action="store_true")
    m.set_defaults(func=cmd_mine)

    r = sub.add_parser("run", help="evaluate a contract against a new batch of traces")
    r.add_argument("--contract", required=True, help="contract.json produced by `mine`")
    r.add_argument("--target", nargs="+", required=True,
                   help="traces produced by the new model/prompt/dependency")
    r.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    r.add_argument("--fail-on", choices=["red", "amber", "never"], default="red",
                   help="which status makes the command exit non-zero (default: red)")
    r.add_argument("--output", help="also write the report to this file")
    r.add_argument("--no-color", action="store_true")
    r.add_argument("-q", "--quiet", action="store_true")
    r.set_defaults(func=cmd_run)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())