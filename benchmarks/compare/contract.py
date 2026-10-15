"""The S4 contract: proof that every framework did identical work.

A 3-agent sequential run passes when the stub saw exactly 3 non-streaming chat
requests, request i+1 carried the nonce of reply i, and the final output
contains the nonce of reply 3.
"""

from __future__ import annotations

AGENTS = 3
CHAT_PATHS = ("/v1/chat/completions", "/v1/responses")


def check(stats: dict, output) -> list[str]:
    """Return the list of contract violations (empty when the run passes)."""
    reqs = [r for r in stats.get("requests", []) if r["path"] in CHAT_PATHS]
    problems = []
    if len(reqs) != AGENTS:
        problems.append(f"expected {AGENTS} chat requests, saw {len(reqs)}")
    streamed = sum(1 for r in reqs if r["stream"])
    if streamed:
        problems.append(f"{streamed} request(s) were streaming")
    for i, r in enumerate(reqs[1:], start=2):
        if not r["has_prev_nonce"]:
            problems.append(f"request {i} does not carry the previous reply's nonce")
    last = next((r["reply_nonce"] for r in reversed(reqs) if r["reply_nonce"]), None)
    if last is None or last not in str(output):
        problems.append(f"final output does not contain the last nonce ({last})")
    return problems
