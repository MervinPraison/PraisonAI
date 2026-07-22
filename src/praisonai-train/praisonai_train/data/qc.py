"""Dataset quality control — runs the pluggable checks + structural dedup.

Per-row checks come from the ``checks`` registry (drop/flag); exact + near
duplicate removal and the dataset-level diversity metrics are structural.
Thresholds are passed via ``cfg`` (YAML-tunable). Research-backed defaults:
Self-Instruct near-dup ROUGE-L 0.7 ≈ char-4gram Jaccard 0.7; distinct-2 >= 0.5
and output-length CV >= 0.4 are the healthy-diversity bars.
"""
from __future__ import annotations

import hashlib
import statistics as st
from collections import Counter
from typing import Any, Iterable

from praisonai_train.data import checks as _checks_mod  # noqa: F401  (registers checks)
from praisonai_train.data._util import fields, jaccard, ngrams, norm
from praisonai_train.data.intent import translation_intent
from praisonai_train.data.registry import checks


def score(rows: Iterable[dict], cfg: dict | None = None) -> dict[str, Any]:
    cfg = dict(cfg or {})
    rows = list(rows)
    drop_checks = [c for c in checks.all() if c.kind == "drop"]
    flag_checks = [c for c in checks.all() if c.kind == "flag"]
    do_near = cfg.get("near_dup", True)
    near_j = cfg.get("near_dup_jaccard", 0.7)

    seen: set[str] = set()
    kept: list[dict] = []
    drops: Counter = Counter()
    flags: Counter = Counter()

    for r in rows:
        ins, inp, out = fields(r)
        key = hashlib.sha1(norm(ins + "\x00" + inp + "\x00" + out).encode()).hexdigest()
        if key in seen:
            drops["exact_dup"] += 1
            continue
        seen.add(key)
        # Per-row context: expose the generator's ground-truth ``task_type`` (when
        # the row carries one) so task-aware checks can prefer metadata over text
        # detection. Existing checks ignore the extra key.
        rcfg = {**cfg, "task_type": r.get("task_type")} if isinstance(r, dict) else cfg
        dropped = False
        for c in drop_checks:
            if c.triggered(ins, inp, out, rcfg):
                drops[c.name] += 1
                dropped = True
                break
        if dropped:
            continue
        for c in flag_checks:
            if c.triggered(ins, inp, out, rcfg):
                flags[c.name] += 1
        kept.append(r)

    if do_near:
        sigs: list[set] = []
        deduped: list[dict] = []
        for r in kept:
            g = ngrams(fields(r)[0])
            if any(jaccard(g, g2) > near_j for g2 in sigs[-3000:]):
                drops["near_dup"] += 1
                continue
            sigs.append(g)
            deduped.append(r)
        kept = deduped

    lens = [len((fields(r)[2] or "").split()) for r in kept]
    cv = st.pstdev(lens) / max(st.mean(lens), 1) if lens else 0.0
    toks = [t for r in kept for t in norm(fields(r)[0]).split()]
    bigrams = list(zip(toks, toks[1:]))
    distinct2 = len(set(bigrams)) / max(len(bigrams), 1)
    prefixes = Counter(" ".join(norm(fields(r)[0]).split()[:5]) for r in kept)
    top_prefix = prefixes.most_common(1)[0][1] / max(len(kept), 1) if kept else 0.0

    # Translation composition of the clean corpus. Computed with the SAME detector
    # the task-aware purity checks use (praisonai_train.data.intent), so the share,
    # the by-direction counts, and the exempted count always reconcile with the
    # per-row exemptions. Denominator is the kept (post-dedup) content rows.
    intents = [translation_intent(fields(r)[0], r.get("task_type") if isinstance(r, dict) else None)
               for r in kept]
    by_dir = Counter(i["direction"] or "unknown" for i in intents if i["is_translation"])
    trans_n = sum(1 for i in intents if i["is_translation"])
    exempted = sum(1 for i in intents if i["expected_script"] == "english")
    translation = {
        "share": round(trans_n / max(len(kept), 1), 3),
        "by_direction": {"en_ta": by_dir["en_ta"], "ta_en": by_dir["ta_en"],
                         "unknown": by_dir["unknown"]},
        "exempted": exempted,
    }

    warnings = []
    if distinct2 < 0.5:
        warnings.append(f"low instruction diversity (distinct-2={distinct2:.2f} < 0.5)")
    if cv < 0.4:
        warnings.append(f"uniform output length (CV={cv:.2f} < 0.4)")
    if top_prefix > 0.01:
        warnings.append(f"template concentration (top prefix={top_prefix:.1%} > 1%)")

    return {
        "in": len(rows),
        "kept": kept,
        "kept_n": len(kept),
        "drops": dict(drops),
        "flags": dict(flags),
        "metrics": {
            "distinct_2": round(distinct2, 3),
            "length_cv": round(cv, 2),
            "top_prefix_share": round(top_prefix, 3),
            "translation": translation,
        },
        "warnings": warnings,
    }


def filter_rows(rows: Iterable[dict], cfg: dict | None = None) -> list[dict]:
    return score(rows, cfg)["kept"]
