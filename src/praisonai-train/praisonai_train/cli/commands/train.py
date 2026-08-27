"""
Train command group for PraisonAI CLI.

Provides two types of training:
1. LLM Fine-tuning: praisonai train dataset.json
2. Agent Training: praisonai train agents [OPTIONS]
"""

import json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Training commands for models and agents")


@app.callback()
def train_callback():
    """
    Training commands for models and agents.
    
    For LLM fine-tuning:
        praisonai train llm dataset.json
    
    For agent training (iterative improvement):
        praisonai train agents --input "What is Python?"
        praisonai train agents --input "Explain AI" --human
    """
    pass


# The knobs worth a flag. Everything else stays in the config file, which is
# now reachable -- `llm` was the only command that would not accept --config,
# though `export` and `serve` both do, so changing a LoRA rank meant editing a
# YAML file the CLI gave you no way to point at.
_TRAIN_FLAGS = (
    ("method", "--method", "sft | cpt | dpo | orpo | kto"),
    ("max_seq_length", "--max-seq-length", "Sequence length."),
    ("num_train_epochs", "--epochs", "Epochs. Ignored if --max-steps is set."),
    ("max_steps", "--max-steps", "Stop after this many steps."),
    ("learning_rate", "--learning-rate", "Learning rate."),
    ("per_device_train_batch_size", "--batch-size", "Per-device batch size."),
    ("gradient_accumulation_steps", "--grad-accum", "Gradient accumulation steps."),
    ("lora_r", "--lora-r", "LoRA rank."),
    ("lora_alpha", "--lora-alpha", "LoRA alpha."),
    ("output_dir", "--output-dir", "Where checkpoints go."),
    ("chat_template", "--chat-template", "Chat template name."),
)


