#!/usr/bin/env python3
"""
Example: Large Corpus Strategy Selection Demo

This example demonstrates:
1. Automatic strategy selection based on corpus size
2. Different retrieval strategies (DIRECT, BASIC, HYBRID, RERANKED, COMPRESSED)
3. Agent-centric knowledge retrieval with unique codes

Requirements:
- pip install praisonaiagents[knowledge]
- OPENAI_API_KEY environment variable

Usage:
    python large_corpus_strategy_demo.py
"""

import os
import tempfile
import shutil

from praisonaiagents import Agent


# Unique verification codes that CANNOT be guessed
VERIFICATION_CODES = {
    "project_alpha": "ALPHA-7X9K2",
    "project_beta": "BETA-3M8N1",
    "project_gamma": "GAMMA-5P2Q7",
    "budget_code": "BUDGET-9R4T6",
    "security_clearance": "CLEARANCE-2W8Y3",
}


def create_test_corpus(temp_dir: str, num_files: int = 10) -> list:
    """Create a test corpus with unique codes in each file."""
    files = []
    
    # Create main project files with unique codes
    for i, (project, code) in enumerate(VERIFICATION_CODES.items()):
        filepath = os.path.join(temp_dir, f"{project}_doc.txt")
        with open(filepath, 'w') as f:
            f.write(f"""
{project.upper().replace('_', ' ')} Documentation
{'=' * 50}

Project Overview:
This document contains confidential information about {project}.
The verification code for this project is: {code}

Key Details:
- Project started: 2024-0{i+1}-15
- Team size: {10 + i * 5} members
- Status: Active
- Priority: {'High' if i < 2 else 'Medium'}

Access Requirements:
To access this project, use verification code: {code}
All access attempts are logged for security purposes.

Last updated: 2024-12-01
            """)
        files.append(filepath)
    
    # Create additional filler files to simulate larger corpus
    for i in range(num_files - len(VERIFICATION_CODES)):
        filepath = os.path.join(temp_dir, f"general_doc_{i}.txt")
        with open(filepath, 'w') as f:
            f.write(f"""
General Documentation File {i}
{'=' * 40}

This is a general documentation file containing various information
about company processes and procedures.

Section {i}.1: Overview
Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

Section {i}.2: Procedures
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
Duis aute irure dolor in reprehenderit in voluptate velit esse.

Section {i}.3: Guidelines
Excepteur sint occaecat cupidatat non proident, sunt in culpa.
Qui officia deserunt mollit anim id est laborum.

Document ID: DOC-{1000 + i}
            """)
        files.append(filepath)
    
    return files


def main():
    temp_dir = tempfile.mkdtemp(prefix='praison_strategy_')
    
    try:
        print("=" * 60)
        print("Example: Large Corpus Strategy Selection Demo")
        print("=" * 60)
        
        # Create test corpus
        files = create_test_corpus(temp_dir, num_files=15)
        print(f"\nCreated {len(files)} test documents in: {temp_dir}")
        print(f"Unique verification codes embedded: {len(VERIFICATION_CODES)}")
        
        # Show strategy selection based on corpus size
        print("\n" + "-" * 40)
        print("Strategy Selection Demo")
        print("-" * 40)
        
        try:
            from praisonaiagents.rag import select_strategy, RetrievalStrategy
            from praisonaiagents.knowledge.indexing import CorpusStats
            
            # Get corpus stats
            stats = CorpusStats.from_directory(temp_dir)
            print(f"\nCorpus Statistics:")
            print(f"  Files: {stats.file_count}")
            print(f"  Estimated tokens: {stats.total_tokens}")
            print(f"  Recommended strategy: {stats.strategy_recommendation}")
            
            # Show strategy selection for different corpus sizes
            print(f"\nStrategy selection by corpus size:")
            for size in [100, 1000, 10000, 50000, 100000]:
                strategy = select_strategy(corpus_tokens=size)
                print(f"  {size:>6} tokens -> {strategy.value}")
                
        except ImportError as e:
            print(f"Note: Strategy module not available: {e}")
        
        # Create agent with knowledge
        print("\n" + "-" * 40)
        print("Agent Knowledge Retrieval Test")
        print("-" * 40)
        
        agent = Agent(
            name="ProjectExpert",
            instructions="""You are a project documentation expert.
Answer questions based ONLY on the provided knowledge context.
When asked about verification codes, provide the EXACT code from the documents.
If information is not in the context, say 'Information not found in documents.'""",
            knowledge=[temp_dir],
            user_id="strategy_demo_user",
            output="verbose",  # Use new consolidated param
        )
        
        # Test retrieval with unique codes
        test_questions = [
            ("What is the verification code for Project Alpha?", "ALPHA-7X9K2"),
            ("What is the budget code?", "BUDGET-9R4T6"),
            ("What is the security clearance code?", "CLEARANCE-2W8Y3"),
        ]
        
        print("\nTesting retrieval of unique codes:\n")
        
        for question, expected_code in test_questions:
            print(f"Q: {question}")
            response = agent.chat(question)
            print(f"A: {response[:200]}...")
            
            if expected_code in response.upper():
                print(f"✅ VERIFIED: Found code {expected_code}\n")
            else:
                print(f"❌ WARNING: Expected code {expected_code} not found\n")
        
        print("=" * 60)
        print("Demo Complete")
        print("=" * 60)
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
