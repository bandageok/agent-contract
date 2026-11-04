"""Cheap, deterministic text comparison.

No embeddings, no API calls, no model download: a regression run has to work
on a laptop in CI with no keys. Token-set similarity catches the drift we care
about (a fact changing, a sentence disappearing) well enough for a gate.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, List, Set, Tuple

WORD_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")

# Numbers carry the facts that hurt when they drift: "7 天" -> "3 天".
# Units are grouped by what a reader would quote back, and every one of them
# showed up in real tool output: line/char counts, entry counts, token counts.
FACT_PATTERNS = [
    (re.compile(r"[¥$￥]\s?\d+(?:[.,]\d+)?"), "money"),
    (re.compile(r"\d+(?:\.\d+)?\s?(?:%|percent|％)"), "percent"),
    (re.compile(r"\d+(?:\.\d+)?\s?(?:天|日|小时|分钟|周|个月|月|年|秒|days?|hours?|minutes?|weeks?|months?|years?|seconds?)"), "duration"),
    (re.compile(r"\d+(?:\.\d+)?\s?(?:元|块|万|千|亿|美元|刀|欧|镑)"), "quantity"),
    (re.compile(r"\d+(?:\.\d+)?\s?(?:lines?|rows?|records?|entries|items|results?|files?|pages?|steps?|calls?|tokens?|words?|characters?|chars?|bytes?|kb|mb|gb|tb)"), "count"),
    (re.compile(r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b"), "date"),
    (re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b"), "version"),
    (re.compile(r"\b\d{1,3}(?:,\d{3})+\b"), "bignum"),
]

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def extract_numbers(text: str) -> List[float]:
    """Every numeric literal, deduped and sorted.

    Used as a drift signal on its own: "830 lines and 54405 characters" turning
    into "277 lines and 18135 characters" barely moves token-set similarity,
    because the sentence is identical — only the values moved.
    """
    seen = set()
    for match in NUMBER_RE.findall(text or ""):
        try:
            seen.add(float(match))
        except ValueError:
            continue
    return sorted(seen)


def normalize(text: str) -> str:
    return " ".join(WORD_RE.findall((text or "").lower()))


def tokens(text: str) -> List[str]:
    return WORD_RE.findall((text or "").lower())


def ratio(a: str, b: str) -> float:
    """Plain sequence ratio, 0..1."""
    return SequenceMatcher(None, a, b).ratio()


def token_set_ratio(a: str, b: str) -> float:
    """Order-insensitive similarity.

    Same idea as fuzzywuzzy's token_set_ratio: compare the intersection
    against each remainder, take the best. Robust to a sentence being added
    or reordered, which is exactly the noise that should not page anyone.
    """
    ta, tb = tokens(a), tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    sa, sb = sorted(set(ta)), sorted(set(tb))
    inter = sorted(set(sa) & set(sb))
    if not inter:
        return 0.0
    combo = " ".join(inter)
    r1 = ratio(combo, " ".join(sorted(set(sa) - set(sb))) + " " + combo)
    r2 = ratio(combo, " ".join(sorted(set(sb) - set(sa))) + " " + combo)
    r3 = ratio(" ".join(sa), " ".join(sb))
    return max(r1, r2, r3)


def extract_facts(text: str) -> Set[str]:
    """Pull out the values a reader would quote back at you."""
    out: Set[str] = set()
    for pattern, label in FACT_PATTERNS:
        for match in pattern.finditer(text or ""):
            value = match.group(0).lower().replace(" ", "")
            out.add("%s:%s" % (label, value))
    return out


def split_facts(a: Set[str], b: Set[str]) -> Tuple[Set[str], Set[str]]:
    """Return (dropped, added) between a baseline and a target."""
    return a - b, b - a


def longest_common_dir(paths: Iterable[str]) -> str:
    """Deepest directory shared by every path, or "" when they diverge."""
    cleaned = []
    for p in paths:
        p = str(p or "").strip().replace("\\", "/")
        if not p:
            continue
        if "/" in p:
            cleaned.append(p.rsplit("/", 1)[0])
        else:
            cleaned.append(".")
    if not cleaned:
        return ""
    parts = [c.split("/") for c in cleaned]
    common: List[str] = []
    for chunk in zip(*parts):
        if len(set(chunk)) == 1:
            common.append(chunk[0])
        else:
            break
    if not common:
        return ""
    return "/".join(common)


def dirname_of(value: str) -> str:
    v = str(value or "").strip().replace("\\", "/")
    return v.rsplit("/", 1)[0] if "/" in v else ""


def dir_allowed(value: str, allowed: Iterable[str]) -> bool:
    """Fallback containment when observed paths share no common prefix.

    Relative paths like ``.research/a.json`` and ``docs/b.md`` have no common
    directory, so a single root cannot be inferred. Instead the set of
    observed directories becomes the allow-list: anything outside them is a
    change worth a red light.
    """
    directory = dirname_of(value)
    if not directory:
        return True  # bare filename: same directory as whatever called it
    low = directory.lower()
    for candidate in allowed:
        base = str(candidate or "").strip("/").lower()
        if not base or base == ".":
            continue
        if low == base or low.startswith(base + "/"):
            return True
    return False