"""
Valkey Vector implementation of KnowledgeStore.

Requires: valkey-glide-sync
Install: pip install 'praisonai[valkey]'
"""

import re
import struct
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument, validate_identifier
from .._valkey_client import create_valkey_client

try:
    from glide_sync import ft
    from glide_sync import (
        TextField, NumericField, VectorField, VectorFieldAttributesHnsw,
        VectorAlgorithm, DistanceMetricType, VectorType,
        FtCreateOptions, DataType, FtSearchOptions, ReturnField,
    )
    from glide_sync import Batch
except ImportError:
    ft = None
    Batch = None
    TextField = NumericField = VectorField = VectorFieldAttributesHnsw = None
    VectorAlgorithm = DistanceMetricType = VectorType = None
    FtCreateOptions = DataType = FtSearchOptions = ReturnField = None


_SEARCH_SPECIAL_RE = re.compile(r'([,.<>{}\[\]"\'\\:;!@#$%^&*()\-+=~?/| \t])')
_FIELD_NAME_RE = re.compile(r'^[a-zA-Z0-9_]+$')


def _escape_search_value(value: str) -> str:
    return _SEARCH_SPECIAL_RE.sub(r'\\\1', str(value))


def _decode(v) -> str:
    return v.decode() if isinstance(v, bytes) else v


