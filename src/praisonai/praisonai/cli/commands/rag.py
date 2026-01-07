"""
RAG command group for PraisonAI CLI.

Provides RAG (Retrieval Augmented Generation) commands:
- index: Build/update an index from sources
- query: One-shot question -> answer with citations
- chat: Interactive RAG chat loop
- eval: Evaluate retrieval quality
- serve: Start RAG microservice (optional)

All commands support --profile for performance profiling using the existing
praisonai profile infrastructure.
"""

import typer
from typing import Optional, List
from pathlib import Path
from contextlib import contextmanager
import time
import json as json_module

app = typer.Typer(help="RAG (Retrieval Augmented Generation) commands")


@contextmanager
def rag_profiler(enabled: bool, profile_out: Optional[Path], profile_top: int = 20):
    """
    Context manager for RAG command profiling.
    
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
        "command": "rag",
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
def rag_index(
    sources: List[str] = typer.Argument(..., help="Source files, directories, or URLs to index"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection/index name"),
    chunking: str = typer.Option("recursive", "--chunking", help="Chunking strategy: token, sentence, recursive, semantic"),
    chunk_size: int = typer.Option(512, "--chunk-size", help="Chunk size in tokens"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Index documents for RAG retrieval.
    
    This command uses the Knowledge substrate for indexing.
    Equivalent to: praisonai knowledge index
    
    Examples:
        praisonai rag index ./docs
        praisonai rag index paper.pdf --collection research
        praisonai rag index ./data --chunking semantic --chunk-size 256
        praisonai rag index ./docs --profile --profile-out ./profile.json
    """
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    console = Console()
    
    with rag_profiler(profile, profile_out, profile_top) as profile_data:
        try:
            # Lazy import to avoid startup cost
            from praisonaiagents.knowledge import Knowledge
            
            # Build config - use unified knowledge path
            knowledge_config = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": collection,
                        "path": f"./.praison/knowledge/{collection}",
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
            
            # Index sources
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
                profile_data["command"] = "rag index"
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
def rag_query(
    question: str = typer.Argument(..., help="Question to answer"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection to query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to retrieve"),
    citations: bool = typer.Option(True, "--citations/--no-citations", help="Include citations"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Query the RAG system with a question.
    
    Examples:
        praisonai rag query "What is the main finding?"
        praisonai rag query "Summarize the document" --collection research
        praisonai rag query "Key points?" --top-k 10 --no-citations
        praisonai rag query "Summary?" --profile --profile-out ./profile.json
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    
    console = Console()
    
    with rag_profiler(profile, profile_out, profile_top) as profile_data:
        try:
            from praisonaiagents.knowledge import Knowledge
            from praisonaiagents.rag import RAG, RAGConfig
            
            # Build config - use unified knowledge path
            knowledge_config = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": collection,
                        "path": f"./.praison/knowledge/{collection}",
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
            
            # Initialize
            knowledge = Knowledge(config=knowledge_config, verbose=verbose)
            rag_config = RAGConfig(
                top_k=top_k,
                include_citations=citations,
            )
            rag = RAG(knowledge=knowledge, config=rag_config)
            
            # Query
            if verbose:
                console.print(f"[dim]Querying collection '{collection}' with top_k={top_k}...[/dim]")
            
            result = rag.query(question)
            
            # Display answer
            console.print(Panel(
                Markdown(result.answer),
                title="[bold]Answer[/bold]",
                border_style="green",
            ))
            
            # Display citations
            if citations and result.citations:
                console.print("\n[bold]Sources:[/bold]")
                for citation in result.citations:
                    score_str = f"[dim](score: {citation.score:.2f})[/dim]" if citation.score else ""
                    console.print(f"  [{citation.id}] {citation.source} {score_str}")
                    if verbose:
                        snippet = citation.text[:200] + "..." if len(citation.text) > 200 else citation.text
                        console.print(f"      [dim]{snippet}[/dim]")
            
            # Show metadata if verbose
            if verbose:
                console.print(f"\n[dim]Elapsed: {result.metadata.get('elapsed_seconds', 0):.2f}s[/dim]")
            
            if profile_data:
                profile_data["command"] = "rag query"
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


@app.command("chat")
def rag_chat(
    collection: str = typer.Option("default", "--collection", "-c", help="Collection to chat with"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results per query"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="Stream responses"),
):
    """
    Interactive RAG chat session.
    
    Examples:
        praisonai rag chat
        praisonai rag chat --collection research
        praisonai rag chat --no-stream
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    
    console = Console()
    
    try:
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG, RAGConfig
        
        # Build config - use unified knowledge path
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": collection,
                    "path": f"./.praison/knowledge/{collection}",
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
        
        # Initialize
        knowledge = Knowledge(config=knowledge_config)
        rag_config = RAGConfig(top_k=top_k, include_citations=True, stream=stream)
        rag = RAG(knowledge=knowledge, config=rag_config)
        
        console.print(Panel(
            f"[bold]RAG Chat[/bold] - Collection: {collection}\n"
            "Type your questions. Use 'exit' or Ctrl+C to quit.",
            border_style="blue",
        ))
        
        while True:
            try:
                question = console.input("\n[bold blue]You:[/bold blue] ").strip()
                
                if not question:
                    continue
                if question.lower() in ("exit", "quit", "q"):
                    console.print("[dim]Goodbye![/dim]")
                    break
                
                console.print("\n[bold green]Assistant:[/bold green]")
                
                if stream:
                    # Stream response
                    full_response = ""
                    for chunk in rag.stream(question):
                        console.print(chunk, end="")
                        full_response += chunk
                    console.print()  # Newline after streaming
                    
                    # Get citations separately
                    citations = rag.get_citations(question)
                else:
                    result = rag.query(question)
                    console.print(Markdown(result.answer))
                    citations = result.citations
                
                # Show citations
                if citations:
                    console.print("\n[dim]Sources:[/dim]")
                    for c in citations[:3]:  # Show top 3
                        console.print(f"  [dim][{c.id}] {c.source}[/dim]")
                
            except KeyboardInterrupt:
                console.print("\n[dim]Goodbye![/dim]")
                break
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
        
    except ImportError as e:
        console.print(f"[red]Error:[/red] Missing dependency: {e}")
        console.print("Install with: pip install 'praisonaiagents[knowledge]'")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("eval")
def rag_eval(
    test_file: Path = typer.Argument(..., help="JSON file with test queries"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection to evaluate"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to retrieve"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output results to file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    profile_out: Optional[Path] = typer.Option(None, "--profile-out", help="Save profile to JSON file"),
    profile_top: int = typer.Option(20, "--profile-top", help="Top N items in profile"),
):
    """
    Evaluate RAG retrieval quality.
    
    Test file format (JSON):
    [
        {"query": "What is X?", "expected_doc": "doc1.pdf", "expected_answer_contains": "answer"},
        ...
    ]
    
    Examples:
        praisonai rag eval golden_queries.json
        praisonai rag eval tests.json --collection research --output results.json
        praisonai rag eval tests.json --profile --profile-out ./profile.json
    """
    import json
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    with rag_profiler(profile, profile_out, profile_top) as profile_data:
        try:
            from praisonaiagents.knowledge import Knowledge
            from praisonaiagents.rag import RAG, RAGConfig
            
            # Load test file
            if not test_file.exists():
                console.print(f"[red]Error:[/red] Test file not found: {test_file}")
                raise typer.Exit(1)
            
            with open(test_file) as f:
                tests = json.load(f)
            
            if not isinstance(tests, list):
                console.print("[red]Error:[/red] Test file must contain a JSON array")
                raise typer.Exit(1)
            
            # Build config - use unified knowledge path
            knowledge_config = {
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": collection,
                        "path": f"./.praison/knowledge/{collection}",
                    }
                }
            }
            
            # Initialize
            knowledge = Knowledge(config=knowledge_config, verbose=verbose)
            rag_config = RAGConfig(top_k=top_k, include_citations=True)
            rag = RAG(knowledge=knowledge, config=rag_config)
            
            # Run evaluation
            results = []
            passed = 0
            failed = 0
            
            console.print(f"\n[bold]Evaluating {len(tests)} queries...[/bold]\n")
            
            for i, test in enumerate(tests):
                query = test.get("query", "")
                expected_doc = test.get("expected_doc", "")
                expected_contains = test.get("expected_answer_contains", "")
                
                result = rag.query(query)
                
                # Check if expected doc is in citations
                doc_found = any(
                    expected_doc in c.source for c in result.citations
                ) if expected_doc else True
                
                # Check if answer contains expected text
                answer_ok = (
                    expected_contains.lower() in result.answer.lower()
                ) if expected_contains else True
                
                test_passed = doc_found and answer_ok
                
                if test_passed:
                    passed += 1
                    status = "[green]PASS[/green]"
                else:
                    failed += 1
                    status = "[red]FAIL[/red]"
                
                results.append({
                    "query": query,
                    "passed": test_passed,
                    "doc_found": doc_found,
                    "answer_ok": answer_ok,
                    "answer": result.answer[:200],
                    "citations": [c.source for c in result.citations],
                })
                
                if verbose:
                    console.print(f"  {status} Query: {query[:50]}...")
            
            # Summary table
            table = Table(title="Evaluation Results")
            table.add_column("Metric", style="bold")
            table.add_column("Value")
            
            table.add_row("Total Tests", str(len(tests)))
            table.add_row("Passed", f"[green]{passed}[/green]")
            table.add_row("Failed", f"[red]{failed}[/red]")
            table.add_row("Pass Rate", f"{passed/len(tests)*100:.1f}%")
            
            console.print(table)
            
            # Save results if output specified
            if output:
                with open(output, "w") as f:
                    json.dump(results, f, indent=2)
                console.print(f"\n[dim]Results saved to {output}[/dim]")
            
            # Exit with error if any failed
            if failed > 0:
                raise typer.Exit(1)
            
            if profile_data:
                profile_data["command"] = "rag eval"
                profile_data["collection"] = collection
                profile_data["test_file"] = str(test_file)
                profile_data["metrics"]["tests_total"] = len(tests)
                profile_data["metrics"]["tests_passed"] = passed
                profile_data["metrics"]["tests_failed"] = failed
            
        except ImportError as e:
            console.print(f"[red]Error:[/red] Missing dependency: {e}")
            console.print("Install with: pip install 'praisonaiagents[knowledge]'")
            raise typer.Exit(1)
        except typer.Exit:
            raise
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            if verbose:
                import traceback
                console.print(traceback.format_exc())
            raise typer.Exit(1)


@app.command("serve")
def rag_serve(
    collection: str = typer.Option("default", "--collection", "-c", help="Collection to serve"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to bind"),
    config: Optional[Path] = typer.Option(None, "--config", "-f", help="Config file path"),
):
    """
    Start RAG microservice API.
    
    Endpoints:
        POST /rag/query - Query with JSON body {"question": "..."}
        POST /rag/chat - Streaming chat
        GET /health - Health check
    
    Examples:
        praisonai rag serve
        praisonai rag serve --collection research --port 9000
    """
    from rich.console import Console
    
    console = Console()
    
    try:
        import uvicorn
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
        from fastapi.responses import StreamingResponse
    except ImportError:
        console.print("[red]Error:[/red] FastAPI/uvicorn not installed")
        console.print("Install with: pip install 'praisonai[rag-api]'")
        raise typer.Exit(1)
    
    try:
        from praisonaiagents.knowledge import Knowledge
        from praisonaiagents.rag import RAG
        
        # Build config
        knowledge_config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": collection,
                    "path": f"./.praison/rag/{collection}",
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
        
        # Initialize
        knowledge = Knowledge(config=knowledge_config)
        rag = RAG(knowledge=knowledge)
        
        # Create FastAPI app
        api = FastAPI(title="PraisonAI RAG API", version="1.0.0")
        
        class QueryRequest(BaseModel):
            question: str
            top_k: int = 5
            include_citations: bool = True
        
        class QueryResponse(BaseModel):
            answer: str
            citations: list
            metadata: dict
        
        @api.get("/health")
        def health():
            return {"status": "healthy", "collection": collection}
        
        @api.post("/rag/query", response_model=QueryResponse)
        def query(request: QueryRequest):
            try:
                rag.config.top_k = request.top_k
                rag.config.include_citations = request.include_citations
                result = rag.query(request.question)
                return QueryResponse(
                    answer=result.answer,
                    citations=[c.to_dict() for c in result.citations],
                    metadata=result.metadata,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @api.post("/rag/chat")
        def chat(request: QueryRequest):
            def generate():
                for chunk in rag.stream(request.question):
                    yield chunk
            return StreamingResponse(generate(), media_type="text/plain")
        
        console.print("\n[bold green]Starting RAG API server[/bold green]")
        console.print(f"  Collection: {collection}")
        console.print(f"  URL: http://{host}:{port}")
        console.print(f"  Docs: http://{host}:{port}/docs\n")
        
        uvicorn.run(api, host=host, port=port)
        
    except ImportError as e:
        console.print(f"[red]Error:[/red] Missing dependency: {e}")
        console.print("Install with: pip install 'praisonaiagents[knowledge]'")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
