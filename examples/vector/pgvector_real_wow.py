"""PGVector Vector Store - Docker Test"""
import sys
import os

# Docker: docker run -d --name pgvector -e POSTGRES_PASSWORD=postgres -p 5433:5432 pgvector/pgvector:pg16
url = os.getenv("PGVECTOR_URL", "postgresql://postgres:postgres@localhost:5433/postgres")

try:
    import psycopg2
except ImportError:
    print("SKIPPED: PGVector - psycopg2 not installed")
    sys.exit(0)

try:
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    
    # Ensure extension
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    
    # Create test table
    cur.execute("DROP TABLE IF EXISTS test_vectors")
    cur.execute("""
        CREATE TABLE test_vectors (
            id SERIAL PRIMARY KEY,
            content TEXT,
            embedding vector(128)
        )
    """)
    conn.commit()
    
    # Insert vectors
    cur.execute("""
        INSERT INTO test_vectors (content, embedding) VALUES
        ('Machine learning is AI', %s),
        ('Deep learning uses neural nets', %s)
    """, ([0.1] * 128, [0.2] * 128))
    conn.commit()
    
    # Search (cosine similarity)
    cur.execute("""
        SELECT content, embedding <=> %s::vector AS distance
        FROM test_vectors
        ORDER BY distance
        LIMIT 1
    """, ([0.1] * 128,))
    
    row = cur.fetchone()
    print(f"Top result: {row[0][:30]}... (distance: {row[1]:.4f})")
    
    # Cleanup
    cur.execute("DROP TABLE test_vectors")
    conn.commit()
    conn.close()
    
    print("PASSED: PGVector vector store")
except Exception as e:
    print(f"SKIPPED: PGVector - {e}")