@app.command("llm")
def train_llm(
    dataset: Optional[str] = typer.Argument(
        None, help="Training dataset path. Optional when --config names one."),
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", exists=True,
        help="Training config YAML. Flags below override it."),
    remote_host: Optional[str] = typer.Option(
        None, "--remote-host",
        help="SSH alias to train on, as in ~/.ssh/config. Omit to train here."),
    remote_python: Optional[str] = typer.Option(
        None, "--remote-python", help="Interpreter on the remote host."),
    remote_workdir: Optional[str] = typer.Option(
        None, "--remote-workdir", help="Directory to work in on the remote host."),
    remote_gpus: Optional[int] = typer.Option(
        None, "--remote-gpus", help="How many GPUs the run expects to find."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Base model to fine-tune"),
    method: Optional[str] = typer.Option(None, "--method", help="sft | cpt | dpo | orpo | kto"),
    max_seq_length: Optional[int] = typer.Option(None, "--max-seq-length"),
    num_train_epochs: Optional[float] = typer.Option(None, "--epochs"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps"),
    learning_rate: Optional[float] = typer.Option(None, "--learning-rate"),
    per_device_train_batch_size: Optional[int] = typer.Option(None, "--batch-size"),
    gradient_accumulation_steps: Optional[int] = typer.Option(None, "--grad-accum"),
    lora_r: Optional[int] = typer.Option(None, "--lora-r"),
    lora_alpha: Optional[int] = typer.Option(None, "--lora-alpha"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir"),
    chat_template: Optional[str] = typer.Option(None, "--chat-template"),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Print the resolved config and exit, without training."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Fine-tune LLM models using Unsloth.

    Examples:
        praisonai-train llm dataset.json
        praisonai-train llm dataset.json --lora-r 32 --epochs 2
        praisonai-train llm -c config.yaml --dry-run
    """
    import sys

    # Typer fills these in when Click invokes the command, but `train_llm` is
    # also called directly as a plain function -- by tests, and by anything
    # importing it. Unfilled parameters then arrive as OptionInfo objects and
    # Path(config) raises. Unwrap them to their declared defaults first.
    def _v(value):
        # ArgumentInfo as well as OptionInfo. `dataset` is a typer.Argument,
        # so it produces the former -- and it was the one parameter neither
        # named below nor recognised here. Called as a plain function it then
        # arrived as an ArgumentInfo, which is truthy, so it was written into
        # the resolved config as `dataset: <ArgumentInfo object>` and the YAML
        # dump raised RepresenterError.
        return (getattr(value, "default", value)
                if type(value).__name__ in ("OptionInfo", "ArgumentInfo")
                else value)

    dataset = _v(dataset)
    config = _v(config)
    model = _v(model)
    method = _v(method)
    max_seq_length = _v(max_seq_length)
    num_train_epochs = _v(num_train_epochs)
    max_steps = _v(max_steps)
    learning_rate = _v(learning_rate)
    per_device_train_batch_size = _v(per_device_train_batch_size)
    gradient_accumulation_steps = _v(gradient_accumulation_steps)
    lora_r = _v(lora_r)
    lora_alpha = _v(lora_alpha)
    output_dir = _v(output_dir)
    chat_template = _v(chat_template)
    remote_host = _v(remote_host)
    remote_python = _v(remote_python)
    remote_workdir = _v(remote_workdir)
    remote_gpus = _v(remote_gpus)
    dry_run = _v(dry_run) or False
    verbose = _v(verbose) or False

    from ..output.console import get_output_controller
    from praisonai_train._code_bridge import code_available, import_code_module

    # File first, flags on top -- the same precedence the dry-run preview shows.
    # Snapshot locals() BEFORE the comprehension: a comprehension has its own
    # scope, so calling locals() inside it sees the comprehension's names, not
    # this function's parameters, and every tuning flag would be dropped.
    supplied = locals()
    overrides = {name: value for name, _flag, _help in _TRAIN_FLAGS
                 if (value := supplied.get(name)) is not None}
    if model:
        overrides["model_name"] = model
    if dataset:
        overrides["dataset"] = dataset

    # Where the run executes, not what it trains. Kept out of `overrides` so it
    # never lands in the trainer's own settings.
    remote_overrides = {"host": remote_host, "python": remote_python,
                        "workdir": remote_workdir, "gpus": remote_gpus}

    if dry_run:
        # Answering "what are you about to do?" before an hour of rented GPU is
        # the difference between a caught typo and a wasted run. Resolved and
        # printed WITHOUT loading the (heavy, optional) runner, so a preview
        # never depends on the training deps being installed.
        _print_resolved_config(config, overrides)
        return

    if not dataset and not config:
        get_output_controller().print_error(
            "No dataset given",
            remediation="Pass a dataset path, or --config a file that names one.",
        )
        raise typer.Exit(1)

    # The legacy `train` dispatcher reads ONLY ./config.yaml in the cwd and
    # parses argv with parse_known_args(), so --config and every tuning flag
    # (--lora-r, --epochs, ...) it does not declare are silently dropped -- the
    # real run would then train from a different config than the --dry-run
    # preview showed. Resolve the config here (file + flags, same precedence as
    # the preview) and write it to the ./config.yaml the dispatcher (and the
    # trainer subprocess it launches) actually loads, so the previewed config
    # IS the one that trains. Pass a bare `train` so the dispatcher takes its
    # "file exists, no model/dataset override" branch and reads our file as-is.
    resolved = _resolve_config(config, overrides)

    # Where before what. Resolved from the same file-then-flags precedence as
    # everything else, so `remote: {host: gpubox}` in the YAML and
    # `--remote-host gpubox` are the same instruction -- and the desktop form,
    # which writes that YAML, is a third way of saying it rather than a
    # separate mode.
    #
    # Checked before the heavy import below on purpose: the whole point of
    # training elsewhere is that this machine does not have torch or a GPU, so
    # requiring them here would make the remote option unreachable from exactly
    # the machines that need it.
    if _dispatch_remote(resolved, remote_overrides, config, dataset):
        return

    try:
        PraisonAI = import_code_module("praisonai_code.cli.main").PraisonAI
    except ImportError as exc:
        output = get_output_controller()
        if not code_available():
            output.print_error(
                "LLM fine-tuning dependencies not installed",
                remediation='pip install "praisonai-train[llm]"',
            )
        else:
            output.print_error(
                f"Failed to load LLM fine-tuning runner: {exc}",
            )
        raise typer.Exit(1)

    _materialize_config(resolved)

    argv = ['train']
    # Deliberately NOT forwarding --dataset or --model.
    #
    # I added them as "belt and braces" and they were the opposite. The legacy
    # dispatcher branches on `args.model or args.dataset != <default>`
    # (praisonai_code/cli/legacy/praison_ai.py:676) and, on that branch, calls
    # generate_config() with every tuning parameter None -- which REWRITES
    # config.yaml from defaults. Measured effect of forwarding them:
    #
    #     lora_r 64 -> 16,  epochs 5 -> 1,  lr 1e-4 -> 2e-4,
    #     max_seq_length 8192 -> 2048,  method dpo -> sft (not even a
    #     generate_config parameter), and worst of all
    #     huggingface_save false -> TRUE with hf_model_name defaulted to
    #     someone else's Hub repo.
    #
    # So a --dry-run preview showed one config and a completely different one
    # trained, and the run tried to publish to a third party's account. The
    # materialised config.yaml above is the single source of truth; passing a
    # bare `train` keeps the dispatcher on its "file exists, no override"
    # branch, which reads that file as-is.
    if verbose:
        argv.append('--verbose')

    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv

    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit as exc:
        # Propagate a non-zero exit (e.g. missing training dependencies) so
        # callers and CI gating on ``$?`` see the failure. A clean exit is
        # swallowed so the command returns 0 as before.
        if exc.code:
            raise typer.Exit(exc.code if isinstance(exc.code, int) else 1) from exc
    finally:
        sys.argv = original_argv


def _dispatch_remote(resolved, remote_overrides, config_path, dataset):
    """Run this job on another machine, if the config says so. True if it ran.

    The local path is untouched: with no host settled this returns False
    immediately and the caller carries on exactly as before.
    """
    from ..output.console import get_output_controller
    from praisonai_train.remote import settings as remote_settings

    try:
        block = remote_settings.resolve(resolved, remote_overrides)
    except remote_settings.RemoteSettingsError as exc:
        get_output_controller().print_error("Bad remote settings", remediation=str(exc))
        raise typer.Exit(1) from exc

    if not block:
        return False

    from praisonai_train.remote.runner import RemoteError, RemoteRunner

    output = get_output_controller()
    runner = RemoteRunner(host=block["host"], python=block["python"],
                          workdir=block["workdir"])

    shipped = _write_shipped_config(resolved)
    try:
        run = runner.start(config_path=shipped,
                           dataset_path=Path(dataset) if dataset else None,
                           expect_gpus=block["gpus"])
    except RemoteError as exc:
        output.print_error(f"Could not start the run on {block['host']}",
                           remediation=str(exc))
        raise typer.Exit(1) from exc

    output.print_success(f"started {run.run_id} on {block['host']}")
    typer.echo(f"  tail:  praisonai-train remote tail {block['host']} {run.run_id}")
    typer.echo(f"  stop:  praisonai-train remote stop {block['host']} {run.run_id}")

    # A stop from the caller has to reach the other machine. Without this the
    # signal ends the tail and leaves the run holding a rented GPU, reporting
    # "cancelled" for a job that is still training -- which is how the desktop
    # Stop button would lie.
    _stop_remote_on_signal(runner, run, output)

    runner.tail(run, on_line=typer.echo)
    state = runner.status(run)
    typer.echo(f"status: {state}")
    if state == "failed":
        raise typer.Exit(1)
    return True


def _write_shipped_config(resolved):
    """The config to send, in a temp file. Returns its path.

    Not _materialize_config: that writes ./config.yaml into the invocation
    directory (and backs up whatever was there), which is the local
    dispatcher's contract. Training elsewhere should not rewrite a file in the
    directory the user happened to be standing in.

    The remote block is stripped. It says where this job goes, and it has
    already been obeyed -- leaving it in would have the far side read its own
    config, find a host, and dispatch again.
    """
    import tempfile

    import yaml

    to_send = {k: v for k, v in resolved.items() if k != "remote"}
    dataset = to_send.get("dataset")
    if isinstance(dataset, str):
        to_send["dataset"] = [{"name": dataset}]

    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", prefix="praisonai-train-", delete=False, encoding="utf-8")
    with handle:
        yaml.safe_dump(to_send, handle, sort_keys=False)
    return Path(handle.name)


def _stop_remote_on_signal(runner, run, output):
    """Make SIGINT and SIGTERM stop the remote run, not just this process."""
    import signal

    def _stop(signum, _frame):
        try:
            runner.stop(run)
            output.print_success(f"stopped {run.run_id} on {runner.host}")
        except Exception as exc:  # noqa: BLE001 - never block the exit
            output.print_error(
                f"Could not stop {run.run_id} on {runner.host}",
                remediation=f"praisonai-train remote stop {runner.host} "
                            f"{run.run_id}  ({exc})")
        raise SystemExit(130 if signum == signal.SIGINT else 143)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _stop)
        except (ValueError, OSError):
            # Not the main thread, or the platform will not take it. The run
            # still started; only the courtesy stop is unavailable.
            pass


def _resolve_config(config_path, overrides):
    """Merge the config file (baseline) with the flags (on top), and return it.

    Single source of truth for both the ``--dry-run`` preview and the real run,
    so what is previewed is exactly what trains -- they cannot drift.
    """
    import yaml

    from ..output.console import get_output_controller

    resolved = {}
    if config_path:
        loaded = yaml.safe_load(Path(config_path).read_text()) or {}
        if not isinstance(loaded, dict):
            get_output_controller().print_error(
                f"{config_path} is not a mapping",
                remediation="A training config is a YAML mapping of key: value.")
            raise typer.Exit(1)
        resolved.update(loaded)
    resolved.update(overrides)
    return resolved


def _print_resolved_config(config_path, overrides):
    """Show the config the run would use: the file, then the flags on top."""
    import yaml

    resolved = _resolve_config(config_path, overrides)
    typer.echo(yaml.safe_dump(resolved, sort_keys=True, default_flow_style=False).rstrip())
    if overrides:
        typer.echo(f"\n# {len(overrides)} value(s) came from flags: "
                   f"{', '.join(sorted(overrides))}")


def _materialize_config(resolved):
    """Write the resolved config to ./config.yaml (the file the legacy `train`
    dispatcher and its trainer subprocess both read) and return its path.

    A `dataset` given as a plain string (from the positional argument or a flag)
    is normalised to the ``[{name: ...}]`` shape the trainer requires; the
    trainer iterates ``config["dataset"]`` expecting a mapping per entry, so a
    bare string would otherwise be read character by character.
    """
    import yaml

    to_write = dict(resolved)
    dataset = to_write.get("dataset")
    if isinstance(dataset, str):
        to_write["dataset"] = [{"name": dataset}]

    config_path = Path.cwd() / "config.yaml"
    # Back up whatever was there. This writes into the invocation directory
    # unconditionally, so it has silently destroyed hand-written configs --
    # including one in this repo's own working tree. The dispatcher only reads
    # ./config.yaml, so the write has to happen; losing the previous contents
    # does not.
    if config_path.exists():
        backup = config_path.with_suffix(".yaml.bak")
        try:
            previous = config_path.read_text()
        except OSError:
            previous = None
        if previous is not None and previous != yaml.safe_dump(
                to_write, sort_keys=True, default_flow_style=False):
            backup.write_text(previous)
            print(f"NOTE: {config_path.name} already existed; the previous "
                  f"contents were saved to {backup.name}.")
    config_path.write_text(
        yaml.safe_dump(to_write, sort_keys=True, default_flow_style=False))
    return config_path


@app.command("agents")
def train_agents(
    agent_file: Optional[str] = typer.Argument(
        None,
        help="Path to agent YAML file or Python file"
    ),
    iterations: int = typer.Option(
        3,
        "--iterations", "-n",
        help="Maximum training iterations (default: 3). "
             "In LLM mode, stops early when a score reaches 9.5."
    ),
    no_early_stop: bool = typer.Option(
        False,
        "--no-early-stop",
        help="Run all iterations even if a score reaches 9.5"
    ),
    human: bool = typer.Option(
        False,
        "--human", "-h",
        help="Use human feedback instead of LLM grading"
    ),
    scenarios: Optional[str] = typer.Option(
        None,
        "--scenarios", "-s",
        help="Path to scenarios JSON file"
    ),
    input_text: Optional[str] = typer.Option(
        None,
        "--input", "-i",
        help="Single input text for training (alternative to scenarios file)"
    ),
    expected: Optional[str] = typer.Option(
        None,
        "--expected", "-e",
        help="Expected output for the input (optional)"
    ),
    output_dir: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Output directory for training data"
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model", "-m",
        help="LLM model for grading (default: gpt-4o-mini)"
    ),
    verbose: bool = typer.Option(
        True,
        "--verbose/--quiet", "-v/-q",
        help="Show detailed progress"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would happen without running"
    ),
    storage_backend: Optional[str] = typer.Option(
        None,
        "--storage-backend",
        help="Storage backend: 'file', 'sqlite', or 'redis://url'. Default: file"
    ),
    storage_path: Optional[str] = typer.Option(
        None,
        "--storage-path",
        help="Path for storage backend (file dir or sqlite db path)"
    ),
):
    """
    Train agents through iterative feedback loops.
    
    Two modes available:
    
    1. LLM-as-Judge (default): Agent runs, LLM grades output, 
       provides suggestions, agent re-runs with feedback.
       Fully automated, no human intervention needed.
    
    2. Human-in-the-Loop (--human): Agent runs, you review
       and provide feedback, agent re-runs with your feedback.
    
    Examples:
        # Simple: Train with a single input
        praisonai train agents --input "What is Python?"
        
        # With expected output
        praisonai train agents --input "What is 2+2?" --expected "4"
        
        # With scenarios file
        praisonai train agents --scenarios scenarios.json
        
        # Human feedback mode
        praisonai train agents --input "Explain AI" --human
        
        # More iterations
        praisonai train agents --input "Hello" --iterations 5
        
        # With agent file
        praisonai train agents my_agent.yaml --scenarios scenarios.json
    """
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    # Validate inputs
    if not input_text and not scenarios:
        output.print_error(
            "No training input provided",
            remediation="Use --input 'text' or --scenarios file.json"
        )
        raise typer.Exit(1)
    
    if dry_run:
        output.print_panel(
            f"Mode: {'Human-in-the-Loop' if human else 'LLM-as-Judge'}\n"
            f"Iterations: {iterations}\n"
            f"Input: {input_text or 'from scenarios file'}\n"
            f"Scenarios file: {scenarios or 'N/A'}\n"
            f"Agent file: {agent_file or 'default agent'}\n"
            f"Output dir: {output_dir or '~/.praison/train/'}",
            title="Dry Run - Would execute:"
        )
        return
    
    # Lazy import to avoid overhead
    try:
        from praisonai_train.train.agents import AgentTrainer, TrainingScenario
    except ImportError as e:
        output.print_error(f"Failed to import training module: {e}")
        raise typer.Exit(1)
    
    # Create or load agent
    agent = None
    if agent_file:
        agent = _load_agent_from_file(agent_file, output)
        if agent is None:
            raise typer.Exit(1)
    else:
        # Create a simple default agent
        try:
            from praisonaiagents import Agent
            agent = Agent(
                instructions="You are a helpful assistant. Provide clear, accurate, and helpful responses."
            )
        except ImportError:
            output.print_error(
                "praisonaiagents not installed",
                remediation="pip install praisonaiagents"
            )
            raise typer.Exit(1)
    
    # Create trainer
    storage_dir = Path(output_dir) if output_dir else None
    
    from praisonai_train.train.agents.grader import TrainingGrader
    grader = TrainingGrader(model=model) if model else None
    
    # Create storage backend if specified
    backend = None
    if storage_backend:
        backend = _create_storage_backend(storage_backend, storage_path, output)
        if backend is None and storage_backend not in ("file", None):
            raise typer.Exit(1)
    
    trainer = AgentTrainer(
        agent=agent,
        iterations=iterations,
        human_mode=human,
        grader=grader,
        storage_dir=storage_dir,
        storage_backend=backend,
        verbose=verbose,
        no_early_stop=no_early_stop,
    )
    
    # Add scenarios
    if scenarios:
        scenarios_list = _load_scenarios_from_file(scenarios, output)
        if scenarios_list is None:
            raise typer.Exit(1)
        trainer.add_scenarios(scenarios_list)
    elif input_text:
        trainer.add_scenario(TrainingScenario(
            id="cli-input",
            input_text=input_text,
            expected_output=expected,
        ))
    
    # Run training. Keep trainer.run() outside the UnicodeEncodeError=success
    # handler so a genuine mid-run encoding failure (before the report is
    # persisted) is still reported as a failure rather than a false success.
    try:
        report = trainer.run()
    except KeyboardInterrupt:
        output.print_warning("Training interrupted by user")
        raise typer.Exit(130)
    except Exception as e:
        output.print_error(f"Training failed: {e}")
        raise typer.Exit(1)

    # Training (and report persistence) succeeded. Displaying the summary must
    # never turn a completed session into a false failure, so a display-only
    # encoding error (e.g. cp1252 on Windows) is downgraded to a warning.
    try:
        if not verbose:
            report.print_summary()

        output.print_success(
            f"Training complete! Session: {report.session_id}\n"
            f"Average score: {report.avg_score:.1f}/10\n"
            f"Improvement: {report.improvement:+.1f}"
        )
    except UnicodeEncodeError as e:
        output.print_warning(f"Training complete but summary could not be displayed: {e}")
        raise typer.Exit(0)


@app.command("export")
def train_export(
    target: str = typer.Argument(..., help="Export target: ollama | gguf | hf"),
    model_dir: str = typer.Option(
        ..., "--model-dir", "-d", help="Directory of the already-trained model"),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Optional config.yaml (for extra export knobs)"),
    ollama: Optional[str] = typer.Option(
        None, "--ollama", help="Ollama model name, e.g. myuser/mymodel"),
    hf: Optional[str] = typer.Option(
        None, "--hf", help="Hugging Face repo id, e.g. myuser/mymodel"),
    quant: Optional[str] = typer.Option(
        None, "--quant", help="Quantization method for gguf/ollama, e.g. q4_k_m"),
    base_model: Optional[str] = typer.Option(
        None, "--base-model", help="Base model id (for chat-template selection)"),
    mtp_draft: bool = typer.Option(
        False, "--mtp-draft/--no-mtp-draft",
        help="Also download the stock MTP drafter (Gemma-4 only) for fast inference"),
):
    """
    Export / publish an ALREADY-trained model without re-running training.

    Examples:
        praisonai-train export hf     --model-dir lora_model --hf   me/my-model
        praisonai-train export gguf   --model-dir lora_model --quant q4_k_m            # local .gguf
        praisonai-train export gguf   --model-dir lora_model --hf   me/my-model        # local + push
        praisonai-train export ollama --model-dir lora_model --ollama me/my-model --quant q4_k_m
    """
    from ..output.console import get_output_controller

    output = get_output_controller()

    target = target.lower()
    if target not in ("ollama", "gguf", "hf"):
        output.print_error(
            f"Unknown export target: {target}",
            remediation="Use one of: ollama, gguf, hf",
        )
        raise typer.Exit(1)

    if not Path(model_dir).is_dir():
        output.print_error(
            f"Model directory not found: {model_dir}",
            remediation="Pass --model-dir pointing at your trained model (e.g. lora_model).",
        )
        raise typer.Exit(1)

    # Build an export-only config, merging an optional YAML file with CLI flags.
    cfg: dict = {}
    if config:
        import yaml
        cfg = yaml.safe_load(Path(config).read_text()) or {}
        if not isinstance(cfg, dict):
            output.print_error(
                f"Config file must be a YAML mapping: {config}",
                remediation="Use `key: value` pairs at the top level.",
            )
            raise typer.Exit(1)
    cfg["final_model_dir"] = model_dir
    cfg.setdefault("model_parameters", "latest")
    if quant:
        cfg["quantization_method"] = quant
    if hf:
        cfg["hf_model_name"] = hf
    if ollama:
        cfg["ollama_model"] = ollama

    # Recover the model name (drives chat-template selection) from --base-model or
    # the trained model's config.json (_name_or_path), falling back to the dir name.
    model_name = base_model or cfg.get("model_name")
    if not model_name:
        cfg_json = Path(model_dir) / "config.json"
        if cfg_json.exists():
            try:
                model_name = json.loads(cfg_json.read_text()).get("_name_or_path")
            except (json.JSONDecodeError, OSError):
                model_name = None
    cfg["model_name"] = model_name or model_dir

    # Validate the destination is present for the chosen target.
    # `hf` publishes to the Hub so a repo id is mandatory. `gguf` produces a
    # LOCAL .gguf (so it can be served with `serve`/`--mtp-draft`) and only
    # additionally pushes to the Hub when --hf is given; without --hf we write
    # the GGUF under the model dir.
    if target == "hf" and not cfg.get("hf_model_name"):
        output.print_error(
            "A Hugging Face repo id is required for this target",
            remediation="Pass --hf <your-username>/<name>.",
        )
        raise typer.Exit(1)
    if target == "gguf" and not cfg.get("hf_model_name"):
        cfg["hf_model_name"] = str(Path(model_dir) / "gguf")
    if target == "ollama" and not cfg.get("ollama_model"):
        output.print_error(
            "An Ollama model name is required for this target",
            remediation="Pass --ollama <your-username>/<name>.",
        )
        raise typer.Exit(1)
    # For an Ollama modelfile the FROM line uses hf_model_name; default it to the
    # local model dir so `ollama create` reads the trained model on disk.
    if target == "ollama":
        cfg.setdefault("hf_model_name", model_dir)

    try:
        from praisonai_train.train.llm.trainer import TrainModel
    except ImportError as exc:
        output.print_error(
            f"LLM export dependencies not installed: {exc}",
            remediation='pip install "praisonai-train[llm]"',
        )
        raise typer.Exit(1)

    import subprocess

    try:
        trainer = TrainModel.for_export(cfg)
        model, tokenizer = trainer.load_model()
        trainer.model = model
        trainer.hf_tokenizer = tokenizer
        if target == "hf":
            trainer.save_model_merged()
        elif target == "gguf":
            # Always produce a LOCAL .gguf so it can be served (and paired with an
            # MTP drafter). Push to the Hub additionally only when --hf is set.
            trainer.save_model_gguf()
            if hf:
                trainer.push_model_gguf()
        else:
            trainer.create_and_push_ollama_model()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        output.print_error(str(exc))
        raise typer.Exit(1)

    # Optionally fetch the stock MTP drafter for fast (self-speculative) inference.
    if mtp_draft:
        from praisonai_train.train import _mtp
        try:
            drafter_path = _mtp.fetch_drafter(cfg["model_name"], model_dir)
            output.print_success(f"Downloaded MTP drafter -> {drafter_path}")
        except (ValueError, RuntimeError) as exc:
            output.print_warning(f"Skipped MTP drafter: {exc}")

    output.print_success(f"Exported model to {target}.")


@app.command("list")
def train_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions to show"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    storage_backend: Optional[str] = typer.Option(
        None,
        "--storage-backend",
        help="Storage backend: 'file', 'sqlite', or 'redis://url'. Default: file"
    ),
    storage_path: Optional[str] = typer.Option(
        None,
        "--storage-path",
        help="Path for storage backend (file dir or sqlite db path)"
    ),
):
    """List all training sessions."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai_train.train.agents.storage import (
            list_sessions_from_backend,
            list_training_sessions,
        )
    except ImportError:
        output.print_error("Training module not available")
        raise typer.Exit(1)
    
    if storage_backend and storage_backend != "file":
        backend = _create_storage_backend(storage_backend, storage_path, output)
        if backend is None:
            raise typer.Exit(1)
        sessions = list_sessions_from_backend(backend, limit=limit)
    elif storage_backend == "file" and storage_path:
        # Custom file directory: scan the requested path, not the default dir.
        sessions = list_training_sessions(
            storage_dir=Path(storage_path).expanduser(), limit=limit
        )
    else:
        sessions = list_training_sessions(limit=limit)
    
    if json_output or output.is_json_mode:
        output.print_json({
            "sessions": [s.to_dict() for s in sessions]
        })
        return
    
    if not sessions:
        output.print_info("No training sessions found")
        return
    
    headers = ["Session ID", "Iterations", "Size", "Modified"]
    rows = []
    
    for s in sessions:
        modified = s.modified_at.strftime("%Y-%m-%d %H:%M")
        size_kb = s.size_bytes / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb >= 1 else f"{s.size_bytes} B"
        
        rows.append([
            s.session_id[:30] + "..." if len(s.session_id) > 30 else s.session_id,
            str(s.iteration_count),
            size_str,
            modified,
        ])
    
    output.print_table(headers, rows, title="Training Sessions")


@app.command("show")
def train_show(
    session_id: str = typer.Argument(..., help="Session ID to show"),
    iterations_flag: bool = typer.Option(False, "--iterations", "-i", help="Show detailed iteration info"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    storage_backend: Optional[str] = typer.Option(
        None,
        "--storage-backend",
        help="Storage backend: 'file', 'sqlite', or 'redis://url'. Default: file"
    ),
    storage_path: Optional[str] = typer.Option(
        None,
        "--storage-path",
        help="Path for storage backend (file dir or sqlite db path)"
    ),
):
    """
    Show details of a training session.
    
    Examples:
        # Show session summary
        praisonai train show train-abc123
        
        # Show with detailed iterations
        praisonai train show train-abc123 --iterations
        
        # Output as JSON
        praisonai train show train-abc123 --json
        
        # Session stored in a SQLite database
        praisonai train show train-abc123 \\
            --storage-backend sqlite --storage-path /data/train.db
    """
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai_train.train.agents.models import console_supports_unicode
    except ImportError:
        output.print_error("Training module not available")
        raise typer.Exit(1)

    storage = _open_session_storage(
        session_id, storage_backend, storage_path, output
    )
    
    report = storage.load_report()
    iterations = storage.load_iterations()
    
    if json_output or output.is_json_mode:
        output.print_json({
            "session_id": session_id,
            "report": report.to_dict() if report else None,
            "iterations": [it.to_dict() for it in iterations],
        })
        return
    
    if report:
        report.print_summary()
        
        # Show best iteration
        best = report.get_best_iteration()
        if best:
            best_prefix = "✨ Best Iteration:" if console_supports_unicode() else "Best Iteration:"
            output.print(f"\n{best_prefix} #{best.iteration_num} (Score: {best.score}/10)")
    
    if iterations:
        output.print("\nIterations:")
        
        # Find best score for highlighting
        best_score = max(it.score for it in iterations) if iterations else 0
        
        best_marker = "★" if console_supports_unicode() else "*"
        for it in iterations:
            # Highlight best iteration
            marker = best_marker if it.score == best_score else " "
            feedback_preview = it.feedback[:50] + "..." if len(it.feedback) > 50 else it.feedback
            output.print(f"  {marker} [{it.iteration_num}] Score: {it.score}/10 - {feedback_preview}")
            
            # Show suggestions if --iterations flag
            if iterations_flag and it.suggestions:
                for suggestion in it.suggestions[:3]:  # Show top 3 suggestions
                    output.print(f"      → {suggestion}")


@app.command("apply")
def train_apply(
    session_id: str = typer.Argument(..., help="Training session ID to apply"),
    agent_file: Optional[str] = typer.Option(
        None,
        "--agent", "-a",
        help="Path to agent YAML file"
    ),
    iteration: Optional[int] = typer.Option(
        None,
        "--iteration", "-n",
        help="Specific iteration number (default: best score)"
    ),
    run_prompt: Optional[str] = typer.Option(
        None,
        "--run", "-r",
        help="Run agent with this prompt after applying training"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    storage_backend: Optional[str] = typer.Option(
        None,
        "--storage-backend",
        help="Storage backend: 'file', 'sqlite', or 'redis://url'. Default: file"
    ),
    storage_path: Optional[str] = typer.Option(
        None,
        "--storage-path",
        help="Path for storage backend (file dir or sqlite db path)"
    ),
):
    """
    Apply training to an agent.
    
    Loads training suggestions from a session and applies them to an agent
    via hooks. By default, uses the iteration with the best score.
    
    Examples:
        # Apply best iteration to default agent
        praisonai train apply train-abc123
        
        # Apply specific iteration
        praisonai train apply train-abc123 --iteration 2
        
        # Apply to agent from YAML file
        praisonai train apply train-abc123 --agent my_agent.yaml
        
        # Apply and run immediately
        praisonai train apply train-abc123 --run "Hello, how are you?"
        
        # Session stored in a SQLite database
        praisonai train apply train-abc123 \\
            --storage-backend sqlite --storage-path /data/train.db
    """
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai_train.train.agents import apply_training, get_training_profile
    except ImportError as e:
        output.print_error(f"Training module not available: {e}")
        raise typer.Exit(1)
    
    # Verify session exists (backend-aware)
    backend = _resolve_backend(storage_backend, storage_path, output)
    storage = _open_session_storage(
        session_id, storage_backend, storage_path, output, backend=backend
    )
    
    # Load the agent early (if provided) to resolve the correct agent name for
    # the profile and to avoid loading the file a second time when --run is set.
    agent = None
    agent_name = "agent"
    if agent_file:
        agent = _load_agent_from_file(agent_file, output)
        if agent is None:
            raise typer.Exit(1)
        if getattr(agent, "name", None):
            agent_name = agent.name
    
    # Get the training profile
    profile = get_training_profile(
        session_id=session_id,
        iteration=iteration,
        agent_name=agent_name,
        backend=backend,
    )
    
    if profile is None:
        output.print_error(f"Could not load training profile from session {session_id}")
        raise typer.Exit(1)
    
    if json_output or output.is_json_mode:
        output.print_json({
            "session_id": session_id,
            "iteration": profile.iteration_num,
            "score": profile.quality_score,
            "suggestions": profile.suggestions,
            "summary": profile.summary,
        })
        if not run_prompt:
            return
    
    # Show profile info
    output.print_panel(
        f"Session: {profile.session_id}\n"
        f"Iteration: {profile.iteration_num}\n"
        f"Score: {profile.quality_score}/10\n"
        f"Suggestions: {len(profile.suggestions)}",
        title="Training Profile"
    )
    
    if profile.suggestions:
        output.print("\nSuggestions:")
        for i, suggestion in enumerate(profile.suggestions, 1):
            output.print(f"  {i}. {suggestion}")
    
    # If run_prompt provided, create agent and run
    if run_prompt:
        # Reuse the agent loaded above when an agent file was given; otherwise
        # fall back to a default agent.
        if agent is None:
            try:
                from praisonaiagents import Agent
                agent = Agent(
                    instructions="You are a helpful assistant."
                )
            except ImportError:
                output.print_error(
                    "praisonaiagents not installed",
                    remediation="pip install praisonaiagents"
                )
                raise typer.Exit(1)
        
        # Apply training
        success = apply_training(agent, profile=profile)
        if not success:
            output.print_error("Failed to apply training to agent")
            raise typer.Exit(1)
        
        output.print_success("Training applied successfully!")
        output.print(f"\nRunning agent with prompt: {run_prompt}\n")
        
        # Run the agent
        try:
            if hasattr(agent, 'chat'):
                response = agent.chat(run_prompt)
            elif hasattr(agent, 'start'):
                response = agent.start(run_prompt)
            else:
                output.print_error("Agent has no chat or start method")
                raise typer.Exit(1)
            
            output.print_panel(str(response), title="Agent Response")
        except Exception as e:
            output.print_error(f"Agent execution failed: {e}")
            raise typer.Exit(1)
    else:
        output.print_info(
            "\nTo apply this training to an agent, use:\n"
            f"  praisonai train apply {session_id} --run 'Your prompt here'\n"
            "\nOr in Python:\n"
            f"  from praisonai_train.train.agents import apply_training\n"
            f"  apply_training(agent, session_id='{session_id}')"
        )


def _load_agent_from_file(file_path: str, output) -> Optional[object]:
    """Load agent from YAML or Python file."""
    path = Path(file_path)
    
    if not path.exists():
        output.print_error(f"File not found: {file_path}")
        return None
    
    if path.suffix in ('.yaml', '.yml'):
        try:
            from praisonai_train._code_bridge import import_code_module

            PraisonAI = import_code_module("praisonai_code.cli.main").PraisonAI
            praison = PraisonAI(agent_file=str(path))
            # Return the agents object
            if hasattr(praison, 'agents') and praison.agents:
                return praison.agents
            output.print_error("Could not load agents from YAML")
            return None
        except Exception as e:
            output.print_error(f"Failed to load YAML: {e}")
            return None
    
    elif path.suffix == '.py':
        output.print_warning(
            "Python file support coming soon. "
            "For now, use YAML files or --input flag."
        )
        return None
    
    else:
        output.print_error(f"Unsupported file type: {path.suffix}")
        return None


def _resolve_backend(backend_type: Optional[str], storage_path: Optional[str], output):
    """
    Resolve a storage backend from CLI flags, or None for the default JSON dir.

    Returns None when no backend is requested, or when the plain ``file`` backend
    is requested without a custom path, so that existing default-directory
    behaviour is preserved. When ``file`` is combined with a custom
    ``storage_path`` a FileBackend for that directory is returned so sessions
    written there are discoverable. Exits with an error if a backend is
    requested but cannot be created.
    """
    if not backend_type:
        return None
    if backend_type == "file" and not storage_path:
        return None
    backend = _create_storage_backend(backend_type, storage_path, output)
    if backend is None:
        raise typer.Exit(1)
    return backend


def _open_session_storage(
    session_id: str,
    backend_type: Optional[str],
    storage_path: Optional[str],
    output,
    backend=None,
):
    """
    Open a TrainingStorage for a session, honouring backend flags.

    Uses backend-aware existence checking so SQLite-only sessions (no JSON
    sidecar) are found. Exits with an error if the session does not exist.
    """
    from praisonai_train.train.agents.storage import TrainingStorage

    if backend is None:
        backend = _resolve_backend(backend_type, storage_path, output)

    storage = TrainingStorage(session_id=session_id, backend=backend)
    if not storage.exists():
        output.print_error(f"Session not found: {session_id}")
        raise typer.Exit(1)
    return storage


def _create_storage_backend(backend_type: str, storage_path: Optional[str], output):
    """Create storage backend from CLI options."""
    try:
        if backend_type == "file":
            from praisonaiagents.storage import FileBackend
            path = str(Path(storage_path or "~/.praison/train").expanduser())
            return FileBackend(storage_dir=path)
        elif backend_type == "sqlite":
            from praisonaiagents.storage import SQLiteBackend
            db_path = str(Path(storage_path or "~/.praison/train.db").expanduser())
            return SQLiteBackend(db_path=db_path)
        elif backend_type.startswith("redis://"):
            from praisonaiagents.storage import RedisBackend
            return RedisBackend(url=backend_type, prefix="train:")
        else:
            output.print_error(
                f"Unknown storage backend: {backend_type}",
                remediation="Use 'file', 'sqlite', or 'redis://url'"
            )
            return None
    except ImportError as e:
        output.print_error(f"Failed to import storage backend: {e}")
        return None
    except Exception as e:
        output.print_error(f"Failed to create storage backend: {e}")
        return None


def _load_scenarios_from_file(file_path: str, output) -> Optional[list]:
    """Load scenarios from JSON file."""
    path = Path(file_path)
    
    if not path.exists():
        output.print_error(f"Scenarios file not found: {file_path}")
        return None
    
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "scenarios" in data:
            return data["scenarios"]
        else:
            output.print_error("Invalid scenarios format. Expected list or {scenarios: [...]}")
            return None
    except json.JSONDecodeError as e:
        output.print_error(f"Invalid JSON: {e}")
        return None


# --- sibling command registration -------------------------------------------
#
# Every other command module does `from ...commands.train import app` and
# registers onto that object as an import side effect. `praisonai_train/cli/
# app.py` imports them all — but the integrated CLI
# (praisonai_code/cli/app.py:429) imports THIS module directly and never that
# one, so `praisonai train` exposed 6 of 15 commands and the whole `remote`
# group was unreachable.
#
# Imported at the bottom, after `app` exists, so the siblings' own
# `from ...train import app` resolves. Failures are swallowed per module: a
# missing optional dependency in one command must not take down the others.
def _register_sibling_commands() -> None:
    import importlib

    for name in ("data", "benchmark", "serve", "remote", "run", "catalog"):
        try:
            importlib.import_module(f"praisonai_train.cli.commands.{name}")
        except Exception:  # noqa: BLE001 - one bad command must not hide the rest
            pass


_register_sibling_commands()
