"""
Storage Backends Example for PraisonAI Agents.

Demonstrates how to use different storage backends (File, SQLite, Redis)
for agent data persistence across all supported components.

Supported Backends:
- FileBackend: JSON file-based storage (default, zero dependencies)
- SQLiteBackend: SQLite database storage (zero dependencies)
- RedisBackend: Redis-based storage (requires redis package)

Supported Components:
- BaseJSONStore: Generic JSON storage
- TrainingStorage: Agent training data
- SessionManager: CLI session state
- RunHistory: Recipe run history
- MCPToolIndex: MCP tool schemas

Usage:
    python storage_backends_example.py
"""

from praisonaiagents.storage import (
    FileBackend,
    SQLiteBackend,
    BaseJSONStore,
    get_backend,
)


def example_file_backend():
    """Example: Using FileBackend for JSON file storage."""
    print("\n=== FileBackend Example ===")
    
    # Create file backend
    backend = FileBackend(storage_dir="/tmp/praison_example")
    
    # Save data
    backend.save("agent_state", {
        "agent_name": "Research Assistant",
        "messages": ["Hello", "How can I help?"],
        "context": {"topic": "AI"}
    })
    
    # Load data
    data = backend.load("agent_state")
    print(f"Loaded: {data}")
    
    # List keys
    keys = backend.list_keys()
    print(f"Keys: {keys}")
    
    # Check existence
    print(f"Exists: {backend.exists('agent_state')}")
    
    # Clean up
    backend.delete("agent_state")
    print("Deleted agent_state")


def example_sqlite_backend():
    """Example: Using SQLiteBackend for database storage."""
    print("\n=== SQLiteBackend Example ===")
    
    # Create SQLite backend (single file, better for concurrent access)
    backend = SQLiteBackend(db_path="/tmp/praison_example.db")
    
    # Save multiple sessions
    for i in range(3):
        backend.save(f"session_{i}", {
            "session_id": f"sess-{i}",
            "messages": [f"Message {j}" for j in range(i + 1)],
            "timestamp": "2024-01-01T00:00:00Z"
        })
    
    # List all sessions
    keys = backend.list_keys(prefix="session_")
    print(f"Sessions: {keys}")
    
    # Load specific session
    session = backend.load("session_1")
    print(f"Session 1: {session}")
    
    # Clean up
    backend.clear()
    backend.close()
    print("Cleaned up SQLite backend")


def example_backend_factory():
    """Example: Using get_backend factory function."""
    print("\n=== Backend Factory Example ===")
    
    # Easy switching between backends
    backend_type = "sqlite"  # Change to "file" or "redis" as needed
    
    if backend_type == "file":
        backend = get_backend("file", storage_dir="/tmp/praison_factory")
    elif backend_type == "sqlite":
        backend = get_backend("sqlite", db_path="/tmp/praison_factory.db")
    # elif backend_type == "redis":
    #     backend = get_backend("redis", url="redis://localhost:6379")
    
    # Use backend
    backend.save("config", {"model": "gpt-4", "temperature": 0.7})
    config = backend.load("config")
    print(f"Config: {config}")
    
    # Clean up
    backend.delete("config")


def example_with_base_json_store():
    """Example: Using BaseJSONStore with custom backend."""
    print("\n=== BaseJSONStore with Backend Example ===")
    
    # Create a custom store with SQLite backend
    backend = SQLiteBackend(db_path="/tmp/praison_store.db")
    
    store = BaseJSONStore(
        storage_path="/tmp/my_store.json",  # Used as key name
        backend=backend,
    )
    
    # Save and load data
    store.save({"items": [1, 2, 3], "count": 3})
    data = store.load()
    print(f"Store data: {data}")
    
    # Clean up
    store.delete()
    backend.close()


