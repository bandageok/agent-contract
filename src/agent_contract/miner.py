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

            # Key-count range: catches serialisers that start dropping fields.
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

# ... (rest of file omitted for brevity in this example, but in real call include full)
