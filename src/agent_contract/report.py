"""Three renderers: terminal, markdown (for PR comments), json (for machines)."""

from __future__ import annotations

import json
from typing import Dict, List

from .model import AMBER, GREEN, RED, Report

ANSI = {
    RED: "\033[31m",
    AMBER: "\033[33m",
    GREEN: "\033[32m",
}
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

LABEL = {RED: "RED  ", AMBER: "AMBER", GREEN: "GREEN"}


def _colorize(text: str, status: str, enabled: bool) -> str:
    if not enabled:
        return text
    return "%s%s%s" % (ANSI.get(status, ""), text, RESET)


def render_text(report: Report, color: bool = True, verbose: bool = True) -> str:
    counts = report.counts()
    lines: List[str] = []
    header = "agent-contract · %d assertions · %d target traces" % (
        len(report.findings), report.stats.get("traces", 0))
    lines.append(_colorize(header, GREEN, color and False) if False else header)
    lines.append("")

    order = {RED: 0, AMBER: 1, GREEN: 2}

    def sort_key(f):
        digits = "".join(ch for ch in f.assertion_id if ch.isdigit())
        return (order.get(f.status, 9), int(digits or 0))

    shown = sorted(report.findings, key=sort_key)

    green_count = 0
    for f in shown:
        if f.status == GREEN:
            green_count += 1
            if not verbose:
                continue
            lines.append("%s %s  %s %s" % (
                _colorize("GREEN", GREEN, color), f.assertion_id, f.kind, f.message))
            continue
        lines.append("%s %s  %-28s %s" % (
            _colorize(LABEL[f.status], f.status, color), f.assertion_id, f.kind, f.title))
        lines.append("      %s%s" % (DIM if color else "", f.message))
        for sample in f.samples[:3]:
            detail = ", ".join("%s=%s" % (k, v) for k, v in sample.items())
            lines.append("      └ %s" % detail)
        if color:
            lines.append(RESET)

    if not verbose and green_count:
        lines.append("GREEN %d assertions passed" % green_count)

    lines.append("")
    coverage = report.stats.get("drift_coverage")
    if coverage is not None and coverage < 0.5:
        uncovered = report.stats.get("uncovered") or []
        lines.append("⚠ drift coverage %d%% — %d drift assertion(s) matched no target input "
                     "(e.g. %s)"
                     % (round(coverage * 100), len(uncovered), ", ".join(uncovered[:3])))
        lines.append("  the target batch must replay the same inputs as the baseline")
        lines.append("")
    verdict = report.worst()
    summary = "%d red · %d amber · %d green" % (counts[RED], counts[AMBER], counts[GREEN])
    tail = "FAIL" if counts[RED] else ("WARN" if counts[AMBER] else "PASS")
    lines.append("%s  →  %s" % (summary, _colorize(tail, verdict, color)))
    return "\n".join(lines)


def render_markdown(report: Report) -> str:
    counts = report.counts()
    verdict = "❌ FAIL" if counts[RED] else ("⚠️ WARN" if counts[AMBER] else "✅ PASS")
    out: List[str] = []
    out.append("## agent-contract report")
    out.append("")
    out.append("| red | amber | green | traces | verdict |")
    out.append("|---|---|---|---|---|")
    out.append("| %d | %d | %d | %d | %s |" % (
        counts[RED], counts[AMBER], counts[GREEN], report.stats.get("traces", 0), verdict))
    out.append("")

    coverage = report.stats.get("drift_coverage")
    if coverage is not None and coverage < 0.5:
        uncovered = report.stats.get("uncovered") or []
        out.append("> ⚠ **drift coverage %d%%** — %d drift assertion(s) matched no target "
                   "input (e.g. %s). The target batch must replay the baseline's inputs."
                   % (round(coverage * 100), len(uncovered), ", ".join(uncovered[:3])))
        out.append("")

    for status, heading in ((RED, "Red"), (AMBER, "Amber")):
        items = [f for f in report.findings if f.status == status]
        if not items:
            continue
        out.append("### %s (%d)" % (heading, len(items)))
        out.append("")
        for f in items:
            out.append("- **%s** `%s` — %s" % (f.assertion_id, f.kind, f.title))
            out.append("  - %s" % f.message)
            for sample in f.samples[:3]:
                detail = ", ".join("%s=%s" % (k, v) for k, v in sample.items())
                out.append("  - `%s`" % detail)
        out.append("")

    greens = [f for f in report.findings if f.status == GREEN]
    if greens:
        out.append("<details><summary>Green (%d)</summary>" % len(greens))
        out.append("")
        for f in greens[:50]:
            out.append("- `%s` %s — %s" % (f.assertion_id, f.kind, f.message))
        out.append("")
        out.append("</details>")
    return "\n".join(out)


def render_json(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


def render(report: Report, fmt: str, color: bool = True, verbose: bool = True) -> str:
    if fmt == "json":
        return render_json(report)
    if fmt == "markdown":
        return render_markdown(report)
    return render_text(report, color=color, verbose=verbose)


def summary_line(report: Report) -> str:
    c = report.counts()
    return "%d red, %d amber, %d green" % (c[RED], c[AMBER], c[GREEN])


def kind_table(report: Report) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in report.findings:
        key = f.kind.split(".")[0]
        out[key] = out.get(key, 0) + 1
    return out