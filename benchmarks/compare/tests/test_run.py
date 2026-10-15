import run


def test_failed_framework_is_not_ranked_or_published():
    sums = {fw: {"median": v, "ci95": [v, v]} for fw, v in (("a", 1.0), ("b", 2.0), ("c", 3.0))}
    m = run.metric("first_response_ms", sums, {"a": "contract failed"})
    assert "a" not in m["summary"]
    assert [e["framework"] for e in m["ranking"]["order"]] == ["b", "c"]


def test_pinned_cpus_are_allowed_cpus():
    cpus = run.pinned_cpus()
    assert cpus == [] or (len(cpus) == 2 and set(cpus) <= run.os.sched_getaffinity(0))
