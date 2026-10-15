"""Summary statistics, ranking and the "fastest" rule (stdlib only).

Rules (see README.md):
- frameworks are ranked by median;
- ratios are relative to the *best* framework, never to PraisonAI;
- the leader is "clear" only when its 95% bootstrap CI of the median does not
  overlap the runner-up's; otherwise first place is "tied (within noise)".
"""

from __future__ import annotations

import random
from statistics import median

RESAMPLES = 2000


def percentile(xs, q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100] (numpy's default method)."""
    s = sorted(xs)
    if not s:
        raise ValueError("percentile of empty sample")
    pos = (len(s) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def bootstrap_ci(xs, seed: int = 0, resamples: int = RESAMPLES, stat=median):
    """95% percentile-bootstrap CI of ``stat`` with a fixed seed."""
    xs = list(xs)
    if len(xs) < 2:
        v = stat(xs)
        return [v, v]
    rng = random.Random(seed)
    n = len(xs)
    boots = [stat([xs[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)]
    return [percentile(boots, 2.5), percentile(boots, 97.5)]


def summarize(xs, seed: int = 0) -> dict:
    xs = list(xs)
    q1, q3 = percentile(xs, 25), percentile(xs, 75)
    return {
        "median": median(xs), "p95": percentile(xs, 95), "q1": q1, "q3": q3,
        "iqr": q3 - q1, "min": min(xs), "max": max(xs), "n": len(xs),
        "ci95": bootstrap_ci(xs, seed),
    }


def diff_summary(xs, base, scale: float = 1.0, seed: int = 0) -> dict:
    """Summary of (median(xs) - median(base)) * scale with a paired-bootstrap CI."""
    xs, base = list(xs), list(base)
    rng = random.Random(seed)
    boots = []
    for _ in range(RESAMPLES):
        a = median([xs[rng.randrange(len(xs))] for _ in xs])
        b = median([base[rng.randrange(len(base))] for _ in base])
        boots.append((a - b) * scale)
    value = (median(xs) - median(base)) * scale
    return {"median": value, "n": len(xs), "ci95": [percentile(boots, 2.5), percentile(boots, 97.5)]}


def rank(summaries: dict, lower_is_better: bool = True) -> dict:
    """Rank frameworks by median.

    Returns ``{"order": [...], "leader": "clear"|"tied"|None}`` where each entry
    is ``{framework, rank, median, ci95, ratio_to_best}``.
    """
    items = sorted(summaries.items(), key=lambda kv: kv[1]["median"],
                   reverse=not lower_is_better)
    if not items:
        return {"order": [], "leader": None}
    best = items[0][1]["median"]
    order = []
    for i, (fw, s) in enumerate(items, start=1):
        # Competition ranking: equal medians share a rank ("1, 1, 3").
        place = order[-1]["rank"] if order and order[-1]["median"] == s["median"] else i
        if lower_is_better:
            ratio = s["median"] / best if best > 0 else None
        else:
            ratio = best / s["median"] if s["median"] > 0 else None
        order.append({"framework": fw, "rank": place, "median": s["median"],
                      "ci95": s.get("ci95"), "ratio_to_best": ratio})
    leader = None
    if len(order) >= 2:
        a, b = order[0]["ci95"], order[1]["ci95"]
        clear = a[1] < b[0] if lower_is_better else a[0] > b[1]
        leader = "clear" if clear else "tied"
    elif order:
        leader = "clear"
    return {"order": order, "leader": leader}
