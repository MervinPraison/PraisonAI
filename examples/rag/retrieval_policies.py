"""
Retrieval Policies: Agent-Decided Retrieval Strategies

This example demonstrates how agents can dynamically decide retrieval
strategies based on query characteristics.

RAG Concept: Not all queries are equal. Some need deep retrieval, others
need broad coverage, and some don't need retrieval at all. Smart policies
optimize both quality and efficiency.
"""

from praisonaiagents import Agent, AutoRagAgent, AutoRagConfig
from praisonaiagents.agents.auto_rag_agent import RetrievalPolicy

# Sample knowledge base: IT support documentation
IT_SUPPORT_DOCS = [
    {
        "id": "password_reset",
        "category": "account",
        "priority": "high",
        "content": """
        Password Reset Procedure:
        1. Go to the self-service portal at https://portal.company.com
        2. Click "Forgot Password"
        3. Enter your employee ID and email
        4. Check your email for the reset link (valid for 1 hour)
        5. Create a new password meeting complexity requirements
        
        If you don't receive the email, check spam or contact IT helpdesk.
        """
    },
    {
        "id": "vpn_setup",
        "category": "network",
        "priority": "medium",
        "content": """
        VPN Setup Guide:
        1. Download the VPN client from the software center
        2. Install with default settings
        3. Launch and enter your credentials
        4. Select the nearest server location
        5. Click Connect
        
        Troubleshooting: If connection fails, check firewall settings
        and ensure port 443 is open.
        """
    },
    {
        "id": "email_config",
        "category": "communication",
        "priority": "medium",
        "content": """
        Email Configuration:
        - Server: mail.company.com
        - Port: 993 (IMAP) / 587 (SMTP)
        - Security: SSL/TLS required
        - Username: your full email address
        
        Mobile setup: Use the Company Portal app for automatic configuration.
        """
    },
    {
        "id": "printer_setup",
        "category": "hardware",
        "priority": "low",
        "content": """
        Printer Setup:
        1. Open Settings > Printers & Scanners
        2. Click Add Printer
        3. Select your floor's printer from the list
        4. Install drivers if prompted
        
        Printer naming convention: FLOOR-WING-NUMBER (e.g., 3-EAST-01)
        """
    },
    {
        "id": "software_request",
        "category": "software",
        "priority": "medium",
        "content": """
        Software Request Process:
        1. Submit request through ServiceNow
        2. Manager approval required for licensed software
        3. IT reviews for security compliance
        4. Approved software deployed within 48 hours
        
        Pre-approved software can be installed directly from Software Center.
        """
    }
]


def query_classification():
    """Demonstrate query classification for retrieval decisions."""
    
    print("=" * 60)
    print("QUERY CLASSIFICATION FOR RETRIEVAL")
    print("=" * 60)
    
    # Different query types
    queries = [
        ("How do I reset my password?", "procedural", True),
        ("Hello!", "greeting", False),
        ("What is 2 + 2?", "general_knowledge", False),
        ("VPN connection keeps failing", "troubleshooting", True),
        ("Thanks for your help", "closing", False),
        ("How do I request new software?", "procedural", True),
    ]
    
    print("\n📊 Query Classification Examples:\n")
    print(f"{'Query':<40} {'Type':<20} {'Needs RAG':<10}")
    print("-" * 70)
    
    for query, query_type, needs_rag in queries:
        rag_indicator = "✅ Yes" if needs_rag else "❌ No"
        print(f"{query:<40} {query_type:<20} {rag_indicator:<10}")
    
    print("\n💡 Smart agents classify queries to decide retrieval strategy.")


