from typing import Optional, List, Dict, Any, Union
import os
from pathlib import Path
import numpy as np
from datetime import datetime
from uuid import uuid4

class Knowledge:
    def __init__(
        self,
        name: str,
        storage_dir: Optional[str] = None,
        vector_store_type: str = "chroma",  # Options: chroma, pinecone, pgvector, qdrant, milvus
        vector_store_url: Optional[str] = None,
        embeddings_model: str = "openai",  # Options: openai, cohere, sentencetransformers, huggingface
        embeddings_model_config: Optional[Dict[str, Any]] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        similarity_threshold: float = 0.8,
        max_results: int = 5,
        cache_enabled: bool = True,
        cache_ttl: int = 3600,  # 1 hour
        encryption_enabled: bool = False,
        encryption_key: Optional[str] = None,
        debug_mode: bool = False,
    ):
        self.name = name
        self.storage_dir = storage_dir or os.path.join(os.getcwd(), "knowledge_store")
        self.vector_store_type = vector_store_type.lower()
        self.vector_store_url = vector_store_url
        self.embeddings_model = embeddings_model.lower()
        self.embeddings_model_config = embeddings_model_config or {}
        
        # Chunking settings
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Search settings
        self.similarity_threshold = similarity_threshold
        self.max_results = max_results
        
        # Cache settings
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_timestamps = {}
        
        # Security settings
        self.encryption_enabled = encryption_enabled
        self._encryption_key = encryption_key
        
        self.debug_mode = debug_mode
        
        # Initialize components
        self._embeddings_client = None
        self._vector_store = None
        self._initialize_storage()
        self._initialize_embeddings()

    def _initialize_storage(self) -> None:
        """Initialize vector storage based on configuration"""
        try:
            if self.vector_store_type == "chroma":
                import chromadb
                self._vector_store = chromadb.Client()
                self.collection = self._vector_store.create_collection(
                    name=self.name,
                    metadata={"description": f"Knowledge collection for {self.name}"}
                )
            
            elif self.vector_store_type == "pinecone":
                import pinecone
                pinecone.init(api_key=self.vector_store_url)
                self._vector_store = pinecone.Index(self.name)
            
            elif self.vector_store_type == "pgvector":
                from pgvector.psycopg2 import register_vector
                import psycopg2
                conn = psycopg2.connect(self.vector_store_url)
                register_vector(conn)
                self._vector_store = conn
            
            elif self.vector_store_type == "qdrant":
                from qdrant_client import QdrantClient
                self._vector_store = QdrantClient(url=self.vector_store_url)
            
            elif self.vector_store_type == "milvus":
                from pymilvus import connections, Collection
                connections.connect(uri=self.vector_store_url)
                self._vector_store = Collection(name=self.name)
            
            else:
                raise ValueError(f"Unsupported vector store type: {self.vector_store_type}")
                
            if self.debug_mode:
                print(f"Successfully initialized {self.vector_store_type} vector store")
                
        except Exception as e:
            if self.debug_mode:
                print(f"Error initializing vector store: {str(e)}")
            raise

    def _initialize_embeddings(self) -> None:
        """Initialize embeddings model based on configuration"""
        try:
            if self.embeddings_model == "openai":
                from openai import OpenAI
                self._embeddings_client = OpenAI(**self.embeddings_model_config)
                
            elif self.embeddings_model == "cohere":
                import cohere
                self._embeddings_client = cohere.Client(**self.embeddings_model_config)
                
            elif self.embeddings_model == "sentencetransformers":
                from sentence_transformers import SentenceTransformer
                model_name = self.embeddings_model_config.get("model_name", "all-MiniLM-L6-v2")
                self._embeddings_client = SentenceTransformer(model_name)
                
            elif self.embeddings_model == "huggingface":
                from transformers import AutoModel, AutoTokenizer
                model_name = self.embeddings_model_config.get("model_name", "bert-base-uncased")
                self._embeddings_client = {
                    "model": AutoModel.from_pretrained(model_name),
                    "tokenizer": AutoTokenizer.from_pretrained(model_name)
                }
                
            else:
                raise ValueError(f"Unsupported embeddings model: {self.embeddings_model}")
                
            if self.debug_mode:
                print(f"Successfully initialized {self.embeddings_model} embeddings model")
                
        except Exception as e:
            if self.debug_mode:
                print(f"Error initializing embeddings model: {str(e)}")
            raise

    def _get_embeddings(self, text: str) -> List[float]:
        """Generate embeddings for given text"""
        if self.embeddings_model == "openai":
            response = self._embeddings_client.embeddings.create(
                input=text,
                model="text-embedding-ada-002"
            )
            return response.data[0].embedding
            
        elif self.embeddings_model == "cohere":
            response = self._embeddings_client.embed(
                texts=[text],
                model="embed-english-v2.0"
            )
            return response.embeddings[0]
            
        elif self.embeddings_model == "sentencetransformers":
            return self._embeddings_client.encode(text).tolist()
            
        elif self.embeddings_model == "huggingface":
            inputs = self._embeddings_client["tokenizer"](
                text,
                return_tensors="pt",
                padding=True,
                truncation=True
            )
            outputs = self._embeddings_client["model"](**inputs)
            return outputs.last_hidden_state.mean(dim=1).squeeze().tolist()

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap"""
        words = text.split()
        chunks = []
        
        chunk_size_words = self.chunk_size
        overlap_words = self.chunk_overlap
        
        for i in range(0, len(words), chunk_size_words - overlap_words):
            chunk = " ".join(words[i:i + chunk_size_words])
            chunks.append(chunk)
            
        return chunks

    def _encrypt_text(self, text: str) -> str:
        """Encrypt text if encryption is enabled"""
        if not self.encryption_enabled:
            return text
            
        if not self._encryption_key:
            raise ValueError("Encryption key not provided")
            
        from cryptography.fernet import Fernet
        f = Fernet(self._encryption_key.encode())
        return f.encrypt(text.encode()).decode()

    def _decrypt_text(self, encrypted_text: str) -> str:
        """Decrypt encrypted text"""
        if not self.encryption_enabled:
            return encrypted_text
            
        if not self._encryption_key:
            raise ValueError("Encryption key not provided")
            
        from cryptography.fernet import Fernet
        f = Fernet(self._encryption_key.encode())
        return f.decrypt(encrypted_text.encode()).decode()

    def add_knowledge(
        self,
        content: Union[str, Path],
        metadata: Optional[Dict[str, Any]] = None,
        chunk_content: bool = True
    ) -> str:
        """
        Add new knowledge content to the store
        
        Args:
            content: Text content or path to file
            metadata: Optional metadata about the content
            chunk_content: Whether to chunk the content before storing
            
        Returns:
            id: Unique ID for the stored content
        """
        try:
            # Handle file input
            if isinstance(content, Path):
                with open(content, 'r') as f:
                    content = f.read()
                    
            # Generate unique ID
            content_id = str(uuid4())
            
            # Add timestamp to metadata
            metadata = metadata or {}
            metadata['timestamp'] = datetime.utcnow().isoformat()
            metadata['content_id'] = content_id
            
            # Chunk content if needed
            if chunk_content:
                chunks = self._chunk_text(content)
            else:
                chunks = [content]
            
            # Process each chunk
            for i, chunk in enumerate(chunks):
                chunk_id = f"{content_id}_{i}"
                
                # Encrypt if enabled
                if self.encryption_enabled:
                    chunk = self._encrypt_text(chunk)
                
                # Generate embeddings
                embeddings = self._get_embeddings(chunk)
                
                # Store in vector database
                if self.vector_store_type == "chroma":
                    self.collection.add(
                        documents=[chunk],
                        embeddings=[embeddings],
                        ids=[chunk_id],
                        metadatas=[metadata]
                    )
                    
                elif self.vector_store_type == "pinecone":
                    self._vector_store.upsert([
                        (chunk_id, embeddings, {"text": chunk, **metadata})
                    ])
                    
                elif self.vector_store_type == "pgvector":
                    with self._vector_store.cursor() as cur:
                        cur.execute(
                            "INSERT INTO vectors (id, embedding, text, metadata) VALUES (%s, %s, %s, %s)",
                            (chunk_id, embeddings, chunk, metadata)
                        )
                    self._vector_store.commit()
                    
                elif self.vector_store_type == "qdrant":
                    self._vector_store.upsert(
                        collection_name=self.name,
                        points=[{
                            "id": chunk_id,
                            "vector": embeddings,
                            "payload": {"text": chunk, **metadata}
                        }]
                    )
                    
                elif self.vector_store_type == "milvus":
                    self._vector_store.insert([
                        [chunk_id],
                        [embeddings],
                        [{"text": chunk, **metadata}]
                    ])
            
            if self.debug_mode:
                print(f"Successfully added content with ID: {content_id}")
                
            return content_id
            
        except Exception as e:
            if self.debug_mode:
                print(f"Error adding knowledge: {str(e)}")
            raise

    def search_knowledge(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge base using similarity search
        
        Args:
            query: Search query text
            filters: Optional metadata filters
            limit: Maximum number of results
            
        Returns:
            List of matching documents with scores
        """
        try:
            # Check cache first
            cache_key = f"{query}_{str(filters)}_{limit}"
            if self.cache_enabled and cache_key in self._cache:
                cache_time = self._cache_timestamps[cache_key]
                if (datetime.now() - cache_time).seconds < self.cache_ttl:
                    return self._cache[cache_key]
            
            # Generate query embeddings
            query_embedding = self._get_embeddings(query)
            
            # Set limit
            limit = limit or self.max_results
            
            # Perform similarity search
            results = []
            
            if self.vector_store_type == "chroma":
                search_results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    where=filters
                )
                
                for idx, (doc, score) in enumerate(zip(
                    search_results['documents'][0],
                    search_results['distances'][0]
                )):
                    if score >= self.similarity_threshold:
                        text = self._decrypt_text(doc) if self.encryption_enabled else doc
                        results.append({
                            "text": text,
                            "score": score,
                            "metadata": search_results['metadatas'][0][idx]
                        })
                        
            elif self.vector_store_type == "pinecone":
                search_results = self._vector_store.query(
                    vector=query_embedding,
                    top_k=limit,
                    filter=filters
                )
                
                for match in search_results.matches:
                    if match.score >= self.similarity_threshold:
                        text = self._decrypt_text(match.metadata['text']) if self.encryption_enabled else match.metadata['text']
                        results.append({
                            "text": text,
                            "score": match.score,
                            "metadata": {k:v for k,v in match.metadata.items() if k != 'text'}
                        })
                        
            elif self.vector_store_type == "pgvector":
                with self._vector_store.cursor() as cur:
                    filter_clause = " AND ".join([f"metadata->>{k} = %s" for k in (filters or {})])
                    filter_values = list((filters or {}).values())
                    
                    query_sql = f"""
                        SELECT text, metadata, 1 - (embedding <-> %s) as similarity
                        FROM vectors
                        {f"WHERE {filter_clause}" if filter_clause else ""}
                        ORDER BY similarity DESC
                        LIMIT %s
                    """
                    
                    cur.execute(query_sql, [query_embedding] + filter_values + [limit])
                    for row in cur.fetchall():
                        if row[2] >= self.similarity_threshold:
                            text = self._decrypt_text(row[0]) if self.encryption_enabled else row[0]
                            results.append({
                                "text": text,
                                "score": row[2],
                                "metadata": row[1]
                            })

            elif self.vector_store_type == "qdrant":
                search_results = self._vector_store.search(
                    collection_name=self.name,
                    query_vector=query_embedding,
                    limit=limit,
                    query_filter=filters
                )
                
                for hit in search_results:
                    if hit.score >= self.similarity_threshold:
                        text = self._decrypt_text(hit.payload['text']) if self.encryption_enabled else hit.payload['text']
                        payload = {k:v for k,v in hit.payload.items() if k != 'text'}
                        results.append({
                            "text": text,
                            "score": hit.score,
                            "metadata": payload
                        })

            elif self.vector_store_type == "milvus":
                search_results = self._vector_store.search(
                    data=[query_embedding],
                    limit=limit,
                    expr=filters
                )
                
                for hit in search_results[0]:
                    if hit.score >= self.similarity_threshold:
                        text = self._decrypt_text(hit.text) if self.encryption_enabled else hit.text
                        results.append({
                            "text": text,
                            "score": hit.score,
                            "metadata": hit.metadata
                        })

            # Cache results if enabled
            if self.cache_enabled:
                self._cache[cache_key] = results
                self._cache_timestamps[cache_key] = datetime.now()

            return results

        except Exception as e:
            if self.debug_mode:
                print(f"Error searching knowledge: {str(e)}")
            raise

    def update_knowledge(
        self,
        content_id: str,
        new_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        merge_metadata: bool = True
    ) -> bool:
        """
        Update existing knowledge content
        
        Args:
            content_id: ID of content to update
            new_content: New text content
            metadata: New metadata
            merge_metadata: Whether to merge with existing metadata
            
        Returns:
            bool: Success status
        """
        try:
            # Get existing content metadata if merging
            if merge_metadata:
                existing = self.get_knowledge(content_id)
                if existing and existing[0].get('metadata'):
                    metadata = {**existing[0]['metadata'], **(metadata or {})}
                    
            # Delete existing chunks
            self.delete_knowledge(content_id)
            
            # Add new content 
            self.add_knowledge(
                content=new_content,
                metadata={
                    **(metadata or {}),
                    'content_id': content_id,
                    'updated_at': datetime.utcnow().isoformat()
                }
            )

            if self.debug_mode:
                print(f"Successfully updated content with ID: {content_id}")

            return True

        except Exception as e:
            if self.debug_mode:
                print(f"Error updating knowledge: {str(e)}")
            raise

    def delete_knowledge(self, content_id: str) -> bool:
        """
        Delete knowledge content and its chunks
        
        Args:
            content_id: ID of content to delete
            
        Returns:
            bool: Success status
        """
        try:
            if self.vector_store_type == "chroma":
                # Get all chunk IDs for this content
                results = self.collection.get(
                    where={"content_id": content_id}
                )
                if results and results['ids']:
                    self.collection.delete(
                        ids=results['ids']
                    )

            elif self.vector_store_type == "pinecone":
                # Delete by metadata filter
                self._vector_store.delete(
                    filter={"content_id": content_id}
                )

            elif self.vector_store_type == "pgvector":
                with self._vector_store.cursor() as cur:
                    cur.execute(
                        "DELETE FROM vectors WHERE metadata->>'content_id' = %s",
                        (content_id,)
                    )
                self._vector_store.commit()

            elif self.vector_store_type == "qdrant":
                self._vector_store.delete(
                    collection_name=self.name,
                    points_selector={"content_id": content_id}
                )

            elif self.vector_store_type == "milvus":
                self._vector_store.delete(
                    expr=f"content_id == '{content_id}'"
                )

            # Clear relevant cache entries
            if self.cache_enabled:
                self._cache = {}
                self._cache_timestamps = {}

            if self.debug_mode:
                print(f"Successfully deleted content with ID: {content_id}")

            return True

        except Exception as e:
            if self.debug_mode:
                print(f"Error deleting knowledge: {str(e)}")
            raise

    def get_knowledge(
        self,
        content_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get knowledge content by ID
        
        Args:
            content_id: ID of content to retrieve
            
        Returns:
            List of content chunks with metadata
        """
        try:
            results = []
            
            if self.vector_store_type == "chroma":
                chunks = self.collection.get(
                    where={"content_id": content_id}
                )
                if chunks:
                    for i, doc in enumerate(chunks['documents']):
                        text = self._decrypt_text(doc) if self.encryption_enabled else doc
                        results.append({
                            "text": text,
                            "metadata": chunks['metadatas'][i]
                        })

            elif self.vector_store_type == "pinecone":
                # Fetch by metadata filter
                query_response = self._vector_store.query(
                    top_k=100,  # Fetch all chunks
                    filter={"content_id": content_id},
                    include_metadata=True
                )
                
                for match in query_response.matches:
                    text = self._decrypt_text(match.metadata['text']) if self.encryption_enabled else match.metadata['text']
                    results.append({
                        "text": text,
                        "metadata": {k:v for k,v in match.metadata.items() if k != 'text'}
                    })

            elif self.vector_store_type == "pgvector":
                with self._vector_store.cursor() as cur:
                    cur.execute(
                        "SELECT text, metadata FROM vectors WHERE metadata->>'content_id' = %s",
                        (content_id,)
                    )
                    for row in cur.fetchall():
                        text = self._decrypt_text(row[0]) if self.encryption_enabled else row[0]
                        results.append({
                            "text": text,
                            "metadata": row[1]
                        })

            elif self.vector_store_type == "qdrant":
                response = self._vector_store.scroll(
                    collection_name=self.name,
                    scroll_filter={"content_id": content_id}
                )
                
                for point in response[0]:
                    text = self._decrypt_text(point.payload['text']) if self.encryption_enabled else point.payload['text']
                    payload = {k:v for k,v in point.payload.items() if k != 'text'}
                    results.append({
                        "text": text,
                        "metadata": payload
                    })

            elif self.vector_store_type == "milvus":
                response = self._vector_store.query(
                    expr=f"content_id == '{content_id}'",
                    output_fields=['text', 'metadata']
                )
                
                for item in response:
                    text = self._decrypt_text(item.text) if self.encryption_enabled else item.text
                    results.append({
                        "text": text,
                        "metadata": item.metadata
                    })

            return results

        except Exception as e:
            if self.debug_mode:
                print(f"Error getting knowledge: {str(e)}")
            raise

    def clear_cache(self) -> None:
        """Clear the search results cache"""
        self._cache = {}
        self._cache_timestamps = {}

    def close(self) -> None:
        """Close connections and clean up resources"""
        try:
            if self.vector_store_type == "pgvector":
                self._vector_store.close()
            elif self.vector_store_type == "milvus":
                from pymilvus import connections
                connections.disconnect()

            self.clear_cache()

        except Exception as e:
            if self.debug_mode:
                print(f"Error closing knowledge store: {str(e)}")
            raise