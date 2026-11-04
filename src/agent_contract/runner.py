"""Evaluate a contract against a fresh set of traces."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List, Optional

from .loader import is_degenerate, is_empty
from .model import AMBER, GREEN, RED, Assertion, Contract, Finding, Report, Trace
from .similarity import dir_allowed, extract_facts, extract_numbers, normalize, token_set_ratio

MAX_SAMPLES = 5


def _norm_path(value: str) -> str:
    return str(value or "").replace("\\", "/").strip()


def inside_root(value: str, root: str) -> bool:
    """Directory-boundary-aware containment check."""
    v = _norm_path(value)
    r = _norm_path(root).strip("/")
    if not v:
        return True
    if not r or r == ".":
        return True
    v_clean = re.sub(r"^\./+", "", v)
    r_low, v_low = r.lower(), v_clean.lower()
    if v_low.startswith(r_low + "/") or v_low == r_low:
        return True
    if v_low.startswith("/") or re.match(r"^[a-z]:/", v_low):
        return ("/" + r_low + "/") in ("/" + v_low + "/")
    return False


def _finding(a: Assertion, status: str, message: str, samples: Optional[List[Dict[str, Any]]] = None,
             checked: int = 0, skipped: int = 0) -> Finding:
    return Finding(
        assertion_id=a.id,
        kind=a.kind,
        title=a.title,
        status=status,
        message=message,
        samples=(samples or [])[:MAX_SAMPLES],
        checked=checked,
        skipped=skipped,
    )


def _calls_for(traces: List[Trace], tool: str):
    out = []
    for t in traces:
        for step in t.tool_calls():
            if (step.name or "<unnamed>") == tool:
                out.append((t, step))
    return out


def eval_tool_result_not_empty(a: Assertion, traces: List[Trace],
                                baseline: Optional[Dict[str, Any]] = None) -> Finding:
    tool = a.params.get("tool", "")
    calls = _calls_for(traces, tool)
    if not calls:
        return _finding(a, GREEN, "no %s calls in target set" % tool, skipped=len(traces))
    tolerance = float(a.params.get("tolerance") or 0.0)
    empties = [(t, s) for t, s in calls if is_empty(s.result)]
    rate = len(empties) / len(calls)
    if not empties:
        return _finding(a, GREEN, "%s: %d calls, none empty" % (tool, len(calls)), checked=len(calls))
    samples = [{"trace": t.id, "tool": tool, "reason": "empty result"} for t, _ in empties[:MAX_SAMPLES]]
    if rate <= tolerance:
        return _finding(a, AMBER, "%d/%d calls empty (%s) within tolerance %s"
                        % (len(empties), len(calls), _pct(rate), _pct(tolerance)),
                        samples, checked=len(calls))
    return _finding(a, RED, "%d/%d calls returned an empty result (%s)"
                    % (len(empties), len(calls), _pct(rate)), samples, checked=len(calls))


def eval_result_has_field(a: Assertion, traces: List[Trace],
                           baseline: Optional[Dict[str, Any]] = None) -> Finding:
    tool = a.params.get("tool", "")
    field = a.params.get("field", "")
    calls = _calls_for(traces, tool)
    dict_calls = [(t, s) for t, s in calls if isinstance(s.result, dict)]
    if not dict_calls:
        return _finding(a, GREEN, "no dict results for %s" % tool, skipped=len(traces))
    missing = [(t, s) for t, s in dict_calls if field not in (s.result or {})]
    if not missing:
        return _finding(a, GREEN, "%s: %d results carry `%s`" % (tool, len(dict_calls), field),
                        checked=len(dict_calls))
    samples = [{"trace": t.id, "tool": tool, "missing": field} for t, _ in missing[:MAX_SAMPLES]]
    return _finding(a, RED, "`%s` missing from %d/%d %s results"
                    % (field, len(missing), len(dict_calls), tool), samples, checked=len(dict_calls))


def eval_result_len_range(a: Assertion, traces: List[Trace],
                           baseline: Optional[Dict[str, Any]] = None) -> Finding:
    tool = a.params.get("tool", "")
    lo, hi = int(a.params.get("min", 0)), int(a.params.get("max", 0))
    calls = [(t, s) for t, s in _calls_for(traces, tool) if isinstance(s.result, list)]
    if not calls:
        return _finding(a, GREEN, "no list results for %s" % tool, skipped=len(traces))
    out_of_range = [(t, len(s.result or [])) for t, s in calls
                    if len(s.result or []) < lo or len(s.result or []) > hi]
    if not out_of_range:
        return _finding(a, GREEN, "%s: %d results within %d..%d" % (tool, len(calls), lo, hi),
                        checked=len(calls))
    samples = [{"trace": t, "tool": tool, "length": n} for t, n in out_of_range[:MAX_SAMPLES]]
    saw_empty = any(n == 0 for _, n in out_of_range)
    status = RED if saw_empty else AMBER
    return _finding(a, status, "%d/%d results outside %d..%d"
                    % (len(out_of_range), len(calls), lo, hi), samples, checked=len(calls))


def eval_result_not_degenerate(a: Assertion, traces: List[Trace],
                                baseline: Optional[Dict[str, Any]] = None) -> Finding:
    tool = a.params.get("tool", "")
    calls = _calls_for(traces, tool)
    dict_calls = [(t, s) for t, s in calls if isinstance(s.result, dict)]
    if not dict_calls:
        return _finding(a, GREEN, "no dict results for %s" % tool, skipped=len(traces))
    tolerance = float(a.params.get("tolerance") or 0.0)
    zeroed = [(t, s) for t, s in dict_calls if is_degenerate(s.result)]
    rate = len(zeroed) / len(dict_calls)
    if not zeroed:
        return _finding(a, GREEN, "%s: %d results carried real values"
                        % (tool, len(dict_calls)), checked=len(dict_calls))
    samples = [{"trace": t.id, "tool": tool, "result": s.result}
               for t, s in zeroed[:MAX_SAMPLES]]
    if rate <= tolerance:
        return _finding(a, AMBER, "%d/%d %s results were zeroed (%s) within tolerance"
                        % (len(zeroed), len(dict_calls), tool, _pct(rate)),
                        samples, checked=len(dict_calls))
    return _finding(a, RED, "%d/%d %s results came back zeroed (%s)"
                    % (len(zeroed), len(dict_calls), tool, _pct(rate)),
                    samples, checked=len(dict_calls))


def eval_tool_allowed(a: Assertion, traces: List[Trace],
                       baseline: Optional[Dict[str, Any]] = None) -> Finding:
    allowed = set(a.params.get("tools") or [])
    seen: Counter = Counter()
    for t in traces:
        for name in t.tool_names():
            seen[name or "<unnamed>"] += 1
    if not seen:
        return _finding(a, GREEN, "no tool calls in target set", skipped=len(traces))
    new_tools = [n for n in sorted(seen) if n not in allowed]
    if not new_tools:
        return _finding(a, GREEN, "%d calls, all tools known" % sum(seen.values()),
                        checked=sum(seen.values()))
    samples = [{"tool": n, "calls": seen[n]} for n in new_tools[:MAX_SAMPLES]]
    return _finding(a, AMBER, "new tool(s) surfaced: %s" % ", ".join(new_tools),
                    samples, checked=sum(seen.values()))


def eval_tool_pair_allowed(a: Assertion, traces: List[Trace],
                            baseline: Optional[Dict[str, Any]] = None) -> Finding:
    allowed = {tuple(p) for p in (a.params.get("pairs") or []) if isinstance(p, (list, tuple)) and len(p) == 2}
    seen: Counter = Counter()
    for t in traces:
        names = t.tool_names()
        for x, y in zip(names, names[1:]):
            seen[(x, y)] += 1
    if not seen:
        return _finding(a, GREEN, "not enough multi-step traces", skipped=len(traces))
    novel = [p for p in sorted(seen) if p not in allowed]
    if not novel:
        return _finding(a, GREEN, "%d transitions, all known" % sum(seen.values()),
                        checked=sum(seen.values()))
    samples = [{"from": p[0], "to": p[1], "count": seen[p]} for p in novel[:MAX_SAMPLES]]
    return _finding(a, AMBER, "%d new transition(s): %s"
                    % (len(novel), "; ".join("%s -> %s" % p for p in novel[:3])),
                    samples, checked=sum(seen.values()))


def eval_path_within_root(a: Assertion, traces: List[Trace],
                           baseline: Optional[Dict[str, Any]] = None) -> Finding:
    tool = a.params.get("tool", "")
    arg = a.params.get("arg", "")
    root = a.params.get("root", "")
    allowed = a.params.get("allowed_dirs") or []
    label = root if root else "%d known dirs" % len(allowed)

    values: List[tuple] = []
    for t, s in _calls_for(traces, tool):
        raw = (s.args or {}).get(arg)
        if isinstance(raw, str) and raw.strip():
            values.append((t.id, raw))
        elif isinstance(raw, list):
            for v in raw:
                if isinstance(v, str) and v.strip():
                    values.append((t.id, v))
    if not values:
        return _finding(a, GREEN, "no `%s` arguments seen" % arg, skipped=len(traces))

    def ok(value: str) -> bool:
        return inside_root(value, root) if root else dir_allowed(value, allowed)

    escapes = [(tid, v) for tid, v in values if not ok(v)]
    if not escapes:
        return _finding(a, GREEN, "%d paths stayed inside `%s`" % (len(values), label),
                        checked=len(values))
    samples = [{"trace": tid, "path": v, "allowed": label} for tid, v in escapes[:MAX_SAMPLES]]
    return _finding(a, RED, "%d/%d `%s` values escaped `%s`"
                    % (len(escapes), len(values), arg, label), samples, checked=len(values))


def eval_numbers_preserved(a: Assertion, traces: List[Trace],
                            baseline: Optional[Dict[str, Any]] = None) -> Finding:
    matched = _match_by_input(a, traces)
    if not matched:
        return _finding(a, GREEN, "input not present in target set", skipped=len(traces))
    baseline = {float(x) for x in (a.params.get("numbers") or [])}
    if not baseline:
        return _finding(a, GREEN, "baseline output had no numbers", checked=len(matched))

    changed: List[Dict[str, Any]] = []
    lost_only: List[Dict[str, Any]] = []
    gained_only: List[Dict[str, Any]] = []
    for t in matched:
        got = set(extract_numbers(t.output or ""))
        lost = sorted(baseline - got)
        gain = sorted(got - baseline)
        if lost and gain:
            changed.append({"trace": t.id, "lost": lost[:4], "gained": gain[:4]})
        elif lost:
            lost_only.append({"trace": t.id, "lost": lost[:4]})
        elif gain:
            gained_only.append({"trace": t.id, "gained": gain[:4]})

    if changed:
        return _finding(a, RED, "every number moved in %d/%d answers" % (len(changed), len(matched)),
                        changed, checked=len(matched))
    if lost_only:
        return _finding(a, RED, "number(s) disappeared from %d/%d answers: %s"
                        % (len(lost_only), len(matched),
                           ", ".join(sorted({_num(x) for d in lost_only for x in d["lost"]})[:4])),
                        lost_only, checked=len(matched))
    if gained_only:
        return _finding(a, AMBER, "%d answer(s) gained new numbers" % len(gained_only),
                        gained_only, checked=len(matched))
    return _finding(a, GREEN, "numbers intact across %d answer(s)" % len(matched),
                    checked=len(matched))


def _num(value: float) -> str:
    return "%d" % value if float(value).is_integer() else "%g" % value


def eval_max_calls(a: Assertion, traces: List[Trace],
                    baseline: Optional[Dict[str, Any]] = None) -> Finding:
    tool = a.params.get("tool", "")
    hard = int(a.params.get("max", 1))
    hard_max = int(a.params.get("hard_max") or hard * 2)
    per_trace = [(t.id, sum(1 for n in t.tool_names() if n == tool)) for t in traces]
    per_trace = [(tid, n) for tid, n in per_trace if n > 0]
    if not per_trace:
        return _finding(a, GREEN, "no %s calls in target set" % tool, skipped=len(traces))
    over = [(tid, n) for tid, n in per_trace if n > hard]
    if not over:
        return _finding(a, GREEN, "%s: max %d calls per trace" % (tool, max(n for _, n in per_trace)),
                        checked=len(per_trace))
    samples = [{"trace": tid, "calls": n, "limit": hard} for tid, n in over[:MAX_SAMPLES]]
    status = RED if any(n > hard_max for _, n in over) else AMBER
    return _finding(a, status, "%d trace(s) exceeded %d calls (max %d)"
                    % (len(over), hard, max(n for _, n in over)), samples, checked=len(per_trace))


def _match_by_input(a: Assertion, traces: List[Trace]) -> List[Trace]:
    key = a.params.get("input_key") or normalize(a.params.get("input", ""))
    return [t for t in traces if normalize(t.input) == key]


def eval_facts_preserved(a: Assertion, traces: List[Trace],
                          baseline: Optional[Dict[str, Any]] = None) -> Finding:
    matched = _match_by_input(a, traces)
    if not matched:
        return _finding(a, GREEN, "input not present in target set", skipped=len(traces))
    baseline = set(a.params.get("facts") or [])
    if not baseline:
        return _finding(a, GREEN, "baseline answer had no facts to preserve",
                        checked=len(matched))
    dropped: List[Dict[str, Any]] = []
    added: List[Dict[str, Any]] = []
    for t in matched:
        facts = extract_facts(t.output or "")
        lost = sorted(baseline - facts)
        gain = sorted(facts - baseline)
        if lost:
            dropped.append({"trace": t.id, "dropped": lost[:6]})
        if gain:
            added.append({"trace": t.id, "added": gain[:6]})
    if dropped:
        return _finding(a, RED, "fact(s) disappeared from %d/%d answers: %s"
                        % (len(dropped), len(matched),
                           ", ".join(sorted({f for d in dropped for f in d["dropped"]})[:4])),
                        dropped, checked=len(matched))
    if added:
        return _finding(a, AMBER, "%d answer(s) gained new facts" % len(added),
                        added, checked=len(matched))
    return _finding(a, GREEN, "facts intact across %d answer(s)" % len(matched),
                    checked=len(matched))


def eval_similarity(a: Assertion, traces: List[Trace],
                     baseline: Optional[Dict[str, Any]] = None) -> Finding:
    matched = _match_by_input(a, traces)
    if not matched:
        return _finding(a, GREEN, "input not present in target set", skipped=len(traces))
    floor = float(a.params.get("min_ratio") or 0.0)
    baseline = str(a.params.get("baseline_output") or "")
    worst = 1.0
    bad: List[Dict[str, Any]] = []
    for t in matched:
        score = token_set_ratio(baseline, t.output or "")
        worst = min(worst, score)
        if score < floor:
            bad.append({"trace": t.id, "ratio": round(score, 3), "floor": floor,
                        "target_excerpt": (t.output or "")[:160]})
    if not bad:
        return _finding(a, GREEN, "lowest similarity %.3f (floor %.2f)" % (worst, floor),
                        checked=len(matched))
    status = RED if worst < max(0.0, floor - 0.15) else AMBER
    return _finding(a, status, "%d/%d answers below %.2f (worst %.3f)"
                    % (len(bad), len(matched), floor, worst), bad, checked=len(matched))


def eval_drift_batch(a: Assertion, traces: List[Trace],
                     baseline: Optional[Dict[str, Any]] = None) -> Finding:
    """Compare every replayed input against the stored baseline answer."""
    store = baseline or {}
    if not store:
        return _finding(a, AMBER, "baseline sidecar not loaded — re-run `mine`")
    floor = float(a.params.get("min_ratio") or 0.55)
    top = int(a.params.get("report_top") or 10)

    matched = 0
    reds: List[Dict[str, Any]] = []
    ambers: List[Dict[str, Any]] = []
    for t in traces:
        ref = store.get(normalize(t.input))
        if not ref:
            continue
        matched += 1
        out = t.output or ""
        ref_facts = set(ref.get("facts") or [])
        ref_nums = {float(x) for x in (ref.get("numbers") or [])}
        got_facts = extract_facts(out)
        got_nums = set(extract_numbers(out))
        lost_facts = sorted(ref_facts - got_facts)
        lost_nums = sorted(ref_nums - got_nums)
        gain_nums = sorted(got_nums - ref_nums)
        score = token_set_ratio(str(ref.get("output") or ""), out)
        label = str(ref.get("input") or "")[:80]

        if lost_facts:
            reds.append({"trace": t.id, "input": label, "why": "facts lost",
                         "detail": lost_facts[:4]})
        elif lost_nums and gain_nums:
            reds.append({"trace": t.id, "input": label, "why": "every number moved",
                         "detail": [_num(x) for x in sorted(lost_nums)[:2] + sorted(gain_nums)[:2]]})
        elif lost_nums:
            reds.append({"trace": t.id, "input": label, "why": "numbers lost",
                         "detail": [_num(x) for x in lost_nums[:4]]})
        elif score < floor - 0.15:
            reds.append({"trace": t.id, "input": label,
                         "why": "answer rewritten (similarity %.2f)" % score})
        elif score < floor:
            ambers.append({"trace": t.id, "input": label,
                           "why": "answer drifted (similarity %.2f)" % score})
        elif gain_nums:
            ambers.append({"trace": t.id, "input": label, "why": "new numbers appeared"})

    skipped = len(traces) - matched
    shown = (reds + ambers)[:top]
    if reds:
        return _finding(a, RED, "%d/%d matched answers drifted" % (len(reds), matched),
                        shown, checked=matched, skipped=skipped)
    if ambers:
        return _finding(a, AMBER, "%d/%d matched answers moved slightly" % (len(ambers), matched),
                        shown, checked=matched, skipped=skipped)
    if matched == 0:
        return _finding(a, AMBER, "no target input matched the baseline — replay the same prompts",
                        checked=0, skipped=skipped)
    return _finding(a, GREEN, "%d/%d matched answers unchanged" % (matched, matched),
                    checked=matched, skipped=skipped)


def _num(value: float) -> str:
    return "%d" % value if float(value).is_integer() else "%g" % value


EVALUATORS: Dict[str, Callable[..., Finding]] = {
    "shape.tool_result_not_empty": eval_tool_result_not_empty,
    "shape.result_not_degenerate": eval_result_not_degenerate,
    "shape.result_has_field": eval_result_has_field,
    "shape.result_len_range": eval_result_len_range,
    "action.tool_allowed": eval_tool_allowed,
    "action.tool_pair_allowed": eval_tool_pair_allowed,
    "action.path_within_root": eval_path_within_root,
    "action.max_calls": eval_max_calls,
    "drift.facts_preserved": eval_facts_preserved,
    "drift.numbers_preserved": eval_numbers_preserved,
    "drift.similarity": eval_similarity,
    "drift.batch": eval_drift_batch,
}


def run_contract(contract: Contract, traces: List[Trace],
                 baseline: Optional[Dict[str, Any]] = None) -> Report:
    findings: List[Finding] = []
    for a in contract.enabled():
        fn = EVALUATORS.get(a.kind)
        if fn is None:
            findings.append(_finding(a, GREEN, "unknown assertion kind, skipped"))
            continue
        try:
            findings.append(fn(a, traces, baseline))
        except Exception as exc:  # a broken assertion must not kill the run
            findings.append(_finding(a, AMBER, "assertion could not be evaluated: %s" % exc))

    kinds: Counter = Counter(f.kind.split(".")[0] for f in findings)
    # A drift assertion that never matched an input proves nothing. Silence it
    # loudly instead of letting it report green.
    drift = [f for f in findings if f.kind.startswith("drift.")]
    checked = sum(f.checked for f in drift)
    possible = sum(f.checked + f.skipped for f in drift)
    coverage = (checked / possible) if possible else 1.0
    report = Report(
        contract=contract,
        findings=findings,
        stats={
            "traces": len(traces),
            "assertions": len(findings),
            "by_kind": dict(kinds),
            "drift_coverage": round(coverage, 3),
            "drift_matched": checked,
            "drift_total": possible,
            "uncovered": [f.assertion_id for f in drift if f.checked == 0][:20],
        },
    )
    return report


def _pct(x: float) -> str:
    return "%.1f%%" % (x * 100)