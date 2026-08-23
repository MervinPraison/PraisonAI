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


class _Progress:
    """Default progress reporter for the ``generate`` command.

    Uses a ``tqdm`` bar when tqdm is importable (it's already an optional dep of
    the training path — never added as a hard requirement here), otherwise falls
    back to printing ``done/total`` every ``every`` requests. Pass ``self.update``
    as ``generate_dataset(..., progress_callback=...)``.
    """

    def __init__(self, total: Optional[int], every: int = 500) -> None:
        self.total = total
        self.every = max(1, every)
        self._bar = None
        self._last = 0
        try:
            from tqdm import tqdm  # optional; guarded so it's never a hard dep
            self._bar = tqdm(total=total, unit="req", desc="generating")
        except Exception:
            self._bar = None

    def update(self, done: int, total: int, kept: int) -> None:
        if self._bar is not None:
            self._bar.update(done - self._last)
            self._last = done
            self._bar.set_postfix(kept=kept)
            return
        # Plain fallback: throttle so large runs don't flood stdout.
        if done and (done % self.every == 0 or done == total):
            typer.echo(f"  ...{done}/{total} requests ({kept} kept)")

    def close(self) -> None:
        if self._bar is not None:
            self._bar.close()


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
                    concurrency=concurrency, start_offset=start_offset,
                    snapshot_every=snapshot_every)
    if num is not None:
        cfg["num_examples"] = num
    out_path = cfg.get("output")
    if not out_path or not cfg.get("num_examples"):
        typer.echo("error: 'output' and 'num_examples' (or --num) are required", err=True)
        raise typer.Exit(1)
    # dedup across existing files listed in config so re-runs never repeat.
    snap_every = cfg.get("snapshot_every")
    snap_dir = cfg.get("snapshot_dir", "snapshots")

    # Write to a sibling temp file and atomically replace the destination only on
    # success (mirrors the `dedup` command). A run that yields no rows — every
    # teacher request failed, bad credentials/recipe, no JSON-mode support — must
    # never destroy an existing corpus: the original file is left untouched and
    # the temp file is removed. A self-referential dedup_from is also read before
    # it could be emptied.
    import os
    import tempfile

    progress = _Progress(cfg.get("num_examples"))
    gen = generate_dataset(cfg, progress_callback=progress.update)
    kept = 0
    out_dir = Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(out_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", buffering=1) as fh:
            for row in gen:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                kept += 1
                if snap_every and kept % snap_every == 0:
                    Path(snap_dir).mkdir(parents=True, exist_ok=True)
                    snap = Path(snap_dir) / f"{Path(out_path).stem}_{kept}.jsonl"
                    snap.write_text(Path(tmp_name).read_text())
                    typer.echo(f"  snapshot: {snap} ({kept} rows)")
        # Only replace the destination when at least one row was produced, so the
        # all-failures path leaves any existing file intact.
        if kept:
            os.replace(tmp_name, out_path)
        else:
            os.unlink(tmp_name)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    finally:
        progress.close()
    typer.echo(f"generated {kept} unique examples -> {out_path}")
    if kept == 0:
        typer.echo("error: no rows generated — check endpoint/api_key/deployment "
                   "and provider JSON-mode support", err=True)
        raise typer.Exit(1)


@app.command("dedup")
def dedup_data(
    inputs: list[str] = typer.Argument(None, help="Input JSONL file(s) to dedup across"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="YAML config"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Write deduped JSONL here"),
    method: Optional[str] = typer.Option(None, "--method", help="near-dup engine: minhash|sliding"),
    threshold: Optional[float] = typer.Option(None, "--threshold", help="near-dup Jaccard (0-1)"),
    exact_only: bool = typer.Option(False, "--exact-only", help="Skip near-dup, exact only"),
):
    """Deduplicate rows ACROSS many batch files with one shared MinHash+LSH index.

    Unlike ``validate`` (per-file), this removes duplicates that span files — the
    common case when merging parallel/incremental generation batches.

    Example: praisonai-train dedup batch_*.jsonl --out merged.jsonl
             praisonai-train dedup --config dedup.yaml
    """
    from praisonai_train.data import global_dedup

    cfg = _load_cfg(config)
    if method is not None:
        cfg["near_dup_method"] = method
    if threshold is not None:
        cfg["near_dup_jaccard"] = threshold
    if exact_only:
        cfg["near_dup"] = False
    sources = list(inputs) if inputs else (cfg.get("inputs") or ([cfg["input"]] if cfg.get("input") else []))
    if not sources:
        typer.echo("error: provide input JSONL path(s) or 'inputs'/'input' in config", err=True)
        raise typer.Exit(1)
    out_path = out or cfg.get("output")
    if not out_path:
        typer.echo("error: provide --out or 'output' in config", err=True)
        raise typer.Exit(1)

    total_in = 0
    for src in sources:
        with open(src) as fh:
            total_in += sum(1 for ln in fh if ln.strip())

    # Write to a sibling temp file and atomically replace the destination only on
    # success. This means (a) an --out that aliases an input is never truncated
    # before its rows are read, and (b) a malformed line mid-stream aborts without
    # leaving a partial file that a downstream job could mistake for a result.
    import os
    import tempfile

    kept = 0
    out_dir = Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(out_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            for row in global_dedup(sources, cfg):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                kept += 1
        os.replace(tmp_name, out_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    removed = total_in - kept
    typer.echo(f"\n─── cross-file dedup: {len(sources)} file(s) ───")
    typer.echo(f"  in={total_in}  kept={kept}  removed={removed} "
               f"({100 * removed / max(total_in, 1):.1f}% dup)")
    typer.echo(f"  wrote {kept} unique rows -> {out_path}")


@app.command("from-trials")
def from_trials(
    report: str = typer.Argument(..., help="Serialised trials report JSON"),
    out: Optional[str] = typer.Option(None, "--out", "-o", help="Output JSONL"),
    all_attempts: bool = typer.Option(False, "--all", help="Include failed/unscored attempts"),
    include_saturated: bool = typer.Option(
        False, "--include-saturated", help="Include all-pass / zero-pass cases"),
    fmt: str = typer.Option("messages", "--format", help="messages (ShareGPT) | alpaca"),
    qc: bool = typer.Option(False, "--qc", help="Run rows through the QC filter"),
):
    """Export passing agent trials to a trainer-ready SFT dataset (+ provenance).

    Rejection sampling on the verifier: keeps verifier-passed attempts from
    frontier cases (0 < pass_rate < 1) and writes ShareGPT ``conversations`` the
    existing trainer consumes directly. A ``{out}.meta.json`` sidecar traces every
    line to its case id, attempt index and score.

    Example: praisonai-train data from-trials trials.json -o data/train.jsonl
             praisonai-train llm --dataset data/train.jsonl
    """
    from praisonai_train.data import export_trials

    out_path = out or f"{Path(report).stem}.jsonl"
    summary = export_trials(
        report, out_path,
        only_passed=not all_attempts,
        frontier_only=not include_saturated,
        format=fmt,
        qc=qc,
    )
    typer.echo(f"\n─── from-trials: {report} ───")
    typer.echo(f"  {summary}")
    typer.echo(f"  wrote {summary.written} rows -> {out_path}")
    typer.echo(f"  provenance -> {out_path}.meta.json")
    if summary.written == 0:
        typer.echo("error: no rows exported — check --all/--include-saturated or "
                   "whether the report has passing, tool-free attempts", err=True)
        raise typer.Exit(1)


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
    rows, bad = [], 0
    with open(path) as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
                typer.echo(f"  ⚠ skipping malformed JSON on line {lineno}", err=True)
    if bad:
        typer.echo(f"  ⚠ skipped {bad} malformed line(s)", err=True)
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