def policy_based_retrieval():
    """Demonstrate different retrieval policies."""
    
    print("\n" + "=" * 60)
    print("RETRIEVAL POLICY COMPARISON")
    print("=" * 60)
    
    # Build context
    context = "\n\n".join([f"[{d['id']}]\n{d['content']}" for d in IT_SUPPORT_DOCS])
    
    base_agent = Agent(
        name="IT Support",
        instructions=f"""You are an IT support agent. Help users with technical issues.
        
        IT SUPPORT DOCS:
        {context}""",
        verbose=False
    )
    
    query = "How do I set up VPN?"
    
    policies = [
        (RetrievalPolicy.AUTO, "Agent decides based on query analysis"),
        (RetrievalPolicy.ALWAYS, "Always retrieve, even for simple queries"),
        (RetrievalPolicy.NEVER, "Never retrieve, use only parametric knowledge"),
    ]
    
    print(f"\n📝 Query: {query}\n")
    
    for policy, description in policies:
        config = AutoRagConfig(retrieval_policy=policy)
        auto_agent = AutoRagAgent(agent=base_agent, config=config)
        
        print(f"🔄 Policy: {policy.value.upper()}")
        print(f"   Description: {description}")
        
        response = auto_agent.chat(query)
        print(f"   Response: {response[:150]}...")
        print()


def adaptive_top_k():
    """Demonstrate adaptive top-k based on query complexity."""
    
    print("\n" + "=" * 60)
    print("ADAPTIVE TOP-K RETRIEVAL")
    print("=" * 60)
    
    print("""
    📊 Adaptive Top-K Strategy:
    
    Query Complexity → Top-K Value
    ─────────────────────────────────
    Simple (single topic)     → k=1-2
    Moderate (related topics) → k=3-5
    Complex (multi-topic)     → k=5-10
    
    Examples:
    """)
    
    queries = [
        ("Reset password", 2, "Simple - single procedure"),
        ("VPN not working, also need email setup", 5, "Moderate - two topics"),
        ("New employee setup: email, VPN, printer, software", 8, "Complex - multiple topics"),
    ]
    
    for query, suggested_k, complexity in queries:
        print(f"   Query: \"{query}\"")
        print(f"   Complexity: {complexity}")
        print(f"   Suggested top_k: {suggested_k}")
        print()


def priority_based_retrieval():
    """Demonstrate priority-based document retrieval."""
    
    print("\n" + "=" * 60)
    print("PRIORITY-BASED RETRIEVAL")
    print("=" * 60)
    
    # Group documents by priority
    high_priority = [d for d in IT_SUPPORT_DOCS if d.get('priority') == 'high']
    all_docs = IT_SUPPORT_DOCS
    
    print("\n📊 Document Priorities in Knowledge Base:")
    for doc in IT_SUPPORT_DOCS:
        print(f"   [{doc['priority'].upper():^6}] {doc['id']}")
    
    # Build contexts
    high_context = "\n\n".join([f"[{d['id']}]\n{d['content']}" for d in high_priority])
    full_context = "\n\n".join([f"[{d['id']}]\n{d['content']}" for d in all_docs])
    
    # High-priority agent (for urgent issues)
    urgent_agent = Agent(
        name="Urgent Support",
        instructions=f"""Handle urgent IT issues. Focus on critical procedures.
        
        HIGH PRIORITY DOCS:
        {high_context}""",
        verbose=False
    )
    
    # Full knowledge agent
    full_agent = Agent(
        name="Full Support",
        instructions=f"""Handle all IT support requests.
        
        IT SUPPORT DOCS:
        {full_context}""",
        verbose=False
    )
    
    query = "I'm locked out of my account!"
    
    print(f"\n📝 Urgent Query: {query}")
    
    print("\n🚨 Urgent Support Agent (high-priority docs only):")
    response1 = urgent_agent.chat(query)
    print(f"   {response1[:200]}...")
    
    print("\n📚 Full Support Agent (all docs):")
    response2 = full_agent.chat(query)
    print(f"   {response2[:200]}...")


