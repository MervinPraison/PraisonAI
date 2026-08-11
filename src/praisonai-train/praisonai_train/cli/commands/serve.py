"""``praisonai-train serve`` — run (or benchmark) a trained GGUF model with MTP.

Serves a trained Gemma-4 model through llama.cpp's OpenAI-compatible endpoint,
automatically fetching the matching stock Multi-Token-Prediction drafter for
lossless self-speculative decoding. Non Gemma-4 families fall back to plain
serving with a clear message.

    praisonai-train serve --gguf model.gguf
    praisonai-train serve -d lora_model --benchmark
    praisonai-train serve --gguf model.gguf --no-mtp-draft --port 9000
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from praisonai_train.cli.commands.train import app


def _find_gguf(model_dir: Path) -> Optional[Path]:
    """Best-effort: locate a single target GGUF inside a model directory.

    Skips MTP drafter files (``mtp-*`` / files under an ``MTP/`` dir) so we don't
    accidentally serve the drafter as the target.
    """
    candidates = [
        p for p in sorted(model_dir.rglob("*.gguf"))
        if not p.name.lower().startswith("mtp-") and "MTP" not in p.parts
    ]
    return candidates[0] if candidates else None


def _recover_model_name(cfg: dict, base_model: Optional[str], model_dir: Optional[Path]) -> Optional[str]:
    """Recover the base model name (drives MTP resolution), mirroring train_export."""
    model_name = base_model or cfg.get("model_name") or cfg.get("model")
    if not model_name and model_dir is not None:
        cfg_json = model_dir / "config.json"
        if cfg_json.exists():
            try:
                model_name = json.loads(cfg_json.read_text()).get("_name_or_path")
            except (json.JSONDecodeError, OSError):
                model_name = None
    return model_name


@app.command("serve")
def train_serve(
    model_dir: Optional[str] = typer.Option(
        None, "--model-dir", "-d", help="Directory of the trained model (GGUF auto-detected)"),
    gguf: Optional[str] = typer.Option(
        None, "--gguf", help="Path to the target GGUF to serve"),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Optional config.yaml (for base model / MTP knobs)"),
    base_model: Optional[str] = typer.Option(
        None, "--base-model", help="Base model id (for MTP drafter selection)"),
    mtp_draft: bool = typer.Option(
        True, "--mtp-draft/--no-mtp-draft",
        help="Use the stock MTP drafter (auto: on if the family supports it)"),
    spec_draft_n_max: int = typer.Option(
        2, "--spec-draft-n-max", help="Max tokens the MTP drafter proposes per step"),
    port: int = typer.Option(8080, "--port", help="Port for llama-server"),
    ngl: int = typer.Option(99, "--ngl", help="Number of layers to offload to GPU"),
    benchmark: bool = typer.Option(
        False, "--benchmark", help="Run a one-shot speed benchmark instead of serving"),
):
    """Serve or benchmark a trained GGUF model with MTP fast inference.

    Determines the target GGUF (from --gguf or --model-dir), recovers the base
    model name (from --config / --base-model / config.json), fetches the matching
    stock MTP drafter when supported, then serves via llama-server (OpenAI API) or
    runs a one-shot llama-cli benchmark.
    """
    from praisonai_train.cli.output.console import get_output_controller
    from praisonai_train.train import _llamacpp, _mtp

    output = get_output_controller()

    # ---- Resolve the target GGUF ---------------------------------------- #
    model_dir_path = Path(model_dir) if model_dir else None
    if gguf:
        target = Path(gguf)
        if not target.exists():
            output.print_error(
                f"GGUF not found: {gguf}",
                remediation="Pass --gguf pointing at your exported model .gguf.",
            )
            raise typer.Exit(1)
    elif model_dir_path:
        if not model_dir_path.exists():
            output.print_error(
                f"Model directory not found: {model_dir}",
                remediation="Pass --model-dir pointing at your trained/exported model.",
            )
            raise typer.Exit(1)
        target = _find_gguf(model_dir_path)
        if target is None:
            output.print_error(
                f"No .gguf found under {model_dir}",
                remediation="Export to GGUF first (praisonai-train export gguf ...) or pass --gguf.",
            )
            raise typer.Exit(1)
    else:
        output.print_error(
            "Nothing to serve: provide --gguf or --model-dir.",
            remediation="e.g. praisonai-train serve --gguf model.gguf",
        )
        raise typer.Exit(1)

    # ---- Load optional config, recover model name ----------------------- #
    cfg: dict = {}
    if config:
        import yaml
        cfg = yaml.safe_load(Path(config).read_text()) or {}
    model_name = _recover_model_name(cfg, base_model, model_dir_path)

    # ---- Decide on the MTP drafter -------------------------------------- #
    draft_path: Optional[Path] = None
    if mtp_draft:
        if not model_name:
            output.print_warning(
                "Could not determine the base model name, so MTP support can't be "
                "checked — serving without a drafter. Pass --base-model to enable MTP."
            )
        elif not _mtp.is_mtp_supported(model_name):
            output.print_warning(
                f"MTP fast inference isn't available for '{model_name}' "
                "(only the Gemma-4 family). Serving without a drafter."
            )
        else:
            try:
                dest = (model_dir_path or target.parent)
                typer.echo(f"Fetching stock MTP drafter for {model_name} ...")
                draft_path = _mtp.fetch_drafter(model_name, dest)
                typer.echo(f"  drafter -> {draft_path}")
            except (ValueError, RuntimeError) as exc:
                output.print_warning(
                    f"Could not fetch the MTP drafter ({exc}). Serving without it."
                )
                draft_path = None

    # ---- Serve or benchmark --------------------------------------------- #
    try:
        if benchmark:
            typer.echo(
                f"Benchmarking {target}"
                + (f" with MTP drafter {draft_path.name}" if draft_path else " (no MTP)")
                + " ..."
            )
            result = _llamacpp.benchmark(
                str(target),
                draft_gguf=str(draft_path) if draft_path else None,
                spec_draft_n_max=spec_draft_n_max,
                ngl=ngl,
            )
            tps = result.get("tokens_per_sec")
            acc = result.get("accept_rate")
            typer.echo(
                f"tokens/sec: {tps:.1f}" if isinstance(tps, (int, float))
                else "tokens/sec: (unparsed)"
            )
            if acc is not None:
                typer.echo(f"draft acceptance: {acc * 100:.1f}%")
            typer.echo(f"MTP: {'on' if result.get('mtp') else 'off'}")
        else:
            proc = _llamacpp.serve(
                str(target),
                draft_gguf=str(draft_path) if draft_path else None,
                spec_draft_n_max=spec_draft_n_max,
                port=port,
                ngl=ngl,
            )
            typer.echo(f"llama-server running (pid {proc.pid}). Press Ctrl-C to stop.")
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                typer.echo("\nStopped.")
    except (ValueError, RuntimeError) as exc:
        output.print_error(str(exc))
        raise typer.Exit(1)
