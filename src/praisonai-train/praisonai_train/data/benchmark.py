"""Generation-speed benchmark for OpenAI-compatible LLM deployments.

Send ``n`` identical chat requests to each target at a fixed ``concurrency`` and
report throughput (rows/min, completion-tokens/sec) and latency (avg / p50 / p95),
plus success count and average output tokens — then rank the targets by throughput.

Designed as a first-class, protocol-driven SDK component that mirrors the data
generator:

* it reuses the generator's own HTTP call path (:func:`build_chat_request` and
  :func:`resolve_cfg` in ``praisonai_train.data.generate``) so a benchmark hits
  endpoints exactly the way real generation does — no duplicated HTTP code, and
  it works against Azure OpenAI *and* any OpenAI-compatible server for free;
* the prompt defaults to a registered :class:`~praisonai_train.data.protocols.Recipe`
  (the same recipes generation uses), so "identical requests" stay representative
  of the workload you actually run; and
* everything is plain data in / dataclasses out, so it is equally usable from the
  SDK (:func:`benchmark_deployments`) and the ``praisonai-train benchmark`` CLI.

Stdlib HTTP only. Network is confined to :func:`_timed_call` / :func:`_measure_target`
so tests can stub it and assert the pure aggregation in :func:`aggregate`.
"""
from __future__ import annotations

import json
import statistics as _st
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Callable, Sequence

from praisonai_train.data.generate import build_chat_request, resolve_cfg
from praisonai_train.data.recipes import resolve as _resolve_recipe

DEFAULT_N = 24
DEFAULT_CONCURRENCY = 8
DEFAULT_MAX_TOKENS = 2048
DEFAULT_API_VERSION = "2024-10-21"
DEFAULT_REQUEST_TIMEOUT = 180


