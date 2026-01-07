# RAG Examples

This directory contains examples demonstrating RAG (Retrieval Augmented Generation) with PraisonAI.

## Examples

### 1. PDF Q&A (`rag_pdf_qa.py`)

Basic RAG example showing how to:
- Use Agent with knowledge parameter
- Create explicit RAG pipeline with citations
- Stream responses

```bash
python rag_pdf_qa.py
```

### 2. Multi-Agent RAG (`rag_multi_agent.py`)

Advanced example showing:
- Shared knowledge base across multiple agents
- Collaborative RAG workflow
- Sequential task processing

```bash
python rag_multi_agent.py
```

### 3. RAG Evaluation (`rag_evaluation.py`)

Evaluation example showing:
- Golden query testing
- Retrieval accuracy metrics
- Answer relevance checking

```bash
python rag_evaluation.py
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
