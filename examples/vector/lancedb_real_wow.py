"""LanceDB Vector Store - Local Test"""
import sys
import os
import shutil

try:
    import lancedb
except ImportError:
    print("SKIPPED: LanceDB - lancedb not installed")
    sys.exit(0)

# Clean up previous test
db_path = "/tmp/lancedb_test"
if os.path.exists(db_path):
    shutil.rmtree(db_path)

db = lancedb.connect(db_path)

# Create table with vectors
data = [
    {"id": "1", "text": "Machine learning is AI", "vector": [0.1] * 128},
    {"id": "2", "text": "Deep learning uses neural nets", "vector": [0.2] * 128},
]
table = db.create_table("demo", data)

# Search
results = table.search([0.1] * 128).limit(1).to_list()
print(f"Found: {len(results)} results")
print(f"Top result: {results[0]['text'][:30]}...")
assert len(results) >= 1
print("PASSED: LanceDB vector store")
