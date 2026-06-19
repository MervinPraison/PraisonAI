"""
Valkey Storage Adapter for PraisonAI.

Implements StorageBackendProtocol using Valkey for high-speed storage.
This is the wrapper implementation that contains the heavy valkey-glide-sync dependency.
"""

import json
import struct
from typing import Dict, Any, List, Optional

from praisonai.persistence._valkey_client import create_valkey_client

try:
    from glide_sync import ExpirySet, ExpiryType
except ImportError:
    ExpirySet = None
    ExpiryType = None

try:
    from glide_sync import ft
    from glide_sync import (
        VectorField, VectorFieldAttributesHnsw, VectorAlgorithm,
        DistanceMetricType, VectorType, FtCreateOptions, DataType,
        FtSearchOptions, ReturnField,
    )
except ImportError:
    ft = None
    VectorField = VectorFieldAttributesHnsw = VectorAlgorithm = None
    DistanceMetricType = VectorType = FtCreateOptions = DataType = None
    FtSearchOptions = ReturnField = None


class ValkeyStorageAdapter:
    """
    Valkey-based storage backend adapter.

    Uses Valkey for high-speed caching and ephemeral data storage.
    Implements StorageBackendProtocol from praisonaiagents.storage.protocols.

    Example:
        ```python
        from praisonai.storage.valkey_adapter import ValkeyStorageAdapter

        adapter = ValkeyStorageAdapter(host="localhost", port=6379)
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        prefix: str = "praisonai:",
        ttl: Optional[int] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize the Valkey storage adapter.

        Args:
            host: Valkey server host
            port: Valkey server port
            prefix: Key prefix for all stored data
            ttl: Optional TTL in seconds for all keys
            password: Optional Valkey password
        """
        self.host = host
        self.port = port
        self.prefix = prefix
        self.ttl = ttl
        self.password = password
        self._client = None

    def _get_client(self):
        """Lazy initialize Valkey client."""
        if self._client is None:
            self._client = create_valkey_client(
                host=self.host,
                port=self.port,
                password=self.password,
            )
        return self._client

    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.prefix}{key}"

    def _scan_keys(self, pattern: str) -> List[bytes]:
        """Collect all keys matching pattern via SCAN."""
        client = self._get_client()
        cursor: bytes = b"0"
        all_keys: List[bytes] = []
        while True:
            result = client.scan(cursor, match=pattern, count=100)
            cursor = result[0]
            all_keys.extend(result[1] or [])
            if not cursor or cursor in (b"0", "0", 0):
                break
        return all_keys

    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        client = self._get_client()
        full_key = self._make_key(key)
        json_data = json.dumps(data, default=str, ensure_ascii=False).encode('utf-8')

        try:
            if self.ttl is not None:
                client.set(full_key, json_data, expiry=ExpirySet(ExpiryType.SEC, self.ttl))
            else:
                client.set(full_key, json_data)
        except Exception as e:
            raise RuntimeError(f"Failed to save data to Valkey: {e}") from e

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        client = self._get_client()
        full_key = self._make_key(key)

        try:
            value = client.get(full_key)
            if value is not None:
                try:
                    if isinstance(value, bytes):
                        value = value.decode('utf-8')
                    return json.loads(value)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON data for key '{key}': {e}") from e
            return None
        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to load data from Valkey: {e}") from e

    def delete(self, key: str) -> bool:
        """Delete data by key."""
        client = self._get_client()
        full_key = self._make_key(key)

        try:
            return client.delete([full_key]) > 0
        except Exception as e:
            raise RuntimeError(f"Failed to delete data from Valkey: {e}") from e

    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        pattern = self._make_key(f"{prefix}*")

        try:
            raw_keys = self._scan_keys(pattern)
            prefix_len = len(self.prefix)
            return sorted(
                (k.decode('utf-8') if isinstance(k, bytes) else k)[prefix_len:]
                for k in raw_keys
            )
        except Exception as e:
            raise RuntimeError(f"Failed to list keys from Valkey: {e}") from e

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        client = self._get_client()
        full_key = self._make_key(key)

        try:
            return client.exists([full_key]) > 0
        except Exception as e:
            raise RuntimeError(f"Failed to check key existence in Valkey: {e}") from e

    def clear(self) -> int:
        """Clear all data with our prefix. Returns number of items deleted."""
        client = self._get_client()
        pattern = self._make_key("*")
        batch_size = 500

        try:
            all_keys = self._scan_keys(pattern)
            if not all_keys:
                return 0
            total = 0
            for i in range(0, len(all_keys), batch_size):
                total += client.delete(all_keys[i:i + batch_size])
            return total
        except Exception as e:
            raise RuntimeError(f"Failed to clear data from Valkey: {e}") from e

    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set TTL on a specific key."""
        client = self._get_client()
        full_key = self._make_key(key)

        try:
            return client.expire(full_key, ttl)
        except Exception as e:
            raise RuntimeError(f"Failed to set TTL in Valkey: {e}") from e

    def ping(self) -> bool:
        """Test connection to Valkey."""
        try:
            client = self._get_client()
            result = client.ping()
            return result is not None
        except Exception:
            return False

    def close(self) -> None:
        """Close the Valkey connection."""
        if self._client:
            try:
                self._client.close()
            finally:
                self._client = None


class ValkeySearchBackend:
    """
    Valkey vector search backend using RediSearch / ValkeySearch FT commands.

    Example:
        ```python
        from praisonai.storage.valkey_adapter import ValkeySearchBackend

        backend = ValkeySearchBackend(host="localhost", port=6379, vector_dim=1536)
        backend.create_index()
        backend.add_document("doc1", "hello world", embedding)
        results = backend.search(query_embedding, k=5)
        ```
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        index_name: str = "praisonai_vectors",
        password: Optional[str] = None,
        vector_dim: int = 1536,
    ):
        """
        Initialize the Valkey search backend.

        Args:
            host: Valkey server host
            port: Valkey server port
            index_name: Name of the FT index
            password: Optional Valkey password
            vector_dim: Dimension of embedding vectors
        """
        self.host = host
        self.port = port
        self.index_name = index_name
        self.password = password
        self.vector_dim = vector_dim
        self._client = None

    def _get_client(self):
        """Lazy initialize Valkey client."""
        if self._client is None:
            self._client = create_valkey_client(
                host=self.host,
                port=self.port,
                password=self.password,
            )
        return self._client

    def create_index(self, vector_dim: int = None) -> None:
        """Create the vector search index (no-op if already exists)."""
        client = self._get_client()
        dim = vector_dim or self.vector_dim

        try:
            schema = [VectorField(
                "embedding",
                VectorAlgorithm.HNSW,
                VectorFieldAttributesHnsw(dim, DistanceMetricType.COSINE, VectorType.FLOAT32),
            )]
            options = FtCreateOptions(DataType.HASH, prefixes=[f"{self.index_name}:"])
            ft.create(client, self.index_name, schema, options)
        except Exception as e:
            err = str(e)
            if "already exists" not in err.lower() and "index already exists" not in err.lower():
                raise RuntimeError(f"Failed to create Valkey search index: {e}") from e

    def add_document(self, doc_id: str, text: str, embedding: List[float]) -> None:
        """Add a document with its embedding to the index."""
        client = self._get_client()
        full_id = f"{self.index_name}:{doc_id}"
        packed = struct.pack(f"{len(embedding)}f", *embedding)

        try:
            client.hset(full_id, {"text": text, "embedding": packed})
        except Exception as e:
            raise RuntimeError(f"Failed to add document to Valkey: {e}") from e

    def search(self, query_embedding: List[float], k: int = 5) -> List[Dict[str, Any]]:
        """Search for nearest neighbors by embedding."""
        client = self._get_client()
        packed = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        try:
            options = FtSearchOptions(
                return_fields=[ReturnField("text"), ReturnField("score")],
                params={"vec": packed},
            )
            raw = ft.search(client, self.index_name, f"*=>[KNN {k} @embedding $vec AS score]", options)
        except Exception as e:
            raise RuntimeError(f"Failed to search Valkey: {e}") from e

        # ft.search returns [count, {doc_id: {field: value, ...}, ...}]
        if not raw or len(raw) < 2:
            return []

        results = []
        key_prefix = f"{self.index_name}:"
        for doc_id, fields in raw[1].items():
            doc: Dict[str, Any] = {}
            raw_id = doc_id.decode('utf-8') if isinstance(doc_id, bytes) else doc_id
            doc["id"] = raw_id.removeprefix(key_prefix)
            for fname, fval in fields.items():
                fname = fname.decode('utf-8') if isinstance(fname, bytes) else fname
                fval = fval.decode('utf-8') if isinstance(fval, bytes) else fval
                doc[fname] = fval
            results.append(doc)

        return results

    def close(self) -> None:
        """Close the Valkey connection."""
        if self._client:
            try:
                self._client.close()
            finally:
                self._client = None
