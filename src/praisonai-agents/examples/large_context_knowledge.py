#!/usr/bin/env python3
"""
Large Context Knowledge Handling Example

Demonstrates the full pipeline:
1. Token Budget calculation
2. Incremental indexing with ignore patterns
3. Strategy selection based on corpus size
4. Smart retrieval with filtering
5. Contextual compression
6. Hierarchical summarization

Usage:
    python examples/large_context_knowledge.py
"""

import os
import tempfile
from pathlib import Path


def create_sample_corpus(base_path: str) -> None:
    """Create a sample corpus for demonstration."""
    # Create directory structure
    src_dir = Path(base_path) / "src"
    docs_dir = Path(base_path) / "docs"
    src_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create Python files
    (src_dir / "main.py").write_text("""
# Main application entry point
def main():
    '''Start the application.'''
    print("Hello from PraisonAI!")
    
if __name__ == "__main__":
    main()
""")
    
    (src_dir / "utils.py").write_text("""
# Utility functions
def helper_function(x: int) -> int:
    '''Double the input value.'''
    return x * 2

def format_output(text: str) -> str:
    '''Format text for display.'''
    return f"[OUTPUT] {text}"
""")
    
    # Create documentation
    (docs_dir / "readme.md").write_text("""
# Project Documentation

This is a sample project demonstrating large context knowledge handling.

## Features
- Token budget management
- Incremental indexing
- Smart retrieval
- Contextual compression
""")
    
    (docs_dir / "api.md").write_text("""
# API Reference

## Functions

### main()
Entry point for the application.

### helper_function(x)
Doubles the input value.

### format_output(text)
Formats text for display.
""")
    
    # Create .praisonignore
    (Path(base_path) / ".praisonignore").write_text("""
# Ignore patterns
*.pyc
__pycache__/
.git/
""")
    
    print(f"Created sample corpus at: {base_path}")


def demo_token_budget():
    """Demonstrate token budget calculation."""
    print("\n" + "="*60)
    print("1. TOKEN BUDGET CALCULATION")
    print("="*60)
    
    from praisonaiagents.rag.budget import TokenBudget, get_model_context_window
    
    # Get context window for different models
    models = ["gpt-4o", "claude-3.5-sonnet", "gemini-1.5-pro", "llama-3.1-70b"]
    print("\nModel context windows:")
    for model in models:
        window = get_model_context_window(model)
        print(f"  {model}: {window:,} tokens")
    
    # Create budget for GPT-4o
    budget = TokenBudget.from_model("gpt-4o")
    print(f"\nBudget for GPT-4o:")
    print(f"  Max tokens: {budget.model_max_tokens:,}")
    print(f"  Reserved for response: {budget.reserved_response_tokens:,}")
    print(f"  Max context tokens: {budget.max_context_tokens:,}")
    
    # Dynamic budget calculation
    available = budget.dynamic_budget(
        prompt_tokens=500,
        history_tokens=2000,
        system_tokens=1000,
    )
    print(f"\nDynamic budget (with 500 prompt + 2000 history + 1000 system):")
    print(f"  Available for context: {available:,} tokens")


def demo_indexing(corpus_path: str):
    """Demonstrate incremental indexing."""
    print("\n" + "="*60)
    print("2. INCREMENTAL INDEXING")
    print("="*60)
    
    from praisonaiagents.knowledge import Knowledge
    from praisonaiagents.knowledge.indexing import CorpusStats
    
    # Get corpus stats before indexing
    stats = CorpusStats.from_directory(corpus_path)
    print(f"\nCorpus statistics:")
    print(f"  Files: {stats.file_count}")
    print(f"  Estimated tokens: {stats.total_tokens:,}")
    print(f"  Recommended strategy: {stats.strategy_recommendation}")
    
    # Index the corpus
    knowledge = Knowledge()
    result = knowledge.index(
        corpus_path,
        user_id="demo_user",
        incremental=False,
        exclude_glob=["*.pyc"],
    )
    
    print(f"\nIndexing result:")
    print(f"  Files indexed: {result.files_indexed}")
    print(f"  Files skipped: {result.files_skipped}")
    print(f"  Chunks created: {result.chunks_created}")
    print(f"  Duration: {result.duration_seconds:.2f}s")
    
    # Incremental re-index (should skip unchanged files)
    print("\nRe-indexing (incremental)...")
    result2 = knowledge.index(corpus_path, user_id="demo_user", incremental=True)
    print(f"  Files indexed: {result2.files_indexed}")
    print(f"  Files skipped: {result2.files_skipped}")


def demo_strategy_selection():
    """Demonstrate strategy selection."""
    print("\n" + "="*60)
    print("3. STRATEGY SELECTION")
    print("="*60)
    
    from praisonaiagents.rag.strategy import select_strategy, get_strategy_description, RetrievalStrategy
    from praisonaiagents.knowledge.indexing import CorpusStats
    
    # Show strategy for different corpus sizes
    sizes = [5, 50, 500, 5000, 50000, 500000]
    print("\nStrategy selection by corpus size:")
    for size in sizes:
        stats = CorpusStats(file_count=size)
        strategy = select_strategy(stats)
        print(f"  {size:>7} files -> {strategy.value}")
    
    # Show strategy descriptions
    print("\nStrategy descriptions:")
    for strategy in RetrievalStrategy:
        desc = get_strategy_description(strategy)
        print(f"  {strategy.value}: {desc[:60]}...")


