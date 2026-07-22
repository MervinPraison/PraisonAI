"""Tests for the praisonai-train data SDK (QC + recipes + registry)."""
from praisonai_train.data import score, filter_rows, recipes, checks


def test_registries_populated():
    assert "tamil" in recipes.names()
    assert {"too_short", "boilerplate_refusal", "low_script_purity"} <= set(checks.names())


def test_qc_drops_bad_rows():
    rows = [
        {"instruction": "நல்ல கேள்வி ஒன்று", "input": "",
         "output": "இது ஒரு முழுமையான தமிழ் பதில், போதுமான நீளம் கொண்டது."},           # good
        {"instruction": "dup", "input": "", "output": "As an AI, I cannot help you."},   # boilerplate
        {"instruction": "s", "input": "", "output": "x"},                                # too short
        {"instruction": "t", "input": "", "output": "Entirely english output text here"},# low purity
    ]
    r = score(rows, {"min_output_chars": 20})
    assert r["drops"].get("boilerplate_refusal", 0) >= 1
    assert r["drops"].get("too_short", 0) >= 1
    assert r["drops"].get("low_script_purity", 0) >= 1
    assert r["kept_n"] == 1


def test_exact_dedup():
    rows = [{"instruction": "same", "input": "", "output": "ஒரு நல்ல முழுமையான தமிழ் பதில்."}] * 3
    assert score(rows)["drops"].get("exact_dup", 0) == 2


def test_recipe_offsets_disjoint():
    t = recipes.get("tamil")
    assert t.prompts(2, 0)[0]["user"] != t.prompts(2, 50000)[0]["user"]


def test_filter_rows_returns_kept():
    rows = [{"instruction": "க", "input": "", "output": "ஒரு நல்ல முழுமையான தமிழ் பதில் இங்கே."}]
    assert filter_rows(rows) == rows


def test_messages_schema_supported():
    rows = [{"messages": [{"role": "user", "content": "hi"},
                          {"role": "assistant", "content": "ஒரு முழுமையான தமிழ் பதில் இங்கே உள்ளது."}]}]
    assert score(rows)["kept_n"] == 1


def test_messages_pairs_user_before_final_assistant():
    from praisonai_train.data._util import fields
    row = {"messages": [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "answer to first"},
        {"role": "user", "content": "unanswered follow-up"},
    ]}
    ins, _, out = fields(row)
    assert ins == "first question"
    assert out == "answer to first"


def test_exact_dedup_keeps_distinct_answers():
    rows = [
        {"instruction": "ஒரு கேள்வி", "input": "", "output": "முதல் முழுமையான தமிழ் பதில் ஒன்று."},
        {"instruction": "ஒரு கேள்வி", "input": "", "output": "இரண்டாவது வேறுபட்ட தமிழ் பதில் ஒன்று."},
    ]
    r = score(rows, {"near_dup": False})
    assert r["drops"].get("exact_dup", 0) == 0
    assert r["kept_n"] == 2
