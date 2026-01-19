"""
Example 15: Recursive Context Pattern

Demonstrates the RLM (Recursive Language Model) pattern for handling large context:
- Store large documents as artifacts (not in LLM context)
- Agent uses tools (grep/head/tail/chunk) to explore artifacts
- Dramatically reduces token usage (~2K vs ~10K+)

This pattern solves "context rot" by treating context as programmatically
explorable data instead of dumping everything into the LLM's context window.
"""

import tempfile
import os
from praisonaiagents import Agent
from praisonai.context import FileSystemArtifactStore
from praisonai.context.queue import create_artifact_tools
from praisonaiagents.context.artifacts import ArtifactMetadata


def create_sample_document():
    """Create a sample large document for testing."""
    # Simulate a research paper / large document
    content = """
# Attention Is All You Need

## Abstract

The dominant sequence transduction models are based on complex recurrent or 
convolutional neural networks that include an encoder and a decoder. The best
performing models also connect the encoder and decoder through an attention
mechanism. We propose a new simple network architecture, the Transformer,
based solely on attention mechanisms, dispensing with recurrence and convolutions
entirely. 

## Introduction

Recurrent neural networks, long short-term memory and gated recurrent neural 
networks in particular, have been firmly established as state of the art 
approaches in sequence modeling and transduction problems such as language 
modeling and machine translation. 

## Background

The goal of reducing sequential computation also forms the foundation of the 
Extended Neural GPU, ByteNet and ConvS2S, all of which use convolutional neural
networks as basic building block.

## Model Architecture

### Encoder and Decoder Stacks

The encoder is composed of a stack of N = 6 identical layers. Each layer has 
two sub-layers. The first is a multi-head self-attention mechanism, and the 
second is a simple, position-wise fully connected feed-forward network.

### Attention

An attention function can be described as mapping a query and a set of key-value
pairs to an output, where the query, keys, values, and output are all vectors.

#### Scaled Dot-Product Attention

We call our particular attention "Scaled Dot-Product Attention". The input 
consists of queries and keys of dimension dk, and values of dimension dv.

The formula is: Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V

### Multi-Head Attention

Multi-head attention allows the model to jointly attend to information from
different representation subspaces at different positions.

## Results

### Machine Translation

On the WMT 2014 English-to-German translation task, the big transformer model
outperforms the best previously reported models including ensembles.

The model achieved a BLEU score of 28.4 on the WMT 2014 English-to-German 
translation task, improving over the existing best results by over 2 BLEU.

On the WMT 2014 English-to-French translation task, our big model achieves 
a BLEU score of 41.8, outperforming all published single models.

### Training

Training took 3.5 days on 8 P100 GPUs. The big model was trained for 300,000
steps (3.5 days) at a cost of approximately $1000 in cloud compute.

## Model Variations

| Model | Parameters | BLEU EN-DE | BLEU EN-FR |
|-------|------------|------------|------------|
| Base  | 65M        | 27.3       | 38.1       |
| Big   | 213M       | 28.4       | 41.8       |

The base model has 65 million parameters (65 × 10^6).
The big model has 213 million parameters.

## Conclusion

In this work, we presented the Transformer, the first sequence transduction
model based entirely on attention, replacing the recurrent layers most commonly
used in encoder-decoder architectures with multi-headed self-attention.

The Transformer can be trained significantly faster than architectures based
on recurrent or convolutional layers.

## Authors

Ashish Vaswani (Google Brain)
Noam Shazeer (Google Brain)
Niki Parmar (Google Research)
Jakob Uszkoreit (Google Research)
Llion Jones (Google Research)
Aidan N. Gomez (University of Toronto)
Łukasz Kaiser (Google Brain)
Illia Polosukhin

## References

[1] Neural Machine Translation by Jointly Learning to Align and Translate
[2] Sequence to Sequence Learning with Neural Networks
[3] Learning Phrase Representations using RNN Encoder-Decoder
"""
    # Repeat content to make it larger
    full_content = (content + "\n\n") * 10  # ~35KB
    return full_content


