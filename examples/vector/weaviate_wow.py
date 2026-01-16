"""Weaviate Cloud Vector Store - Agent-First Example

Requires: export WEAVIATE_URL=... and WEAVIATE_API_KEY=...
"""
import os
import sys
from praisonaiagents import Agent

weaviate_url = os.getenv("WEAVIATE_URL", "https://your-cluster.weaviate.cloud")
weaviate_key = os.getenv("WEAVIATE_API_KEY")
if not weaviate_key:
    print("SKIPPED: Weaviate - WEAVIATE_API_KEY not set")
    sys.exit(0)

# Agent-first approach: use knowledge parameter with Weaviate
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge=["./docs/guide.pdf"],  # Add your documents here
    knowledge={
        "vector_store": "weaviate",
        "url": weaviate_url,
        "api_key": weaviate_key
    }
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: Weaviate with Agent")

# --- Advanced: Direct Store Usage ---
# import weaviate
# from weaviate.classes.init import Auth
# client = weaviate.connect_to_weaviate_cloud(cluster_url=weaviate_url, auth_credentials=Auth.api_key(weaviate_key))
