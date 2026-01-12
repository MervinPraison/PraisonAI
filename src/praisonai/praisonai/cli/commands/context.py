"""
Context command group for PraisonAI CLI.

Provides context management commands:
- stats: Show context statistics
- compact: Manually trigger context compaction
- export: Export context to file
- show: Show current context
- clear: Clear current context
"""

import typer

app = typer.Typer(help="Context management")


@app.command("show")
def context_show(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Show current context."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['context', 'show']
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


@app.command("clear")
def context_clear():
    """Clear current context."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['context', 'clear']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("add")
def context_add(
    content: str = typer.Argument(..., help="Content to add to context"),
):
    """Add content to context."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['context', 'add', content]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("stats")
def context_stats(
    agent: str = typer.Option("", "--agent", "-a", help="Agent name to show stats for"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """
    Show context management statistics.
    
    Displays token usage, utilization, cache stats, and optimization history.
    """
    try:
        from praisonaiagents.context import get_metrics
        import json
        
        # Get global metrics
        metrics = get_metrics()
        stats = metrics.to_dict()
        
        if json_output:
            print(json.dumps(stats, indent=2))
        else:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            # Timing table
            timing_table = Table(title="Context Operation Timing")
            timing_table.add_column("Operation", style="cyan")
            timing_table.add_column("Calls", justify="right")
            timing_table.add_column("Avg (ms)", justify="right")
            timing_table.add_column("Max (ms)", justify="right")
            
            for op, data in stats["timing"].items():
                timing_table.add_row(
                    op,
                    str(data["calls"]),
                    f"{data['avg_ms']:.2f}",
                    f"{data['max_ms']:.2f}",
                )
            
            console.print(timing_table)
            
            # Token stats
            console.print("\n[bold]Token Statistics:[/bold]")
            console.print(f"  Processed: {stats['tokens']['processed']:,}")
            console.print(f"  Saved: {stats['tokens']['saved']:,}")
            console.print(f"  Compactions: {stats['tokens']['compactions']}")
            
            # Cache stats
            console.print("\n[bold]Cache Statistics:[/bold]")
            console.print(f"  Hits: {stats['cache']['hits']:,}")
            console.print(f"  Misses: {stats['cache']['misses']:,}")
            console.print(f"  Hit Rate: {stats['cache']['hit_rate']:.1%}")
            
    except ImportError as e:
        typer.echo(f"Error: Context module not available: {e}", err=True)
        raise typer.Exit(1)


@app.command("compact")
def context_compact(
    agent: str = typer.Option("", "--agent", "-a", help="Agent name to compact"),
    threshold: float = typer.Option(0.8, "--threshold", "-t", help="Compaction threshold (0.0-1.0)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be compacted without doing it"),
):
    """
    Manually trigger context compaction.
    
    Compacts context when utilization exceeds threshold.
    """
    try:
        from praisonaiagents.context import get_global_store
        
        store = get_global_store()
        stats = store.get_stats()
        
        if dry_run:
            typer.echo("[Dry Run] Current store stats:")
            typer.echo(f"  Agents: {stats['agent_count']}")
            typer.echo(f"  Total messages: {stats['total_messages']}")
            for agent_id, agent_stats in stats.get("agents", {}).items():
                typer.echo(f"  {agent_id}: {agent_stats['message_count']} messages, {agent_stats['effective_count']} effective")
        else:
            # Cleanup orphaned parents for all agents
            for agent_id in stats.get("agents", {}).keys():
                if agent and agent_id != agent:
                    continue
                store.cleanup_agent(agent_id)
                typer.echo(f"Cleaned up agent: {agent_id}")
            
            typer.echo("Compaction complete.")
            
    except ImportError as e:
        typer.echo(f"Error: Context module not available: {e}", err=True)
        raise typer.Exit(1)


@app.command("export")
def context_export(
    output: str = typer.Argument("context_export.json", help="Output file path"),
    agent: str = typer.Option("", "--agent", "-a", help="Agent name to export"),
    format: str = typer.Option("json", "--format", "-f", help="Export format (json, txt)"),
):
    """
    Export context to a file.
    
    Exports the current context store state for debugging or backup.
    """
    try:
        from praisonaiagents.context import get_global_store
        from pathlib import Path
        
        store = get_global_store()
        
        if format == "json":
            data = store.snapshot()
            output_path = Path(output)
            output_path.write_bytes(data)
            typer.echo(f"Exported context to: {output_path}")
        else:
            # Text format
            stats = store.get_stats()
            output_path = Path(output)
            
            lines = ["# Context Export", ""]
            lines.append(f"Agents: {stats['agent_count']}")
            lines.append(f"Total Messages: {stats['total_messages']}")
            lines.append("")
            
            for agent_id, agent_stats in stats.get("agents", {}).items():
                if agent and agent_id != agent:
                    continue
                lines.append(f"## Agent: {agent_id}")
                lines.append(f"Messages: {agent_stats['message_count']}")
                lines.append(f"Effective: {agent_stats['effective_count']}")
                lines.append("")
            
            output_path.write_text("\n".join(lines))
            typer.echo(f"Exported context to: {output_path}")
            
    except ImportError as e:
        typer.echo(f"Error: Context module not available: {e}", err=True)
        raise typer.Exit(1)


# =============================================================================
# Artifact Commands (Dynamic Context Discovery)
# =============================================================================

artifacts_app = typer.Typer(help="Artifact management for dynamic context discovery")
app.add_typer(artifacts_app, name="artifacts")


@artifacts_app.command("list")
def artifacts_list(
    run_id: str = typer.Option(None, "--run-id", "-r", help="Filter by run ID"),
    agent_id: str = typer.Option(None, "--agent-id", "-a", help="Filter by agent ID"),
    tool_name: str = typer.Option(None, "--tool", "-t", help="Filter by tool name"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List artifacts."""
    try:
        from praisonai.context import FileSystemArtifactStore
        import json as json_module
        
        store = FileSystemArtifactStore()
        artifacts = store.list_artifacts(
            run_id=run_id,
            agent_id=agent_id,
            tool_name=tool_name,
        )
        
        if json_output:
            data = [a.to_dict() for a in artifacts]
            print(json_module.dumps(data, indent=2))
        else:
            if not artifacts:
                typer.echo("No artifacts found.")
                return
            
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title=f"Artifacts ({len(artifacts)} found)")
            table.add_column("ID", style="cyan")
            table.add_column("Tool", style="green")
            table.add_column("Size", justify="right")
            table.add_column("Summary")
            table.add_column("Path", style="dim")
            
            for ref in artifacts:
                size_str = ref._format_size(ref.size_bytes)
                table.add_row(
                    ref.artifact_id,
                    ref.tool_name or "-",
                    size_str,
                    ref.summary[:40] + "..." if len(ref.summary) > 40 else ref.summary,
                    ref.path,
                )
            
            console.print(table)
            
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@artifacts_app.command("show")
def artifacts_show(
    artifact_path: str = typer.Argument(..., help="Path to artifact"),
    lines: int = typer.Option(None, "--lines", "-n", help="Number of lines to show"),
):
    """Show artifact content."""
    try:
        from praisonai.context import FileSystemArtifactStore
        from praisonaiagents.context.artifacts import ArtifactRef
        
        store = FileSystemArtifactStore()
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0)
        
        if lines:
            content = store.head(ref, lines=lines)
        else:
            content = store.load(ref)
            if not isinstance(content, str):
                import json
                content = json.dumps(content, indent=2)
        
        typer.echo(content)
        
    except FileNotFoundError:
        typer.echo(f"Artifact not found: {artifact_path}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@artifacts_app.command("tail")
def artifacts_tail(
    artifact_path: str = typer.Argument(..., help="Path to artifact"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines"),
):
    """Get last N lines of artifact."""
    try:
        from praisonai.context import FileSystemArtifactStore
        from praisonaiagents.context.artifacts import ArtifactRef
        
        store = FileSystemArtifactStore()
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0)
        content = store.tail(ref, lines=lines)
        typer.echo(content)
        
    except FileNotFoundError:
        typer.echo(f"Artifact not found: {artifact_path}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@artifacts_app.command("grep")
def artifacts_grep(
    artifact_path: str = typer.Argument(..., help="Path to artifact"),
    pattern: str = typer.Argument(..., help="Search pattern (regex)"),
    context_lines: int = typer.Option(2, "--context", "-C", help="Context lines"),
    max_matches: int = typer.Option(50, "--max", "-m", help="Max matches"),
):
    """Search for pattern in artifact."""
    try:
        from praisonai.context import FileSystemArtifactStore
        from praisonaiagents.context.artifacts import ArtifactRef
        
        store = FileSystemArtifactStore()
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0)
        matches = store.grep(ref, pattern=pattern, context_lines=context_lines, max_matches=max_matches)
        
        if not matches:
            typer.echo(f"No matches found for: {pattern}")
            return
        
        from rich.console import Console
        console = Console()
        
        console.print(f"[bold]Found {len(matches)} matches:[/bold]")
        for match in matches:
            console.print(f"\n[cyan]--- Line {match.line_number} ---[/cyan]")
            for ctx in match.context_before:
                console.print(f"  {ctx}", style="dim")
            console.print(f"[green]> {match.line_content}[/green]")
            for ctx in match.context_after:
                console.print(f"  {ctx}", style="dim")
        
    except FileNotFoundError:
        typer.echo(f"Artifact not found: {artifact_path}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Invalid pattern: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@artifacts_app.command("export")
def artifacts_export(
    artifact_path: str = typer.Argument(..., help="Path to artifact"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """Export artifact to file."""
    try:
        from pathlib import Path
        import shutil
        
        src_path = Path(artifact_path)
        if not src_path.exists():
            typer.echo(f"Artifact not found: {artifact_path}", err=True)
            raise typer.Exit(1)
        
        if output:
            dst_path = Path(output)
        else:
            dst_path = Path.cwd() / src_path.name
        
        shutil.copy2(src_path, dst_path)
        typer.echo(f"Exported to: {dst_path}")
        
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
