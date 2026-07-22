"""Tests for the MinHash+LSH near-dedup engine and cross-file global dedup.

Deterministic: MinHasher is seeded, so signatures/bucketing are reproducible.
"""
import json

from praisonai_train.data import global_dedup, near_dedup, score
from praisonai_train.data.dedup import (
    MinHashLSH,
    MinHasher,
    optimal_bands,
    signature_similarity,
)


def _rows(*instructions):
    return [{"instruction": t, "input": "", "output": "ஒரு முழுமையான தமிழ் பதில் இங்கே."}
            for t in instructions]


# ── MinHash primitives ────────────────────────────────────────────────────────

def test_minhasher_is_deterministic():
    a = MinHasher(num_perm=64, seed=7).signature("the quick brown fox jumps")
    b = MinHasher(num_perm=64, seed=7).signature("the quick brown fox jumps")
    assert a == b and len(a) == 64


def test_signature_similarity_tracks_jaccard():
    h = MinHasher(num_perm=256, seed=1)
    base = "please summarize the following article about tamil history in detail"
    near = "please summarize the following article about tamil history in brief"
    far = "write a python function that reverses a linked list quickly"
    sim_near = signature_similarity(h.signature(base), h.signature(near))
    sim_far = signature_similarity(h.signature(base), h.signature(far))
    assert sim_near > 0.7 > sim_far


def test_optimal_bands_partition_num_perm():
    b, r = optimal_bands(128, 0.7)
    assert b * r == 128 and b >= 1 and r >= 1


# ── LSH index behaviour ───────────────────────────────────────────────────────

def test_lsh_flags_near_and_keeps_distinct():
    lsh = MinHashLSH(threshold=0.7, num_perm=128, seed=1)
    assert lsh.add_if_new("explain photosynthesis to a curious school student") is True
    # near-identical (one word changed) → duplicate, index unchanged
    assert lsh.add_if_new("explain photosynthesis to a curious school pupil") is False
    # genuinely different → kept
    assert lsh.add_if_new("give me a recipe for spicy tomato rice") is True
    assert len(lsh) == 2


def test_lsh_query_returns_candidates_via_banding():
    lsh = MinHashLSH(threshold=0.7, num_perm=128, seed=1)
    lsh.add_if_new("the mitochondria is the powerhouse of the cell indeed")
    _, cands = lsh.query("the mitochondria is the powerhouse of the cell today")
    assert cands, "banded hashing should surface the near-dup as a candidate"


# ── The headline claim: minhash catches near-dups the sliding window misses ────

def test_minhash_catches_far_near_dup_that_sliding_window_misses():
    a = "translate the following tamil sentence into fluent english please"
    b = "translate the following tamil sentence into fluent english now"  # near-dup of a
    filler = _rows(
        "how do bees communicate the location of flowers",
        "recommend a good beginner yoga routine for mornings",
        "why is the sky blue during the daytime hours",
        "give tips for growing tomatoes in a small balcony",
        "explain how a suspension bridge carries its load",
    )
    rows = _rows(a) + filler + _rows(b)

    # Sliding window of 1 only ever compares against the immediately previous row,
    # so the near-dup 6 rows later slips through (the real limitation at scale).
    slide_kept, slide_dropped = near_dedup(
        rows, {"near_dup_method": "sliding", "near_dup_window": 1})
    assert slide_dropped == 0
    assert len(slide_kept) == len(rows)

    # MinHash+LSH has no look-back window → it catches it regardless of distance.
    mh_kept, mh_dropped = near_dedup(rows, {"near_dup_method": "minhash"})
    assert mh_dropped == 1
    assert len(mh_kept) == len(rows) - 1


def test_minhash_does_not_drop_genuinely_distinct_rows():
    rows = _rows(
        "what is the capital of france",
        "describe the process of cellular respiration",
        "write a haiku about the monsoon season",
        "compute the derivative of x squared plus three x",
        "list five benefits of regular physical exercise",
    )
    kept, dropped = near_dedup(rows, {"near_dup_method": "minhash"})
    assert dropped == 0 and len(kept) == len(rows)


def test_score_minhash_method_removes_near_dups():
    rows = _rows(
        "summarize the history of the tamil sangam literature in three lines",
        "summarize the history of the tamil sangam literature in three sentences",
    )
    r = score(rows, {"near_dup_method": "minhash", "min_output_chars": 5})
    assert r["drops"].get("near_dup", 0) == 1
    assert r["kept_n"] == 1


def test_unknown_method_raises():
    import pytest
    with pytest.raises(ValueError):
        near_dedup(_rows("x"), {"near_dup_method": "bogus"})


# ── Cross-file / global dedup (what per-file score() cannot do) ────────────────

def test_global_dedup_removes_cross_file_dups(tmp_path):
    f1 = tmp_path / "batch1.jsonl"
    f2 = tmp_path / "batch2.jsonl"
    f1.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in _rows(
        "what is machine learning",
        "explain gradient descent simply",
    )) + "\n", encoding="utf-8")
    f2.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in _rows(
        "what is machine learning",                 # exact cross-file dup
        "explain gradient descent very simply",     # near cross-file dup
        "a totally unrelated fresh question here",  # unique
    )) + "\n", encoding="utf-8")

    kept = list(global_dedup([str(f1), str(f2)]))
    instrs = [k["instruction"] for k in kept]
    assert "what is machine learning" in instrs
    assert instrs.count("what is machine learning") == 1        # exact dup removed
    assert "explain gradient descent very simply" not in instrs  # near dup removed
    assert "a totally unrelated fresh question here" in instrs   # unique preserved
    assert len(kept) == 3


def test_global_dedup_exact_only(tmp_path):
    f1 = tmp_path / "a.jsonl"
    f1.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in _rows(
        "identical prompt", "identical prompt", "near identical prompt")) + "\n",
        encoding="utf-8")
    kept = list(global_dedup([str(f1)], {"near_dup": False}))
    # exact dup collapsed; the near one survives because near-dup is disabled
    assert len(kept) == 2


def test_global_dedup_accepts_inmemory_rows():
    kept = list(global_dedup([_rows("alpha one two"), _rows("alpha one two")]))
    assert len(kept) == 1


# ── Backward compatibility: default path is unchanged ─────────────────────────

def test_default_method_is_sliding_and_matches_legacy():
    dup_a = "please write a short poem about the rain and the sea"
    rows = _rows(dup_a, dup_a + " today")  # >0.7 char-4gram Jaccard, adjacent
    kept, dropped = near_dedup(rows, {})  # no method → sliding default
    assert dropped == 1 and len(kept) == 1