@dataclass
class BenchResult:
    """One deployment's measured speed. ``rows_per_min`` is the ranking key."""

    deployment: str
    n: int
    ok: int
    wall_s: float
    rows_per_min: float
    compl_tok_per_s: float
    avg_latency_s: float
    p50_s: float
    p95_s: float
    avg_out_tok: float

    def as_dict(self) -> dict:
        return asdict(self)


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Nearest-rank percentile on an already-sorted list (matches the scratch
    benchmark: index ``min(int(len*q), len-1)``)."""
    if not sorted_vals:
        return 0.0
    idx = min(int(len(sorted_vals) * q), len(sorted_vals) - 1)
    return sorted_vals[idx]


def aggregate(deployment: str, n: int, latencies: Sequence[float], ctoks: int,
              ok: int, wall_s: float) -> BenchResult:
    """Turn raw measurements into a :class:`BenchResult` (pure, no I/O).

    ``latencies`` is one wall-time-per-request (seconds), ``ctoks`` the summed
    ``usage.completion_tokens`` over successful calls, ``ok`` the success count
    and ``wall_s`` the elapsed wall-clock of the whole batch. Throughput is
    per wall-clock second so it reflects real concurrency; latency percentiles
    are over the per-request times.
    """
    lat = sorted(latencies)
    wall = wall_s if wall_s > 0 else 1e-9
    return BenchResult(
        deployment=deployment,
        n=n,
        ok=ok,
        wall_s=round(wall_s, 2),
        rows_per_min=round(ok / wall * 60, 1),
        compl_tok_per_s=round(ctoks / wall, 1),
        avg_latency_s=round(_st.mean(lat), 2) if lat else 0.0,
        p50_s=round(_percentile(lat, 0.50), 2),
        p95_s=round(_percentile(lat, 0.95), 2),
        avg_out_tok=round(ctoks / max(ok, 1), 1),
    )


def _timed_call(cfg: dict, messages: list[dict], timeout: int) -> tuple[float, int, bool]:
    """One timed chat request via the shared call path.

    Returns ``(latency_s, completion_tokens, ok)``. Never raises: a failed call
    still contributes its latency but counts as ``ok=False`` with 0 tokens, so
    error rates show up as a lower success count rather than crashing the run.
    This is the single network seam — tests monkeypatch it.
    """
    req = build_chat_request(cfg, messages)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        dt = time.perf_counter() - t0
        ctok = int(data.get("usage", {}).get("completion_tokens", 0) or 0)
        ok = bool(data.get("choices", [{}])[0].get("message", {}).get("content"))
        return dt, ctok, ok
    except Exception:
        return time.perf_counter() - t0, 0, False


def _measure_target(cfg: dict, messages: list[dict], n: int, concurrency: int,
                    timeout: int) -> tuple[list[float], int, int, float]:
    """Fire ``n`` identical requests at ``concurrency`` and collect raw numbers.

    Returns ``(latencies, total_completion_tokens, ok_count, wall_s)``. Tests
    monkeypatch this to inject deterministic timings without touching the wall
    clock or the thread pool.
    """
    latencies: list[float] = []
    ctoks = 0
    ok = 0
    wall0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futs = [pool.submit(_timed_call, cfg, messages, timeout) for _ in range(n)]
        for fut in as_completed(futs):
            dt, ct, is_ok = fut.result()
            latencies.append(dt)
            ctoks += ct
            if is_ok:
                ok += 1
    return latencies, ctoks, ok, time.perf_counter() - wall0


def _messages_for(prompt, recipe) -> list[dict]:
    """Resolve the fixed system+user messages sent on every request.

    ``prompt`` may be a ``{"system","user"}`` dict, a plain string (used as the
    user turn), or ``None`` — in which case the first spec of the registered
    ``recipe`` is reused, so the benchmark exercises the same prompt shape as a
    real generation run.
    """
    if isinstance(prompt, dict):
        spec = {"system": prompt.get("system", ""), "user": prompt["user"]}
    elif isinstance(prompt, str):
        spec = {"system": "", "user": prompt}
    else:
        spec = _resolve_recipe(recipe).prompts(1)[0]
    return [{"role": "system", "content": spec["system"]},
            {"role": "user", "content": spec["user"]}]


def benchmark_deployments(
    targets: Sequence,
    n: int = DEFAULT_N,
    concurrency: int = DEFAULT_CONCURRENCY,
    *,
    base: dict | None = None,
    prompt=None,
    recipe: str = "tamil",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    api_version: str = DEFAULT_API_VERSION,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    on_result: Callable[[BenchResult], None] | None = None,
) -> list[BenchResult]:
    """Benchmark generation speed across one or more deployments; ranked fastest first.

    Args:
        targets: deployment names (``str``) and/or per-target config dicts. A
            dict may carry ``deployment`` plus any override (``endpoint``,
            ``api_key``, ``azure``, ``api_version``, ``max_completion_tokens``)
            for benchmarking across endpoints in one call.
        n: identical requests per target.
        concurrency: in-flight requests per target.
        base: shared config merged under every target (e.g. ``endpoint``,
            ``api_key``, ``azure``). Endpoint/key/azure fall back to the
            ``AZURE_OPENAI_*`` / ``OPENAI_*`` environment, exactly like
            :func:`~praisonai_train.data.generate.generate_dataset`.
        prompt: fixed prompt for every request — a ``{"system","user"}`` dict, a
            user string, or ``None`` to reuse the ``recipe``'s first prompt.
        recipe: registered recipe name used when ``prompt`` is ``None``.
        max_tokens: ``max_completion_tokens`` cap per request.
        api_version: Azure OpenAI api-version (ignored for plain OpenAI).
        request_timeout: per-request timeout in seconds.
        on_result: optional callback invoked with each :class:`BenchResult` as
            soon as that target finishes (for live CLI/notebook output).

    Returns:
        ``list[BenchResult]`` sorted by ``rows_per_min`` descending.
    """
    messages = _messages_for(prompt, recipe)
    base = dict(base or {})
    base.setdefault("api_version", api_version)
    base.setdefault("max_completion_tokens", max_tokens)

    results: list[BenchResult] = []
    for target in targets:
        merged = dict(base)
        if isinstance(target, dict):
            merged.update(target)
        else:
            merged["deployment"] = target
        cfg = resolve_cfg(merged)
        name = cfg["deployment"]
        latencies, ctoks, ok, wall = _measure_target(
            cfg, messages, n, concurrency, request_timeout)
        res = aggregate(name, n, latencies, ctoks, ok, wall)
        results.append(res)
        if on_result:
            on_result(res)

    results.sort(key=lambda r: r.rows_per_min, reverse=True)
    return results
