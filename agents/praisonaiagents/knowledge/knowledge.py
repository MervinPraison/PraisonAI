# knowledge.py
"""
PraisonAI Knowledge - Advanced knowledge management system with configurable features
"""

import os
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

try:
    from mem0.memory.main import Memory, MemoryConfig
except ImportError:
    print("PraisonAI Knowledge requires additional dependencies.")
    print("Please install with: pip install 'praisonai[knowledge]'")
    sys.exit(1)

class Knowledge:
    """Advanced knowledge management system with configurable storage and search capabilities"""

    def __init__(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        vector_store: str = "chroma",
        embedder: str = "openai",
        use_graph: bool = False,
    ):
        """Initialize knowledge system with flexible configuration

        Args:
            user_id: Unique identifier for the user/organization
            agent_id: Optional agent identifier for multi-agent systems
            run_id: Optional run identifier for tracking sessions
            config: Custom configuration override
            vector_store: Vector store provider ("chroma", "qdrant", "pgvector", etc.)
            embedder: Embedding provider ("openai", "huggingface", etc.) 
            use_graph: Enable graph capabilities
        """
        self.user_id = user_id
        self.agent_id = agent_id
        self.run_id = run_id

        # Build optimized configuration
        memory_config = config or {
            "vector_store": {
                "provider": vector_store,
                "config": {
                    "collection_name": "praison_knowledge",
                    "path": ".praison/knowledge",
                }
            },
            "embedder": {
                "provider": embedder,
                "config": {
                    "model": "text-embedding-3-small"
                }
            },
            "version": "v1.0"
        }

        # Add graph capabilities if enabled
        if use_graph:
            memory_config.update({
                "graph_store": {
                    "provider": "neo4j",
                    "config": {
                        "url": os.getenv("PRAISON_GRAPH_URL", "bolt://localhost:7687"),
                        "username": os.getenv("PRAISON_GRAPH_USER", "neo4j"), 
                        "password": os.getenv("PRAISON_GRAPH_PASSWORD", "password")
                    }
                },
                "version": "v1.1"
            })

        self._store = Memory(MemoryConfig(**memory_config))

    def add(self, content: Union[str, Path], metadata: Optional[Dict] = None) -> None:
        """Add knowledge content with optional metadata"""
        if isinstance(content, Path):
            content = content.read_text(encoding="utf-8")
        
        self._store.add(
            messages=[{"role": "user", "content": content}],
            user_id=self.user_id,
            agent_id=self.agent_id,
            run_id=self.run_id,
            metadata=metadata or {}
        )

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search knowledge using semantic understanding"""
        results = self._store.search(
            query=query,
            user_id=self.user_id,
            agent_id=self.agent_id,
            run_id=self.run_id,
            limit=limit
        )
        return results.get("results", results)

    def delete(self) -> None:
        """Delete knowledge for current context"""
        self._store.delete_all(
            user_id=self.user_id,
            agent_id=self.agent_id,
            run_id=self.run_id
        )

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all knowledge entries"""
        results = self._store.get_all(
            user_id=self.user_id,
            agent_id=self.agent_id,
            run_id=self.run_id,
            limit=limit
        )
        return results.get("results", results)