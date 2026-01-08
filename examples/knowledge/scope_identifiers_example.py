#!/usr/bin/env python3
"""
Example: Using Scope Identifiers (user_id, agent_id, run_id)

This example demonstrates:
1. Multi-user knowledge isolation with user_id
2. Multi-agent knowledge sharing with agent_id
3. Run-specific context with run_id
4. Error handling for missing scope identifiers

Requirements:
- pip install praisonaiagents[knowledge]
- OPENAI_API_KEY environment variable

Usage:
    python scope_identifiers_example.py
"""

import os
import tempfile
import shutil

from praisonaiagents import Agent


def main():
    temp_dir = tempfile.mkdtemp(prefix='praison_scope_')
    
    try:
        # Create test document
        doc = os.path.join(temp_dir, 'shared_knowledge.txt')
        with open(doc, 'w') as f:
            f.write("""
            Company Policy Document
            
            1. All employees must complete security training annually.
            2. Remote work is allowed with manager approval.
            3. Expense reports must be submitted within 30 days.
            """)
        
        print("=" * 60)
        print("Example: Scope Identifiers for Knowledge Isolation")
        print("=" * 60)
        
        # Example 1: User-scoped knowledge
        print("\n1. User-scoped knowledge (user_id):")
        print("-" * 40)
        
        user1_agent = Agent(
            name="HR_Assistant_User1",
            instructions="You are an HR assistant.",
            knowledge=[temp_dir],
            user_id="user_alice",  # Knowledge scoped to Alice
        )
        
        response = user1_agent.chat("What is the policy on remote work?")
        print("User Alice asks: What is the policy on remote work?")
        print(f"Response: {response[:200]}...")
        
        # Example 2: Agent-scoped knowledge
        print("\n2. Agent-scoped knowledge (agent_id):")
        print("-" * 40)
        
        shared_agent = Agent(
            name="Policy_Expert",
            instructions="You are a policy expert.",
            knowledge=[temp_dir],
            agent_id="policy_agent_v1",  # Knowledge scoped to this agent
        )
        
        response = shared_agent.chat("What are the expense report rules?")
        print("Agent policy_agent_v1 query: What are the expense report rules?")
        print(f"Response: {response[:200]}...")
        
        # Example 3: Combined scoping
        print("\n3. Combined scoping (user_id + agent_id):")
        print("-" * 40)
        
        combined_agent = Agent(
            name="Personal_HR_Bot",
            instructions="You are a personal HR assistant.",
            knowledge=[temp_dir],
            user_id="user_bob",
            agent_id="hr_bot_v2",
        )
        
        response = combined_agent.chat("What training is required?")
        print("User Bob with hr_bot_v2: What training is required?")
        print(f"Response: {response[:200]}...")
        
        print("\n" + "=" * 60)
        print("Scope Identifier Summary:")
        print("=" * 60)
        print("""
- user_id: Isolates knowledge per user (multi-tenant)
- agent_id: Isolates knowledge per agent type/version
- run_id: Isolates knowledge per execution run (ephemeral)

Best Practices:
1. Always provide at least one scope identifier
2. Use user_id for user-specific data
3. Use agent_id for shared agent knowledge
4. Use run_id for temporary/session-specific context
        """)
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
