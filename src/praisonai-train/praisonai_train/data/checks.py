"""Built-in QC checks (pluggable RowCheck implementations).

Each check trips per row and is either a 'drop' (removed) or 'flag' (kept but
counted). Thresholds come from config so everything is YAML-tunable. Add a new
check by registering another class — the scorer picks it up automatically.
"""
from __future__ import annotations

import re

from praisonai_train.data._util import jaccard, norm
from praisonai_train.data.registry import checks

_BOILER = re.compile(
    r"(as an ai\b|as a language model|i cannot\b|i can'?t\b|i'?m sorry,? but|"
    r"my knowledge cutoff|i don'?t have real-time|language model (developed|created)|"
    r"நான் ஒரு (ai|செயற்கை)|என்னால் .{0,20}முடியாது)",
    re.I,
)
_ALPHA = re.compile(r"[^\W\d_]", re.UNICODE)


@checks.register
class TooShort:
    name = "too_short"
    kind = "drop"

    def triggered(self, instruction, input, output, cfg):
        return len((output or "").strip()) < cfg.get("min_output_chars", 20)


@checks.register
class BoilerplateRefusal:
    name = "boilerplate_refusal"
    kind = "drop"

    def triggered(self, instruction, input, output, cfg):
        return bool(_BOILER.search(output or ""))


@checks.register
class LowScriptPurity:
    name = "low_script_purity"
    kind = "drop"

    def triggered(self, instruction, input, output, cfg):
        lo, hi = cfg.get("script_range", (0x0B80, 0x0BFF))
        alpha = _ALPHA.findall(output or "")
        if not alpha:
            return False
        ratio = sum(1 for c in alpha if lo <= ord(c) <= hi) / len(alpha)
        return ratio < cfg.get("script_drop", 0.50)


@checks.register
class ScriptReview:
    name = "script_review"
    kind = "flag"

    def triggered(self, instruction, input, output, cfg):
        lo, hi = cfg.get("script_range", (0x0B80, 0x0BFF))
        alpha = _ALPHA.findall(output or "")
        if not alpha:
            return False
        ratio = sum(1 for c in alpha if lo <= ord(c) <= hi) / len(alpha)
        return cfg.get("script_drop", 0.50) <= ratio < cfg.get("script_flag", 0.70)


@checks.register
class MaybeTruncated:
    name = "maybe_truncated"
    kind = "flag"

    def triggered(self, instruction, input, output, cfg):
        return not re.search(r'[.!?।”"\')\]`]\s*$|```\s*$', (output or "").strip())


@checks.register
class RestatesQuestion:
    name = "restates_question"
    kind = "flag"

    def triggered(self, instruction, input, output, cfg):
        first = re.split(r"(?<=[.!?।])\s", (output or "").strip(), 1)[0]
        return jaccard(set(norm(first).split()), set(norm(instruction).split())) > 0.6
