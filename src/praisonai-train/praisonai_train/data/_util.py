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
    """(instruction, input, output) from {instruction,input,output} or {messages}.

    For a chat transcript, take the last assistant turn and the user turn that
    *precedes* it, so we never pair a trailing unanswered user turn with an
    earlier assistant reply that answered a different question.
    """
    if "messages" in row:
        msgs = row["messages"]
        asst_idx = next((i for i in range(len(msgs) - 1, -1, -1)
                         if msgs[i].get("role") == "assistant"), None)
        if asst_idx is None:
            return "", "", ""
        asst = msgs[asst_idx].get("content", "")
        user = next((msgs[i].get("content", "") for i in range(asst_idx - 1, -1, -1)
                     if msgs[i].get("role") == "user"), "")
        return user, "", asst
    return row.get("instruction", ""), row.get("input", ""), row.get("output", "")
