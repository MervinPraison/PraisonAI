"""Recipe serve keeps bounded per-client and per-label state."""

import pytest

pytest.importorskip("starlette")
from praisonai.recipe.serve import MetricsCollector, RateLimiter


def test_rate_limiter_keeps_a_bounded_number_of_clients():
    limiter = RateLimiter(requests_per_minute=5)
    cap = limiter._requests.max_items
    for i in range(cap + 500):
        limiter.check(f"client-{i}")
    assert len(limiter._requests) <= cap


def test_rate_limiter_still_limits():
    limiter = RateLimiter(requests_per_minute=2)
    assert limiter.check("c")[0] and limiter.check("c")[0]
    allowed, retry = limiter.check("c")
    assert not allowed and retry >= 1


def test_metrics_memory_does_not_grow_per_request():
    m = MetricsCollector()
    for _ in range(5000):
        m.record_request("/health", "GET", 200, 0.01)
    (agg,) = m._request_durations.values()
    assert agg[0] == 5000 and len(agg) < 20
    text = m.get_prometheus_metrics()
    assert 'praisonai_http_request_duration_seconds_count{path="/health",method="GET"} 5000' in text
    assert 'le="0.01"} 5000' in text and 'le="0.005"} 0' in text


def test_metrics_label_sets_are_bounded():
    m = MetricsCollector()
    for i in range(3000):
        m.record_request(f"/x{i}", "GET", 404, 0.001)
    assert len(m._requests_total) <= 1000 and len(m._errors_total) <= 1000
