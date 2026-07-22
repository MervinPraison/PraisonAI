"""Translation-intent detection — the single source of truth for task-awareness.

Two QC features depend on knowing whether a row is a *translation* task and which
script its output should be written in:

* task-aware script purity (``checks.LowScriptPurity`` / ``ScriptReview`` /
  ``WrongTargetScript``) — a Tamil->English row's correct output is English, so it
  must be exempted from the Tamil-purity drop instead of being deleted as
  "low_script_purity"; and
* the corpus-level ``translation`` metric in ``qc.score`` — the fraction of rows
  that are translation tasks, by direction.

Both import ``translation_intent`` from here so they can never disagree (DRY).
The generator's ground-truth ``task_type`` label is authoritative when present;
for externally-sourced rows without metadata we fall back to keyword/directional
cues on the instruction text. An unresolved direction yields *no* exemption (safe
default) so garbage can never slip past the strict purity thresholds.
"""
from __future__ import annotations

import re

# Ground-truth task labels the Tamil recipe stamps (see ``recipes.Tamil``). Kept
# here so the recipe axis label and the detector share one literal (no drift).
EN_TA_TASK = "ஆங்கிலத்திலிருந்து தமிழுக்கு மொழிபெயர்ப்பு"  # en->ta (output: Tamil)
TA_EN_TASK = "தமிழிலிருந்து ஆங்கிலத்துக்கு மொழிபெயர்ப்பு"  # ta->en (output: English)

# Translation lemma: Tamil root 'மொழிபெயர்' covers every inflection; 'translat'
# covers translate/translation/translated.
_XLATE_RE = re.compile(r"மொழிபெயர்|translat", re.IGNORECASE)
# Directional cues keyed to the language the OUTPUT should be written in.
_TO_EN_RE = re.compile(  # -> English output (ta->en)
    r"ஆங்கிலத்துக்கு|ஆங்கிலத்திற்கு|ஆங்கிலத்தில்|to\s+english|into\s+english|in\s+english",
    re.IGNORECASE,
)
_TO_TA_RE = re.compile(  # -> Tamil output (en->ta)
    r"தமிழுக்கு|தமிழிற்கு|தமிழில்|to\s+tamil|into\s+tamil|in\s+tamil",
    re.IGNORECASE,
)


def translation_intent(instruction: str, task_type: str | None = None) -> dict:
    """Classify a row's translation intent and the script its output should use.

    Prefers the generator's ground-truth ``task_type`` label; falls back to
    keyword/directional detection on the instruction text for external rows.

    Returns ``{is_translation, direction, expected_script}`` where ``direction``
    is ``'en_ta' | 'ta_en' | 'unknown' | None`` and ``expected_script`` is
    ``'tamil' | 'english' | None`` (``None`` when the row is not translation or
    the direction is unresolved — callers must then apply the strict Tamil-purity
    default rather than exempt the row).
    """
    # 1) Ground-truth metadata path (authoritative for generator-made rows).
    # Only the two labels the recipe stamps are authoritative; an *unrecognised*
    # non-empty label (e.g. an external row tagged ``"translation"``) is NOT
    # evidence the row is native, so we fall through to text detection rather than
    # declaring it non-translation and losing a legitimate English output.
    if task_type == TA_EN_TASK:
        return {"is_translation": True, "direction": "ta_en", "expected_script": "english"}
    if task_type == EN_TA_TASK:
        return {"is_translation": True, "direction": "en_ta", "expected_script": "tamil"}

    # 2) Text-detection fallback (external rows without metadata).
    text = instruction or ""
    if not _XLATE_RE.search(text):
        return {"is_translation": False, "direction": None, "expected_script": None}
    to_en, to_ta = bool(_TO_EN_RE.search(text)), bool(_TO_TA_RE.search(text))
    if to_en and not to_ta:
        return {"is_translation": True, "direction": "ta_en", "expected_script": "english"}
    if to_ta and not to_en:
        return {"is_translation": True, "direction": "en_ta", "expected_script": "tamil"}
    # Direction ambiguous ('both ways', neither/both named): it IS translation,
    # but default SAFE — no script exemption — so garbage can't slip through.
    return {"is_translation": True, "direction": "unknown", "expected_script": None}
