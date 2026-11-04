"""Load traces from whatever shape your app already writes.

The rule here is: never drop data. Unknown keys survive in ``meta`` so a
hand-written contract can still reference them later.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .model import Step, Trace, short_hash

EMPTY_VALUES = {None, "", "null", "None", "{}", "[]"}


class LoadError(ValueError):
    """Raised when a trace file cannot be read at all."""


def is_empty(value: Any) -> bool:
    """True for the shapes that silently poison a downstream agent."""
    if value is None:
        return True
    if isinstance(value, (str, bytes, list, tuple, dict, set)):
        if len(value) == 0:
            return True
        if isinstance(value, str) and value.strip() in EMPTY_VALUES:
            return True
        return False
    return False


def is_degenerate(value: Any) -> bool:
    """True when a tool "succeeded" but handed back nothing usable.

    ``{"content_chars": 0, "bytes": 0}`` is not an empty result by identity —
    it is a non-empty dict the downstream agent will happily consume. This is
    the most common silent failure we see in the wild, so it needs its own
    predicate rather than a top-level emptiness check.
    """
    if is_empty(value):
        return True
    if isinstance(value, dict):
        numbers = [v for v in value.values()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
        strings = [v for v in value.values() if isinstance(v, str)]
        if numbers and all(n == 0 for n in numbers) and all(not s.strip() for s in strings):
            return True
    return False


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "{[":
            try:
                return json.loads(stripped)
            except (ValueError, TypeError):
                return value
    return value


def _collect_inputs(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for m in messages:
        if str(m.get("role") or "") in {"user", "human"}:
            parts.append(_text_of(m.get("content")))
    return "\n".join(p for p in parts if p).strip()


def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") in {"text", "input_text", "output_text"}:
                    out.append(str(part.get("text") or ""))
                elif "text" in part:
                    out.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                out.append(part)
        return "".join(out)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return str(content)


def from_openai_chat(record: Dict[str, Any]) -> Optional[Trace]:
    """Normalise an OpenAI-style ``{"messages": [...]}`` record."""
    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    steps: List[Step] = []
    pending: List[Step] = []
    output_parts: List[str] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role in {"assistant", "model"}:
            text = _text_of(msg.get("content"))
            if text:
                steps.append(Step(kind="message", text=text))
                output_parts.append(text)
            for call in msg.get("tool_calls") or []:
                fn = (call or {}).get("function") or {}
                name = str(fn.get("name") or (call or {}).get("name") or "")
                args = _maybe_json(fn.get("arguments") or (call or {}).get("arguments") or {})
                step = Step(kind="tool", name=name, args=args if isinstance(args, dict) else {"_raw": args})
                steps.append(step)
                pending.append(step)
        elif role in {"tool", "function"}:
            value = _maybe_json(msg.get("content"))
            if pending:
                pending.pop(0).result = value
            else:
                steps.append(Step(kind="tool", name=str(msg.get("name") or ""), result=value))

    if not steps:
        return None

    trace_input = _collect_inputs(messages)
    output = output_parts[-1] if output_parts else ""
    meta = {k: v for k, v in record.items() if k not in {"messages", "id", "input", "output", "steps"}}
    return Trace(
        id=str(record.get("id") or short_hash(trace_input + output, 12)),
        input=trace_input,
        output=output,
        steps=steps,
        meta=meta,
    )


def from_langchain(record: Dict[str, Any]) -> Optional[Trace]:
    """Normalise a LangChain-ish ``{"inputs","outputs","intermediate_steps"}`` record."""
    steps_raw = record.get("intermediate_steps")
    if not isinstance(steps_raw, list):
        return None

    steps: List[Step] = []
    for item in steps_raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            action, observation = item[0], item[1]
            if isinstance(action, dict):
                name = str(action.get("tool") or action.get("tool_name") or "")
                args = action.get("tool_input") or {}
            else:
                name = str(getattr(action, "tool", "") or "")
                args = getattr(action, "tool_input", {}) or {}
            steps.append(Step(
                kind="tool",
                name=name,
                args=args if isinstance(args, dict) else {"_raw": args},
                result=_maybe_json(observation),
            ))
        elif isinstance(item, dict):
            steps.append(Step(
                kind="tool",
                name=str(item.get("tool") or item.get("name") or ""),
                args=item.get("args") or {},
                result=_maybe_json(item.get("result") or item.get("observation")),
            ))
    if not steps:
        return None

    inputs = record.get("inputs")
    outputs = record.get("outputs")
    if isinstance(inputs, dict):
        trace_input = str(inputs.get("input") or inputs.get("question") or inputs)
    else:
        trace_input = str(inputs or "")
    if isinstance(outputs, dict):
        output = str(outputs.get("output") or outputs.get("answer") or outputs)
    else:
        output = str(outputs or "")
    meta = {k: v for k, v in record.items()
            if k not in {"inputs", "outputs", "intermediate_steps", "id"}}
    return Trace(
        id=str(record.get("id") or short_hash(trace_input + output, 12)),
        input=trace_input,
        output=output,
        steps=steps,
        meta=meta,
    )


def from_canonical(record: Dict[str, Any]) -> Optional[Trace]:
    """The documented shape: ``{id, input, output, steps:[...]}``."""
    steps_raw = record.get("steps")
    if not isinstance(steps_raw, list):
        return None

    steps: List[Step] = []
    for raw in steps_raw:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or raw.get("type") or "message")
        if kind in {"tool_call", "tool", "action", "function_call"}:
            args = raw.get("args")
            if args is None:
                args = raw.get("arguments")
            args = _maybe_json(args if args is not None else {})
            steps.append(Step(
                kind="tool",
                name=str(raw.get("name") or raw.get("tool") or ""),
                args=args if isinstance(args, dict) else {"_raw": args},
                result=raw.get("result") if "result" in raw else raw.get("observation"),
            ))
        elif kind in {"error", "exception"}:
            steps.append(Step(kind="error", text=_text_of(raw.get("text") or raw.get("message"))))
        else:
            steps.append(Step(kind="message", text=_text_of(raw.get("text") or raw.get("content"))))

    return Trace(
        id=str(record.get("id") or short_hash(str(record.get("input") or "") + str(record.get("output") or ""), 12)),
        input=str(record.get("input") or ""),
        output=_text_of(record.get("output")) if record.get("output") is not None else "",
        steps=steps,
        meta=dict(record.get("meta") or {}),
    )


def normalize_record(record: Dict[str, Any]) -> Optional[Trace]:
    """Try every known shape, most specific first."""
    for adapter in (from_canonical, from_langchain, from_openai_chat):
        trace = adapter(record)
        if trace is not None:
            return trace
    # Last resort: a bare input/output pair still carries drift signal.
    if record.get("input") is not None or record.get("output") is not None:
        return Trace(
            id=str(record.get("id") or short_hash(str(record.get("input")) + str(record.get("output")), 12)),
            input=str(record.get("input") or ""),
            output=str(record.get("output") or ""),
            steps=[],
            meta={k: v for k, v in record.items() if k not in {"id", "input", "output"}},
        )
    return None


def iter_records(path: Path) -> Iterable[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return
    if text[0] == "[":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise LoadError("%s: invalid JSON array (%s)" % (path, exc)) from exc
        for item in data:
            if isinstance(item, dict):
                yield item
        return
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise LoadError("%s:%d: invalid JSON line (%s)" % (path, lineno, exc)) from exc
        if isinstance(item, dict):
            yield item


def expand_paths(paths: Iterable[str]) -> List[Path]:
    """Accept files, directories and globs; return a deterministic file list."""
    out: List[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            out.extend(sorted(p.rglob("*.jsonl")))
            out.extend(sorted(p.rglob("*.json")))
        elif any(ch in raw for ch in "*?["):
            out.extend(sorted(Path().glob(raw)))
        elif p.exists():
            out.append(p)
        else:
            raise LoadError("no such file or directory: %s" % raw)
    seen = set()
    unique = []
    for p in out:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    if not unique:
        raise LoadError("no trace files matched: %s" % ", ".join(paths))
    return unique


def load_traces(paths: Iterable[str]) -> Tuple[List[Trace], Dict[str, Any]]:
    """Load and normalise. Returns traces plus load statistics."""
    files = expand_paths(paths)
    traces: List[Trace] = []
    skipped = 0
    by_file: Dict[str, int] = {}
    for f in files:
        count = 0
        for record in iter_records(f):
            trace = normalize_record(record)
            if trace is None:
                skipped += 1
                continue
            traces.append(trace)
            count += 1
        by_file[str(f)] = count
    stats = {
        "files": len(files),
        "traces": len(traces),
        "skipped": skipped,
        "by_file": by_file,
    }
    return traces, stats


def write_traces(path: str, traces: List[Trace]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for t in traces:
            fh.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")