"""Tools for working with MongoDB databases and Atlas Vector Search.

Usage:
from praisonaiagents.tools import mongodb_tools
result = mongodb_tools.insert_document("my_collection", {"name": "test", "value": 42})

or
from praisonaiagents.tools import connect_mongodb, insert_document, vector_search
client = connect_mongodb("mongodb://localhost:27017/")
result = insert_document(client, "my_collection", {"name": "test"})
"""

import logging
from typing import List, Dict, Any, Optional, Union, TYPE_CHECKING
from importlib import util
from datetime import datetime

if TYPE_CHECKING:
    import pymongo
    from pymongo import MongoClient
    from pymongo.collection import Collection

class MongoDBTools:
    """Tools for working with MongoDB databases and Atlas Vector Search."""
    
    def __init__(self, connection_string: str = "mongodb://localhost:27017/", database_name: str = "praisonai"):
        """Initialize MongoDBTools.
        
        Args:
            connection_string: MongoDB connection string
            database_name: Name of the database to use
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self._client = None
        self._db = None
    
    def _get_pymongo(self) -> Optional['pymongo']:
        """Get pymongo module, with helpful error if not installed"""
        if util.find_spec('pymongo') is None:
            error_msg = "pymongo package is not available. Please install it using: pip install 'praisonaiagents[mongodb]'"
            logging.error(error_msg)
            return None
        import pymongo
        return pymongo

    def _get_motor(self) -> Optional[Any]:
        """Get motor module for async operations"""
        if util.find_spec('motor') is None:
            error_msg = "motor package is not available. Please install it using: pip install 'praisonaiagents[mongodb]'"
            logging.error(error_msg)
            return None
        import motor.motor_asyncio
        return motor.motor_asyncio

    def _get_client(self) -> Optional['MongoClient']:
        """Get or create MongoDB client"""
        if self._client is None:
            pymongo = self._get_pymongo()
            if pymongo is None:
                return None
            try:
                self._client = pymongo.MongoClient(
                    self.connection_string,
                    maxPoolSize=50,
                    minPoolSize=10,
                    maxIdleTimeMS=30000,
                    serverSelectionTimeoutMS=5000,
                    retryWrites=True,
                    retryReads=True
                )
                # Test connection
                self._client.admin.command('ping')
                self._db = self._client[self.database_name]
            except Exception as e:
                error_msg = f"Error connecting to MongoDB: {str(e)}"
                logging.error(error_msg)
                return None
        return self._client

    def _get_database(self):
        """Get database instance"""
        if self._db is None:
            client = self._get_client()
            if client is None:
                return None
            self._db = client[self.database_name]
        return self._db

    def _get_collection(self, collection_name: str) -> Optional['Collection']:
        """Get collection instance"""
        db = self._get_database()
        if db is None:
            return None
        return db[collection_name]

    def insert_document(
        self, 
        collection_name: str, 
        document: Dict[str, Any], 
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Insert a document into a collection.
        
        Args:
            collection_name: Name of the collection
            document: Document to insert
            metadata: Optional metadata to include
            
        Returns:
            Result dict with success status and inserted_id
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            # Add metadata and timestamp
            doc_to_insert = document.copy()
            if metadata:
                doc_to_insert.update(metadata)
            doc_to_insert["_created_at"] = datetime.utcnow()
            
            result = collection.insert_one(doc_to_insert)
            return {
                "success": True,
                "inserted_id": str(result.inserted_id),
                "message": "Document inserted successfully"
            }

        except Exception as e:
            error_msg = f"Error inserting document: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def insert_documents(
        self, 
        collection_name: str, 
        documents: List[Dict[str, Any]], 
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Insert multiple documents into a collection.
        
        Args:
            collection_name: Name of the collection
            documents: List of documents to insert
            metadata: Optional metadata to include in all documents
            
        Returns:
            Result dict with success status and inserted_ids
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            # Add metadata and timestamp to all documents
            docs_to_insert = []
            for doc in documents:
                doc_copy = doc.copy()
                if metadata:
                    doc_copy.update(metadata)
                doc_copy["_created_at"] = datetime.utcnow()
                docs_to_insert.append(doc_copy)
            
            result = collection.insert_many(docs_to_insert)
            return {
                "success": True,
                "inserted_ids": [str(oid) for oid in result.inserted_ids],
                "count": len(result.inserted_ids),
                "message": f"Successfully inserted {len(result.inserted_ids)} documents"
            }

        except Exception as e:
            error_msg = f"Error inserting documents: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def find_documents(
        self, 
        collection_name: str, 
        query: Dict[str, Any] = None,
        limit: int = 10,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, int]] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """Find documents in a collection.
        
        Args:
            collection_name: Name of the collection
            query: Query filter (default: empty dict for all documents)
            limit: Maximum number of documents to return
            sort: Sort specification as list of (field, direction) tuples
            projection: Fields to include/exclude
            
        Returns:
            List of documents or error dict
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            query = query or {}
            cursor = collection.find(query, projection)
            
            if sort:
                cursor = cursor.sort(sort)
            
            cursor = cursor.limit(limit)
            
            # Convert ObjectIds to strings for JSON serialization
            results = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                results.append(doc)
            
            return results

        except Exception as e:
            error_msg = f"Error finding documents: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def update_document(
        self, 
        collection_name: str, 
        query: Dict[str, Any], 
        update: Dict[str, Any],
        upsert: bool = False
    ) -> Dict[str, Any]:
        """Update a document in a collection.
        
        Args:
            collection_name: Name of the collection
            query: Query to find the document
            update: Update operations
            upsert: Whether to insert if document doesn't exist
            
        Returns:
            Result dict with success status
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            # Add timestamp to update
            if "$set" not in update:
                update["$set"] = {}
            update["$set"]["_updated_at"] = datetime.utcnow()
            
            result = collection.update_one(query, update, upsert=upsert)
            return {
                "success": True,
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
                "upserted_id": str(result.upserted_id) if result.upserted_id else None,
                "message": "Document updated successfully"
            }

        except Exception as e:
            error_msg = f"Error updating document: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def delete_document(
        self, 
        collection_name: str, 
        query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delete a document from a collection.
        
        Args:
            collection_name: Name of the collection
            query: Query to find the document to delete
            
        Returns:
            Result dict with success status
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            result = collection.delete_one(query)
            return {
                "success": True,
                "deleted_count": result.deleted_count,
                "message": f"Deleted {result.deleted_count} document(s)"
            }

        except Exception as e:
            error_msg = f"Error deleting document: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def create_vector_index(
        self, 
        collection_name: str, 
        vector_field: str = "embedding",
        dimensions: int = 1536,
        similarity: str = "cosine",
        index_name: str = "vector_index"
    ) -> Dict[str, Any]:
        """Create a vector search index for Atlas Vector Search.
        
        Args:
            collection_name: Name of the collection
            vector_field: Name of the field containing vectors
            dimensions: Number of dimensions in the vectors
            similarity: Similarity metric ('cosine', 'euclidean', 'dotProduct')
            index_name: Name of the index
            
        Returns:
            Result dict with success status
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            # Create Atlas Vector Search index
            index_definition = {
                "mappings": {
                    "dynamic": True,
                    "fields": {
                        vector_field: {
                            "type": "knnVector",
                            "dimensions": dimensions,
                            "similarity": similarity
                        }
                    }
                }
            }
            
            try:
                # Use SearchIndexModel for PyMongo 4.6+ compatibility
                try:
                    from pymongo.operations import SearchIndexModel
                    search_index_model = SearchIndexModel(definition=index_definition, name=index_name)
                    collection.create_search_index(search_index_model)
                except ImportError:
                    # Fallback for older PyMongo versions
                    collection.create_search_index(index_definition, index_name)
                return {
                    "success": True,
                    "message": f"Vector search index '{index_name}' created successfully"
                }
            except Exception as e:
                if "already exists" in str(e).lower():
                    return {
                        "success": True,
                        "message": f"Vector search index '{index_name}' already exists"
                    }
                raise

        except Exception as e:
            error_msg = f"Error creating vector index: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def vector_search(
        self, 
        collection_name: str, 
        query_vector: List[float],
        vector_field: str = "embedding",
        limit: int = 10,
        num_candidates: int = 100,
        score_threshold: float = 0.0,
        filter_query: Optional[Dict[str, Any]] = None,
        index_name: str = "vector_index"
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """Perform vector similarity search using Atlas Vector Search.
        
        Args:
            collection_name: Name of the collection
            query_vector: Vector to search for
            vector_field: Name of the field containing vectors
            limit: Maximum number of results to return
            num_candidates: Number of candidates to consider
            score_threshold: Minimum similarity score
            filter_query: Optional additional filter
            index_name: Name of the vector index to use
            
        Returns:
            List of search results or error dict
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            # Build aggregation pipeline for vector search
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": index_name,
                        "path": vector_field,
                        "queryVector": query_vector,
                        "numCandidates": num_candidates,
                        "limit": limit
                    }
                },
                {
                    "$addFields": {
                        "score": {"$meta": "vectorSearchScore"}
                    }
                }
            ]
            
            # Add score threshold filter if specified
            if score_threshold > 0:
                pipeline.append({
                    "$match": {
                        "score": {"$gte": score_threshold}
                    }
                })
            
            # Add additional filter if specified
            if filter_query:
                pipeline.append({
                    "$match": filter_query
                })
            
            # Execute search
            results = []
            for doc in collection.aggregate(pipeline):
                doc["_id"] = str(doc["_id"])
                results.append(doc)
            
            return results

        except Exception as e:
            error_msg = f"Error performing vector search: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def store_with_embedding(
        self, 
        collection_name: str, 
        text: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Store text with its embedding vector.
        
        Args:
            collection_name: Name of the collection
            text: Text content
            embedding: Vector embedding
            metadata: Optional metadata
            
        Returns:
            Result dict with success status
        """
        document = {
            "text": text,
            "embedding": embedding,
            "metadata": metadata or {},
            "created_at": datetime.utcnow()
        }
        
        return self.insert_document(collection_name, document)

    def text_search(
        self, 
        collection_name: str, 
        query: str,
        limit: int = 10,
        text_field: str = "text"
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """Perform text search using MongoDB text indexes.
        
        Args:
            collection_name: Name of the collection
            query: Search query
            limit: Maximum number of results
            text_field: Field to search in
            
        Returns:
            List of search results or error dict
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            # Create text index if it doesn't exist
            try:
                collection.create_index([(text_field, "text")])
            except Exception:
                pass  # Index might already exist
            
            # Perform text search
            results = []
            for doc in collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit):
                doc["_id"] = str(doc["_id"])
                results.append(doc)
            
            return results

        except Exception as e:
            error_msg = f"Error performing text search: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def get_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get collection statistics.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Dict with collection statistics
        """
        try:
            collection = self._get_collection(collection_name)
            if collection is None:
                return {"error": "Could not connect to MongoDB"}

            stats = collection.estimated_document_count()
            return {
                "success": True,
                "collection_name": collection_name,
                "document_count": stats,
                "database_name": self.database_name
            }

        except Exception as e:
            error_msg = f"Error getting collection stats: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def close(self):
        """Close MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

# Create default instance for direct function access
_mongodb_tools = MongoDBTools()

# Export functions for direct use
insert_document = _mongodb_tools.insert_document
insert_documents = _mongodb_tools.insert_documents
find_documents = _mongodb_tools.find_documents
update_document = _mongodb_tools.update_document
delete_document = _mongodb_tools.delete_document
create_vector_index = _mongodb_tools.create_vector_index
vector_search = _mongodb_tools.vector_search
store_with_embedding = _mongodb_tools.store_with_embedding
text_search = _mongodb_tools.text_search
get_stats = _mongodb_tools.get_stats

def connect_mongodb(connection_string: str, database_name: str = "praisonai") -> MongoDBTools:
    """Create a new MongoDB connection.
    
    Args:
        connection_string: MongoDB connection string
        database_name: Database name to use
        
    Returns:
        MongoDBTools instance
    """
    return MongoDBTools(connection_string, database_name)

if __name__ == "__main__":
    print("\n==================================================")
    print("MongoDB Tools Demonstration")
    print("==================================================\n")
    
    # Test basic operations
    print("1. Testing Document Operations")
    print("------------------------------")
    
    # Insert a document
    result = insert_document("test_collection", {
        "name": "Test Document",
        "value": 42,
        "tags": ["test", "mongodb"]
    })
    print(f"Insert result: {result}")
    
    # Find documents
    results = find_documents("test_collection", {"name": "Test Document"})
    print(f"Find results: {results}")
    
    print("\n2. Testing Vector Operations")
    print("------------------------------")
    
    # Create vector index
    index_result = create_vector_index("vector_collection", dimensions=3)
    print(f"Vector index result: {index_result}")
    
    # Store document with embedding
    embedding_result = store_with_embedding(
        "vector_collection",
        "This is a test document for vector search",
        [0.1, 0.2, 0.3],
        {"category": "test"}
    )
    print(f"Store with embedding result: {embedding_result}")
    
    print("\n3. Testing Statistics")
    print("------------------------------")
    
    stats = get_stats("test_collection")
    print(f"Collection stats: {stats}")
    
    print("\n==================================================")
    print("MongoDB Tools Demonstration Complete")
    print("==================================================\n")