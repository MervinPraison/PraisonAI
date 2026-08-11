"""Tests for the speed-benchmark SDK component.

The network is fully stubbed: aggregation is tested as a pure function, the
target-measurement seam (``_measure_target``) is monkeypatched to inject
deterministic timings for ranking/success tests, and one test monkeypatches the
low-level ``_timed_call`` to prove the real threaded path counts successes and
failures correctly. Nothing here touches a socket.
"""
import io
import json
import math

import pytest

from praisonai_train.data import benchmark_deployments, BenchResult
from praisonai_train.data import benchmark as bm


def _cfg():
    return {"endpoint": "http://x", "api_key": "k", "azure": False}


# --------------------------------------------------------------------------- #
# aggregate(): pure math on a known set of fake timings                         #
# --------------------------------------------------------------------------- #

def test_aggregate_throughput_and_percentiles():
    # 10 requests, all ok, latencies 1..10s, 100 tokens each (1000 total),
    # batch wall clock 20s.
    latencies = [float(i) for i in range(1, 11)]
    r = bm.aggregate("d", n=10, latencies=latencies, ctoks=1000, ok=10, wall_s=20.0)

    assert r.rows_per_min == pytest.approx(10 / 20 * 60)   # 30 rows/min
    assert r.compl_tok_per_s == pytest.approx(1000 / 20)   # 50 tok/s
    assert r.avg_latency_s == pytest.approx(5.5)           # mean(1..10)
    assert r.p50_s == pytest.approx(6.0)                   # index int(10*0.5)=5 -> 6.0
    assert r.p95_s == pytest.approx(10.0)                  # index min(9,9) -> 10.0
    assert r.avg_out_tok == pytest.approx(100.0)           # 1000 / 10
    assert r.ok == 10 and r.n == 10


def test_aggregate_counts_only_successful_tokens_for_avg():
    # 4 requests, 2 ok; 400 tokens over 2 successes -> 200 avg out tokens.
    r = bm.aggregate("d", n=4, latencies=[1.0, 2.0, 3.0, 4.0], ctoks=400, ok=2, wall_s=8.0)
    assert r.avg_out_tok == pytest.approx(200.0)
    assert r.rows_per_min == pytest.approx(2 / 8 * 60)     # only successes count
    assert r.ok == 2


def test_aggregate_all_failed_is_safe():
    r = bm.aggregate("d", n=3, latencies=[1.0, 1.0, 1.0], ctoks=0, ok=0, wall_s=3.0)
    assert r.ok == 0
    assert r.rows_per_min == 0.0
    assert r.compl_tok_per_s == 0.0
    assert r.avg_out_tok == 0.0                            # max(ok,1) guard, no ZeroDivision


def test_aggregate_zero_wall_does_not_divide_by_zero():
    r = bm.aggregate("d", n=1, latencies=[0.0], ctoks=10, ok=1, wall_s=0.0)
    assert math.isfinite(r.rows_per_min) and math.isfinite(r.compl_tok_per_s)


# --------------------------------------------------------------------------- #
# benchmark_deployments(): ranking + success handling with stubbed measurement  #
# --------------------------------------------------------------------------- #

def _fake_measure_factory(table):
    """Return a _measure_target stub driven by a {deployment: (lat, ctoks, ok, wall)} table."""
    def _fake(cfg, messages, n, concurrency, timeout, json_mode=True):
        return table[cfg["deployment"]]
    return _fake


def test_ranks_descending_by_throughput(monkeypatch):
    # slow: 5 ok / 10s = 30 rows/min; fast: 10 ok / 10s = 60 rows/min.
    table = {
        "slow": ([1.0] * 5, 500, 5, 10.0),
        "fast": ([1.0] * 10, 1000, 10, 10.0),
        "mid":  ([1.0] * 8, 800, 8, 10.0),
    }
    monkeypatch.setattr(bm, "_measure_target", _fake_measure_factory(table))

    results = benchmark_deployments(["slow", "fast", "mid"], n=10, concurrency=4,
                                    base=_cfg())

    assert [r.deployment for r in results] == ["fast", "mid", "slow"]
    assert all(isinstance(r, BenchResult) for r in results)
    # monotonically non-increasing throughput
    tputs = [r.rows_per_min for r in results]
    assert tputs == sorted(tputs, reverse=True)


def test_success_count_reflects_failures(monkeypatch):
    # 10 requests, only 3 succeeded (7 failed): ok=3, tokens only from the 3.
    table = {"d": ([2.0] * 10, 300, 3, 20.0)}
    monkeypatch.setattr(bm, "_measure_target", _fake_measure_factory(table))

    (r,) = benchmark_deployments(["d"], n=10, concurrency=5, base=_cfg())

    assert r.ok == 3 and r.n == 10
    assert r.rows_per_min == pytest.approx(3 / 20 * 60)
    assert r.avg_out_tok == pytest.approx(100.0)           # 300 / 3


