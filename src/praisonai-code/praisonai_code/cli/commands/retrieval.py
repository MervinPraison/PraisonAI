"""
Unified Retrieval CLI Commands - Agent-First Experience

This module provides the unified CLI commands for knowledge and retrieval:
- `praisonai index` - Index documents into knowledge base
- `praisonai query` - Query with structured answer and citations
- `praisonai chat` - Conversational interface with knowledge (handled by chat.py)

These commands replace the separate `knowledge` and `rag` command families.
"""

import typer
from pathlib import Path
from typing import List, Optional
from contextlib import contextmanager
import time
import sys

app = typer.Typer(
    name="retrieval",
    help="Knowledge indexing and retrieval commands",
    no_args_is_help=True,
)


@contextmanager
def retrieval_profiler(profile: bool, profile_out: Optional[Path], profile_top: int):
    """Context manager for profiling retrieval operations."""
    if not profile:
        yield None
        return
    
    import json as json_module
    
    start_time = time.perf_counter()
    start_modules = set(sys.modules.keys())
    
    profile_data = {
        "metrics": {},
        "modules_loaded": [],
    }
    
    try:
        import tracemalloc
        tracemalloc.start()
        has_tracemalloc = True
    except ImportError:
        has_tracemalloc = False
    
    yield profile_data
    
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    profile_data["metrics"]["elapsed_ms"] = elapsed_ms
    
    if has_tracemalloc:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        profile_data["metrics"]["peak_memory_mb"] = peak / 1024 / 1024
    
    new_modules = set(sys.modules.keys()) - start_modules
    profile_data["modules_loaded"] = sorted(list(new_modules))[:profile_top]
    
    if profile_out:
        try:
            profile_out.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_out, "w") as f:
                json_module.dump(profile_data, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Failed to save profile: {e}")
    
    from rich.console import Console
    console = Console(stderr=True)
    console.print(f"\n[dim]Profile: {elapsed_ms:.2f}ms wall time[/dim]")
    if "peak_memory_mb" in profile_data["metrics"]:
        console.print(f"[dim]Profile: {profile_data['metrics']['peak_memory_mb']:.2f}MB peak memory[/dim]")
    console.print(f"[dim]Profile: {len(new_modules)} modules imported[/dim]")
    if profile_out:
        console.print(f"[dim]Profile saved to: {profile_out}[/dim]")


@app.command("index")
def index_command(
    sources: List[str] = typer.Argument(..., help="Source files, directories, or URLs to index"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection/knowledge base name"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Index documents into a knowledge base.
    
    This is the canonical command for adding documents to a knowledge base.
    Use `praisonai query` to get answers with citations from the indexed knowledge.
    
    Examples:
        praisonai index ./docs
        praisonai index paper.pdf --collection research
        praisonai index ./data --profile --profile-out ./profile.json
    """
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    console = Console()
    
    with retrieval_profiler(profile, profile_out, profile_top) as profile_data:
        try:
            from praisonaiagents.knowledge import Knowledge
            
            knowledge_config = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": collection,
                        "path": f"./.praison/knowledge/{collection}",
                    }
                }
            }
            
            if config and config.exists():
                import yaml
                with open(config) as f:
                    file_config = yaml.safe_load(f)
                    if "knowledge" in file_config:
                        knowledge_config.update(file_config["knowledge"])
            
            knowledge = Knowledge(config=knowledge_config, verbose=verbose)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                for source in sources:
                    task = progress.add_task(f"Indexing {source}...", total=None)
                    try:
                        result = knowledge.add(source)
                        count = len(result.get("results", [])) if isinstance(result, dict) else 0
                        console.print(f"[green]✓[/green] Indexed {source}: {count} chunks")
                    except Exception as e:
                        console.print(f"[red]✗[/red] Failed to index {source}: {e}")
                    progress.remove_task(task)
            
            console.print(f"\n[bold green]Indexing complete![/bold green] Collection: {collection}")
            if profile_data:
                profile_data["command"] = "index"
                profile_data["collection"] = collection
                profile_data["sources"] = sources
            
        except ImportError as e:
            console.print(f"[red]Error:[/red] Missing dependency: {e}")
            console.print("Install with: pip install 'praisonaiagents[knowledge]'")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)


@app.command("query")
def query_command(
    question: str = typer.Argument(..., help="Question to answer"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection to query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to retrieve"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum relevance score (0.0-1.0)"),
    hybrid: bool = typer.Option(False, "--hybrid", help="Use hybrid retrieval (dense + keyword)"),
    rerank: bool = typer.Option(False, "--rerank", help="Enable reranking of results"),
    citations: bool = typer.Option(True, "--citations/--no-citations", help="Include citations"),
    citations_mode: str = typer.Option("append", "--citations-mode", help="Citations mode: append, inline, hidden"),
    max_context_tokens: int = typer.Option(4000, "--max-context-tokens", help="Maximum context tokens"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Query knowledge and get a structured answer with citations.
    
    Uses the Agent-first retrieval pipeline with token-aware context building.
    
    Examples:
        praisonai query "What is the main finding?"
        praisonai query "Summarize the document" --collection research
        praisonai query "Key points?" --top-k 10 --no-citations
        praisonai query "Summary?" --hybrid --rerank
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    
    console = Console()
    
    with retrieval_profiler(profile, profile_out, profile_top) as profile_data:
        try:
            from praisonaiagents import Agent
            from praisonaiagents.rag.retrieval_config import RetrievalConfig, RetrievalPolicy, CitationsMode
            
            retrieval_config = RetrievalConfig(
                enabled=True,
                policy=RetrievalPolicy.ALWAYS,
                top_k=top_k,
                min_score=min_score,
                max_context_tokens=max_context_tokens,
                rerank=rerank,
                hybrid=hybrid,
                citations=citations,
                citations_mode=CitationsMode(citations_mode),
                vector_store_provider="chroma",
                persist_path=f"./.praison/knowledge/{collection}",
                collection_name=collection,
            )
            
            if config and config.exists():
                import yaml
                with open(config) as f:
                    file_config = yaml.safe_load(f)
                    if "retrieval" in file_config:
                        for key, value in file_config["retrieval"].items():
                            if hasattr(retrieval_config, key):
                                setattr(retrieval_config, key, value)
            
            agent = Agent(
                name="QueryAgent",
                instructions="You are a helpful assistant that answers questions based on the provided knowledge.",
                knowledge=[],  # Empty - we'll use existing indexed knowledge
                retrieval_config=retrieval_config,
                verbose=verbose,
            )
            
            agent._ensure_knowledge_processed = lambda: None
            from praisonaiagents.knowledge import Knowledge
            agent.knowledge = Knowledge(config=retrieval_config.to_knowledge_config(), verbose=verbose)
            agent._knowledge_processed = True
            
            if verbose:
                strategy_str = "hybrid (dense + keyword)" if hybrid else "dense"
                rerank_str = " with reranking" if rerank else ""
                console.print(f"[dim]Querying collection '{collection}' using {strategy_str}{rerank_str}, top_k={top_k}...[/dim]")
            
            result = agent.query(question)
            
            console.print(Panel(
                Markdown(result.answer),
                title="[bold]Answer[/bold]",
                border_style="green",
            ))
            
            if citations and result.citations:
                console.print("\n[bold]Sources:[/bold]")
                for citation in result.citations:
                    score_str = f"[dim](score: {citation.score:.2f})[/dim]" if citation.score else ""
                    console.print(f"  [{citation.id}] {citation.source} {score_str}")
                    if verbose:
                        snippet = citation.text[:200] + "..." if len(citation.text) > 200 else citation.text
                        console.print(f"      [dim]{snippet}[/dim]")
            
            if verbose and result.metadata:
                elapsed = result.metadata.get('elapsed_seconds', 0)
                console.print(f"\n[dim]Elapsed: {elapsed:.2f}s[/dim]")
            
            if profile_data:
                profile_data["command"] = "query"
                profile_data["collection"] = collection
                profile_data["question"] = question
            
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


@app.command("search")
def search_command(
    query: str = typer.Argument(..., help="Search query"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection to search"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to retrieve"),
    hybrid: bool = typer.Option(False, "--hybrid", help="Use hybrid retrieval (dense + keyword)"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Search/retrieve from a knowledge base (no LLM generation).
    
    Returns raw search results without generating an answer.
    For answers with citations, use `praisonai query`.
    
    Examples:
        praisonai search "capital of France"
        praisonai search "main findings" --collection research --top-k 10
    """
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    try:
        from praisonaiagents.knowledge import Knowledge
        
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": collection,
                    "path": f"./.praison/knowledge/{collection}",
                }
            }
        }
        
        if hybrid:
            knowledge_config["retrieval"] = {"strategy": "hybrid"}
        
        if config and config.exists():
            import yaml
            with open(config) as f:
                file_config = yaml.safe_load(f)
                if "knowledge" in file_config:
                    knowledge_config.update(file_config["knowledge"])
        
        knowledge = Knowledge(config=knowledge_config, verbose=verbose)
        
        if verbose:
            console.print(f"[dim]Searching collection '{collection}' for: {query}[/dim]")
        
        results = knowledge.search(query)
        
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return
        
        if isinstance(results, dict) and 'results' in results:
            result_list = results['results']
        elif isinstance(results, list):
            result_list = results
        else:
            result_list = [results]
        
        table = Table(title=f"Search Results ({len(result_list[:top_k])} of {len(result_list)})")
        table.add_column("#", style="dim", width=3)
        table.add_column("Score", width=8)
        table.add_column("Content", overflow="fold")
        
        for i, result in enumerate(result_list[:top_k], 1):
            if isinstance(result, dict):
                content = result.get('memory', result.get('text', str(result)))
                score = result.get('score', result.get('distance', 'N/A'))
            else:
                content = str(result)
                score = 'N/A'
            
            content_preview = content[:300] + "..." if len(content) > 300 else content
            score_str = f"{score:.3f}" if isinstance(score, float) else str(score)
            table.add_row(str(i), score_str, content_preview)
        
        console.print(table)
        
    except ImportError as e:
        console.print(f"[red]Error:[/red] Missing dependency: {e}")
        console.print("Install with: pip install 'praisonaiagents[knowledge]'")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def register_commands(main_app: typer.Typer):
    """Register unified retrieval commands with the main CLI app."""
    main_app.command("index")(index_command)
    main_app.command("query")(query_command)
    main_app.command("search")(search_command)
