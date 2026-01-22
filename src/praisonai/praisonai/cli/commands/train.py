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


@app.command("llm")
def train_llm(
    dataset: str = typer.Argument(..., help="Training dataset path"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Base model to fine-tune"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Fine-tune LLM models using Unsloth.
    
    Examples:
        praisonai train llm dataset.json
        praisonai train llm --model llama-3.1 dataset.json
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['train', dataset]
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("agents")
def train_agents(
    agent_file: Optional[str] = typer.Argument(
        None,
        help="Path to agent YAML file or Python file"
    ),
    iterations: int = typer.Option(
        3,
        "--iterations", "-n",
        help="Number of training iterations"
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
        from praisonai.train.agents import AgentTrainer, TrainingScenario
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
    
    from praisonai.train.agents.grader import TrainingGrader
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
    
    # Run training
    try:
        report = trainer.run()
        
        if not verbose:
            report.print_summary()
        
        output.print_success(
            f"Training complete! Session: {report.session_id}\n"
            f"Average score: {report.avg_score:.1f}/10\n"
            f"Improvement: {report.improvement:+.1f}"
        )
        
    except KeyboardInterrupt:
        output.print_warning("Training interrupted by user")
        raise typer.Exit(130)
    except Exception as e:
        output.print_error(f"Training failed: {e}")
        raise typer.Exit(1)


@app.command("list")
def train_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Max sessions to show"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List all training sessions."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.train.agents.storage import list_training_sessions
    except ImportError:
        output.print_error("Training module not available")
        raise typer.Exit(1)
    
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
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show details of a training session."""
    from ..output.console import get_output_controller
    
    output = get_output_controller()
    
    try:
        from praisonai.train.agents.storage import TrainingStorage
    except ImportError:
        output.print_error("Training module not available")
        raise typer.Exit(1)
    
    storage = TrainingStorage(session_id=session_id)
    
    if not storage.storage_path.exists():
        output.print_error(f"Session not found: {session_id}")
        raise typer.Exit(1)
    
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
    
    if iterations:
        output.print("\nIterations:")
        for it in iterations:
            output.print(f"  [{it.iteration_num}] Score: {it.score}/10 - {it.feedback[:50]}...")


def _load_agent_from_file(file_path: str, output) -> Optional[object]:
    """Load agent from YAML or Python file."""
    path = Path(file_path)
    
    if not path.exists():
        output.print_error(f"File not found: {file_path}")
        return None
    
    if path.suffix in ('.yaml', '.yml'):
        try:
            from praisonai.cli.main import PraisonAI
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


def _create_storage_backend(backend_type: str, storage_path: Optional[str], output):
    """Create storage backend from CLI options."""
    try:
        if backend_type == "file":
            from praisonaiagents.storage import FileBackend
            return FileBackend(storage_dir=storage_path or "~/.praison/train")
        elif backend_type == "sqlite":
            from praisonaiagents.storage import SQLiteBackend
            db_path = storage_path or "~/.praison/train.db"
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
        with open(path) as f:
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