def test_on_result_callback_fires_per_target(monkeypatch):
    table = {"a": ([1.0], 100, 1, 1.0), "b": ([1.0], 100, 1, 1.0)}
    monkeypatch.setattr(bm, "_measure_target", _fake_measure_factory(table))
    seen = []
    benchmark_deployments(["a", "b"], n=1, concurrency=1, base=_cfg(),
                          on_result=seen.append)
    assert {r.deployment for r in seen} == {"a", "b"}


# --------------------------------------------------------------------------- #
# Real threaded path (only the HTTP seam stubbed): success/failure counting      #
# --------------------------------------------------------------------------- #

def test_real_thread_pool_counts_success_and_failure(monkeypatch):
    # Every odd call "fails" (ok=False, 0 tokens); even calls succeed with 50 tok.
    state = {"i": 0}

    def _fake_timed(cfg, messages, timeout, json_mode=True):
        i = state["i"]
        state["i"] += 1
        if i % 2 == 0:
            return 0.01, 50, True
        return 0.01, 0, False

    monkeypatch.setattr(bm, "_timed_call", _fake_timed)

    (r,) = benchmark_deployments(["d"], n=10, concurrency=4, base=_cfg())

    assert r.n == 10
    assert r.ok == 5                                       # half succeeded
    assert r.avg_out_tok == pytest.approx(50.0)            # 250 tokens / 5 ok


def test_per_target_endpoint_override(monkeypatch):
    # A dict target may override the endpoint; benchmark must resolve per-target.
    captured = {}

    def _fake(cfg, messages, n, concurrency, timeout, json_mode=True):
        captured[cfg["deployment"]] = cfg["endpoint"]
        return ([1.0], 100, 1, 1.0)

    monkeypatch.setattr(bm, "_measure_target", _fake)
    benchmark_deployments(
        [{"deployment": "x", "endpoint": "http://a", "api_key": "k", "azure": False},
         {"deployment": "y", "endpoint": "http://b", "api_key": "k", "azure": False}],
        n=1, concurrency=1)
    assert captured == {"x": "http://a", "y": "http://b"}


def test_default_prompt_uses_recipe():
    msgs = bm._messages_for(None, "tamil")
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert msgs[0]["content"] and msgs[1]["content"]       # recipe filled both turns


def test_explicit_prompt_forms():
    d = bm._messages_for({"system": "s", "user": "u"}, "tamil")
    assert d[0]["content"] == "s" and d[1]["content"] == "u"
    s = bm._messages_for("just user", "tamil")
    assert s[0]["content"] == "" and s[1]["content"] == "just user"


# --------------------------------------------------------------------------- #
# Input validation + provider-compat edge cases (reviewer feedback)             #
# --------------------------------------------------------------------------- #

def test_malformed_prompt_dict_raises_valueerror():
    # A dict without 'user' must be a clear config error, not a KeyError mid-run.
    with pytest.raises(ValueError):
        bm._messages_for({"system": "You are helpful"}, "tamil")
    with pytest.raises(ValueError):
        bm._messages_for({"user": ""}, "tamil")


def test_invalid_counts_raise_valueerror():
    with pytest.raises(ValueError):
        benchmark_deployments(["d"], n=0, concurrency=8, base=_cfg())
    with pytest.raises(ValueError):
        benchmark_deployments(["d"], n=8, concurrency=0, base=_cfg())


def test_failed_response_does_not_add_tokens(monkeypatch):
    # A completion that reports tokens but has empty content is ok=False AND
    # contributes 0 tokens, so token throughput stays consistent with success.
    payload = {"usage": {"completion_tokens": 99},
               "choices": [{"message": {"content": ""}}]}

    def _fake_urlopen(req, timeout=None):
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(bm.urllib.request, "urlopen", _fake_urlopen)
    dt, ctok, ok = bm._timed_call({**_cfg(), "deployment": "d"}, [], 5)
    assert ok is False and ctok == 0


def test_json_mode_flag_reaches_request_builder(monkeypatch):
    # The json_mode flag must be threaded through to build_chat_request so an
    # endpoint without JSON mode can be benchmarked (--no-json-mode).
    captured = {}

    def _fake_build(cfg, messages, json_mode=True):
        captured["json_mode"] = json_mode
        return object()

    def _fake_urlopen(req, timeout=None):
        raise OSError("no network in test")

    monkeypatch.setattr(bm, "build_chat_request", _fake_build)
    monkeypatch.setattr(bm.urllib.request, "urlopen", _fake_urlopen)
    bm._timed_call({**_cfg(), "deployment": "d"}, [], 5, json_mode=False)
    assert captured["json_mode"] is False
