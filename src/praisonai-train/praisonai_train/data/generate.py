"""Synthetic instruction-data generation via a teacher LLM.

Calls any OpenAI-compatible chat endpoint (Azure OpenAI or OpenAI) to synthesize
{instruction,input,output} rows from a registered (or inline) *recipe*. Built for
scale + safety: JSON mode for high parse yield, prompt-diversity axes so large
runs don't collapse, ``start_offset`` for disjoint parallel slices, dedup-on-write,
and a stop-file circuit-breaker (a billing guard can halt it): queued work is
cancelled at once, and already-running requests drain (bounded by the per-request
timeout) rather than starting new ones. Stdlib HTTP.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterator

from praisonai_train.data._util import norm as _norm_text
from praisonai_train.data.recipes import resolve


def resolve_cfg(config: dict) -> dict:
    """Fill endpoint/api_key/azure defaults from the environment and validate.

    Shared by generation and benchmarking so every call path resolves
    credentials and the Azure-vs-OpenAI flag the same way. Returns a *copy*;
    the input dict is never mutated. Raises ``ValueError`` if the endpoint,
    api_key or deployment cannot be determined.
    """
    cfg = dict(config)
    cfg.setdefault("endpoint", os.environ.get("AZURE_OPENAI_ENDPOINT",
                                              os.environ.get("OPENAI_BASE_URL", "")))
    cfg.setdefault("api_key", os.environ.get("AZURE_OPENAI_KEY",
                                             os.environ.get("OPENAI_API_KEY", "")))
    if "azure" not in cfg:
        cfg["azure"] = bool(os.environ.get("AZURE_OPENAI_ENDPOINT")) or "openai.azure.com" in cfg["endpoint"]
    if not (cfg["endpoint"] and cfg["api_key"] and cfg.get("deployment")):
        raise ValueError("endpoint, api_key and deployment are required")
    return cfg


def build_chat_request(cfg: dict, messages: list[dict],
                       json_mode: bool = True) -> "urllib.request.Request":
    """Build a urllib chat-completion ``Request`` for any OpenAI-compatible endpoint.

    Encapsulates the only vendor-specific bits — the Azure deployment URL +
    ``api-key`` header vs the plain OpenAI ``/chat/completions`` URL + bearer
    token + ``model`` field — so generation and benchmarking share one call
    path and both work against Azure OpenAI or any OpenAI-compatible server.
    """
    if cfg.get("azure"):
        url = (f"{cfg['endpoint'].rstrip('/')}/openai/deployments/{cfg['deployment']}"
               f"/chat/completions?api-version={cfg.get('api_version', '2024-10-21')}")
    else:
        url = f"{cfg['endpoint'].rstrip('/')}/chat/completions"
    body = {
        "messages": messages,
        "max_completion_tokens": cfg.get("max_completion_tokens", 2048),
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if cfg.get("azure"):
        headers["api-key"] = cfg["api_key"]
    else:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
        body["model"] = cfg["deployment"]
    return urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)


def _call(cfg: dict, spec: dict) -> dict | None:
    req = build_chat_request(cfg, [{"role": "system", "content": spec["system"]},
                                   {"role": "user", "content": spec["user"]}])
    content = None
    timeout = cfg.get("request_timeout", 120)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = json.load(resp)["choices"][0]["message"]["content"].strip()
            break
        except Exception:
            if attempt == 1:
                return None
    if not content:
        return None
    if content.startswith("```"):
        content = content.split("```")[1].removeprefix("json").strip()
    row = None
    try:
        row = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                row = json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    if not isinstance(row, dict) or not (row.get("instruction") and row.get("output")):
        return None
    out = {"instruction": row["instruction"], "input": row.get("input", ""),
           "output": row["output"]}
    # Per-row provenance: which model + category produced this row, so the dataset
    # is self-describing (downstream splits/QC key off metadata, not text). Additive
    # and backward-compatible — a key is added only when its value is available.
    if cfg.get("deployment"):
        out["model"] = cfg["deployment"]
    if spec.get("task_type"):
        out["task_type"] = spec["task_type"]
    if spec.get("topic"):
        out["topic"] = spec["topic"]
    return out


def azure_sponsorship_guard(
    subscription_id: str, quota_id: str = "Sponsored_2016-01-01"
) -> Callable[[], bool]:
    """Build a ``should_continue`` predicate that is True while an Azure subscription
    still reads as sponsored (``subscriptionPolicies.quotaId == quota_id``).

    Fail-OPEN: any transient error (CLI missing, network blip, unparseable output)
    returns True. This is a belt-and-suspenders guard against runaway spend once a
    sponsorship converts to pay-as-you-go — an external watchdog is the hard,
    fail-closed guard; this one must never halt a healthy run on a flaky check.
    """
    def _check() -> bool:
        import subprocess
        try:
            out = subprocess.run(
                ["az", "rest", "--method", "GET", "--url",
                 f"https://management.azure.com/subscriptions/{subscription_id}"
                 "?api-version=2022-12-01"],
                capture_output=True, text=True, timeout=10).stdout
            return json.loads(out)["subscriptionPolicies"]["quotaId"] == quota_id
        except Exception:
            return True

    return _check


def _resolve_guard(cfg: dict,
                   should_continue: Callable[[], bool] | None) -> Callable[[], bool] | None:
    """Pick the continuation guard: an explicit ``should_continue`` callback wins;
    otherwise fall back to the built-in Azure sponsorship check when a subscription
    id is supplied (``cfg['subscription_id']`` or env ``AZ_SUBSCRIPTION``). Returns
    ``None`` when neither is configured (no guard)."""
    if should_continue is not None:
        return should_continue
    sub = cfg.get("subscription_id") or os.environ.get("AZ_SUBSCRIPTION")
    if sub:
        return azure_sponsorship_guard(sub)
    return None


def _norm_row(row: dict) -> str:
    return _norm_text(row.get("instruction") or "")


def generate_dataset(
    config: dict,
    on_row: Callable[[dict], None] | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> Iterator[dict]:
    """Yield unique synthetic rows.

    Required config: deployment, num_examples (+ endpoint/api_key or env).
    Optional: recipe (name|dict, default 'tamil'), concurrency, start_offset,
    dedup_from (rows or JSONL paths), stop_file, azure (bool), api_version,
    max_completion_tokens, subscription_id, sponsor_check_rows.

    ``should_continue`` is an optional guard ``fn() -> bool`` re-checked every
    ``config['sponsor_check_rows']`` completed requests (default 5000). When it
    returns False the run halts cleanly — the stop-file is touched, pending futures
    are cancelled and the loop breaks — the same shutdown path as the stop-file
    circuit-breaker. If omitted but ``config['subscription_id']`` (or env
    ``AZ_SUBSCRIPTION``) is set, the built-in Azure sponsorship guard is used
    (see ``azure_sponsorship_guard``); with neither, generation is unguarded. The
    guard should fail-OPEN (return True on transient errors) — an external watchdog
    is the hard fail-closed guard; this in-loop check is belt-and-suspenders.

    ``progress_callback`` is an optional ``fn(done, total, kept)`` invoked as work
    completes so a CLI/monitor/notebook can show completion + remaining. ``done``
    counts teacher requests finished (monotonic, up to ``total`` = number of prompt
    specs); ``kept`` counts unique rows emitted so far — it is reported *after* the
    row is yielded, so ``kept`` never runs ahead of the rows the consumer has
    received. It fires once up-front with ``(0, total, 0)`` and again after each
    completed request. Default ``None`` keeps the original behaviour (no callback).
    Keep it cheap — it runs on the hot path; throttle any printing inside the
    callback.
    """
    cfg = resolve_cfg(config)

    recipe = resolve(cfg.get("recipe", "tamil"))

    seen: set[str] = set()
    for src in cfg.get("dedup_from") or []:
        rows = ([json.loads(l) for l in open(src) if l.strip()]
                if isinstance(src, str) and os.path.exists(src) else src)
        for r in rows:
            seen.add(_norm_row(r))

    stop_file = cfg.get("stop_file") or os.path.expanduser("~/.praisonai_train_stop")
    guard = _resolve_guard(cfg, should_continue)
    # Guard against a misconfigured interval: 0 would divide-by-zero and a
    # negative value would silently never poll (disabling the safety check).
    _interval = cfg.get("sponsor_check_rows")
    check_every = max(1, int(_interval)) if _interval is not None else 5000
    specs = recipe.prompts(cfg["num_examples"], start=cfg.get("start_offset", 0))
    total = len(specs)
    done = kept = 0
    if progress_callback:
        progress_callback(done, total, kept)
    with ThreadPoolExecutor(max_workers=cfg.get("concurrency", 32)) as pool:
        futures = {pool.submit(_call, cfg, s): s for s in specs}
        for fut in as_completed(futures):
            if os.path.exists(stop_file):
                pool.shutdown(wait=False, cancel_futures=True)
                break
            try:
                row = fut.result()
            except Exception:
                row = None
            done += 1
            # Emit the just-completed row first so a paid, already-finished request
            # is never dropped by the guard/shutdown that may follow this iteration.
            emit = False
            if row:
                key = _norm_row(row)
                if key and key not in seen:
                    seen.add(key)
                    kept += 1
                    emit = True
                    if on_row:
                        on_row(row)
            if emit:
                yield row
            if progress_callback:
                progress_callback(done, total, kept)
            # In-loop continuation guard (billing/sponsorship self-check): every
            # ``check_every`` completions, if the predicate says stop, halt cleanly
            # via the same shutdown path as the stop-file breaker.
            if guard is not None and done % check_every == 0 and not guard():
                try:
                    open(stop_file, "w").close()
                except Exception:
                    pass
                pool.shutdown(wait=False, cancel_futures=True)
                break
