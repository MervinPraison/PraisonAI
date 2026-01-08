#!/usr/bin/env python3
"""
Example: Knowledge Retrieval with Context-Required Questions

This example demonstrates:
1. Agent answers questions that REQUIRE retrieved context (not general knowledge)
2. Unique codes/secrets that cannot be guessed
3. Verification that context is text, not file path

Requirements:
- pip install praisonaiagents[knowledge]
- OPENAI_API_KEY environment variable

Usage:
    python context_required_example.py
"""

import os
import tempfile
import shutil

from praisonaiagents import Agent


def main():
    temp_dir = tempfile.mkdtemp(prefix='praison_ctx_')
    
    try:
        # Create test document with UNIQUE content that cannot be guessed
        doc = os.path.join(temp_dir, 'company_policy.txt')
        with open(doc, 'w') as f:
            f.write("""
Acme Corporation Internal Policy Document
==========================================

Remote Work Policy:
- Employees may work from home up to 3 days per week
- Manager approval is required for remote work
- Manager approval code: ZEBRA-71
- All requests must be submitted via the HR portal

Expense Reimbursement:
- Maximum daily meal allowance: $47.50
- Mileage rate: $0.655 per mile
- Expense submission code: TIGER-42
- Receipts required for amounts over $25

IT Security:
- VPN access code prefix: FALCON-
- Password reset hotline: 555-0199
- Security incident code: HAWK-88

This document is confidential. Last updated: 2024-01-15.
            """)
        
        print("=" * 60)
        print("Example: Context-Required Knowledge Retrieval")
        print("=" * 60)
        print(f"\nDocument location: {doc}")
        print("\nThis example asks questions that CANNOT be answered")
        print("without the retrieved context (unique codes/values).\n")
        
        # Create agent with knowledge
        agent = Agent(
            name="PolicyExpert",
            instructions="""You are a company policy expert. 
Answer questions based ONLY on the provided knowledge context.
If the answer is not in the context, say 'I don't have that information.'
Be precise and quote exact values when asked about codes or numbers.""",
            knowledge=[temp_dir],
            user_id="demo_user",
            verbose=True,
        )
        
        # Question 1: Unique code that requires context
        print("-" * 40)
        print("Question 1: What is the manager approval code for remote work?")
        print("-" * 40)
        response = agent.chat("What is the manager approval code for remote work?")
        print(f"\nAnswer: {response}\n")
        
        # Verify the answer contains the unique code
        if "ZEBRA-71" in response.upper():
            print("✅ VERIFIED: Agent correctly retrieved the unique code from context!\n")
        else:
            print("❌ WARNING: Agent did not find the code - check retrieval\n")
        
        # Question 2: Another unique value
        print("-" * 40)
        print("Question 2: What is the maximum daily meal allowance?")
        print("-" * 40)
        response = agent.chat("What is the maximum daily meal allowance?")
        print(f"\nAnswer: {response}\n")
        
        if "47.50" in response or "$47.50" in response:
            print("✅ VERIFIED: Agent correctly retrieved the specific amount!\n")
        else:
            print("❌ WARNING: Agent did not find the amount - check retrieval\n")
        
        # Question 3: Security code
        print("-" * 40)
        print("Question 3: What is the security incident code?")
        print("-" * 40)
        response = agent.chat("What is the security incident code?")
        print(f"\nAnswer: {response}\n")
        
        if "HAWK-88" in response.upper():
            print("✅ VERIFIED: Agent correctly retrieved the security code!\n")
        else:
            print("❌ WARNING: Agent did not find the code - check retrieval\n")
        
        # Show context preview to prove it's text, not path
        print("=" * 60)
        print("Context Verification")
        print("=" * 60)
        context, _ = agent._get_knowledge_context("policy codes", use_rag=True)
        print(f"\nRetrieved context preview (first 300 chars):")
        print("-" * 40)
        print(context[:300] if context else "NO CONTEXT")
        print("-" * 40)
        
        # Verify context is text, not path
        if temp_dir in context:
            print("\n❌ ERROR: Context contains file path instead of text!")
        else:
            print("\n✅ VERIFIED: Context contains actual text, not file path!")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
