"""Synthetic instruction-data generation via a teacher LLM.

Calls any OpenAI-compatible chat endpoint (Azure OpenAI or OpenAI) to synthesize
{instruction,input,output} rows from a registered (or inline) *recipe*. Built for
scale + safety: JSON mode for high parse yield, prompt-diversity axes so large
runs don't collapse, ``start_offset`` for disjoint parallel slices, dedup-on-write,
and a stop-file circuit-breaker (a billing guard can halt it instantly). Stdlib HTTP.
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


def _call(cfg: dict, spec: dict) -> dict | None:
    if cfg.get("azure"):
        url = (f"{cfg['endpoint'].rstrip('/')}/openai/deployments/{cfg['deployment']}"
               f"/chat/completions?api-version={cfg.get('api_version', '2024-10-21')}")
    else:
        url = f"{cfg['endpoint'].rstrip('/')}/chat/completions"
    body = {
        "messages": [{"role": "system", "content": spec["system"]},
                     {"role": "user", "content": spec["user"]}],
        "max_completion_tokens": cfg.get("max_completion_tokens", 2048),
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if cfg.get("azure"):
        headers["api-key"] = cfg["api_key"]
    else:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
        body["model"] = cfg["deployment"]
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    content = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
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
    return {"instruction": row["instruction"], "input": row.get("input", ""),
            "output": row["output"]}


def _norm_row(row: dict) -> str:
    return _norm_text(row.get("instruction") or "")


def generate_dataset(config: dict, on_row: Callable[[dict], None] | None = None) -> Iterator[dict]:
    """Yield unique synthetic rows.

    Required config: deployment, num_examples (+ endpoint/api_key or env).
    Optional: recipe (name|dict, default 'tamil'), concurrency, start_offset,
    dedup_from (rows or JSONL paths), stop_file, azure (bool), api_version,
    max_completion_tokens.
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

    recipe = resolve(cfg.get("recipe", "tamil"))

    seen: set[str] = set()
    for src in cfg.get("dedup_from") or []:
        rows = ([json.loads(l) for l in open(src) if l.strip()]
                if isinstance(src, str) and os.path.exists(src) else src)
        for r in rows:
            seen.add(_norm_row(r))

    stop_file = cfg.get("stop_file") or os.path.expanduser("~/.praisonai_train_stop")
    specs = recipe.prompts(cfg["num_examples"], start=cfg.get("start_offset", 0))
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
            if not row:
                continue
            key = _norm_row(row)
            if not key or key in seen:
                continue
            seen.add(key)
            if on_row:
                on_row(row)
            yield row