def example_training_storage_with_backend():
    """Example: Using TrainingStorage with SQLite backend."""
    print("\n=== TrainingStorage with Backend Example ===")
    
    try:
        from praisonai.train.agents.storage import TrainingStorage
        
        # Create SQLite backend for training data
        backend = SQLiteBackend(db_path="/tmp/training.db")
        
        # Use with TrainingStorage
        storage = TrainingStorage(
            session_id="train-example-001",
            backend=backend,
        )
        
        print(f"Training storage created with session: {storage.session_id}")
        print("Training data will be stored in SQLite instead of JSON files")
        
        backend.close()
    except ImportError:
        print("praisonai package not installed, skipping training example")


def example_session_manager_with_backend():
    """Example: Using SessionManager with SQLite backend."""
    print("\n=== SessionManager with Backend Example ===")
    
    try:
        from praisonai.cli.state.sessions import SessionManager
        
        # Create SQLite backend for sessions
        backend = SQLiteBackend(db_path="/tmp/sessions.db")
        
        # Use with SessionManager
        manager = SessionManager(backend=backend)
        sessions = manager.list(limit=10)
        
        print(f"SessionManager created with SQLite backend, {len(sessions)} sessions")
        print("Sessions will be stored in database instead of files")
        
        backend.close()
    except ImportError:
        print("praisonai package not installed, skipping session example")


def example_run_history_with_backend():
    """Example: Using RunHistory with SQLite backend."""
    print("\n=== RunHistory with Backend Example ===")
    
    try:
        from praisonai.recipe.history import RunHistory
        
        # Create SQLite backend for run history
        backend = SQLiteBackend(db_path="/tmp/runs.db")
        
        # Use with RunHistory
        history = RunHistory(backend=backend)
        runs = history.list()
        
        print(f"RunHistory created with SQLite backend, {len(runs)} runs")
        print("Recipe runs will be stored in database instead of files")
        
        backend.close()
    except ImportError:
        print("praisonai package not installed, skipping run history example")


def example_mcp_tool_index_with_backend():
    """Example: Using MCPToolIndex with SQLite backend."""
    print("\n=== MCPToolIndex with Backend Example ===")
    
    try:
        from praisonai.mcp_server.tool_index import MCPToolIndex
        
        # Create SQLite backend for MCP tool index
        backend = SQLiteBackend(db_path="/tmp/mcp.db")
        
        # Use with MCPToolIndex
        index = MCPToolIndex(backend=backend)
        servers = index.list_servers()
        
        print(f"MCPToolIndex created with SQLite backend, {len(servers)} servers")
        print("MCP tool schemas will be stored in database instead of files")
        
        backend.close()
    except ImportError:
        print("praisonai package not installed, skipping MCP example")


def example_redis_backend():
    """Example: Using RedisBackend for high-speed caching."""
    print("\n=== RedisBackend Example ===")
    
    try:
        from praisonaiagents.storage import RedisBackend
        
        # Create Redis backend with TTL
        backend = RedisBackend(
            url="redis://localhost:6379",
            prefix="example:",
            ttl=3600  # 1 hour TTL
        )
        
        # CRUD operations
        backend.save("test_key", {"data": "value", "count": 42})
        data = backend.load("test_key")
        print(f"Loaded from Redis: {data}")
        
        # List keys
        keys = backend.list_keys()
        print(f"Keys: {keys}")
        
        # Clean up
        backend.delete("test_key")
        backend.close()
        print("RedisBackend example completed")
        
    except ImportError:
        print("redis package not installed: pip install redis")
    except Exception as e:
        print(f"Redis not available: {e}")


if __name__ == "__main__":
    print("PraisonAI Storage Backends Examples")
    print("=" * 50)
    
    example_file_backend()
    example_sqlite_backend()
    example_backend_factory()
    example_with_base_json_store()
    example_training_storage_with_backend()
    example_session_manager_with_backend()
    example_run_history_with_backend()
    example_mcp_tool_index_with_backend()
    example_redis_backend()
    
    print("\n" + "=" * 50)
    print("All examples completed!")
