#!/usr/bin/env python3
"""
Example: Using mem0 Backend with Agent Retrieval

This example demonstrates:
1. Agent with knowledge using mem0 backend (default)
2. Proper scope identifiers (user_id/agent_id)
3. Handling of metadata normalization (mem0 returns metadata=None)
4. Agent-first retrieval API

Requirements:
- pip install praisonaiagents[knowledge]
- OPENAI_API_KEY environment variable

Usage:
    python mem0_backend_example.py
"""

import os
import tempfile
import shutil

from praisonaiagents import Agent


def main():
    # Create temporary directory with test documents
    temp_dir = tempfile.mkdtemp(prefix='praison_example_')
    
    try:
        # Create test documents with UNIQUE content that requires retrieval
        doc1 = os.path.join(temp_dir, 'acme_policy.txt')
        with open(doc1, 'w') as f:
            f.write("""
            Acme Corp Travel Policy Document
            
            Flight booking code: FALCON-77
            Hotel reservation prefix: HTL-
            Maximum daily meal allowance: $52.75
            Mileage reimbursement rate: $0.67 per mile
            Travel approval required for trips over: $500
            Emergency travel hotline: 555-ACME-911
            """)
        
        doc2 = os.path.join(temp_dir, 'project_info.txt')
        with open(doc2, 'w') as f:
            f.write("""
            Project Phoenix Status Report
            
            Project code: PHOENIX-2024
            Lead engineer: Dr. Sarah Chen
            Budget allocation: $2.4 million
            Target completion: Q3 2025
            Security clearance required: Level 3
            Weekly standup: Tuesdays at 10am PST
            """)
        
        print("=" * 60)
        print("Example: Agent with Knowledge (mem0 backend)")
        print("=" * 60)
        
        # Create agent with knowledge
        # mem0 is the default backend - it requires scope identifiers
        agent = Agent(
            name="PolicyExpert",
            instructions="You are a company policy expert. Answer questions based ONLY on the provided knowledge. Quote exact values when asked about codes or numbers.",
            knowledge=[temp_dir],  # Add directory with documents
            user_id="example_user",  # Required for mem0 backend
        )
        
        print("\n1. Testing Agent.chat() with context-required question:")
        print("-" * 40)
        
        # Question that REQUIRES the retrieved context (unique code)
        response = agent.chat("What is the flight booking code?")
        print("Q: What is the flight booking code?")
        print(f"A: {response}")
        
        # Verify the answer contains the unique code
        if "FALCON-77" in response.upper():
            print("✅ VERIFIED: Agent correctly retrieved the unique code!")
        
        print("\n2. Testing Agent.chat() with another context-required question:")
        print("-" * 40)
        
        response = agent.chat("What is the maximum daily meal allowance?")
        print("Q: What is the maximum daily meal allowance?")
        print(f"A: {response}")
        
        if "52.75" in response:
            print("✅ VERIFIED: Agent correctly retrieved the specific amount!")
        
        print("\n3. Testing Agent.retrieve() for context-only retrieval:")
        print("-" * 40)
        
        # retrieve() returns context without LLM generation
        try:
            context_pack = agent.retrieve("Project Phoenix")
            print("Query: Project Phoenix")
            print(f"Context preview: {context_pack.context[:200]}...")
            print(f"Citations: {len(context_pack.citations)} found")
        except Exception as e:
            print(f"Note: retrieve() requires RAG module: {e}")
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
