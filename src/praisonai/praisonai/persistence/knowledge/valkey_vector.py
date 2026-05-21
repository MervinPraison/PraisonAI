"""
Valkey Vector implementation of KnowledgeStore.

Uses ValkeySearch (the ``ft`` module from valkey-glide-sync) for vector
indexing and semantic search.

Requires: valkey-glide-sync
Install: pip install 'praisonai[valkey]'
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument, validate_identifier
from .._valkey_client import create_valkey_client, scan_keys

logger = logging.getLogger(__name__)


class ValkeyVectorKnowledgeStore(KnowledgeStore):
    """
    Valkey-based knowledge store using ValkeySearch for vector search.

    Requires Valkey with ValkeySearch module for vector indexing and search.

    Example:
        store = ValkeyVectorKnowledgeStore(
            host="localhost",
            port=6379,
            password="secret",
        )
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        prefix: str = "praison:vec:",
        **kwargs: Any,
    ):
        """
        Initialize Valkey vector knowledge store.

        Args:
            host:     Valkey host (env ``VALKEY_HOST``, default ``"localhost"``).
            port:     Valkey port (env ``VALKEY_PORT``, default ``6379``).
            password: Valkey password (env ``VALKEY_PASSWORD``, optional).
            prefix:   Key prefix for namespacing (default ``"praison:vec:"``).
            **kwargs: Additional ``GlideClientConfiguration`` options.
        """
        self.prefix = prefix
        self._client = create_valkey_client(host=host, port=port, password=password, **kwargs)

        try:
            self._client.ping()
            logger.info("Connected to Valkey at %s:%s", host or "localhost", port or 6379)
        except Exception as exc:
            logger.error("Failed to connect to Valkey: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Key/index helpers
    # ------------------------------------------------------------------

    def _index_name(self, collection: str) -> str:
        """Return the ValkeySearch index name for *collection*."""
        return f"{self.prefix}{collection}:idx"

    def _doc_key(self, collection: str, doc_id: str) -> str:
        """Return the hash key for a single document."""
        return f"{self.prefix}{collection}:{doc_id}"

    @staticmethod
    def _decode(value: Any) -> str:
        """Decode bytes to str."""
        if isinstance(value, (bytes, bytearray)):
            return value.decode()
        return value

    # ------------------------------------------------------------------
    # KnowledgeStore interface – collection management
    # ------------------------------------------------------------------

    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a new HNSW vector index."""
        validate_identifier(name, "collection name")

        try:
            from glide_sync import (  # type: ignore[import]
                ft,
                DataType,
                DistanceMetricType,
                FtCreateOptions,
                TextField,
                NumericField,
                VectorAlgorithm,
                VectorField,
                VectorFieldAttributesHnsw,
                VectorType,
            )
        except ImportError as exc:
            raise ImportError(
                "valkey-glide-sync is required for vector search. "
                "Install with: pip install 'praisonai[valkey]'"
            ) from exc

        _distance_map = {
            "cosine": DistanceMetricType.COSINE,
            "euclidean": DistanceMetricType.L2,
            "dot": DistanceMetricType.IP,
        }
        distance_metric = _distance_map.get(distance, DistanceMetricType.COSINE)

        index_name = self._index_name(name)
        prefix = f"{self.prefix}{name}:"

        schema = [
            TextField("content"),
            TextField("content_hash"),
            NumericField("created_at"),
            VectorField(
                "embedding",
                VectorAlgorithm.HNSW,
                VectorFieldAttributesHnsw(
                    dimensions=dimension,
                    distance_metric=distance_metric,
                    type=VectorType.FLOAT32,
                ),
            ),
        ]
        options = FtCreateOptions(
            data_type=DataType.HASH,
            prefixes=[prefix],
        )

        try:
            ft.create(self._client, index_name, schema, options)
            logger.info("Created Valkey vector index: %s", index_name)
        except Exception as exc:
            if "Index already exists" not in str(exc):
                logger.error("Failed to create index %s: %s", index_name, exc)
                raise

    def delete_collection(self, name: str) -> bool:
        """Delete an index (and its associated documents)."""
        validate_identifier(name, "collection name")
        try:
            from glide_sync import ft  # type: ignore[import]
            ft.dropindex(self._client, self._index_name(name))
            return True
        except Exception as exc:
            logger.warning("Failed to delete index %s: %s", self._index_name(name), exc)
            return False

    def collection_exists(self, name: str) -> bool:
        """Return ``True`` if the index exists."""
        validate_identifier(name, "collection name")
        try:
            from glide_sync import ft  # type: ignore[import]
            ft.info(self._client, self._index_name(name))
            return True
        except Exception:
            return False

    def list_collections(self) -> List[str]:
        """Return a list of collection names managed by this store."""
        try:
            from glide_sync import ft  # type: ignore[import]
            indexes = ft.list(self._client)
            prefix = self.prefix
            suffix = ":idx"
            result = []
            for idx in indexes:
                idx_str = self._decode(idx)
                if idx_str.startswith(prefix) and idx_str.endswith(suffix):
                    result.append(idx_str[len(prefix):-len(suffix)])
            return result
        except Exception:
            return []

    # ------------------------------------------------------------------
    # KnowledgeStore interface – document operations
    # ------------------------------------------------------------------

    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument],
    ) -> List[str]:
        """Insert *documents* into *collection*."""
        validate_identifier(collection, "collection name")

        import numpy as np  # type: ignore[import]

        ids = []
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")

            key = self._doc_key(collection, doc.id)
            embedding_bytes = np.array(doc.embedding, dtype=np.float32).tobytes()

            fields: Dict[Any, Any] = {
                "content": doc.content,
                "content_hash": doc.content_hash or "",
                "created_at": str(doc.created_at),
                "embedding": embedding_bytes,
            }
            self._client.hset(key, fields)
            ids.append(doc.id)

        return ids

    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument],
    ) -> List[str]:
        """Insert or update *documents* (identical to insert for Valkey hashes)."""
        return self.insert(collection, documents)

    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[KnowledgeDocument]:
        """Return the *limit* most similar documents to *query_embedding*."""
        validate_identifier(collection, "collection name")

        import numpy as np  # type: ignore[import]

        try:
            from glide_sync import (  # type: ignore[import]
                ft,
                FtSearchOptions,
                FtSearchLimit,
                ReturnField,
            )
        except ImportError as exc:
            raise ImportError(
                "valkey-glide-sync is required for vector search."
            ) from exc

        index_name = self._index_name(collection)
        query_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

        query_str = f"*=>[KNN {limit} @embedding $vec AS score]"
        options = FtSearchOptions(
            return_fields=[
                ReturnField("content"),
                ReturnField("content_hash"),
                ReturnField("created_at"),
                ReturnField("score"),
            ],
            params={"vec": query_bytes},
            limit=FtSearchLimit(offset=0, count=limit),
        )

        try:
            results = ft.search(self._client, index_name, query_str, options)
        except Exception as exc:
            logger.error("Search failed for collection %s: %s", collection, exc)
            return []

        # results[0] is the total count; subsequent entries are
        # {key: {field: value}} mappings.
        documents: List[KnowledgeDocument] = []
        for entry in results[1:]:
            for doc_key, field_map in entry.items():
                doc_key_str = self._decode(doc_key)
                # Decode all field values
                decoded: Dict[str, str] = {
                    self._decode(k): self._decode(v)
                    for k, v in field_map.items()
                }

                score = float(decoded.get("score", "0"))
                # Convert cosine distance (0-2) to similarity (1-0)
                similarity = 1.0 - score
                if score_threshold is not None and similarity < score_threshold:
                    continue

                doc_id = doc_key_str.split(":")[-1]

                documents.append(
                    KnowledgeDocument(
                        id=doc_id,
                        content=decoded.get("content", ""),
                        embedding=None,  # embeddings are not returned in search results
                        metadata={},
                        content_hash=decoded.get("content_hash", ""),
                        created_at=float(decoded.get("created_at", "0")),
                    )
                )

        return documents

    def get(
        self,
        collection: str,
        ids: List[str],
    ) -> List[KnowledgeDocument]:
        """Retrieve documents by their IDs."""
        validate_identifier(collection, "collection name")

        import numpy as np  # type: ignore[import]

        documents: List[KnowledgeDocument] = []
        for doc_id in ids:
            key = self._doc_key(collection, doc_id)
            raw_map = self._client.hgetall(key)

            if not raw_map:
                continue

            data: Dict[str, Any] = {
                self._decode(k): v for k, v in raw_map.items()
            }

            embedding: Optional[List[float]] = None
            if "embedding" in data:
                try:
                    embedding = np.frombuffer(data["embedding"], dtype=np.float32).tolist()
                except Exception:
                    pass

            documents.append(
                KnowledgeDocument(
                    id=doc_id,
                    content=self._decode(data.get("content", b"")),
                    embedding=embedding,
                    metadata={},
                    content_hash=self._decode(data.get("content_hash", b"")),
                    created_at=float(self._decode(data.get("created_at", b"0"))),
                )
            )

        return documents

    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Delete documents by ID. Returns the number of deleted documents."""
        validate_identifier(collection, "collection name")

        if not ids:
            return 0

        count = 0
        for doc_id in ids:
            key = self._doc_key(collection, doc_id)
            if self._client.delete([key]) > 0:
                count += 1
        return count

    def count(self, collection: str) -> int:
        """Return the number of documents in *collection*."""
        validate_identifier(collection, "collection name")
        try:
            from glide_sync import ft  # type: ignore[import]
            info = ft.info(self._client, self._index_name(collection))
            # info is a Mapping[bytes, ...]; look for b"num_docs"
            for key in (b"num_docs", "num_docs"):
                if key in info:
                    return int(info[key])
            return 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying Valkey connection."""
        if self._client:
            self._client.close()
            self._client = None