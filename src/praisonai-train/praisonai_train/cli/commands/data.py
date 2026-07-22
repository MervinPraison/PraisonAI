"""Dataset commands for praisonai-train: ``generate`` and ``validate``.

Both are YAML-driven (``--config file.yaml``) to match ``praisonai-train llm``,
with a few common flags as overrides. Generation streams to JSONL with dedup and
optional incremental snapshots; validation runs the research-backed QC filter.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from praisonai_train.cli.commands.train import app


def _load_cfg(config: Optional[str], **overrides) -> dict:
    cfg: dict = {}
    if config:
        import yaml
        cfg = yaml.safe_load(Path(config).read_text()) or {}
    for k, v in overrides.items():
        if v is not None:
            cfg[k] = v
    return cfg


@app.command("generate")
def generate_data(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="YAML config"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output JSONL"),
    recipe: Optional[str] = typer.Option(None, "--recipe", "-r", help="Recipe name (e.g. tamil)"),
    deployment: Optional[str] = typer.Option(None, "--deployment", "-d", help="Teacher model/deployment"),
    num: Optional[int] = typer.Option(None, "--num", "-n", help="Examples to generate"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Parallel requests"),
    start_offset: Optional[int] = typer.Option(None, "--start-offset", help="Prompt offset (parallel runs)"),
    snapshot_every: Optional[int] = typer.Option(None, "--snapshot-every", help="Snapshot every N rows"),
):
    """Generate a synthetic instruction dataset from a teacher LLM.

    Example: praisonai-train generate --config gen.yaml
             praisonai-train generate -r tamil -d gpt-4o -n 1000 -o out.jsonl
    """
    from praisonai_train.data import generate_dataset

    cfg = _load_cfg(config, output=output, recipe=recipe, deployment=deployment,
                    concurrency=concurrency, start_offset=start_offset)
    if num is not None:
        cfg["num_examples"] = num
    out_path = cfg.get("output")
    if not out_path or not cfg.get("num_examples"):
        typer.echo("error: 'output' and 'num_examples' (or --num) are required", err=True)
        raise typer.Exit(1)
    # dedup across existing files listed in config so re-runs never repeat.
    snap_every = cfg.get("snapshot_every")
    snap_dir = cfg.get("snapshot_dir", "snapshots")

    kept = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", buffering=1) as fh:
        for row in generate_dataset(cfg):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            kept += 1
            if snap_every and kept % snap_every == 0:
                Path(snap_dir).mkdir(parents=True, exist_ok=True)
                snap = Path(snap_dir) / f"{Path(out_path).stem}_{kept}.jsonl"
                snap.write_text(Path(out_path).read_text())
                typer.echo(f"  snapshot: {snap} ({kept} rows)")
    typer.echo(f"generated {kept} unique examples -> {out_path}")


@app.command("validate")
def validate_data(
    dataset: Optional[str] = typer.Argument(None, help="Dataset JSONL to validate"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="YAML config"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write filtered JSONL here"),
    no_near_dup: bool = typer.Option(False, "--no-near-dup", help="Skip the O(n^2) near-dup pass"),
):
    """Quality-check a dataset (dedup, boilerplate/refusal, script purity, diversity).

    Example: praisonai-train validate data.jsonl --out clean.jsonl
             praisonai-train validate --config qc.yaml
    """
    from praisonai_train.data import score

    cfg = _load_cfg(config)
    path = dataset or cfg.get("input")
    if not path:
        typer.echo("error: provide a dataset path or 'input' in config", err=True)
        raise typer.Exit(1)
    if no_near_dup:
        cfg["near_dup"] = False
    rows = [json.loads(l) for l in open(path) if l.strip()]
    result = score(rows, cfg)

    typer.echo(f"\n─── QC: {path} ───")
    typer.echo(f"  in={result['in']}  kept={result['kept_n']} "
               f"({100 * result['kept_n'] / max(result['in'], 1):.1f}%)")
    typer.echo(f"  drops: {result['drops']}")
    typer.echo(f"  flags: {result['flags']}")
    typer.echo(f"  metrics: {result['metrics']}")
    if result["warnings"]:
        for w in result["warnings"]:
            typer.echo(f"  ⚠ {w}")
    else:
        typer.echo("  ✓ no diversity warnings")

    out_path = out or cfg.get("output")
    if out_path:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as fh:
            for r in result["kept"]:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        typer.echo(f"  wrote {result['kept_n']} filtered rows -> {out_path}")