class ValkeyVectorKnowledgeStore(KnowledgeStore):
    """
    Valkey-based knowledge store using ValkeySearch FT commands for vector search.

    Requires Valkey with ValkeySearch module.

    Example:
        store = ValkeyVectorKnowledgeStore(
            host="localhost",
            port=6379,
        )
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        prefix: str = "praison:vec:",
    ):
        self.host = host
        self.port = port
        self.password = password
        self.prefix = prefix
        self._client = None

    def _get_client(self):
        """Lazy initialize Valkey client."""
        if self._client is None:
            self._client = create_valkey_client(
                host=self.host,
                port=self.port,
                password=self.password,
                client_name="praisonai_knowledge_client",
            )
        return self._client

    def _index_name(self, collection: str) -> str:
        return f"{self.prefix}{collection}:idx"

    def _doc_key(self, collection: str, doc_id: str) -> str:
        return f"{self.prefix}{collection}:{doc_id}"

    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a new index."""
        validate_identifier(name, "collection name")
        client = self._get_client()
        index_name = self._index_name(name)

        try:
            dist_enum = {"cosine": DistanceMetricType.COSINE, "euclidean": DistanceMetricType.L2, "dot": DistanceMetricType.IP}.get(distance, DistanceMetricType.COSINE)
            schema = [
                TextField("content"),
                TextField("content_hash"),
                NumericField("created_at"),
                VectorField("embedding", VectorAlgorithm.HNSW, VectorFieldAttributesHnsw(dimension, dist_enum, VectorType.FLOAT32)),
            ]
            options = FtCreateOptions(DataType.HASH, prefixes=[f"{self.prefix}{name}:"])
            ft.create(client, index_name, schema, options)
        except Exception as e:
            err = str(e)
            if "already exists" not in err.lower():
                raise RuntimeError(f"Failed to create collection in Valkey: {e}") from e

    def delete_collection(self, name: str) -> bool:
        """Delete an index and all documents."""
        client = self._get_client()
        index_name = self._index_name(name)
        try:
            ft.dropindex(client, index_name)
        except Exception:
            return False

        # Manually remove orphaned document hashes left behind (no DD flag in ValkeySearch)
        pattern = f"{self.prefix}{name}:*"
        cursor: bytes = b"0"
        while True:
            result = client.scan(cursor, match=pattern, count=100)
            cursor = result[0]
            keys = result[1] or []
            if keys:
                client.delete(keys)
            if not cursor or cursor in (b"0", "0", 0):
                break

        return True

    def collection_exists(self, name: str) -> bool:
        """Check if an index exists."""
        client = self._get_client()
        index_name = self._index_name(name)
        try:
            ft.info(client, index_name)
            return True
        except Exception:
            return False

    def list_collections(self) -> List[str]:
        """List all collections."""
        client = self._get_client()
        try:
            indexes = ft.list(client)
            if not indexes:
                return []
            result = []
            for idx in indexes:
                idx_str = _decode(idx)
                if idx_str.startswith(self.prefix):
                    name = idx_str[len(self.prefix):]
                    if name.endswith(":idx"):
                        name = name[:-4]
                    result.append(name)
            return result
        except Exception:
            return []

    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument],
    ) -> List[str]:
        """Insert documents using a non-atomic batch (pipeline)."""
        client = self._get_client()
        ids = []
        batch = Batch(is_atomic=False)

        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")

            key = self._doc_key(collection, doc.id)
            embedding_bytes = struct.pack(f"{len(doc.embedding)}f", *doc.embedding)

            batch.hset(key, {
                "content": doc.content,
                "content_hash": doc.content_hash or "",
                "created_at": str(doc.created_at),
                "embedding": embedding_bytes,
            })
            ids.append(doc.id)

        try:
            client.exec(batch, raise_on_error=True)
        except Exception as e:
            raise RuntimeError(f"Failed to insert documents into Valkey: {e}") from e

        return ids

    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument],
    ) -> List[str]:
        """Insert or update documents."""
        return self.insert(collection, documents)

    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[KnowledgeDocument]:
        """Search for similar documents.

        Args:
            collection: Collection name.
            query_embedding: Query vector.
            limit: Max results.
            filters: Optional dict of field-value equality filters applied as
                a ValkeySearch pre-filter (e.g. {"content_hash": "abc"}).
            score_threshold: Minimum similarity (1 - distance) to include.
        """
        client = self._get_client()
        index_name = self._index_name(collection)
        packed = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        # Build pre-filter expression
        if filters:
            filter_parts = []
            for field, value in filters.items():
                if not _FIELD_NAME_RE.match(field):
                    raise ValueError(f"Invalid filter field name: {field!r}")
                if not isinstance(value, str):
                    raise TypeError(
                        f"Filter value for {field!r} must be a string, got {type(value).__name__}"
                    )
                escaped = _escape_search_value(value)
                filter_parts.append(f"@{field}:({escaped})")
            pre_filter = " ".join(filter_parts)
            query = f"({pre_filter})=>[KNN {limit} @embedding $vec AS score]"
        else:
            query = f"*=>[KNN {limit} @embedding $vec AS score]"

        try:
            options = FtSearchOptions(
                return_fields=[
                    ReturnField("content"),
                    ReturnField("content_hash"),
                    ReturnField("created_at"),
                    ReturnField("score"),
                ],
                params={"vec": packed},
            )
            raw = ft.search(client, index_name, query, options)
        except Exception as e:
            raise RuntimeError(f"Failed to search Valkey: {e}") from e

        # ft.search returns [count, {doc_id: {field: value, ...}, ...}]
        if not raw or len(raw) < 2:
            return []

        documents = []
        key_prefix = f"{self.prefix}{collection}:"
        for doc_id_raw, fields in raw[1].items():
            doc_id_str = _decode(doc_id_raw)
            bare_id = doc_id_str.removeprefix(key_prefix)

            field_map: Dict[str, str] = {}
            for fname, fval in fields.items():
                fname = _decode(fname)
                fval = _decode(fval)
                field_map[fname] = fval

            score = float(field_map.get("score", 0))
            similarity = 1 - score

            if score_threshold is not None and similarity < score_threshold:
                continue

            documents.append(KnowledgeDocument(
                id=bare_id,
                content=field_map.get("content", ""),
                embedding=None,
                metadata={},
                content_hash=field_map.get("content_hash", ""),
                created_at=float(field_map.get("created_at", 0)),
            ))

        return documents

    def get(
        self,
        collection: str,
        ids: List[str],
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs using a non-atomic batch (pipeline)."""
        client = self._get_client()
        keys = [self._doc_key(collection, doc_id) for doc_id in ids]

        batch = Batch(is_atomic=False)
        for key in keys:
            batch.hgetall(key)

        try:
            results = client.exec(batch, raise_on_error=True)
        except Exception as e:
            raise RuntimeError(f"Failed to get documents from Valkey: {e}") from e

        documents = []
        for doc_id, data in zip(ids, results):
            if data:
                embedding = None
                emb_key = b"embedding" if b"embedding" in data else "embedding"
                if emb_key in data:
                    raw_bytes = data[emb_key]
                    count = len(raw_bytes) // 4
                    embedding = list(struct.unpack(f"{count}f", raw_bytes))

                content = _decode(data.get(b"content", data.get("content", b"")))
                content_hash = _decode(data.get(b"content_hash", data.get("content_hash", b"")))
                created_at_raw = data.get(b"created_at", data.get("created_at", b"0"))
                created_at = float(_decode(created_at_raw))

                doc = KnowledgeDocument(
                    id=doc_id,
                    content=content,
                    embedding=embedding,
                    metadata={},
                    content_hash=content_hash,
                    created_at=created_at,
                )
                documents.append(doc)

        return documents

    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Delete documents by IDs. Filter-based deletion is not supported."""
        if filters and not ids:
            raise NotImplementedError("Filter-based deletion is not supported by the Valkey backend")
        if not ids:
            return 0

        client = self._get_client()
        keys = [self._doc_key(collection, doc_id) for doc_id in ids]

        try:
            deleted = client.delete(keys)
        except Exception as e:
            raise RuntimeError(f"Failed to delete documents from Valkey: {e}") from e

        return deleted

    def count(self, collection: str) -> int:
        """Count documents in a collection."""
        client = self._get_client()
        index_name = self._index_name(collection)
        try:
            info = ft.info(client, index_name)
            # ft.info returns a Mapping; num_docs may be bytes key
            for k in (b"num_docs", "num_docs"):
                if k in info:
                    return int(info[k])
            return 0
        except Exception:
            return 0

    def close(self) -> None:
        """Close the store."""
        if self._client:
            try:
                self._client.close()
            finally:
                self._client = None
