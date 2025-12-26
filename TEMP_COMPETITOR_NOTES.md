# Competitor Analysis Notes (INTERNAL - DO NOT PUBLISH)

## Agno VectorDB Patterns

### Base Class Design
- Abstract `VectorDb` class with sync + async methods
- Methods: `create`, `insert`, `upsert`, `search`, `drop`, `delete`, `exists`
- Uses `Document` dataclass for content
- Supports filters on all operations
- `content_hash` for deduplication
- `id`, `name`, `description` fields

### Supported Backends (from /agno/libs/agno/agno/vectordb/)
- cassandra, chroma, clickhouse, couchbase, lancedb
- langchaindb (adapter), lightrag, llamaindex (adapter)
- milvus, mongodb, pgvector, pineconedb, qdrant, redis
- singlestore, surrealdb, upstashdb, weaviate

### Key Patterns
1. Each backend in its own subdirectory
2. Lazy imports of heavy dependencies
3. Both sync and async variants
4. Filter support for metadata queries
5. Embedder integration (separate from vectordb)

---

## Agno Storage/Session Patterns

### Session Storage (from agno/storage/)
- PostgreSQL, SQLite, MongoDB, DynamoDB, Redis, S3, Singlestore
- `AgentStorage` base class
- Methods: `create`, `read`, `upsert`, `delete`, `drop`
- Stores: sessions, runs, memories

### Key Patterns
1. Session-based storage (session_id as key)
2. Run tracking (run_id within session)
3. Memory persistence
4. Async variants available

---

## Observability Patterns (from cookbook examples)

### Integration Approach
- Environment variable based configuration
- OpenTelemetry as common bridge
- Provider-specific SDK initialization
- Trace context propagation

### Providers Referenced
- Arize Phoenix, Langfuse, Langtrace, Traceloop
- OpenLIT, Braintrust, AgentOps

---

## CrewAI Memory Patterns

### Memory Types
- Short-term, Long-term, Entity memory
- External memory adapters
- Async memory support

### Storage
- ChromaDB as default vector store
- External storage adapters

---

## Design Decisions for PraisonAI

### VectorDB/Knowledge
1. Use `KnowledgeStore` as base class (already exists)
2. Add missing backends: Couchbase, LightRAG, LangChain adapter, LlamaIndex adapter
3. Add vector mode for: SingleStore, SurrealDB, MongoDB Atlas

### Conversation/State
1. Use existing `ConversationStore` and `StateStore` base classes
2. Add async variants for: PostgreSQL, MySQL, SQLite, MongoDB
3. Add Neon as PostgreSQL-compatible layer

### Observability
1. Use `BaseObservabilityProvider` (already exists in PraisonAI-tools)
2. All 20 providers already implemented
3. Need to wire into core SDK with lazy loading

### API Simplicity Target
```python
from praisonaiagents import Agent, db, obs

agent = Agent(
    db=db.PraisonDB(url="postgresql://..."),
    observability=obs.auto()  # or obs.langfuse()
)
```

This requires:
1. `db` module in praisonaiagents with lazy loading
2. `obs` module in praisonaiagents with lazy loading
3. Both delegate to wrapper package implementations
