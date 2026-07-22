"""Task-aware script purity + translation-share metric in the praisonai-train
data SDK, plus the shared translation-intent detector.

Mirrors the modeltrain reference (tests/test_task_aware_qc.py) but exercises the
SDK idiom: the purity behaviour lives in registered ``RowCheck`` classes and the
translation composition is a corpus metric returned by ``score``.
"""
from praisonai_train.data import score, translation_intent
from praisonai_train.data.intent import EN_TA_TASK, TA_EN_TASK

TAMIL_OUT = "இது ஒரு முழுமையான தமிழ் பதில். இது நன்றாக முடிகிறது."  # >20 chars, pure Tamil
ENGLISH_OUT = "This is a complete English translation of the given Tamil sentence."


# ---- shared detector (single source of truth) ------------------------------

def test_intent_metadata_ta_en():
    i = translation_intent("anything", task_type=TA_EN_TASK)
    assert i == {"is_translation": True, "direction": "ta_en", "expected_script": "english"}


def test_intent_metadata_en_ta():
    i = translation_intent("anything", task_type=EN_TA_TASK)
    assert i == {"is_translation": True, "direction": "en_ta", "expected_script": "tamil"}


def test_intent_metadata_native_is_not_translation():
    i = translation_intent("ஆங்கிலம் பற்றிய கேள்வி", task_type="ஒரு பொதுவான கேள்வி-பதில்")
    assert i["is_translation"] is False and i["expected_script"] is None


def test_intent_text_fallback_ta_en():
    i = translation_intent("இந்த வாக்கியத்தை ஆங்கிலத்துக்கு மொழிபெயர்க்கவும்.")
    assert i["direction"] == "ta_en" and i["expected_script"] == "english"


def test_intent_text_fallback_en_ta():
    i = translation_intent("Translate this sentence into Tamil.")
    assert i["direction"] == "en_ta" and i["expected_script"] == "tamil"


def test_intent_ambiguous_direction_is_safe():
    i = translation_intent("Translate between Tamil and English both ways.")
    assert i["is_translation"] is True and i["expected_script"] is None


def test_intent_language_topic_without_translate_intent():
    i = translation_intent("ஆங்கிலம் கற்றுக்கொள்வது எப்படி என்று விளக்குங்கள்.")
    assert i["is_translation"] is False


# ---- feature #1: task-aware purity via registered RowChecks ----------------

def test_ta_en_english_output_recovered_via_metadata():
    rows = [{"instruction": "மொழிபெயர்க்க", "input": "", "output": ENGLISH_OUT,
             "task_type": TA_EN_TASK}]
    res = score(rows, {"near_dup": False})
    assert res["kept_n"] == 1                        # NOT dropped as low_script_purity
    assert "low_script_purity" not in res["drops"]
    assert res["metrics"]["translation"]["exempted"] == 1


def test_ta_en_english_output_recovered_via_text_fallback():
    rows = [{"instruction": "இந்த வாக்கியத்தை ஆங்கிலத்தில் மொழிபெயர்க்கவும்.",
             "input": "", "output": ENGLISH_OUT}]
    res = score(rows, {"near_dup": False})
    assert res["kept_n"] == 1 and res["metrics"]["translation"]["exempted"] == 1


def test_native_low_purity_still_dropped():
    rows = [{"instruction": "தமிழில் ஒரு கதை எழுதுங்கள்.", "input": "",
             "output": ENGLISH_OUT}]   # native task, English body -> bad
    res = score(rows, {"near_dup": False})
    assert res["kept_n"] == 0 and res["drops"].get("low_script_purity") == 1
    assert res["metrics"]["translation"]["exempted"] == 0


def test_wrong_target_script_flag_for_failed_ta_en():
    # ta->en asked, but output is still Tamil = failed translation: kept + flagged.
    rows = [{"instruction": "ஆங்கிலத்துக்கு மொழிபெயர்க்கவும்.", "input": "",
             "output": TAMIL_OUT, "task_type": TA_EN_TASK}]
    res = score(rows, {"near_dup": False})
    assert res["kept_n"] == 1
    assert res["flags"].get("wrong_target_script") == 1


def test_wrong_target_disabled():
    rows = [{"instruction": "ஆங்கிலத்துக்கு மொழிபெயர்க்கவும்.", "input": "",
             "output": TAMIL_OUT, "task_type": TA_EN_TASK}]
    res = score(rows, {"near_dup": False, "verify_translation_target": False})
    assert "wrong_target_script" not in res["flags"]


def test_task_aware_purity_can_be_disabled():
    # Turning off task-awareness restores the strict behaviour: the English
    # output of a ta->en row is then dropped as low purity.
    rows = [{"instruction": "மொழிபெயர்க்க", "input": "", "output": ENGLISH_OUT,
             "task_type": TA_EN_TASK}]
    res = score(rows, {"near_dup": False, "task_aware_purity": False})
    assert res["kept_n"] == 0 and res["drops"].get("low_script_purity") == 1


def test_ambiguous_translation_stays_strict():
    rows = [{"instruction": "Translate this both ways between Tamil and English.",
             "input": "", "output": ENGLISH_OUT}]
    res = score(rows, {"near_dup": False})
    assert res["kept_n"] == 0 and res["drops"].get("low_script_purity") == 1


# ---- feature #2: translation-share corpus metric ---------------------------

def test_translation_share_and_by_direction():
    rows = [
        {"instruction": "a", "input": "", "output": ENGLISH_OUT, "task_type": TA_EN_TASK},
        {"instruction": "b", "input": "", "output": TAMIL_OUT, "task_type": EN_TA_TASK},
        {"instruction": "c", "input": "", "output": TAMIL_OUT, "task_type": "ஒரு விளக்கம்"},
        {"instruction": "d", "input": "", "output": TAMIL_OUT, "task_type": "ஒரு விளக்கம்"},
    ]
    res = score(rows, {"near_dup": False})
    t = res["metrics"]["translation"]
    assert t["share"] == 0.5                          # 2 of 4 kept rows
    assert t["by_direction"] == {"en_ta": 1, "ta_en": 1, "unknown": 0}
    assert t["exempted"] == 1                         # only the English-target row


def test_translation_share_reconciles_with_exempted():
    rows = [{"instruction": f"i{n}", "input": "", "output": ENGLISH_OUT,
             "task_type": TA_EN_TASK} for n in range(3)]
    t = score(rows, {"near_dup": False})["metrics"]["translation"]
    assert t["by_direction"]["ta_en"] == t["exempted"] == 3


def test_empty_corpus_guard():
    res = score([], {"near_dup": False})
    assert res["metrics"]["translation"]["share"] == 0.0 and res["kept_n"] == 0
