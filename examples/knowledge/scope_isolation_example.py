#!/usr/bin/env python3
"""
Example: Multi-Agent Scope Isolation

This example demonstrates:
1. Agent A ingests knowledge under user_id=U1
2. Agent B queries under user_id=U2 - should NOT find the knowledge
3. Agent B queries under user_id=U1 - should find the knowledge
4. Proves scope isolation works correctly

Requirements:
- pip install praisonaiagents[knowledge]
- OPENAI_API_KEY environment variable

Usage:
    python scope_isolation_example.py
"""

import os
import tempfile
import shutil

from praisonaiagents import Agent, Knowledge


def main():
    temp_dir = tempfile.mkdtemp(prefix='praison_scope_')
    
    try:
        # Create test document with UNIQUE secret
        doc = os.path.join(temp_dir, 'secret.txt')
        with open(doc, 'w') as f:
            f.write("""
Project Codename: PHOENIX
Secret access code: WRENCH-992
Classification: Top Secret
Only authorized personnel with code WRENCH-992 may access this project.
            """)
        
        print("=" * 60)
        print("Example: Multi-Agent Scope Isolation")
        print("=" * 60)
        
        # Step 1: Agent A ingests knowledge under user_id=U1
        print("\n1. Agent A ingests knowledge under user_id='user_alice'")
        print("-" * 40)
        
        agent_a = Agent(
            name="AgentA_Ingester",
            instructions="You ingest and store knowledge.",
            knowledge=[temp_dir],
            user_id="user_alice",  # Scoped to Alice
            verbose=False,
        )
        
        # Ensure knowledge is processed
        agent_a._ensure_knowledge_processed()
        print("   Knowledge ingested by Agent A under user_alice scope")
        
        # Step 2: Agent B queries under user_id=U2 - should NOT find
        print("\n2. Agent B queries under user_id='user_bob' (different scope)")
        print("-" * 40)
        
        # Create a separate Knowledge instance for Agent B with different scope
        knowledge_b = Knowledge()
        search_result = knowledge_b.search("WRENCH-992", user_id="user_bob")
        
        results = search_result.get('results', []) if isinstance(search_result, dict) else []
        
        if len(results) == 0:
            print("   ✅ CORRECT: Agent B (user_bob) found NO results")
            print("   Scope isolation is working!")
        else:
            # Check if any result actually contains the secret
            found_secret = any('wrench-992' in str(r.get('memory', '')).lower() for r in results)
            if found_secret:
                print("   ❌ ERROR: Agent B found the secret - scope isolation failed!")
            else:
                print("   ✅ CORRECT: Agent B found no matching content")
        
        # Step 3: Agent B queries under user_id=U1 - should find
        print("\n3. Agent B queries under user_id='user_alice' (same scope)")
        print("-" * 40)
        
        search_result = knowledge_b.search("WRENCH-992", user_id="user_alice")
        results = search_result.get('results', []) if isinstance(search_result, dict) else []
        
        if len(results) > 0:
            memory = results[0].get('memory', '')
            if 'wrench-992' in memory.lower():
                print("   ✅ CORRECT: Agent B (as user_alice) found the secret!")
                print(f"   Retrieved: {memory[:80]}...")
            else:
                print(f"   ⚠️ Found results but no secret: {memory[:80]}...")
        else:
            print("   ❌ ERROR: Agent B should have found results with user_alice scope")
        
        # Step 4: Full Agent chat test with scope
        print("\n4. Full Agent chat test with correct scope")
        print("-" * 40)
        
        agent_b = Agent(
            name="AgentB_Querier",
            instructions="Answer questions based on the provided knowledge. If you don't have the information, say so.",
            knowledge=[temp_dir],
            user_id="user_alice",  # Same scope as Agent A
            verbose=False,
        )
        
        response = agent_b.chat("What is the secret access code for Project PHOENIX?")
        print(f"   Question: What is the secret access code?")
        print(f"   Answer: {response}")
        
        if "WRENCH-992" in response.upper():
            print("\n   ✅ VERIFIED: Agent correctly retrieved the secret code!")
        else:
            print("\n   ⚠️ Agent may not have found the code")
        
        print("\n" + "=" * 60)
        print("Summary: Scope Isolation")
        print("=" * 60)
        print("""
- user_id='user_alice': Can access knowledge ingested by user_alice
- user_id='user_bob': Cannot access knowledge ingested by user_alice
- This enables multi-tenant knowledge isolation
        """)
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
