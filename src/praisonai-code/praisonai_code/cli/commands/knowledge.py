"""
Knowledge command group for PraisonAI CLI.

Provides knowledge base management commands:
- index: Add/index documents into a knowledge base (canonical indexing command)
- search: Search/retrieve from knowledge base (no generation)
- list: List available knowledge bases

Knowledge is the canonical substrate for indexing and retrieval.
For answering questions with citations, use `praisonai rag query`.
"""

import typer
from typing import Optional, List
from pathlib import Path
from contextlib import contextmanager
import time
import json as json_module

app = typer.Typer(help="Knowledge base management (indexing and retrieval)")


@contextmanager
def knowledge_profiler(enabled: bool, profile_out: Optional[Path], profile_top: int = 20):
    """
    Context manager for knowledge command profiling.
    
    Uses the existing praisonai.profiler infrastructure when available,
    falls back to basic timing if not.
    """
    if not enabled:
        yield None
        return
    
    import sys
    start_time = time.perf_counter()
    start_modules = set(sys.modules.keys())
    
    # Try to use the full profiler
    profiler = None
    try:
        from praisonai.profiler import Profiler
        Profiler.enable()
        Profiler.clear()
        profiler = Profiler
    except ImportError:
        pass
    
    # Try tracemalloc for memory
    try:
        import tracemalloc
        tracemalloc.start()
    except Exception:
        tracemalloc = None
    
    profile_data = {
        "command": "knowledge",
        "start_time": time.time(),
        "metrics": {},
        "imports": [],
        "top_functions": [],
    }
    
    try:
        yield profile_data
    finally:
        end_time = time.perf_counter()
        elapsed_ms = (end_time - start_time) * 1000
        
        # Collect metrics
        profile_data["metrics"]["wall_time_ms"] = elapsed_ms
        profile_data["metrics"]["wall_time_s"] = elapsed_ms / 1000
        
        # Memory usage
        if tracemalloc:
            try:
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                profile_data["metrics"]["peak_memory_mb"] = peak / (1024 * 1024)
                profile_data["metrics"]["current_memory_mb"] = current / (1024 * 1024)
            except Exception:
                pass
        
        # New imports during execution
        end_modules = set(sys.modules.keys())
        new_modules = end_modules - start_modules
        profile_data["imports"] = sorted(list(new_modules))[:profile_top]
        profile_data["metrics"]["modules_imported"] = len(new_modules)
        
        # Get profiler data if available
        if profiler:
            try:
                profiler.disable()
                stats = profiler.get_statistics()
                if stats:
                    profile_data["top_functions"] = stats.get("top_functions", [])[:profile_top]
                    profile_data["metrics"].update(stats.get("summary", {}))
            except Exception:
                pass
        
        # Save to file if requested
        if profile_out:
            try:
                profile_out.parent.mkdir(parents=True, exist_ok=True)
                with open(profile_out, "w") as f:
                    json_module.dump(profile_data, f, indent=2, default=str)
            except Exception as e:
                print(f"Warning: Failed to save profile: {e}")
        
        # Print summary
        from rich.console import Console
        console = Console(stderr=True)
        console.print(f"\n[dim]Profile: {elapsed_ms:.2f}ms wall time[/dim]")
        if "peak_memory_mb" in profile_data["metrics"]:
            console.print(f"[dim]Profile: {profile_data['metrics']['peak_memory_mb']:.2f}MB peak memory[/dim]")
        console.print(f"[dim]Profile: {len(new_modules)} modules imported[/dim]")
        if profile_out:
            console.print(f"[dim]Profile saved to: {profile_out}[/dim]")