def context_aware_retrieval():
    """Demonstrate context-aware retrieval strategies."""
    
    print("\n" + "=" * 60)
    print("CONTEXT-AWARE RETRIEVAL")
    print("=" * 60)
    
    print("""
    🎯 Context-Aware Retrieval Strategies:
    
    1. **User Role Context**
       - New employee → Onboarding docs first
       - IT admin → Technical docs
       - Executive → Summary docs
    
    2. **Time Context**
       - Business hours → Standard support
       - After hours → Emergency procedures only
    
    3. **Conversation Context**
       - First message → Broad retrieval
       - Follow-up → Narrow to topic
    
    4. **Device Context**
       - Mobile → Mobile-specific guides
       - Desktop → Full documentation
    
    Implementation:
    ```python
    def get_retrieval_config(context: dict) -> dict:
        if context.get("user_role") == "new_employee":
            return {"filter": {"category": "onboarding"}, "top_k": 5}
        elif context.get("is_followup"):
            return {"top_k": 2}  # Narrow focus
        else:
            return {"top_k": 3}  # Default
    ```
    """)


def fallback_strategies():
    """Demonstrate fallback strategies when retrieval fails."""
    
    print("\n" + "=" * 60)
    print("RETRIEVAL FALLBACK STRATEGIES")
    print("=" * 60)
    
    print("""
    🔄 Fallback Strategy Chain:
    
    1. Primary: Vector search in knowledge base
       ↓ (if no relevant results)
    2. Secondary: Expand search with synonyms
       ↓ (if still no results)
    3. Tertiary: Search external sources
       ↓ (if still no results)
    4. Final: Acknowledge limitation, offer alternatives
    
    Example Implementation:
    ```python
    def retrieve_with_fallback(query: str, knowledge) -> str:
        # Primary retrieval
        results = knowledge.search(query, top_k=3)
        
        if results and results[0].score > 0.7:
            return format_context(results)
        
        # Fallback: Expand query
        expanded = expand_query(query)  # Add synonyms
        results = knowledge.search(expanded, top_k=5)
        
        if results and results[0].score > 0.5:
            return format_context(results)
        
        # Final fallback
        return "I don't have specific information about that. " \\
               "Please contact IT helpdesk at ext. 1234."
    ```
    """)


def retrieval_metrics():
    """Explain retrieval quality metrics."""
    
    print("\n" + "=" * 60)
    print("RETRIEVAL QUALITY METRICS")
    print("=" * 60)
    
    print("""
    📈 Key Metrics for Retrieval Policy Tuning:
    
    ┌─────────────────┬────────────────────────────────────────┐
    │ Metric          │ Description                            │
    ├─────────────────┼────────────────────────────────────────┤
    │ Precision@K     │ % of retrieved docs that are relevant │
    │ Recall@K        │ % of relevant docs that are retrieved │
    │ MRR             │ Mean Reciprocal Rank of first hit     │
    │ NDCG            │ Normalized Discounted Cumulative Gain │
    │ Latency         │ Time to retrieve (ms)                 │
    │ Token Usage     │ Context tokens consumed               │
    └─────────────────┴────────────────────────────────────────┘
    
    Policy Optimization Goals:
    
    - High Precision: Use smaller top_k, stricter thresholds
    - High Recall: Use larger top_k, relaxed thresholds
    - Low Latency: Use smaller top_k, skip reranking
    - Low Cost: Use smaller top_k, aggressive filtering
    
    Balanced Default:
    ```python
    config = {
        "top_k": 3,
        "score_threshold": 0.5,
        "rerank": True,
        "max_tokens": 2000
    }
    ```
    """)


def main():
    """Run all retrieval policy examples."""
    print("\n🚀 PraisonAI Retrieval Policies Examples\n")
    
    # Example 1: Query classification
    query_classification()
    
    # Example 2: Policy comparison
    policy_based_retrieval()
    
    # Example 3: Adaptive top-k
    adaptive_top_k()
    
    # Example 4: Priority-based
    priority_based_retrieval()
    
    # Example 5: Context-aware
    context_aware_retrieval()
    
    # Example 6: Fallback strategies
    fallback_strategies()
    
    # Example 7: Metrics
    retrieval_metrics()
    
    print("\n✅ Retrieval policies examples completed!")


if __name__ == "__main__":
    main()
