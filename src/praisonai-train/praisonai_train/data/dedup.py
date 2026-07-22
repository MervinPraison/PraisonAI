"""Scalable near-duplicate detection for large synthetic corpora (stdlib only).

Two engines share one ``near_dedup`` interface — the choice is YAML-tunable via
``near_dup_method`` so existing behaviour is unchanged unless opted in:

- ``"sliding"`` (default, unchanged): char-4gram Jaccard of each instruction vs
  the last ``near_dup_window`` (3000) kept rows. Simple and exact, but O(n·window)
  and structurally *blind* to near-duplicates more than ``window`` rows apart.

- ``"minhash"``: MinHash + LSH banding. Each instruction is reduced to a fixed
  ``num_perm``-length MinHash signature (an unbiased estimator of the shingle-set
  Jaccard), and candidates are found by banded hashing — sub-linear lookup with
  **no fixed comparison window**, so it catches near-dups anywhere in the corpus,
  and one shared index can dedup *across many batch files* (``global_dedup``).

Research backing (Self-Instruct's ROUGE-L<0.7 novelty filter is approximated by
char-4gram Jaccard≥0.7; MinHash+LSH is the standard scalable near-dup method for
LLM training corpora — Lee et al. 2022 "Deduplicating Training Data Makes LMs
Better", and the CCNet/Gopher/RefinedWeb pipelines). The shingles here are the
same normalized char-4grams the ``sliding`` engine uses, so the ``near_dup_jaccard``
threshold keeps identical semantics across both engines.

Pure stdlib: no ``datasketch``/``numpy`` dependency. ``datasketch`` could back the
same interface for very large runs, but is intentionally *not* a hard dep.
"""
from __future__ import annotations

import hashlib
import random
from typing import Iterable, Iterator

from praisonai_train.data._util import fields, jaccard, ngrams, norm

# Signatures live in [0, 2**32), so a band value packs to 4 bytes.
_MASK32 = (1 << 32) - 1
# A Mersenne prime > 2**32 for the universal-hash permutation family h(x)=(a*x+b) % p.
_MERSENNE_61 = (1 << 61) - 1


def _shingle_hash(shingle: str) -> int:
    """Stable 32-bit hash of a shingle (blake2b, so it's independent of
    PYTHONHASHSEED and reproducible across processes/persisted indexes)."""
    return int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=4).digest(), "big")


def optimal_bands(num_perm: int, threshold: float) -> tuple[int, int]:
    """Pick (bands b, rows-per-band r) with b·r == num_perm whose LSH S-curve
    crossover (1/b)**(1/r) sits closest to ``threshold``. Standard MinHash-LSH
    tuning: more bands → higher recall, fewer → higher precision."""
    best, best_err = (num_perm, 1), float("inf")
    for b in range(1, num_perm + 1):
        if num_perm % b:
            continue
        r = num_perm // b
        crossover = (1.0 / b) ** (1.0 / r)
        err = abs(crossover - threshold)
        if err < best_err:
            best, best_err = (b, r), err
    return best


class MinHasher:
    """Deterministic MinHash: char-n-gram shingles → ``num_perm`` minima.

    Uses one universal-hash permutation family seeded by ``seed`` so signatures
    are reproducible run-to-run (needed for tests and for a persistable index).
    """

    def __init__(self, num_perm: int = 128, seed: int = 1, n: int = 4) -> None:
        if num_perm < 1:
            raise ValueError(f"minhash_perm must be >= 1, got {num_perm}")
        if n < 1:
            raise ValueError(f"ngram_n must be >= 1, got {n}")
        self.num_perm = num_perm
        self.n = n
        rnd = random.Random(seed)
        self._ab = [(rnd.randrange(1, _MERSENNE_61), rnd.randrange(0, _MERSENNE_61))
                    for _ in range(num_perm)]

    def signature(self, text: str) -> tuple[int, ...]:
        shingles = ngrams(text, self.n)  # normalized char n-grams (shared with sliding)
        if not shingles:
            return (0,) * self.num_perm
        base = [_shingle_hash(s) for s in shingles]
        return tuple(min(((a * h + b) % _MERSENNE_61) & _MASK32 for h in base)
                     for a, b in self._ab)