@app.command("index")
def knowledge_index(
    sources: List[str] = typer.Argument(..., help="Source files, directories, or URLs to index"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection/knowledge base name"),
    user_id: Optional[str] = typer.Option(None, "--user-id", "-u", help="User ID for scoping (required for mem0 backend)"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", "-a", help="Agent ID for scoping"),
    run_id: Optional[str] = typer.Option(None, "--run-id", "-r", help="Run ID for scoping"),
    backend: str = typer.Option("mem0", "--backend", "-b", help="Knowledge backend: mem0, chroma, internal"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Index documents into a knowledge base.
    
    This is the canonical command for adding documents to a knowledge base.
    Use `praisonai rag query` to answer questions using the indexed knowledge.
    
    Examples:
        praisonai knowledge index ./docs --user-id myuser
        praisonai knowledge index paper.pdf --collection research --agent-id research_agent
        praisonai knowledge index ./data --backend chroma --profile
    """
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    console = Console()
    
    with knowledge_profiler(profile, profile_out, profile_top) as profile_data:
        try:
            # Lazy import to avoid startup cost
            from praisonaiagents.knowledge import Knowledge
            
            # Validate scope for mem0 backend
            if backend == "mem0" and not any([user_id, agent_id, run_id]):
                console.print("[yellow]Warning:[/yellow] mem0 backend requires at least one scope identifier.")
                console.print("Use --user-id, --agent-id, or --run-id to scope your knowledge.")
                console.print("Defaulting to user_id='default_user'")
                user_id = "default_user"
            
            # Build config based on backend
            if backend == "chroma":
                knowledge_config = {
                    "vector_store": {
                        "provider": "chroma",
                        "config": {
                            "collection_name": collection,
                            "path": f"./.praison/knowledge/{collection}",
                        }
                    }
                }
            else:
                # mem0 or internal backend
                knowledge_config = {
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "collection_name": collection,
                        }
                    }
                }
            
            # Load config file if provided
            if config and config.exists():
                import yaml
                with open(config) as f:
                    file_config = yaml.safe_load(f)
                    if "knowledge" in file_config:
                        knowledge_config.update(file_config["knowledge"])
            
            # Initialize Knowledge
            knowledge = Knowledge(config=knowledge_config, verbose=verbose)
            
            # Index sources with scope identifiers
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                for source in sources:
                    task = progress.add_task(f"Indexing {source}...", total=None)
                    try:
                        result = knowledge.add(
                            source,
                            user_id=user_id,
                            agent_id=agent_id,
                            run_id=run_id,
                        )
                        count = len(result.get("results", [])) if isinstance(result, dict) else 0
                        console.print(f"[green]✓[/green] Indexed {source}: {count} chunks")
                    except Exception as e:
                        console.print(f"[red]✗[/red] Failed to index {source}: {e}")
                    progress.remove_task(task)
            
            console.print(f"\n[bold green]Indexing complete![/bold green] Collection: {collection}")
            if profile_data:
                profile_data["command"] = "knowledge index"
                profile_data["collection"] = collection
                profile_data["sources"] = sources
            
        except ImportError as e:
            console.print(f"[red]Error:[/red] Missing dependency: {e}")
            console.print("Install with: pip install 'praisonaiagents[knowledge]'")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)


@app.command("search")
def knowledge_search(
    query: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection to search"),
    user_id: Optional[str] = typer.Option(None, "--user-id", "-u", help="User ID for scoping (required for mem0 backend)"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", "-a", help="Agent ID for scoping"),
    run_id: Optional[str] = typer.Option(None, "--run-id", "-r", help="Run ID for scoping"),
    backend: str = typer.Option("mem0", "--backend", "-b", help="Knowledge backend: mem0, chroma, internal"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to retrieve"),
    hybrid: bool = typer.Option(False, "--hybrid", help="Use hybrid retrieval (dense + BM25)"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Search/retrieve from a knowledge base (no LLM generation).
    
    Returns raw search results without generating an answer.
    For answers with citations, use `praisonai rag query`.
    
    Examples:
        praisonai knowledge search "capital of France" --user-id myuser
        praisonai knowledge search "main findings" --collection research --top-k 10
        praisonai knowledge search "Python tutorial" --hybrid --backend chroma
    """
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    with knowledge_profiler(profile, profile_out, profile_top) as profile_data:
        try:
            from praisonaiagents.knowledge import Knowledge
            
            # Validate scope for mem0 backend
            if backend == "mem0" and not any([user_id, agent_id, run_id]):
                console.print("[yellow]Warning:[/yellow] mem0 backend requires at least one scope identifier.")
                console.print("Use --user-id, --agent-id, or --run-id to scope your search.")
                console.print("Defaulting to user_id='default_user'")
                user_id = "default_user"
            
            # Build config based on backend
            if backend == "chroma":
                knowledge_config = {
                    "vector_store": {
                        "provider": "chroma",
                        "config": {
                            "collection_name": collection,
                            "path": f"./.praison/knowledge/{collection}",
                        }
                    }
                }
            else:
                # mem0 or internal backend
                knowledge_config = {
                    "vector_store": {
                        "provider": "qdrant",
                        "config": {
                            "collection_name": collection,
                        }
                    }
                }
            
            # Add hybrid retrieval config if enabled
            if hybrid:
                knowledge_config["retrieval"] = {
                    "strategy": "hybrid",
                }
            
            # Load config file if provided
            if config and config.exists():
                import yaml
                with open(config) as f:
                    file_config = yaml.safe_load(f)
                    if "knowledge" in file_config:
                        knowledge_config.update(file_config["knowledge"])
            
            # Initialize and search
            knowledge = Knowledge(config=knowledge_config, verbose=verbose)
            
            # Use hybrid search if enabled, pass scope identifiers
            if hybrid:
                if verbose:
                    console.print("[dim]Using hybrid retrieval (dense + BM25)...[/dim]")
                results = knowledge.search(
                    query, limit=top_k, hybrid=True,
                    user_id=user_id, agent_id=agent_id, run_id=run_id,
                )
            else:
                results = knowledge.search(
                    query, limit=top_k,
                    user_id=user_id, agent_id=agent_id, run_id=run_id,
                )
            
            if not results:
                console.print("[yellow]No results found.[/yellow]")
                return
            
            # Display results
            table = Table(title=f"Search Results for: {query}")
            table.add_column("#", style="dim", width=3)
            table.add_column("Score", width=8)
            table.add_column("Source", width=20)
            table.add_column("Content", width=60)
            
            result_list = results.get('results', results) if isinstance(results, dict) else results
            for i, result in enumerate(result_list[:top_k], 1):
                if isinstance(result, dict):
                    score = f"{result.get('score', 0):.3f}" if result.get('score') else "-"
                    # CRITICAL: Handle metadata=None from mem0
                    metadata = result.get('metadata') or {}
                    source = metadata.get('filename', metadata.get('source', '-'))
                    content = result.get('memory', result.get('text', ''))[:100] + "..."
                else:
                    score = "-"
                    source = "-"
                    content = str(result)[:100] + "..."
                
                table.add_row(str(i), score, source, content)
            
            console.print(table)
            
            if profile_data:
                profile_data["command"] = "knowledge search"
                profile_data["collection"] = collection
                profile_data["query"] = query
                profile_data["num_results"] = len(result_list)
            
        except ImportError as e:
            console.print(f"[red]Error:[/red] Missing dependency: {e}")
            console.print("Install with: pip install 'praisonaiagents[knowledge]'")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            if verbose:
                import traceback
                console.print(traceback.format_exc())
            raise typer.Exit(1)


@app.command("add")
def knowledge_add(
    sources: List[str] = typer.Argument(..., help="Source files, directories, or URLs to index"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection/knowledge base name"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Add documents to a knowledge base (alias for 'index').
    
    This is a backward-compatible alias for `praisonai knowledge index`.
    
    Examples:
        praisonai knowledge add ./docs
        praisonai knowledge add paper.pdf --collection research
    """
    # Delegate to index command
    knowledge_index(
        sources=sources,
        collection=collection,
        config=config,
        verbose=verbose,
        profile=profile,
        profile_out=profile_out,
        profile_top=profile_top,
    )


@app.command("list")
def knowledge_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """List available knowledge bases/collections."""
    from rich.console import Console
    from rich.table import Table
    import os
    
    console = Console()
    
    # Check for knowledge directories
    knowledge_dirs = ["./.praison/knowledge", "./.praison/rag", ".praison"]
    collections = set()
    
    for base_dir in knowledge_dirs:
        if os.path.exists(base_dir):
            for item in os.listdir(base_dir):
                item_path = os.path.join(base_dir, item)
                if os.path.isdir(item_path):
                    collections.add((item, base_dir))
    
    if not collections:
        console.print("[yellow]No knowledge bases found.[/yellow]")
        console.print("Create one with: praisonai knowledge index ./docs --collection myknowledge")
        return
    
    table = Table(title="Knowledge Bases")
    table.add_column("Collection", style="cyan")
    table.add_column("Path", style="dim")
    
    for name, path in sorted(collections):
        table.add_row(name, os.path.join(path, name))
    
    console.print(table)
