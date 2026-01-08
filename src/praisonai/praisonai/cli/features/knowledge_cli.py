"""
CLI commands for Knowledge Management (Phase 7).

Provides CLI parity for knowledge indexing and retrieval operations.

Commands:
- index: Index a directory or file into the knowledge store
- stats: Show corpus statistics
- search: Search the knowledge store with strategy/rerank/compress options
- summarize: Build hierarchical summaries for large corpora
- clear: Clear the knowledge store
"""

import json
import os
from typing import Optional
from enum import Enum

try:
    import typer
    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False


class StrategyChoice(str, Enum):
    """Retrieval strategy choices."""
    auto = "auto"
    direct = "direct"
    basic = "basic"
    hybrid = "hybrid"
    reranked = "reranked"
    compressed = "compressed"
    hierarchical = "hierarchical"


def create_knowledge_app():
    """Create the knowledge CLI app."""
    if not HAS_TYPER:
        return None
    
    app = typer.Typer(
        name="knowledge",
        help="Knowledge management commands for indexing and retrieval.",
        no_args_is_help=True,
    )
    
    @app.command("index")
    def index_command(
        path: str = typer.Argument(..., help="Path to directory or file to index"),
        incremental: bool = typer.Option(True, "--incremental/--full", help="Use incremental indexing"),
        include: Optional[str] = typer.Option(None, "--include", "-i", help="Glob patterns to include (comma-separated)"),
        exclude: Optional[str] = typer.Option(None, "--exclude", "-e", help="Glob patterns to exclude (comma-separated)"),
        user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for scoping"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Index a directory or file into the knowledge store."""
        try:
            from praisonaiagents.knowledge import Knowledge
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        if not os.path.exists(path):
            typer.echo(f"Error: Path does not exist: {path}", err=True)
            raise typer.Exit(1)
        
        # Parse glob patterns
        include_glob = include.split(",") if include else None
        exclude_glob = exclude.split(",") if exclude else None
        
        if verbose:
            typer.echo(f"Indexing: {path}")
            typer.echo(f"  Incremental: {incremental}")
            if include_glob:
                typer.echo(f"  Include: {include_glob}")
            if exclude_glob:
                typer.echo(f"  Exclude: {exclude_glob}")
        
        knowledge = Knowledge()
        result = knowledge.index(
            path,
            incremental=incremental,
            include_glob=include_glob,
            exclude_glob=exclude_glob,
            user_id=user_id or "cli_user",
        )
        
        typer.echo(f"✓ Indexed {result.files_indexed} files")
        if result.files_skipped > 0:
            typer.echo(f"  Skipped {result.files_skipped} unchanged files")
        if result.errors:
            typer.echo(f"  Errors: {len(result.errors)}", err=True)
            if verbose:
                for err in result.errors[:5]:
                    typer.echo(f"    - {err}", err=True)
        
        typer.echo(f"  Duration: {result.duration_seconds:.2f}s")
    
    @app.command("stats")
    def stats_command(
        path: Optional[str] = typer.Argument(None, help="Path to get stats for"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        """Show corpus statistics."""
        try:
            from praisonaiagents.knowledge import Knowledge
            from praisonaiagents.knowledge.indexing import CorpusStats
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        if path and os.path.isdir(path):
            stats = CorpusStats.from_directory(path)
        else:
            knowledge = Knowledge()
            stats = knowledge.get_corpus_stats()
        
        if json_output:
            typer.echo(json.dumps(stats.to_dict(), indent=2))
        else:
            typer.echo("Corpus Statistics:")
            typer.echo(f"  Files: {stats.file_count}")
            typer.echo(f"  Chunks: {stats.chunk_count}")
            typer.echo(f"  Tokens: {stats.total_tokens}")
            typer.echo(f"  Recommended strategy: {stats.strategy_recommendation}")
    
    @app.command("search")
    def search_command(
        query: str = typer.Argument(..., help="Search query"),
        top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to return"),
        strategy: StrategyChoice = typer.Option(StrategyChoice.auto, "--strategy", "-s", help="Retrieval strategy"),
        rerank: bool = typer.Option(False, "--rerank/--no-rerank", help="Enable reranking of results"),
        compress: bool = typer.Option(False, "--compress/--no-compress", help="Enable context compression"),
        compression_ratio: float = typer.Option(0.5, "--compression-ratio", help="Target compression ratio (0.0-1.0)"),
        max_context_tokens: Optional[int] = typer.Option(None, "--max-context-tokens", help="Maximum tokens for context"),
        include: Optional[str] = typer.Option(None, "--include", "-i", help="Glob patterns to include (comma-separated)"),
        exclude: Optional[str] = typer.Option(None, "--exclude", "-e", help="Glob patterns to exclude (comma-separated)"),
        path_filter: Optional[str] = typer.Option(None, "--path-filter", help="Filter by path prefix"),
        min_score: float = typer.Option(0.0, "--min-score", help="Minimum relevance score (0.0-1.0)"),
        user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for scoping"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Search the knowledge store with advanced retrieval options.
        
        Examples:
            praisonai knowledge search "What is the API key?"
            praisonai knowledge search "config" --strategy hybrid --rerank
            praisonai knowledge search "auth" --compress --max-context-tokens 2000
            praisonai knowledge search "*.py" --include "*.py" --exclude "test_*"
        """
        try:
            from praisonaiagents.knowledge import Knowledge
            from praisonaiagents.rag import (
                SmartRetriever, ContextCompressor, RetrievalResult,
            )
        except ImportError as e:
            typer.echo(f"Error: praisonaiagents not installed: {e}", err=True)
            raise typer.Exit(1)
        
        # Parse glob patterns
        include_glob = include.split(",") if include else None
        exclude_glob = exclude.split(",") if exclude else None
        
        if verbose:
            typer.echo(f"Query: {query}")
            typer.echo(f"Strategy: {strategy.value}")
            typer.echo(f"Rerank: {rerank}, Compress: {compress}")
            if max_context_tokens:
                typer.echo(f"Max context tokens: {max_context_tokens}")
        
        knowledge = Knowledge()
        
        # Basic search
        results = knowledge.search(
            query,
            user_id=user_id or "cli_user",
            limit=top_k * 3 if rerank or compress else top_k,  # Fetch more for reranking
        )
        
        items = results.get("results", []) if isinstance(results, dict) else results
        
        # Apply path filter
        if path_filter and items:
            items = [item for item in items if path_filter in str(item.get("metadata", {}).get("path", ""))]
        
        # Apply include/exclude patterns
        if include_glob and items:
            import fnmatch
            filtered = []
            for item in items:
                path = str(item.get("metadata", {}).get("path", ""))
                for pattern in include_glob:
                    if fnmatch.fnmatch(path, f"*{pattern}*") or fnmatch.fnmatch(os.path.basename(path), pattern):
                        filtered.append(item)
                        break
            items = filtered
        
        if exclude_glob and items:
            import fnmatch
            filtered = []
            for item in items:
                path = str(item.get("metadata", {}).get("path", ""))
                excluded = False
                for pattern in exclude_glob:
                    if fnmatch.fnmatch(path, f"*{pattern}*") or fnmatch.fnmatch(os.path.basename(path), pattern):
                        excluded = True
                        break
                if not excluded:
                    filtered.append(item)
            items = filtered
        
        # Apply min_score filter
        if min_score > 0 and items:
            items = [item for item in items if item.get("score", 0) >= min_score]
        
        # Apply reranking
        if rerank and items:
            try:
                reranker = SmartRetriever()
                # Convert to RetrievalResult format
                retrieval_results = [
                    RetrievalResult(
                        text=item.get("text", item.get("memory", "")),
                        score=item.get("score", 0),
                        metadata=item.get("metadata", {}),
                    )
                    for item in items
                ]
                reranked = reranker.rerank(query, retrieval_results, top_k=top_k)
                items = [
                    {"text": r.text, "score": r.score, "metadata": r.metadata}
                    for r in reranked
                ]
                if verbose:
                    typer.echo(f"Reranked {len(items)} results")
            except Exception as e:
                if verbose:
                    typer.echo(f"Reranking skipped: {e}", err=True)
        
        # Apply compression
        if compress and items:
            try:
                compressor = ContextCompressor(
                    max_tokens=max_context_tokens or 4000,
                    target_ratio=compression_ratio,
                )
                texts = [item.get("text", item.get("memory", "")) for item in items]
                compressed = compressor.compress(texts, query=query)
                if verbose:
                    typer.echo(f"Compressed: {compressed.original_tokens} -> {compressed.compressed_tokens} tokens")
                # Update items with compressed text
                if compressed.chunks:
                    items = items[:len(compressed.chunks)]
                    for i, chunk in enumerate(compressed.chunks):
                        if i < len(items):
                            items[i]["text"] = chunk
            except Exception as e:
                if verbose:
                    typer.echo(f"Compression skipped: {e}", err=True)
        
        # Limit to top_k
        items = items[:top_k]
        
        if json_output:
            typer.echo(json.dumps(items, indent=2, default=str))
        else:
            if not items:
                typer.echo("No results found.")
                return
            
            typer.echo(f"Found {len(items)} results:\n")
            
            for i, item in enumerate(items, 1):
                text = item.get("text", item.get("memory", ""))[:200]
                score = item.get("score", 0)
                metadata = item.get("metadata", {})
                path = metadata.get("path", "")
                
                typer.echo(f"{i}. [score: {score:.3f}]")
                if path:
                    typer.echo(f"   Source: {os.path.basename(path)}")
                typer.echo(f"   {text}...")
                typer.echo()
    
    @app.command("summarize")
    def summarize_command(
        path: str = typer.Argument(..., help="Path to directory to summarize"),
        levels: int = typer.Option(3, "--levels", "-l", help="Number of hierarchy levels (1=file, 2=folder, 3=project)"),
        incremental: bool = typer.Option(True, "--incremental/--rebuild", help="Incremental update vs full rebuild"),
        include: Optional[str] = typer.Option(None, "--include", "-i", help="Glob patterns to include (comma-separated)"),
        exclude: Optional[str] = typer.Option(None, "--exclude", "-e", help="Glob patterns to exclude (comma-separated)"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Output path for summary artifacts"),
        user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for scoping"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Build hierarchical summaries for large corpora.
        
        Creates multi-level summaries (file → folder → project) for efficient
        navigation and query routing in large knowledge bases.
        
        Examples:
            praisonai knowledge summarize ./docs
            praisonai knowledge summarize ./src --levels 2 --rebuild
            praisonai knowledge summarize ./project --output ./summaries
        """
        try:
            from praisonaiagents.rag import HierarchicalSummarizer
            from praisonaiagents.knowledge.indexing import CorpusStats
        except ImportError as e:
            typer.echo(f"Error: praisonaiagents not installed: {e}", err=True)
            raise typer.Exit(1)
        
        if not os.path.exists(path):
            typer.echo(f"Error: Path does not exist: {path}", err=True)
            raise typer.Exit(1)
        
        if not os.path.isdir(path):
            typer.echo(f"Error: Path must be a directory: {path}", err=True)
            raise typer.Exit(1)
        
        # Parse glob patterns
        include_glob = include.split(",") if include else None
        exclude_glob = exclude.split(",") if exclude else None
        
        if verbose:
            typer.echo(f"Summarizing: {path}")
            typer.echo(f"  Levels: {levels}")
            typer.echo(f"  Incremental: {incremental}")
        
        # Get corpus stats first
        stats = CorpusStats.from_directory(path)
        if verbose:
            typer.echo(f"  Files: {stats.file_count}")
            typer.echo(f"  Estimated tokens: {stats.total_tokens}")
        
        # Build hierarchical summaries
        summarizer = HierarchicalSummarizer(max_levels=levels)
        
        try:
            # Collect files
            import fnmatch as fnmatch_module
            files_to_summarize = []
            
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for filename in files:
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, path)
                    
                    # Apply include patterns
                    if include_glob:
                        matched = False
                        for pattern in include_glob:
                            if fnmatch_module.fnmatch(filename, pattern):
                                matched = True
                                break
                        if not matched:
                            continue
                    
                    # Apply exclude patterns
                    if exclude_glob:
                        excluded = False
                        for pattern in exclude_glob:
                            if fnmatch_module.fnmatch(filename, pattern) or fnmatch_module.fnmatch(rel_path, pattern):
                                excluded = True
                                break
                        if excluded:
                            continue
                    
                    files_to_summarize.append(filepath)
            
            if verbose:
                typer.echo(f"  Processing {len(files_to_summarize)} files...")
            
            # Build hierarchy
            result = summarizer.build_hierarchy(
                files_to_summarize,
                base_path=path,
            )
            
            # Save if output path specified
            if output:
                os.makedirs(output, exist_ok=True)
                output_file = os.path.join(output, "hierarchy.json")
                summarizer.save(output_file)
                if verbose:
                    typer.echo(f"  Saved to: {output_file}")
            
            if json_output:
                typer.echo(json.dumps(result.to_dict() if hasattr(result, 'to_dict') else {"nodes": len(result.nodes) if hasattr(result, 'nodes') else 0}, indent=2))
            else:
                typer.echo("✓ Built hierarchical summaries")
                typer.echo(f"  Levels: {levels}")
                typer.echo(f"  Files processed: {len(files_to_summarize)}")
                if hasattr(result, 'nodes'):
                    typer.echo(f"  Summary nodes: {len(result.nodes)}")
                if output:
                    typer.echo(f"  Output: {output}")
                    
        except Exception as e:
            typer.echo(f"Error building summaries: {e}", err=True)
            if verbose:
                import traceback
                typer.echo(traceback.format_exc(), err=True)
            raise typer.Exit(1)
    
    @app.command("clear")
    def clear_command(
        confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
        user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID to clear"),
    ):
        """Clear the knowledge store."""
        if not confirm:
            confirm = typer.confirm("Are you sure you want to clear the knowledge store?")
        
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit(0)
        
        try:
            from praisonaiagents.knowledge import Knowledge
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        knowledge = Knowledge()
        knowledge.reset()
        typer.echo("✓ Knowledge store cleared.")
    
    return app


# Create the app instance
knowledge_app = create_knowledge_app()
