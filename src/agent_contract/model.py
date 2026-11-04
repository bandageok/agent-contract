"""Core data types for agent-contract.

Everything here is plain dataclasses with explicit dict round-trips, so a
contract file stays human-diffable in git and needs no serialiser dependency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

CONTRACT_VERSION = 1

# Status vocabulary. Three colours, no scores: a score invites optimisation.
RED = "red"
AMBER = "amber"
GREEN = "green"

STATUS_ORDER = {RED: 0, AMBER: 1, GREEN: 2}


def short_hash(text: str, size: int = 10) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]


@dataclass
class Step:
    """One observable action inside a trace.

    ``kind`` is normalised to one of ``tool``, ``message`` or ``error`` by the
    loader; anything unknown is kept as ``message`` so no data is dropped.
    """

    kind: str = "message"
    name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"kind": self.kind}
        if self.name:
            out["name"] = self.name
        if self.args:
            out["args"] = self.args
        if self.result is not None:
            out["result"] = self.result
        if self.text:
            out["text"] = self.text
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Step":
        return cls(
            kind=str(data.get("kind") or "message"),
            name=str(data.get("name") or ""),
            args=dict(data.get("args") or {}),
            result=data.get("result"),
            text=str(data.get("text") or ""),
        )


@dataclass
class Trace:
    """One end-to-end run: an input, the steps taken, the final output."""

    id: str
    input: str = ""
    output: str = ""
    steps: List[Step] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def tool_calls(self) -> List[Step]:
        return [s for s in self.steps if s.kind == "tool"]

    def tool_names(self) -> List[str]:
        return [s.name for s in self.tool_calls()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "input": self.input,
            "output": self.output,
            "steps": [s.to_dict() for s in self.steps],
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Trace":
        return cls(
            id=str(data.get("id") or ""),
            input=str(data.get("input") or ""),
            output=str(data.get("output") or ""),
            steps=[Step.from_dict(s) for s in (data.get("steps") or [])],
            meta=dict(data.get("meta") or {}),
        )


@dataclass
class Assertion:
    """One mined expectation.

    ``evidence`` is mandatory: an assertion without a historical basis is a
    guess, and guesses are what make linters get switched off.
    """

    id: str
    kind: str
    title: str
    params: Dict[str, Any] = field(default_factory=dict)
    evidence: str = ""
    severity: str = RED
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "params": self.params,
            "evidence": self.evidence,
            "severity": self.severity,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Assertion":
        return cls(
            id=str(data.get("id") or ""),
            kind=str(data.get("kind") or ""),
            title=str(data.get("title") or ""),
            params=dict(data.get("params") or {}),
            evidence=str(data.get("evidence") or ""),
            severity=str(data.get("severity") or RED),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class Contract:
    """The mined bundle. Committed to git, reviewed like code."""

    assertions: List[Assertion] = field(default_factory=list)
    version: int = CONTRACT_VERSION
    generated_at: str = ""
    source: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "source": self.source,
            "assertions": [a.to_dict() for a in self.assertions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Contract":
        return cls(
            assertions=[Assertion.from_dict(a) for a in (data.get("assertions") or [])],
            version=int(data.get("version") or CONTRACT_VERSION),
            generated_at=str(data.get("generated_at") or ""),
            source=dict(data.get("source") or {}),
        )

    def enabled(self) -> List[Assertion]:
        return [a for a in self.assertions if a.enabled]


@dataclass
class Finding:
    """One assertion evaluated against the target traces."""

    assertion_id: str
    kind: str
    title: str
    status: str = GREEN
    message: str = ""
    samples: List[Dict[str, Any]] = field(default_factory=list)
    checked: int = 0
    skipped: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assertion_id": self.assertion_id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "message": self.message,
            "samples": self.samples,
            "checked": self.checked,
            "skipped": self.skipped,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        return cls(
            assertion_id=str(data.get("assertion_id") or ""),
            kind=str(data.get("kind") or ""),
            title=str(data.get("title") or ""),
            status=str(data.get("status") or GREEN),
            message=str(data.get("message") or ""),
            samples=list(data.get("samples") or []),
            checked=int(data.get("checked") or 0),
            skipped=int(data.get("skipped") or 0),
        )


@dataclass
class Report:
    contract: Contract
    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def counts(self) -> Dict[str, int]:
        out = {RED: 0, AMBER: 0, GREEN: 0}
        for f in self.findings:
            out[f.status] = out.get(f.status, 0) + 1
        return out

    def worst(self) -> str:
        if not self.findings:
            return GREEN
        return min(self.findings, key=lambda f: STATUS_ORDER.get(f.status, 9)).status

    def failed(self) -> bool:
        return self.counts()[RED] > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "counts": self.counts(),
            "worst": self.worst(),
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
            "contract": self.contract.to_dict(),
        }


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)


def loads(text: str) -> Any:
    return json.loads(text)


def _unused_optional(x: Optional[Any]) -> Optional[Any]:  # pragma: no cover
    """Keeps the Optional import meaningful for type checkers."""
    return x


def as_dict(obj: Any) -> Dict[str, Any]:  # pragma: no cover - convenience
    return asdict(obj)