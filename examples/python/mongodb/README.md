# MongoDB Integration Examples for PraisonAI Agents

This directory contains comprehensive examples demonstrating how to integrate MongoDB with PraisonAI agents for memory, knowledge, and data operations.

## Features

MongoDB integration with PraisonAI provides:

- **Memory Provider**: Use MongoDB as a persistent memory store for agents
- **Knowledge Store**: Store and retrieve documents with vector search capabilities
- **Tools Integration**: Perform MongoDB operations directly from agents
- **Vector Search**: Leverage MongoDB Atlas Vector Search for semantic similarity
- **Scalability**: Handle large datasets with MongoDB's scalable architecture
- **Flexibility**: Use MongoDB as both key-value store and vector database

## Prerequisites

### Installation

```bash
# Install PraisonAI with MongoDB support
pip install 'praisonaiagents[mongodb]'
```

### Dependencies

- **MongoDB**: Local MongoDB instance or MongoDB Atlas
- **OpenAI API Key**: For embeddings and LLM operations
- **Python 3.10+**: Required for PraisonAI

### Environment Setup

```bash
# Set your OpenAI API key
export OPENAI_API_KEY="your-openai-api-key"

# Optional: Set MongoDB connection string
export MONGODB_CONNECTION_STRING="mongodb://localhost:27017/"
```

## Examples Overview

### 1. [mongodb_memory_example.py](mongodb_memory_example.py)

Demonstrates using MongoDB as a memory provider for PraisonAI agents.

**Features:**
- MongoDB as persistent memory storage
- Quality scoring and filtering
- Vector search for memory retrieval
- Multi-session memory persistence
- Memory search and context building

**Usage:**
```bash
python mongodb_memory_example.py
```

### 2. [mongodb_knowledge_example.py](mongodb_knowledge_example.py)

Shows how to use MongoDB as a knowledge store with vector search capabilities.

**Features:**
- MongoDB as knowledge vector store
- Document processing and storage
- Vector search for knowledge retrieval
- Knowledge-based agent interactions
- File processing with MongoDB storage

**Usage:**
```bash
python mongodb_knowledge_example.py
```

### 3. [mongodb_tools_example.py](mongodb_tools_example.py)

Demonstrates MongoDB tools integration for database operations.

**Features:**
- MongoDB CRUD operations
- Vector search with embeddings
- Data analysis and aggregation
- Collection management
- Index creation and optimization

**Usage:**
```bash
python mongodb_tools_example.py
```

### 4. [mongodb_comprehensive_example.py](mongodb_comprehensive_example.py)

Complete business scenario simulation using all MongoDB features.

**Features:**
- Full MongoDB integration (memory + knowledge + tools)
- Multi-agent business workflow
- Real-world e-commerce simulation
- Business intelligence analytics
- Customer service automation

**Usage:**
```bash
python mongodb_comprehensive_example.py
```

## Configuration

### MongoDB Memory Configuration

```python
mongodb_memory_config = {
    "provider": "mongodb",
    "config": {
        "connection_string": "mongodb://localhost:27017/",
        "database": "praisonai_memory",
        "use_vector_search": True,  # Enable Atlas Vector Search
        "max_pool_size": 50,
        "min_pool_size": 10,
        "server_selection_timeout": 5000
    }
}
```

### MongoDB Knowledge Configuration

```python
mongodb_knowledge_config = {
    "vector_store": {
        "provider": "mongodb",
        "config": {
            "connection_string": "mongodb://localhost:27017/",
            "database": "praisonai_knowledge",
            "collection": "knowledge_base",
            "use_vector_search": True
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small"
        }
    }
}
```

## MongoDB Atlas Vector Search

For production use with advanced vector search capabilities:

### Setup

1. **Create MongoDB Atlas Cluster**
   - Sign up for MongoDB Atlas
   - Create a new cluster
   - Get your connection string

2. **Enable Vector Search**
   - Create vector search indexes
   - Configure embedding dimensions (1536 for OpenAI)
   - Set similarity metric (cosine, euclidean, dotProduct)

3. **Update Connection String**
   ```python
   "connection_string": "mongodb+srv://username:password@cluster.mongodb.net/"
   ```

### Vector Search Index Creation

```python
# Vector search index definition
{
    "mappings": {
        "dynamic": True,
        "fields": {
            "embedding": {
                "type": "knnVector",
                "dimensions": 1536,
                "similarity": "cosine"
            }
        }
    }
}
```

## Best Practices

### 1. Connection Management

```python
# Use connection pooling
mongodb_config = {
    "connection_string": "mongodb://localhost:27017/",
    "max_pool_size": 50,
    "min_pool_size": 10,
    "maxIdleTimeMS": 30000,
    "serverSelectionTimeoutMS": 5000
}
```

### 2. Indexing Strategy

```python
# Create appropriate indexes
collection.create_index([("content", "text")])  # Text search
collection.create_index([("created_at", -1)])   # Time-based queries
collection.create_index([("metadata.category", 1)])  # Category filtering
```

### 3. Error Handling

```python
try:
    # MongoDB operations
    result = collection.insert_one(document)
except PyMongoError as e:
    logger.error(f"MongoDB error: {e}")
    # Implement fallback strategy
```

### 4. Data Validation

```python
# Validate data before storage
def validate_document(doc):
    required_fields = ["content", "metadata", "created_at"]
    return all(field in doc for field in required_fields)
```

## Performance Considerations

### 1. Indexing

- Create indexes on frequently queried fields
- Use compound indexes for complex queries
- Monitor index usage with MongoDB profiler

### 2. Vector Search Optimization

- Use appropriate vector dimensions
- Optimize numCandidates parameter
- Consider filtering to reduce search space

### 3. Connection Pooling

- Configure appropriate pool sizes
- Use connection pooling for high-concurrency scenarios
- Monitor connection metrics

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Check MongoDB server is running
   - Verify connection string format
   - Ensure network connectivity

2. **Vector Search Issues**
   - Verify Atlas Vector Search indexes exist
   - Check embedding dimensions match
   - Ensure proper index configuration

3. **Memory Issues**
   - Monitor memory usage with large datasets
   - Use appropriate batch sizes
   - Consider data pagination

### Debugging

```python
# Enable detailed logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Monitor MongoDB operations
from pymongo import monitoring
monitoring.register(CommandLogger())
```

## Production Deployment

### 1. Security

```python
# Use authentication
connection_string = "mongodb://username:password@host:port/database"

# Enable SSL/TLS
client = MongoClient(connection_string, tls=True)
```

### 2. Monitoring

- Use MongoDB Atlas monitoring
- Implement application-level metrics
- Set up alerting for critical issues

### 3. Backup and Recovery

- Configure automated backups
- Test restore procedures
- Implement disaster recovery plans

## Support

For additional support:

- [PraisonAI Documentation](https://docs.praisonai.com)
- [MongoDB Documentation](https://docs.mongodb.com)
- [MongoDB Atlas Vector Search](https://docs.atlas.mongodb.com/atlas-vector-search/)

## License

These examples are provided under the same license as PraisonAI.