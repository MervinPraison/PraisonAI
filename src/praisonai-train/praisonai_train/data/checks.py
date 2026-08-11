"""Built-in QC checks (pluggable RowCheck implementations).

Each check trips per row and is either a 'drop' (removed) or 'flag' (kept but
counted). Thresholds come from config so everything is YAML-tunable. Add a new
check by registering another class — the scorer picks it up automatically.
"""
from __future__ import annotations

import re

from praisonai_train.data._util import jaccard, norm
from praisonai_train.data.intent import translation_intent
from praisonai_train.data.registry import checks

_BOILER = re.compile(
    r"(as an ai\b|as a language model|i cannot\b|i can'?t\b|i'?m sorry,? but|"
    r"my knowledge cutoff|i don'?t have real-time|language model (developed|created)|"
    r"நான் ஒரு (ai|செயற்கை)|என்னால் .{0,20}முடியாது)",
    re.I,
)
_ALPHA = re.compile(r"[^\W\d_]", re.UNICODE)


def _script_ratio(output, cfg):
    """Fraction of alphabetic chars inside the target script block (None if no
    alphabetic chars — nothing to judge)."""
    lo, hi = cfg.get("script_range", (0x0B80, 0x0BFF))
    alpha = _ALPHA.findall(output or "")
    if not alpha:
        return None
    return sum(1 for c in alpha if lo <= ord(c) <= hi) / len(alpha)


def _target_is_english(instruction, cfg):
    """True when this row is a resolved translation-INTO-English task, so its
    output is legitimately English and must be exempted from the target-script
    purity thresholds. Metadata (``task_type``) wins; text is the fallback. Only a
    resolved English target exempts — en->ta / ambiguous / native stay strict.
    Disabled by ``task_aware_purity: false``.
    """
    if not cfg.get("task_aware_purity", True):
        return False
    return translation_intent(instruction, cfg.get("task_type"))["expected_script"] == "english"


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
    """Drop rows whose output falls below the target-script purity floor.

    TASK-AWARE: a translation-into-English row's correct output *is* English, so
    exempt it here instead of deleting a legitimate row (see ``_target_is_english``).
    """

    name = "low_script_purity"
    kind = "drop"

    def triggered(self, instruction, input, output, cfg):
        if _target_is_english(instruction, cfg):
            return False
        ratio = _script_ratio(output, cfg)
        if ratio is None:
            return False
        return ratio < cfg.get("script_drop", 0.50)


@checks.register
class ScriptReview:
    """Flag borderline-purity rows for review — also skipped for English targets."""

    name = "script_review"
    kind = "flag"

    def triggered(self, instruction, input, output, cfg):
        if _target_is_english(instruction, cfg):
            return False
        ratio = _script_ratio(output, cfg)
        if ratio is None:
            return False
        return cfg.get("script_drop", 0.50) <= ratio < cfg.get("script_flag", 0.70)


@checks.register
class WrongTargetScript:
    """Flag a *failed* translation: the task asked for English output but the
    output is still mostly in the source script. Net-new signal that only the
    task-aware path can surface — a naive purity filter would have kept this
    silently (Tamil output passes a Tamil-purity check). Toggle with
    ``verify_translation_target: false``.
    """

    name = "wrong_target_script"
    kind = "flag"

    def triggered(self, instruction, input, output, cfg):
        if not cfg.get("verify_translation_target", True):
            return False
        if not _target_is_english(instruction, cfg):
            return False
        ratio = _script_ratio(output, cfg)
        if ratio is None:
            return False
        return ratio >= cfg.get("script_drop", 0.50)


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
