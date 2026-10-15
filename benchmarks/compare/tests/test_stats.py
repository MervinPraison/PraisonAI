import stats


def test_percentile_and_summary():
    xs = [5, 1, 4, 2, 3]
    s = stats.summarize(xs)
    assert (s["median"], s["min"], s["max"], s["n"]) == (3, 1, 5, 5)
    assert stats.percentile(xs, 25) == 2 and stats.percentile(xs, 95) == 4.8
    assert s["iqr"] == 2


def test_bootstrap_is_deterministic_under_seed():
    xs = [1.0, 2.0, 2.5, 3.0, 10.0, 2.2, 1.9]
    assert stats.bootstrap_ci(xs, seed=1) == stats.bootstrap_ci(xs, seed=1)
    lo, hi = stats.bootstrap_ci(xs, seed=1)
    assert lo <= stats.median(xs) <= hi


def test_clear_leader_only_without_overlap():
    a = stats.summarize([1.0, 1.1, 1.0, 1.05, 0.95] * 4)
    b = stats.summarize([2.0, 2.1, 2.0, 1.95, 2.05] * 4)
    assert stats.rank({"a": a, "b": b})["leader"] == "clear"
    c = stats.summarize([1.0, 1.9, 1.1, 2.1, 1.5] * 4)
    d = stats.summarize([1.1, 2.0, 1.2, 2.0, 1.6] * 4)
    assert stats.rank({"c": c, "d": d})["leader"] == "tied"


def test_ratios_relative_to_best_not_praisonai():
    r = stats.rank({"praisonai": {"median": 4.0, "ci95": [3.9, 4.1]},
                    "other": {"median": 2.0, "ci95": [1.9, 2.1]}})
    order = r["order"]
    assert [e["framework"] for e in order] == ["other", "praisonai"]
    assert order[0]["ratio_to_best"] == 1.0 and order[1]["ratio_to_best"] == 2.0


def test_equal_medians_share_rank_and_tie():
    r = stats.rank({fw: {"median": v, "ci95": [v, v]} for fw, v in
                    (("a", 19), ("b", 19), ("c", 24))})
    assert [e["rank"] for e in r["order"]] == [1, 1, 3]
    assert r["leader"] == "tied"


def test_diff_summary():
    s = stats.diff_summary([7.0, 7.1, 6.9], [4.0, 4.1, 3.9], scale=1 / 3)
    assert abs(s["median"] - 1.0) < 1e-9
    assert s["ci95"][0] <= s["median"] <= s["ci95"][1]
