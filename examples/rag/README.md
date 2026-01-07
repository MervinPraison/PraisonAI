# RAG Examples

This directory contains comprehensive examples demonstrating RAG (Retrieval Augmented Generation) with PraisonAI Agents.

## Core RAG Concepts

| Example | Description | Key Concepts |
|---------|-------------|--------------|
| `basic_retrieval.py` | Fundamental retrieve-then-generate pattern | Knowledge base, context injection |
| `auto_retrieval.py` | Intelligent retrieval decisions with AutoRagAgent | Conditional RAG, retrieval policies |
| `chunking_strategies.py` | Document splitting approaches | Paragraph, section, fixed-size chunking |
| `hybrid_search.py` | Dense + sparse retrieval combination | Semantic search, keyword matching |
| `reranking.py` | Two-stage retrieval with reranking | Precision optimization, cross-encoders |

## Advanced RAG Patterns

| Example | Description | Key Concepts |
|---------|-------------|--------------|
| `multi_document.py` | Synthesizing across multiple sources | Cross-referencing, source diversity |
| `knowledge_graph.py` | Relationship-aware retrieval | Entity connections, multi-hop reasoning |
| `external_sources.py` | Web, API, and database augmentation | Real-time data, hybrid sources |
| `structured_output.py` | Guided and constrained generation | JSON output, Pydantic schemas |
| `retrieval_policies.py` | Agent-decided retrieval strategies | Adaptive top-k, priority filtering |
| `citations.py` | Source attribution and verification | Inline citations, verification |

## Application Examples

### PDF Q&A (`rag_pdf_qa.py`)

Basic RAG example showing how to:
- Use Agent with knowledge parameter
- Create explicit RAG pipeline with citations
- Stream responses

```bash
python rag_pdf_qa.py
```

### Multi-Agent RAG (`rag_multi_agent.py`)

Advanced example showing:
- Shared knowledge base across multiple agents
- Collaborative RAG workflow
- Sequential task processing

```bash
python rag_multi_agent.py
```

### RAG Evaluation (`rag_evaluation.py`)

Evaluation example showing:
- Golden query testing
- Retrieval accuracy metrics
- Answer relevance checking

```bash
python rag_evaluation.py
```

## Quick Start

Run any example:

```bash
# Basic RAG
python basic_retrieval.py

# Auto RAG with intelligent decisions
python auto_retrieval.py

# Hybrid search (dense + sparse)
python hybrid_search.py

# RAG with citations
python citations.py
```

## Installation

```bash
pip install "praisonaiagents[knowledge]"
```

## CLI Usage

```bash
# Index documents
praisonai rag index ./documents --collection my_docs

# Query
praisonai rag query "What is the main finding?" --collection my_docs

# Interactive chat
praisonai rag chat --collection my_docs

# Evaluate
praisonai rag eval golden_queries.json --collection my_docs
```

## Configuration

Create `rag_config.yaml`:

```yaml
knowledge:
  collection: my_docs
  chunking:
    strategy: recursive
    chunk_size: 512

rag:
  top_k: 5
  min_score: 0.3
  include_citations: true
```

Use with:
```bash
praisonai rag query "Question" --config rag_config.yaml
```
