"""Shared text helpers (kept in one place — DRY)."""
from __future__ import annotations

import re
import unicodedata

ALPHA = re.compile(r"[^\W\d_]", re.UNICODE)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "").strip().lower())


def ngrams(s: str, n: int = 4) -> set:
    s = norm(s)
    return {s[i : i + n] for i in range(max(len(s) - n + 1, 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / max(len(a | b), 1)


def script_ratio(s: str, lo: int, hi: int) -> float:
    alpha = ALPHA.findall(s or "")
    if not alpha:
        return 1.0
    return sum(1 for c in alpha if lo <= ord(c) <= hi) / len(alpha)


def fields(row: dict) -> tuple[str, str, str]:
    """(instruction, input, output) from {instruction,input,output} or {messages}."""
    if "messages" in row:
        msgs = row["messages"]
        user = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
        asst = next((m["content"] for m in reversed(msgs) if m.get("role") == "assistant"), "")
        return user, "", asst
    return row.get("instruction", ""), row.get("input", ""), row.get("output", "")
