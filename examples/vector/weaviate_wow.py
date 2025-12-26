"""Weaviate Cloud Vector Store - Real API Test"""
import os
import sys

# Requires: export WEAVIATE_URL=... and WEAVIATE_API_KEY=...
weaviate_url = os.getenv("WEAVIATE_URL", "https://thhoyczshsawyt16ot3uw.c0.europe-west3.gcp.weaviate.cloud")
weaviate_key = os.getenv("WEAVIATE_API_KEY")
if not weaviate_key:
    print("SKIPPED: Weaviate - WEAVIATE_API_KEY not set")
    sys.exit(0)

import weaviate
from weaviate.classes.init import Auth

client = weaviate.connect_to_weaviate_cloud(
    cluster_url=weaviate_url,
    auth_credentials=Auth.api_key(weaviate_key)
)

print(f"Weaviate connected: {client.is_ready()}")
collections = client.collections.list_all()
print(f"Found {len(collections)} collections")
client.close()
print("PASSED: Weaviate cloud vector store")