def demo_smart_retriever():
    """Demonstrate smart retriever with filtering."""
    print("\n" + "="*60)
    print("4. SMART RETRIEVER")
    print("="*60)
    
    from praisonaiagents.rag.retriever import SmartRetriever, SimpleReranker
    
    # Create retriever with reranker
    reranker = SimpleReranker()
    retriever = SmartRetriever(reranker=reranker)
    
    # Demonstrate filtering
    chunks = [
        {"text": "Python code for data processing", "metadata": {"filename": "process.py"}},
        {"text": "JavaScript frontend code", "metadata": {"filename": "app.js"}},
        {"text": "Python utilities and helpers", "metadata": {"filename": "utils.py"}},
        {"text": "CSS styling rules", "metadata": {"filename": "styles.css"}},
    ]
    
    print("\nFiltering by include pattern (*.py):")
    filtered = retriever._apply_filters(chunks, include_glob=["*.py"])
    for chunk in filtered:
        print(f"  - {chunk['metadata']['filename']}: {chunk['text'][:40]}...")
    
    print("\nFiltering by exclude pattern (utils*):")
    filtered = retriever._apply_filters(chunks, exclude_glob=["utils*"])
    for chunk in filtered:
        print(f"  - {chunk['metadata']['filename']}: {chunk['text'][:40]}...")
    
    # Demonstrate reranking
    print("\nReranking for query 'Python data':")
    reranked = reranker.rerank("Python data", chunks)
    for i, chunk in enumerate(reranked[:3], 1):
        print(f"  {i}. [{chunk['score']:.2f}] {chunk['text'][:40]}...")


def demo_compression():
    """Demonstrate contextual compression."""
    print("\n" + "="*60)
    print("5. CONTEXTUAL COMPRESSION")
    print("="*60)
    
    from praisonaiagents.rag.compressor import ContextCompressor
    
    compressor = ContextCompressor()
    
    # Create chunks with some redundancy
    chunks = [
        {"text": "Python is a high-level programming language. It is known for its simplicity and readability. Python supports multiple programming paradigms."},
        {"text": "Python is a high-level programming language. It is known for its simplicity and readability. Python supports multiple programming paradigms."},  # Duplicate
        {"text": "JavaScript is the language of the web. It runs in browsers and on servers with Node.js."},
        {"text": "Python has extensive libraries for data science, machine learning, and web development."},
    ]
    
    print(f"\nOriginal chunks: {len(chunks)}")
    
    result = compressor.compress(chunks, "Python programming", target_tokens=200)
    
    print(f"After compression:")
    print(f"  Chunks: {len(result.chunks)}")
    print(f"  Original tokens: {result.original_tokens}")
    print(f"  Compressed tokens: {result.compressed_tokens}")
    print(f"  Compression ratio: {result.compression_ratio:.2%}")
    print(f"  Method: {result.method_used}")


def demo_hierarchical_summarizer(corpus_path: str):
    """Demonstrate hierarchical summarization."""
    print("\n" + "="*60)
    print("6. HIERARCHICAL SUMMARIZATION")
    print("="*60)
    
    from praisonaiagents.rag.summarizer import HierarchicalSummarizer
    
    summarizer = HierarchicalSummarizer()
    
    # Build hierarchy
    print(f"\nBuilding hierarchy for: {corpus_path}")
    result = summarizer.build_hierarchy(corpus_path, levels=2)
    
    print(f"\nHierarchy result:")
    print(f"  Total files: {result.total_files}")
    print(f"  Total nodes: {len(result.nodes)}")
    print(f"  Total tokens: {result.total_tokens}")
    
    # Show summaries
    print("\nFile summaries:")
    for path, node in result.nodes.items():
        if node.level == 1:  # File level
            filename = node.metadata.get("filename", os.path.basename(path))
            summary = node.summary[:60] + "..." if len(node.summary) > 60 else node.summary
            print(f"  {filename}: {summary}")
    
    # Query hierarchy
    print("\nQuerying hierarchy for 'function':")
    results = summarizer.query_hierarchy("function", corpus_path, max_results=3)
    for r in results:
        print(f"  - {os.path.basename(r['path'])}: score={r['score']}")


def main():
    """Run all demonstrations."""
    print("="*60)
    print("LARGE CONTEXT KNOWLEDGE HANDLING DEMO")
    print("="*60)
    
    # Create temporary corpus
    with tempfile.TemporaryDirectory() as tmpdir:
        create_sample_corpus(tmpdir)
        
        # Run demos
        demo_token_budget()
        demo_indexing(tmpdir)
        demo_strategy_selection()
        demo_smart_retriever()
        demo_compression()
        demo_hierarchical_summarizer(tmpdir)
    
    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()
