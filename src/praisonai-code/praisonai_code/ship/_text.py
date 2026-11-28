"""Shared untrusted-text fencing and noisy-diff filtering for ``praisonai ship``."""

import re

MAX_UNTRUSTED = 20_000
_NOISY_EXACT = frozenset({"package-lock.json", "pnpm-lock.yaml", "yarn.lock"})
_NOISY_SUFFIX = (".lock", ".min.js", ".min.css")
_DIFF_SPLIT = re.compile(r"(?m)^(?=diff --git )")
_DIFF_PATH = re.compile(r'\s+"?b/([^"]+)"?$')


def strip_noisy_diff(diff: str) -> str:
    """Drop lockfile and minified bundle hunks from unified git diffs."""
    if "diff --git " not in diff:
        return diff
    kept, saw, kept_diff = [], False, False
    for sec in _DIFF_SPLIT.split(diff):
        if not sec.startswith("diff --git "):
            kept.append(sec)
            continue
        saw = True
        m = _DIFF_PATH.search(sec.splitlines()[0])
        name = m.group(1).strip().strip('"').rsplit("/", 1)[-1].lower() if m else ""
        if name in _NOISY_EXACT or name.endswith(_NOISY_SUFFIX):
            continue
        kept.append(sec)
        kept_diff = True
    return "(only lockfile/minified changes)" if saw and not kept_diff else "".join(kept)


def fence_untrusted(
    text: str, *, lang: str = "text", max_chars: int = MAX_UNTRUSTED, strip_noise: bool = False
) -> str:
    """Optionally strip noisy diff hunks, cap length, and wrap in an uncloseable backtick fence."""
    if strip_noise:
        text = strip_noisy_diff(text)
    if len(text) > max_chars:
        text = text[:max_chars] + ("\n... (diff truncated)" if lang == "diff" else "\n... (truncated)")
    fence = "`" * max(3, 1 + max((len(m) for m in re.findall(r"`+", text)), default=0))
    return f"{fence}{lang}\n{text}\n{fence}"