def main():
    print("=" * 70)
    print("Recursive Context Pattern - Token Efficiency Demo")
    print("=" * 70)
    
    # Track token usage across methods
    token_stats = {
        "traditional": {"input": 0, "output": 0},
        "recursive": {"input": 0, "output": 0},
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Create artifact store and tools
        store = FileSystemArtifactStore(base_dir=tmpdir)
        artifact_tools = create_artifact_tools(store=store)
        
        print(f"\n1. Created FileSystemArtifactStore")
        print(f"   Location: {tmpdir}")
        print(f"   Tools available: {[t.__name__ for t in artifact_tools]}")
        
        # 2. Create sample document and store as artifact
        document = create_sample_document()
        doc_size = len(document)
        doc_tokens = doc_size // 4  # Rough estimate: 4 chars per token
        
        metadata = ArtifactMetadata(
            agent_id="research_agent",
            run_id="demo_run",
            tool_name="document_loader",
            turn_id=1
        )
        
        ref = store.store(document, metadata)
        
        print(f"\n2. Stored document as artifact")
        print(f"   Size: {doc_size:,} chars (~{doc_tokens:,} tokens)")
        print(f"   Path: {ref.path}")
        print(f"   Summary: {ref.summary[:80]}...")
        
        # 3. Create agent WITH artifact tools (Recursive Context approach)
        agent = Agent(
            instructions="""You are a research paper analyst with access to artifact exploration tools.
When given an artifact path, use the tools to explore it efficiently:
- artifact_grep: Search for patterns (USE THIS FIRST)
- artifact_head: See first N lines
- artifact_tail: See last N lines
- artifact_chunk: Get specific line ranges

Be precise and cite line numbers when finding information.""",
            tools=artifact_tools,
            output='silent'  # Quiet output for cleaner demo
        )
        
        print(f"\n3. Created agent with {len(agent.tools)} artifact tools")
        
        # 4. Query using RECURSIVE CONTEXT (small prompt + tools)
        print(f"\n4. RECURSIVE CONTEXT APPROACH")
        print("-" * 40)
        
        prompt = f"""I have a research paper stored at: {ref.path}

Find the BLEU score on the WMT 2014 English-to-German translation task.
Use artifact_grep to search, then report the answer with line number."""

        prompt_tokens = len(prompt) // 4
        print(f"   Prompt size: {len(prompt)} chars (~{prompt_tokens} tokens)")
        print(f"   Document NOT in prompt context!")
        
        response = agent.chat(prompt)
        
        # Estimate output tokens (could use actual LiteLLM response if available)
        output_tokens = len(response) // 4
        
        # Calculate recursive approach tokens (prompt + tool calls + response)
        # Tool call: ~200 tokens for tool desc + call
        # Tool response: ~300 tokens for grep results
        estimated_total = prompt_tokens + 200 + 300 + output_tokens
        token_stats["recursive"]["input"] = estimated_total
        
        print(f"\n   Agent Response:")
        print(f"   {response[:200]}...")
        print(f"\n   Estimated tokens used: ~{estimated_total:,}")
        
        # 5. Compare with TRADITIONAL approach (full context)
        print(f"\n5. TRADITIONAL APPROACH (for comparison)")
        print("-" * 40)
        
        traditional_prompt_tokens = prompt_tokens + doc_tokens
        token_stats["traditional"]["input"] = traditional_prompt_tokens
        
        print(f"   If we passed FULL document in prompt:")
        print(f"   Prompt: {prompt_tokens} + Document: {doc_tokens} = {traditional_prompt_tokens:,} tokens")
        
        # 6. Show token savings
        print(f"\n6. TOKEN COMPARISON")
        print("=" * 40)
        
        savings = token_stats["traditional"]["input"] - token_stats["recursive"]["input"]
        savings_pct = (savings / token_stats["traditional"]["input"]) * 100
        
        print(f"   Traditional approach: ~{token_stats['traditional']['input']:,} tokens")
        print(f"   Recursive approach:   ~{token_stats['recursive']['input']:,} tokens")
        print(f"   -----------------------------------")
        print(f"   SAVINGS:             ~{savings:,} tokens ({savings_pct:.0f}%)")
        
        # 7. Demonstrate other artifact operations
        print(f"\n7. ARTIFACT OPERATIONS DEMO")
        print("-" * 40)
        
        # head
        head_result = store.head(ref, lines=5)
        print(f"   head(5 lines):")
        for line in head_result.split('\n')[:3]:
            print(f"      {line[:60]}")
        
        # grep
        grep_results = store.grep(ref, pattern=r"BLEU.*\d+", max_matches=3)
        print(f"\n   grep('BLEU.*\\d+'):")
        for match in grep_results[:2]:
            print(f"      Line {match.line_number}: {match.line_content[:50].strip()}...")
        
        # chunk
        chunk_result = store.chunk(ref, start_line=50, end_line=55)
        print(f"\n   chunk(lines 50-55):")
        for line in chunk_result.split('\n')[:3]:
            print(f"      {line[:60]}")
        
        print("\n" + "=" * 70)
        print("CONCLUSION: Recursive Context Pattern")
        print("=" * 70)
        print("""
The Recursive Context pattern (RLM) provides:
✓ Token efficiency: ~{savings_pct:.0f}% reduction in token usage
✓ Scalability: Handle documents of any size
✓ Precision: Agent searches for exactly what it needs
✓ Cost savings: Lower API costs due to fewer tokens
✓ Better accuracy: Avoids "context rot" from large contexts
""".format(savings_pct=savings_pct))


if __name__ == "__main__":
    main()
