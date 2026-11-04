"""Mine a behavioural contract from traces that already worked.

Design rule: every assertion must carry evidence from history. An assertion
that has never been observed cannot be justified to the person reading the
report at 2am, and unjustified red lights get switched off within a week.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .loader import is_degenerate, is_empty
from .model import AMBER, RED, Assertion, Contract, Step, Trace
from .similarity import dirname_of, extract_facts, extract_numbers, longest_common_dir, normalize

PATH_KEYS = {
    "path", "paths", "file", "files", "filepath", "file_path", "filename",
    "dir", "directory", "folder", "target", "output_path", "dest", "src",
}
WRITE_HINTS = ("write", "edit", "create", "delete", "remove", "move", "put", "patch", "exec", "run", "send")


@dataclass
class MineOptions:
    """Knobs, all with defaults that survived real trace sets."""

    min_support: int = 5
    # kept for backwards compat with hand-written option dicts
    empty_tolerance: float = 0.05
    field_threshold: float = 0.98
    sequence_threshold: float = 0.6
    similarity_floor: float = 0.55
    max_drift: int = 25
    max_chars: int = 2000
    include_drift: bool = True
    include_action: bool = True


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (pos - low))


def _fmt_pct(x: float) -> str:
    return "%.1f%%" % (x * 100)


def _as_dict(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _as_list(value: Any) -> Optional[List[Any]]:
    return value if isinstance(value, list) else None


class _Builder:
    """Collects assertions with stable, diffable ids."""

    def __init__(self) -> None:
        self.items: List[Assertion] = []

    def add(self, kind: str, title: str, params: Dict[str, Any], evidence: str,
            severity: str = RED) -> None:
        self.items.append(Assertion(
            id="A%d" % (len(self.items) + 1),
            kind=kind,
            title=title,
            params=params,
            evidence=evidence,
            severity=severity,
        ))


def _tool_calls(traces: Iterable[Trace]) -> List[Tuple[Trace, Step]]:
    out: List[Tuple[Trace, Step]] = []
    for t in traces:
        for s in t.tool_calls():
            out.append((t, s))
    return out


def mine_shape(traces: List[Trace], opts: MineOptions, b: _Builder) -> None:
    calls = _tool_calls(traces)
    if not calls:
        return
    by_tool: Dict[str, List[Step]] = defaultdict(list)
    for _, step in calls:
        by_tool[step.name or "<unnamed>"].append(step)

    for tool in sorted(by_tool):
        steps = by_tool[tool]
        total = len(steps)
        if total < opts.min_support:
            continue

        empty = sum(1 for s in steps if is_empty(s.result))
        empty_rate = empty / total
        if empty == 0:
            b.add(
                "shape.tool_result_not_empty",
                "%s never returns an empty result" % tool,
                {"tool": tool},
                "%s returned a non-empty result in %d/%d calls" % (tool, total, total),
            )
        elif empty_rate <= opts.empty_tolerance:
            b.add(
                "shape.tool_result_not_empty",
                "%s returns a non-empty result" % tool,
                {"tool": tool, "tolerance": round(empty_rate, 4)},
                "%s was empty in %d/%d calls (%s) — a rare failure, not normal behaviour"
                % (tool, empty, total, _fmt_pct(empty_rate)),
            )

        dict_results = [s for s in steps if _as_dict(s.result) is not None]
        if dict_results and len(dict_results) / total >= 0.9:
            degenerate = sum(1 for s in dict_results if is_degenerate(s.result))
            if degenerate / len(dict_results) <= 0.02:
                b.add(
                    "shape.result_not_degenerate",
                    "%s never returns a zeroed result" % tool,
                    {"tool": tool, "tolerance": round(degenerate / len(dict_results), 4)},
                    "%d/%d %s results carried non-zero values"
                    % (len(dict_results) - degenerate, len(dict_results), tool),
                )
            field_counts: Counter = Counter()
            for s in dict_results:
                for key in _as_dict(s.result) or {}:
                    field_counts[key] += 1
            for key in sorted(field_counts):
                rate = field_counts[key] / len(dict_results)
                if rate >= opts.field_threshold:
                    b.add(
                        "shape.result_has_field",
                        "%s result always carries `%s`" % (tool, key),
                        {"tool": tool, "field": key},
                        "`%s` present in %d/%d %s results (%s)"
                        % (key, field_counts[key], len(dict_results), tool, _fmt_pct(rate)),
                    )

        list_results = [s for s in steps if _as_list(s.result) is not None]
        if list_results and len(list_results) / total >= 0.9:
            lengths = [len(_as_list(s.result) or []) for s in list_results]
            lo = int(math.floor(percentile(lengths, 0.05)))
            hi = int(math.ceil(percentile(lengths, 0.95)))
            b.add(
                "shape.result_len_range",
                "%s result length stays within %d..%d" % (tool, lo, hi),
                {"tool": tool, "min": lo, "max": hi},
                "observed %d results, p05=%d p95=%d" % (len(lengths), lo, hi),
            )


def mine_action(traces: List[Trace], opts: MineOptions, b: _Builder) -> None:
    if not opts.include_action:
        return
    calls = _tool_calls(traces)
    if not calls or len(traces) < opts.min_support:
        return

    tool_counts: Counter = Counter()
    for _, step in calls:
        tool_counts[step.name or "<unnamed>"] += 1

    b.add(
        "action.tool_allowed",
        "only tools seen in the baseline are called",
        {"tools": sorted(tool_counts)},
        "baseline used %d distinct tools over %d calls: %s"
        % (len(tool_counts), sum(tool_counts.values()), ", ".join(sorted(tool_counts))),
        severity=AMBER,
    )

    pair_counts: Counter = Counter()
    for trace in traces:
        names = trace.tool_names()
        for a, c in zip(names, names[1:]):
            pair_counts[(a, c)] += 1
    if pair_counts:
        pairs = [[a, c] for (a, c), _ in sorted(pair_counts.items())]
        b.add(
            "action.tool_pair_allowed",
            "tool call order matches the baseline",
            {"pairs": pairs},
            "%d distinct adjacent tool pairs observed across %d traces"
            % (len(pairs), len(traces)),
            severity=AMBER,
        )

    # Path containment: the assertion that catches "read my SSH keys".
    for tool in sorted({s.name or "<unnamed>" for _, s in calls}):
        tool_steps = [s for _, s in calls if (s.name or "<unnamed>") == tool]
        for key in sorted(PATH_KEYS):
            values = []
            for step in tool_steps:
                val = (step.args or {}).get(key)
                if isinstance(val, str) and val.strip():
                    values.append(val)
                elif isinstance(val, list):
                    values.extend([v for v in val if isinstance(v, str) and v.strip()])
            if len(values) < max(opts.min_support, 2):
                continue
            root = longest_common_dir(values)
            if root and root != ".":
                b.add(
                    "action.path_within_root",
                    "%s keeps `%s` inside %s" % (tool, key, root),
                    {"tool": tool, "arg": key, "root": root},
                    "%d observed %s values all lived under `%s`" % (len(values), key, root),
                )
                continue
            # Relative paths rarely share a prefix; fall back to the set of
            # directories that were actually observed, so an escape still trips.
            dirs = sorted({d for d in (dirname_of(v) for v in values) if d})[:50]
            if not dirs:
                continue
            b.add(
                "action.path_within_root",
                "%s keeps `%s` inside known directories" % (tool, key),
                {"tool": tool, "arg": key, "allowed_dirs": dirs},
                "%d observed %s values spanned %d directories: %s"
                % (len(values), key, len(dirs), ", ".join(dirs[:4])),
            )

    per_trace_max: Dict[str, List[int]] = defaultdict(list)
    for trace in traces:
        local: Counter = Counter(trace.tool_names())
        for name, n in local.items():
            per_trace_max[name].append(n)
    for tool in sorted(per_trace_max):
        samples = per_trace_max[tool]
        if len(samples) < opts.min_support:
            continue
        hard = max(1, int(math.ceil(percentile(samples, 0.95))))
        b.add(
            "action.max_calls",
            "%s called at most %d times per trace" % (tool, hard),
            {"tool": tool, "max": hard, "hard_max": hard * 2},
            "p95 of per-trace call count is %d (max observed %d)" % (hard, max(samples)),
            severity=AMBER,
        )


def mine_drift(traces: List[Trace], opts: MineOptions, b: _Builder) -> None:
    if not opts.include_drift:
        return

    groups: Dict[str, List[Trace]] = defaultdict(list)
    for trace in traces:
        key = normalize(trace.input)
        if key:
            groups[key].append(trace)

    repeated = [(k, v) for k, v in groups.items() if len(v) >= 2]
    repeated.sort(key=lambda kv: (-len(kv[1]), kv[0]))
    singles = [(k, v) for k, v in groups.items() if len(v) == 1]
    singles.sort(key=lambda kv: len(kv[0]))

    picked: List[Tuple[str, Trace]] = []
    for key, items in repeated:
        picked.append((key, items[0]))
    for key, items in singles:
        picked.append((key, items[0]))
    picked = picked[: opts.max_drift]

    for key, trace in picked:
        output = (trace.output or "").strip()
        if not output:
            continue
        facts = sorted(extract_facts(output))
        if facts:
            b.add(
                "drift.facts_preserved",
                "answer for `%s` keeps its facts" % _shorten(trace.input, 48),
                {
                    "input": _shorten(trace.input, 200),
                    "input_key": key,
                    "facts": facts,
                },
                "%d facts in the baseline answer: %s"
                % (len(facts), ", ".join(facts[:6])),
            )
        numbers = extract_numbers(output)
        if facts:
            # Fact patterns already quote the numbers that matter, with units.
            # A second, coarser number check on the same input is noise: it
            # fires alongside facts on the same trace and doubles the report.
            pass
        elif numbers and len(numbers) <= 12:
            b.add(
                "drift.numbers_preserved",
                "answer for `%s` keeps its numbers" % _shorten(trace.input, 48),
                {
                    "input": _shorten(trace.input, 200),
                    "input_key": key,
                    "numbers": numbers,
                },
                "baseline answer contains %d numeric values: %s"
                % (len(numbers), ", ".join(_num(v) for v in numbers[:6])),
            )
        b.add(
            "drift.similarity",
            "answer for `%s` stays close to baseline" % _shorten(trace.input, 48),
            {
                "input": _shorten(trace.input, 200),
                "input_key": key,
                "baseline_output": _shorten(output, opts.max_chars),
                "min_ratio": opts.similarity_floor,
            },
            "baseline answer is %d characters; floor %.2f" % (len(output), opts.similarity_floor),
        )


def _num(value: float) -> str:
    return "%d" % value if float(value).is_integer() else "%g" % value


def _shorten(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def mine(traces: List[Trace], options: Optional[MineOptions] = None,
         source: Optional[Dict[str, Any]] = None) -> Contract:
    opts = options or MineOptions()
    builder = _Builder()
    mine_shape(traces, opts, builder)
    mine_action(traces, opts, builder)
    mine_drift(traces, opts, builder)

    return Contract(
        assertions=builder.items,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source=dict(source or {}, trace_count=len(traces)),
    )


def summarize_mining(contract: Contract) -> Dict[str, int]:
    counts: Counter = Counter()
    for a in contract.assertions:
        counts[a.kind.split(".")[0]] += 1
    return dict(counts)