def signature_similarity(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    """Estimated Jaccard = fraction of agreeing MinHash positions.

    Empty signatures carry no information, so they are treated as *non*-similar
    (0.0) rather than identical — otherwise a degenerate ``num_perm``/``ngram_n``
    would make every row collapse into the first one.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


class MinHashLSH:
    """A MinHash + LSH near-duplicate index.

    ``add_if_new(text)`` returns True and indexes ``text`` when it is *not* a
    near-duplicate (estimated Jaccard ≥ ``threshold``) of anything already in the
    index; otherwise returns False and leaves the index unchanged. Banded hashing
    keeps candidate lookup sub-linear, so this scales to large corpora and, unlike
    the sliding window, has no bounded look-back — the whole corpus is the index.
    """

    def __init__(self, threshold: float = 0.7, num_perm: int = 128,
                 n: int = 4, seed: int = 1) -> None:
        self.threshold = threshold
        self.hasher = MinHasher(num_perm, seed, n)
        self.bands, self.rows = optimal_bands(num_perm, threshold)
        self._buckets: list[dict[bytes, list[int]]] = [dict() for _ in range(self.bands)]
        self._sigs: dict[int, tuple[int, ...]] = {}
        self._next = 0

    def __len__(self) -> int:
        return len(self._sigs)

    def _band_keys(self, sig: tuple[int, ...]) -> Iterator[tuple[int, bytes]]:
        for i in range(self.bands):
            band = sig[i * self.rows:(i + 1) * self.rows]
            key = hashlib.blake2b(b"".join(v.to_bytes(4, "big") for v in band),
                                  digest_size=8).digest()
            yield i, key

    def query(self, text: str) -> tuple[tuple[int, ...], set[int]]:
        """Return (signature, candidate keys sharing ≥1 band with ``text``)."""
        sig = self.hasher.signature(text)
        cands: set[int] = set()
        for i, key in self._band_keys(sig):
            cands.update(self._buckets[i].get(key, ()))
        return sig, cands

    def _insert(self, sig: tuple[int, ...]) -> int:
        key = self._next
        self._next += 1
        self._sigs[key] = sig
        for i, band_key in self._band_keys(sig):
            self._buckets[i].setdefault(band_key, []).append(key)
        return key

    def is_near_dup(self, text: str) -> bool:
        sig, cands = self.query(text)
        return any(signature_similarity(sig, self._sigs[k]) >= self.threshold for k in cands)

    def add_if_new(self, text: str) -> bool:
        """True (and index it) if ``text`` is new; False if it's a near-dup."""
        sig, cands = self.query(text)
        if any(signature_similarity(sig, self._sigs[k]) >= self.threshold for k in cands):
            return False
        self._insert(sig)
        return True


def _make_lsh(cfg: dict) -> "MinHashLSH":
    """Build a MinHashLSH from the shared cfg keys (one place — DRY)."""
    return MinHashLSH(
        threshold=cfg.get("near_dup_jaccard", 0.7),
        num_perm=cfg.get("minhash_perm", 128),
        n=cfg.get("ngram_n", 4),
        seed=cfg.get("minhash_seed", 1),
    )


def _sliding_dedup(rows: list[dict], threshold: float, window: int) -> tuple[list[dict], int]:
    # A non-positive window has no meaningful "last N" semantics; treat it as an
    # unbounded look-back (compare against every kept row) rather than silently
    # letting ``sigs[-0:]`` mean the whole list only when window == 0.
    unbounded = window <= 0
    sigs: list[set] = []
    kept: list[dict] = []
    dropped = 0
    for r in rows:
        g = ngrams(fields(r)[0])
        recent = sigs if unbounded else sigs[-window:]
        if any(jaccard(g, g2) > threshold for g2 in recent):
            dropped += 1
            continue
        sigs.append(g)
        kept.append(r)
    return kept, dropped


def _minhash_dedup(rows: list[dict], cfg: dict, index: "MinHashLSH | None") -> tuple[list[dict], int]:
    # ``index is not None`` (not ``index or ...``): a freshly-created shared index
    # is empty and therefore falsy, so ``or`` would discard it and break the
    # documented cross-batch dedup on the very first call.
    lsh = index if index is not None else _make_lsh(cfg)
    kept: list[dict] = []
    dropped = 0
    for r in rows:
        if lsh.add_if_new(fields(r)[0]):
            kept.append(r)
        else:
            dropped += 1
    return kept, dropped


def near_dedup(rows: Iterable[dict], cfg: dict | None = None,
               index: "MinHashLSH | None" = None) -> tuple[list[dict], int]:
    """Drop near-duplicate rows (by instruction). Returns (kept, n_dropped).

    ``near_dup_method``: ``"sliding"`` (default) or ``"minhash"``. When an
    ``index`` is supplied (minhash only) it is reused/mutated, enabling dedup
    across successive batches against one shared index.
    """
    cfg = dict(cfg or {})
    rows = list(rows)
    threshold = cfg.get("near_dup_jaccard", 0.7)
    method = cfg.get("near_dup_method", "sliding")
    if method == "minhash":
        return _minhash_dedup(rows, cfg, index)
    if method != "sliding":
        raise ValueError(f"unknown near_dup_method {method!r}; use 'sliding' or 'minhash'")
    return _sliding_dedup(rows, threshold, cfg.get("near_dup_window", 3000))


def global_dedup(sources: Iterable, cfg: dict | None = None) -> Iterator[dict]:
    """Deduplicate rows ACROSS many batch files with one shared index.

    ``sources`` is an iterable of JSONL paths (str) or in-memory row lists; rows
    are streamed in source order and each unique one is yielded once. Exact dups
    (sha1 of the normalized instruction+input+output) are removed first, then
    near-dups via MinHash+LSH (``near_dup_method`` defaults to ``"minhash"`` here,
    since a shared index is the whole point; set ``near_dup: false`` to do exact
    only). This is what the per-file ``score()`` cannot do — its exact/near state
    is rebuilt per call, so cross-file duplicates survive.
    """
    import json
    import os

    cfg = dict(cfg or {})
    method = cfg.setdefault("near_dup_method", "minhash")
    if method not in ("minhash", "sliding"):
        raise ValueError(f"unknown near_dup_method {method!r}; use 'sliding' or 'minhash'")
    do_near = cfg.get("near_dup", True)
    # Honour the requested engine. ``minhash`` uses one shared LSH index across
    # every file (the whole point of global dedup); ``sliding`` keeps a growing
    # shingle list so it still spans files, but with the classic window semantics.
    use_minhash = do_near and method == "minhash"
    lsh = _make_lsh(cfg) if use_minhash else None
    slide_sigs: list[set] = []
    slide_window = cfg.get("near_dup_window", 3000)
    slide_thresh = cfg.get("near_dup_jaccard", 0.7)
    seen_exact: set[str] = set()

    for src in sources:
        if isinstance(src, str):
            if not os.path.exists(src):
                raise FileNotFoundError(f"dedup source not found: {src}")
            with open(src, encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
        else:
            rows = src
        for r in rows:
            ins, inp, out = fields(r)
            key = hashlib.sha1(norm(ins + "\x00" + inp + "\x00" + out).encode()).hexdigest()
            if key in seen_exact:
                continue
            seen_exact.add(key)
            if lsh is not None:
                if not lsh.add_if_new(ins):
                    continue
            elif do_near:  # sliding near-dup across files
                g = ngrams(ins)
                recent = slide_sigs if slide_window <= 0 else slide_sigs[-slide_window:]
                if any(jaccard(g, g2) > slide_thresh for g2 in recent):
                    continue
                slide_sigs.append(g)
            yield r
