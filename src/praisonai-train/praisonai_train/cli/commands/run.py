"""``praisonai-train checkpoints`` and ``generate`` — what to do after a run.

Two questions every fine-tune ends with, neither of which had an answer:

* **What did it save?** After an interrupted run there was no way to find the
  checkpoints without `ls`, and ``export --model-dir`` requires you to already
  know the path.
* **Did it work?** ``TrainModel.inference()`` has existed for a while with no
  caller anywhere in the package, and ``serve --benchmark`` measures tokens per
  second without showing a single token. The only way to see output was to
  write Python.

    praisonai-train checkpoints
    praisonai-train checkpoints -d outputs --json
    praisonai-train infer -d lora_model "Summarise this release."
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import typer

from praisonai_train.cli.commands.train import app

_CHECKPOINT = re.compile(r"^checkpoint-(\d+)$")


def _out():
    from praisonai_train.cli.output.console import get_output_controller
    return get_output_controller()


def find_checkpoints(root: Path):
    """Saved checkpoints under `root`, newest step first.

    Matches `checkpoint-<n>` exactly, so a directory a user happened to call
    `checkpoint-final` is not reported as step 0.
    """
    if not root.is_dir():
        return []
    found = []
    for child in sorted(root.iterdir()):
        m = _CHECKPOINT.match(child.name)
        if not m or not child.is_dir():
            continue
        size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
        found.append({"step": int(m.group(1)), "path": str(child), "bytes": size})
    return sorted(found, key=lambda c: c["step"], reverse=True)


@app.command("checkpoints")
def checkpoints(
    model_dir: Path = typer.Option(Path("outputs"), "--model-dir", "-d",
                                   help="Directory the run wrote to."),
    as_json: bool = typer.Option(False, "--json", "-j"),
):
    """List the checkpoints a run saved."""
    found = find_checkpoints(model_dir)
    if as_json:
        typer.echo(json.dumps(found, indent=2))
        return
    if not found:
        _out().print_error(
            f"No checkpoints in {model_dir}",
            remediation="Set save_steps in the config, or pass --model-dir to "
                        "the directory the run used (output_dir).")
        raise typer.Exit(1)
    for c in found:
        typer.echo(f"  checkpoint-{c['step']:<8} {c['bytes'] / 1e9:6.2f} GB  {c['path']}")
    typer.echo(f"\n{len(found)} checkpoint(s); newest is step {found[0]['step']}.")


@app.command("infer")
def infer(
    prompt: str = typer.Argument(..., help="What to send the model."),
    model_dir: Path = typer.Option(Path("lora_model"), "--model-dir", "-d",
                                   exists=True, help="A trained adapter or model."),
    max_new_tokens: int = typer.Option(256, "--max-new-tokens"),
    temperature: float = typer.Option(0.7, "--temperature"),
    max_seq_length: int = typer.Option(2048, "--max-seq-length"),
    load_in_4bit: bool = typer.Option(True, "--load-in-4bit/--no-load-in-4bit"),
):
    """Generate once from a model you just trained."""
    try:
        from unsloth import FastLanguageModel
        from transformers import TextStreamer
    except ImportError as exc:
        _out().print_error(
            "Inference dependencies not installed",
            remediation='pip install "praisonai-train[llm]"')
        raise typer.Exit(1) from exc

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(model_dir),
        max_seq_length=max_seq_length,
        load_in_4bit=load_in_4bit,
    )
    FastLanguageModel.for_inference(model)
    inputs = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=True, add_generation_prompt=True, return_tensors="pt",
    ).to(model.device)
    # Streamed rather than returned in one lump: the first token is the answer
    # to "is this model alive", and on a large model it arrives long before the
    # last one.
    model.generate(
        input_ids=inputs,
        streamer=TextStreamer(tokenizer, skip_prompt=True),
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        use_cache=True,
    )
