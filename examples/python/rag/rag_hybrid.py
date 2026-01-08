"""
RAG Hybrid Retrieval Example

Demonstrates hybrid retrieval (dense + BM25 keyword search) for better results.

Requirements:
    pip install praisonaiagents
    
Environment:
    OPENAI_API_KEY - Required for LLM calls
"""

import os
from praisonaiagents import Agent, AutoRagAgent

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)

# Create a sample document with technical content
sample_doc = "/tmp/rag_hybrid_doc.txt"
with open(sample_doc, "w") as f:
    f.write("""
API Documentation

Authentication:
All API requests require an API key in the X-API-Key header.
Rate limits: 100 requests per minute for free tier, 1000 for pro tier.

Endpoints:

POST /api/v1/users
Creates a new user account.
Required fields: email, password, name
Returns: user_id, created_at

GET /api/v1/users/{id}
Retrieves user information by ID.
Returns: email, name, created_at, last_login

PUT /api/v1/users/{id}
Updates user information.
Optional fields: name, email, password

DELETE /api/v1/users/{id}
Deletes a user account. Requires admin privileges.

Error Codes:
- 400: Bad Request - Invalid input
- 401: Unauthorized - Missing or invalid API key
- 403: Forbidden - Insufficient permissions
- 404: Not Found - Resource doesn't exist
- 429: Too Many Requests - Rate limit exceeded
""")

# Create agent with knowledge
agent = Agent(
    name="APIDocBot",
    instructions="You are an API documentation assistant.",
    knowledge=[sample_doc],
    user_id="hybrid_user",
    llm="openai/gpt-4o-mini",
    output="minimal",
)

print("=" * 60)
print("RAG Hybrid Retrieval Example")
print("=" * 60)

# Standard retrieval
print("\n[Standard Retrieval]")
auto_rag_standard = AutoRagAgent(agent=agent, hybrid=False)
response = auto_rag_standard.chat("What error code means rate limit exceeded?")
print(f"Response: {response}")

# Hybrid retrieval (dense + BM25)
print("\n[Hybrid Retrieval - Dense + BM25]")
auto_rag_hybrid = AutoRagAgent(agent=agent, hybrid=True)
response = auto_rag_hybrid.chat("What error code means rate limit exceeded?")
print(f"Response: {response}")

# Hybrid with reranking for best quality
print("\n[Hybrid + Reranking]")
auto_rag_best = AutoRagAgent(agent=agent, hybrid=True, rerank=True, top_k=10)
response = auto_rag_best.chat("How do I create a new user via the API?")
print(f"Response: {response}")

# Cleanup
os.remove(sample_doc)

print("\n" + "=" * 60)
print("Example completed successfully!")
print("=" * 60)
