"""``praisonai-train benchmark`` — compare generation speed across deployments.

YAML-driven (``--config bench.yaml``) to match ``generate`` / ``validate`` /
``llm``, with the common knobs also exposed as flags. Prints a ranked table
(fastest first) and, optionally, writes machine-readable JSON.

    praisonai-train benchmark --config bench.yaml
    praisonai-train benchmark -d gpt-4o -d gpt-4o-mini --n 24 --concurrency 8 -o bench.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer

from praisonai_train.cli.commands.data import _load_cfg
from praisonai_train.cli.commands.train import app

_TABLE_HEADERS = ["deployment", "rows/min", "tok/s", "avg_lat", "p50", "p95", "out_tok", "ok"]


def _row_cells(r) -> list:
    return [r.deployment, f"{r.rows_per_min:.0f}", f"{r.compl_tok_per_s:.0f}",
            f"{r.avg_latency_s:.1f}", f"{r.p50_s:.1f}", f"{r.p95_s:.1f}",
            f"{r.avg_out_tok:.0f}", f"{r.ok}/{r.n}"]


@app.command("benchmark")
def benchmark(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="YAML config"),
    deployment: Optional[List[str]] = typer.Option(
        None, "--deployment", "-d", help="Deployment/model to benchmark (repeatable)"),
    n: Optional[int] = typer.Option(None, "--n", "-n", help="Requests per deployment (default 24)"),
    concurrency: Optional[int] = typer.Option(
        None, "--concurrency", help="In-flight requests per deployment (default 8)"),
    api_version: Optional[str] = typer.Option(None, "--api-version", help="Azure OpenAI api-version"),
    max_tokens: Optional[int] = typer.Option(None, "--max-tokens", help="max_completion_tokens per request"),
    recipe: Optional[str] = typer.Option(None, "--recipe", "-r", help="Recipe for the default prompt"),
    json_mode: Optional[bool] = typer.Option(
        None, "--json-mode/--no-json-mode",
        help="Send response_format json_object (disable for endpoints without JSON mode)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Write results JSON here"),
):
    """Measure and rank generation speed across LLM deployments.

    Sends N identical requests to each deployment at a fixed concurrency and
    reports throughput (rows/min, completion-tokens/sec), latency (avg/p50/p95),
    success count and average output tokens. Endpoint/api-key are read from the
    config or the AZURE_OPENAI_* / OPENAI_* environment.

    Example: praisonai-train benchmark --config bench.yaml
             praisonai-train benchmark -d gpt-4o -d gpt-4o-mini --n 24 -o bench.json
    """
    from praisonai_train.data import benchmark_deployments
    from praisonai_train.data.benchmark import (
        DEFAULT_API_VERSION, DEFAULT_CONCURRENCY, DEFAULT_MAX_TOKENS, DEFAULT_N)

    cfg = _load_cfg(config, api_version=api_version, max_tokens=max_tokens, recipe=recipe,
                    json_mode=json_mode)
    # CLI --deployment overrides config; config accepts "deployments" or "targets".
    targets = deployment or cfg.get("deployments") or cfg.get("targets")
    if not targets:
        typer.echo("error: provide at least one deployment (--deployment or 'deployments' "
                   "in config)", err=True)
        raise typer.Exit(1)

    n = n if n is not None else cfg.get("n", DEFAULT_N)
    concurrency = concurrency if concurrency is not None else cfg.get("concurrency", DEFAULT_CONCURRENCY)
    # Shared endpoint/api_key/azure for every target (env fallbacks apply downstream).
    base = {k: cfg[k] for k in ("endpoint", "api_key", "azure") if k in cfg}

    typer.echo(f"benchmark: n={n} concurrency={concurrency} per deployment "
               f"({len(targets)} target{'s' if len(targets) != 1 else ''})\n")

    def _live(r):  # print each result as it lands so long runs show progress
        typer.echo(f"  measured {r.deployment}: {r.rows_per_min:.0f} rows/min, "
                   f"{r.compl_tok_per_s:.0f} tok/s, ok={r.ok}/{r.n}")

    results = benchmark_deployments(
        targets, n=n, concurrency=concurrency, base=base or None,
        recipe=cfg.get("recipe", "tamil"), prompt=cfg.get("prompt"),
        max_tokens=cfg.get("max_tokens", DEFAULT_MAX_TOKENS),
        api_version=cfg.get("api_version", DEFAULT_API_VERSION),
        request_timeout=cfg.get("request_timeout", 180),
        json_mode=cfg.get("json_mode", True),
        on_result=_live,
    )

    from praisonai_train.cli.output.console import get_output_controller
    get_output_controller().print_table(
        _TABLE_HEADERS, [_row_cells(r) for r in results],
        title=f"speed benchmark (ranked by rows/min)",
    )

    out_path = output or cfg.get("output")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(json.dumps([r.as_dict() for r in results], indent=2))
        typer.echo(f"\nwrote results -> {out_path}")

    if not any(r.ok for r in results):
        typer.echo("error: every request failed — check endpoint/api_key/deployment "
                   "and provider availability", err=True)
        raise typer.Exit(1)
