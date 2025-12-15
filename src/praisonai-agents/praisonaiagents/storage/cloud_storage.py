"""
Cloud storage backends for PraisonAI Agents.

This module provides cloud storage implementations for AWS S3, Google Cloud Storage,
and Azure Blob Storage.
"""

import json
import time
import asyncio
from typing import Any, Dict, List, Optional
from .base import BaseStorage

# AWS S3 imports
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False
    boto3 = None

# Google Cloud Storage imports
try:
    from google.cloud import storage as gcs
    from google.api_core import exceptions as gcs_exceptions
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    gcs = None

# Azure Blob Storage imports
try:
    from azure.storage.blob.aio import BlobServiceClient
    from azure.core.exceptions import ResourceNotFoundError, AzureError
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    BlobServiceClient = None


class S3Storage(BaseStorage):
    """
    AWS S3 storage backend implementation.
    
    Provides object storage with versioning, lifecycle policies,
    and cross-region replication support.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize S3 storage.
        
        Args:
            config: Configuration dictionary with keys:
                - bucket: S3 bucket name (required)
                - region: AWS region (default: "us-east-1")
                - prefix: Key prefix for namespacing (default: "agents/")
                - aws_access_key_id: AWS access key (optional if using IAM roles)
                - aws_secret_access_key: AWS secret key (optional if using IAM roles)
                - aws_profile: AWS profile name (optional)
                - endpoint_url: Custom endpoint URL for S3-compatible services (optional)
                - storage_class: S3 storage class (default: "STANDARD")
                - server_side_encryption: Encryption type (default: None)
        """
        if not S3_AVAILABLE:
            raise ImportError(
                "S3 storage requires boto3. "
                "Install with: pip install boto3"
            )
        
        super().__init__(config)
        
        self.bucket = config.get("bucket")
        if not self.bucket:
            raise ValueError("bucket is required for S3 storage")
        
        self.region = config.get("region", "us-east-1")
        self.prefix = config.get("prefix", "agents/")
        self.aws_access_key_id = config.get("aws_access_key_id")
        self.aws_secret_access_key = config.get("aws_secret_access_key")
        self.aws_profile = config.get("aws_profile")
        self.endpoint_url = config.get("endpoint_url")
        self.storage_class = config.get("storage_class", "STANDARD")
        self.server_side_encryption = config.get("server_side_encryption")
        
        # Initialize session and client
        self.session = None
        self.s3_client = None
        self._initialized = False
    
    def _make_key(self, key: str) -> str:
        """Create prefixed S3 key."""
        return f"{self.prefix}{key}.json"
    
    def _strip_prefix(self, s3_key: str) -> str:
        """Remove prefix and extension from S3 key."""
        if s3_key.startswith(self.prefix):
            key = s3_key[len(self.prefix):]
            if key.endswith(".json"):
                key = key[:-5]
            return key
        return s3_key
    
    async def _ensure_connection(self):
        """Ensure S3 connection is established."""
        if not self._initialized:
            try:
                # Create session with credentials
                session_kwargs = {"region_name": self.region}
                
                if self.aws_profile:
                    self.session = boto3.Session(profile_name=self.aws_profile, **session_kwargs)
                elif self.aws_access_key_id and self.aws_secret_access_key:
                    self.session = boto3.Session(
                        aws_access_key_id=self.aws_access_key_id,
                        aws_secret_access_key=self.aws_secret_access_key,
                        **session_kwargs
                    )
                else:
                    self.session = boto3.Session(**session_kwargs)
                
                # Create S3 client
                client_kwargs = {}
                if self.endpoint_url:
                    client_kwargs["endpoint_url"] = self.endpoint_url
                
                self.s3_client = self.session.client("s3", **client_kwargs)
                
                # Verify bucket access
                await self._verify_bucket()
                
                self._initialized = True
                self.logger.info(f"Connected to S3 bucket: {self.bucket}")
                
            except Exception as e:
                self.logger.error(f"Failed to connect to S3: {e}")
                raise
    
    async def _verify_bucket(self):
        """Verify bucket exists and is accessible."""
        loop = asyncio.get_event_loop()
        
        try:
            await loop.run_in_executor(
                None,
                self.s3_client.head_bucket,
                {"Bucket": self.bucket}
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                raise ValueError(f"S3 bucket '{self.bucket}' does not exist")
            elif error_code == '403':
                raise ValueError(f"Access denied to S3 bucket '{self.bucket}'")
            else:
                raise
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        s3_key = self._make_key(key)
        
        try:
            response = await loop.run_in_executor(
                None,
                self.s3_client.get_object,
                {"Bucket": self.bucket, "Key": s3_key}
            )
            
            content = response["Body"].read().decode("utf-8")
            data = json.loads(content)
            data["id"] = key
            return data
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            self.logger.error(f"Failed to read key {key}: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON for key {key}: {e}")
            return None
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        s3_key = self._make_key(key)
        
        try:
            # Prepare record
            record = data.copy()
            record["updated_at"] = time.time()
            if "created_at" not in record:
                record["created_at"] = record["updated_at"]
            
            # Serialize to JSON
            content = json.dumps(record, ensure_ascii=False, indent=2)
            
            # Prepare put_object arguments
            put_args = {
                "Bucket": self.bucket,
                "Key": s3_key,
                "Body": content.encode("utf-8"),
                "ContentType": "application/json",
                "StorageClass": self.storage_class
            }
            
            # Add server-side encryption if configured
            if self.server_side_encryption:
                put_args["ServerSideEncryption"] = self.server_side_encryption
            
            await loop.run_in_executor(
                None,
                self.s3_client.put_object,
                put_args
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        s3_key = self._make_key(key)
        
        try:
            await loop.run_in_executor(
                None,
                self.s3_client.delete_object,
                {"Bucket": self.bucket, "Key": s3_key}
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for records matching the query."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # List all objects with prefix
            response = await loop.run_in_executor(
                None,
                self.s3_client.list_objects_v2,
                {"Bucket": self.bucket, "Prefix": self.prefix}
            )
            
            results = []
            limit = query.get("limit", 100)
            
            for obj in response.get("Contents", []):
                if len(results) >= limit:
                    break
                
                s3_key = obj["Key"]
                key = self._strip_prefix(s3_key)
                
                # Read and filter object
                record = await self.read(key)
                if record and self._matches_query(record, query):
                    results.append(record)
            
            # Sort by updated_at descending
            results.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to search: {e}")
            return []
    
    def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a record matches the search query."""
        # Text search in content
        if "text" in query:
            content = str(record.get("content", "")).lower()
            search_text = query["text"].lower()
            if search_text not in content:
                return False
        
        # Metadata search
        if "metadata" in query:
            record_metadata = record.get("metadata", {})
            for key, value in query["metadata"].items():
                if record_metadata.get(key) != value:
                    return False
        
        # Time range filters
        if "created_after" in query:
            if record.get("created_at", 0) < query["created_after"]:
                return False
        
        if "created_before" in query:
            if record.get("created_at", float('inf')) > query["created_before"]:
                return False
        
        return True
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # Build S3 prefix
            s3_prefix = self.prefix
            if prefix:
                s3_prefix += prefix
            
            # List objects
            list_args = {"Bucket": self.bucket, "Prefix": s3_prefix}
            if limit:
                list_args["MaxKeys"] = limit
            
            response = await loop.run_in_executor(
                None,
                self.s3_client.list_objects_v2,
                list_args
            )
            
            keys = []
            for obj in response.get("Contents", []):
                key = self._strip_prefix(obj["Key"])
                keys.append(key)
            
            return keys
            
        except Exception as e:
            self.logger.error(f"Failed to list keys: {e}")
            return []
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # List all objects
            response = await loop.run_in_executor(
                None,
                self.s3_client.list_objects_v2,
                {"Bucket": self.bucket, "Prefix": self.prefix}
            )
            
            # Delete all objects
            for obj in response.get("Contents", []):
                await loop.run_in_executor(
                    None,
                    self.s3_client.delete_object,
                    {"Bucket": self.bucket, "Key": obj["Key"]}
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        s3_key = self._make_key(key)
        
        try:
            await loop.run_in_executor(
                None,
                self.s3_client.head_object,
                {"Bucket": self.bucket, "Key": s3_key}
            )
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            self.logger.error(f"Failed to check existence of key {key}: {e}")
            return False
    
    async def count(self) -> int:
        """Count total number of records in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                self.s3_client.list_objects_v2,
                {"Bucket": self.bucket, "Prefix": self.prefix}
            )
            
            return response.get("KeyCount", 0)
            
        except Exception as e:
            self.logger.error(f"Failed to count records: {e}")
            return 0


class GCSStorage(BaseStorage):
    """
    Google Cloud Storage backend implementation.
    
    Provides object storage with automatic lifecycle management,
    versioning, and global distribution.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize GCS storage.
        
        Args:
            config: Configuration dictionary with keys:
                - bucket: GCS bucket name (required)
                - project: GCP project ID (optional)
                - prefix: Key prefix for namespacing (default: "agents/")
                - credentials_path: Path to service account JSON (optional)
                - storage_class: GCS storage class (default: "STANDARD")
        """
        if not GCS_AVAILABLE:
            raise ImportError(
                "GCS storage requires google-cloud-storage. "
                "Install with: pip install google-cloud-storage"
            )
        
        super().__init__(config)
        
        self.bucket_name = config.get("bucket")
        if not self.bucket_name:
            raise ValueError("bucket is required for GCS storage")
        
        self.project = config.get("project")
        self.prefix = config.get("prefix", "agents/")
        self.credentials_path = config.get("credentials_path")
        self.storage_class = config.get("storage_class", "STANDARD")
        
        # Initialize client and bucket
        self.client = None
        self.bucket = None
        self._initialized = False
    
    def _make_key(self, key: str) -> str:
        """Create prefixed GCS key."""
        return f"{self.prefix}{key}.json"
    
    def _strip_prefix(self, gcs_key: str) -> str:
        """Remove prefix and extension from GCS key."""
        if gcs_key.startswith(self.prefix):
            key = gcs_key[len(self.prefix):]
            if key.endswith(".json"):
                key = key[:-5]
            return key
        return gcs_key
    
    async def _ensure_connection(self):
        """Ensure GCS connection is established."""
        if not self._initialized:
            try:
                # Create client with optional credentials
                client_kwargs = {}
                if self.project:
                    client_kwargs["project"] = self.project
                if self.credentials_path:
                    client_kwargs["credentials"] = self.credentials_path
                
                self.client = gcs.Client(**client_kwargs)
                self.bucket = self.client.bucket(self.bucket_name)
                
                # Verify bucket exists
                if not self.bucket.exists():
                    raise ValueError(f"GCS bucket '{self.bucket_name}' does not exist")
                
                self._initialized = True
                self.logger.info(f"Connected to GCS bucket: {self.bucket_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to connect to GCS: {e}")
                raise
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        gcs_key = self._make_key(key)
        
        try:
            blob = self.bucket.blob(gcs_key)
            content = await loop.run_in_executor(None, blob.download_as_text)
            
            data = json.loads(content)
            data["id"] = key
            return data
            
        except gcs_exceptions.NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Failed to read key {key}: {e}")
            return None
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        gcs_key = self._make_key(key)
        
        try:
            # Prepare record
            record = data.copy()
            record["updated_at"] = time.time()
            if "created_at" not in record:
                record["created_at"] = record["updated_at"]
            
            # Serialize to JSON
            content = json.dumps(record, ensure_ascii=False, indent=2)
            
            # Upload to GCS
            blob = self.bucket.blob(gcs_key)
            blob.storage_class = self.storage_class
            
            await loop.run_in_executor(
                None,
                blob.upload_from_string,
                content,
                content_type="application/json"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        gcs_key = self._make_key(key)
        
        try:
            blob = self.bucket.blob(gcs_key)
            await loop.run_in_executor(None, blob.delete)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for records matching the query."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # List all blobs with prefix
            blobs = await loop.run_in_executor(
                None,
                list,
                self.client.list_blobs(self.bucket, prefix=self.prefix)
            )
            
            results = []
            limit = query.get("limit", 100)
            
            for blob in blobs:
                if len(results) >= limit:
                    break
                
                key = self._strip_prefix(blob.name)
                
                # Read and filter blob
                record = await self.read(key)
                if record and self._matches_query(record, query):
                    results.append(record)
            
            # Sort by updated_at descending
            results.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to search: {e}")
            return []
    
    def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a record matches the search query."""
        # Text search in content
        if "text" in query:
            content = str(record.get("content", "")).lower()
            search_text = query["text"].lower()
            if search_text not in content:
                return False
        
        # Metadata search
        if "metadata" in query:
            record_metadata = record.get("metadata", {})
            for key, value in query["metadata"].items():
                if record_metadata.get(key) != value:
                    return False
        
        # Time range filters
        if "created_after" in query:
            if record.get("created_at", 0) < query["created_after"]:
                return False
        
        if "created_before" in query:
            if record.get("created_at", float('inf')) > query["created_before"]:
                return False
        
        return True
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # Build GCS prefix
            gcs_prefix = self.prefix
            if prefix:
                gcs_prefix += prefix
            
            # List blobs
            blobs = await loop.run_in_executor(
                None,
                list,
                self.client.list_blobs(self.bucket, prefix=gcs_prefix, max_results=limit)
            )
            
            keys = [self._strip_prefix(blob.name) for blob in blobs]
            return keys
            
        except Exception as e:
            self.logger.error(f"Failed to list keys: {e}")
            return []
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # List and delete all blobs
            blobs = await loop.run_in_executor(
                None,
                list,
                self.client.list_blobs(self.bucket, prefix=self.prefix)
            )
            
            for blob in blobs:
                await loop.run_in_executor(None, blob.delete)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        gcs_key = self._make_key(key)
        
        try:
            blob = self.bucket.blob(gcs_key)
            return await loop.run_in_executor(None, blob.exists)
            
        except Exception as e:
            self.logger.error(f"Failed to check existence of key {key}: {e}")
            return False
    
    async def count(self) -> int:
        """Count total number of records in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            blobs = await loop.run_in_executor(
                None,
                list,
                self.client.list_blobs(self.bucket, prefix=self.prefix)
            )
            
            return len(blobs)
            
        except Exception as e:
            self.logger.error(f"Failed to count records: {e}")
            return 0


class AzureStorage(BaseStorage):
    """
    Azure Blob Storage backend implementation.
    
    Provides object storage with tiering, lifecycle management,
    and global replication.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Azure storage.
        
        Args:
            config: Configuration dictionary with keys:
                - container: Azure container name (required)
                - connection_string: Azure storage connection string (required)
                - prefix: Key prefix for namespacing (default: "agents/")
                - storage_tier: Storage tier ("Hot", "Cool", "Archive") (default: "Hot")
        """
        if not AZURE_AVAILABLE:
            raise ImportError(
                "Azure storage requires azure-storage-blob. "
                "Install with: pip install azure-storage-blob"
            )
        
        super().__init__(config)
        
        self.container_name = config.get("container")
        if not self.container_name:
            raise ValueError("container is required for Azure storage")
        
        self.connection_string = config.get("connection_string")
        if not self.connection_string:
            raise ValueError("connection_string is required for Azure storage")
        
        self.prefix = config.get("prefix", "agents/")
        self.storage_tier = config.get("storage_tier", "Hot")
        
        # Initialize client
        self.blob_service_client = None
        self.container_client = None
        self._initialized = False
    
    def _make_key(self, key: str) -> str:
        """Create prefixed Azure key."""
        return f"{self.prefix}{key}.json"
    
    def _strip_prefix(self, azure_key: str) -> str:
        """Remove prefix and extension from Azure key."""
        if azure_key.startswith(self.prefix):
            key = azure_key[len(self.prefix):]
            if key.endswith(".json"):
                key = key[:-5]
            return key
        return azure_key
    
    async def _ensure_connection(self):
        """Ensure Azure connection is established."""
        if not self._initialized:
            try:
                # Create blob service client
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    self.connection_string
                )
                
                # Get container client
                self.container_client = self.blob_service_client.get_container_client(
                    self.container_name
                )
                
                # Verify container exists
                try:
                    await self.container_client.get_container_properties()
                except ResourceNotFoundError:
                    raise ValueError(f"Azure container '{self.container_name}' does not exist")
                
                self._initialized = True
                self.logger.info(f"Connected to Azure container: {self.container_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to connect to Azure: {e}")
                raise
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        await self._ensure_connection()
        
        azure_key = self._make_key(key)
        
        try:
            blob_client = self.container_client.get_blob_client(azure_key)
            content = await blob_client.download_blob()
            content_str = await content.readall()
            
            data = json.loads(content_str.decode("utf-8"))
            data["id"] = key
            return data
            
        except ResourceNotFoundError:
            return None
        except Exception as e:
            self.logger.error(f"Failed to read key {key}: {e}")
            return None
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        await self._ensure_connection()
        
        azure_key = self._make_key(key)
        
        try:
            # Prepare record
            record = data.copy()
            record["updated_at"] = time.time()
            if "created_at" not in record:
                record["created_at"] = record["updated_at"]
            
            # Serialize to JSON
            content = json.dumps(record, ensure_ascii=False, indent=2)
            
            # Upload to Azure
            blob_client = self.container_client.get_blob_client(azure_key)
            await blob_client.upload_blob(
                content.encode("utf-8"),
                content_type="application/json",
                overwrite=True,
                standard_blob_tier=self.storage_tier
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        await self._ensure_connection()
        
        azure_key = self._make_key(key)
        
        try:
            blob_client = self.container_client.get_blob_client(azure_key)
            await blob_client.delete_blob()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for records matching the query."""
        await self._ensure_connection()
        
        try:
            # List all blobs with prefix
            blobs = []
            async for blob in self.container_client.list_blobs(name_starts_with=self.prefix):
                blobs.append(blob)
            
            results = []
            limit = query.get("limit", 100)
            
            for blob in blobs:
                if len(results) >= limit:
                    break
                
                key = self._strip_prefix(blob.name)
                
                # Read and filter blob
                record = await self.read(key)
                if record and self._matches_query(record, query):
                    results.append(record)
            
            # Sort by updated_at descending
            results.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to search: {e}")
            return []
    
    def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a record matches the search query."""
        # Text search in content
        if "text" in query:
            content = str(record.get("content", "")).lower()
            search_text = query["text"].lower()
            if search_text not in content:
                return False
        
        # Metadata search
        if "metadata" in query:
            record_metadata = record.get("metadata", {})
            for key, value in query["metadata"].items():
                if record_metadata.get(key) != value:
                    return False
        
        # Time range filters
        if "created_after" in query:
            if record.get("created_at", 0) < query["created_after"]:
                return False
        
        if "created_before" in query:
            if record.get("created_at", float('inf')) > query["created_before"]:
                return False
        
        return True
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        await self._ensure_connection()
        
        try:
            # Build Azure prefix
            azure_prefix = self.prefix
            if prefix:
                azure_prefix += prefix
            
            # List blobs
            keys = []
            async for blob in self.container_client.list_blobs(name_starts_with=azure_prefix):
                if limit and len(keys) >= limit:
                    break
                keys.append(self._strip_prefix(blob.name))
            
            return keys
            
        except Exception as e:
            self.logger.error(f"Failed to list keys: {e}")
            return []
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        await self._ensure_connection()
        
        try:
            # List and delete all blobs
            async for blob in self.container_client.list_blobs(name_starts_with=self.prefix):
                blob_client = self.container_client.get_blob_client(blob.name)
                await blob_client.delete_blob()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        await self._ensure_connection()
        
        azure_key = self._make_key(key)
        
        try:
            blob_client = self.container_client.get_blob_client(azure_key)
            await blob_client.get_blob_properties()
            return True
            
        except ResourceNotFoundError:
            return False
        except Exception as e:
            self.logger.error(f"Failed to check existence of key {key}: {e}")
            return False
    
    async def count(self) -> int:
        """Count total number of records in storage."""
        await self._ensure_connection()
        
        try:
            count = 0
            async for _ in self.container_client.list_blobs(name_starts_with=self.prefix):
                count += 1
            
            return count
            
        except Exception as e:
            self.logger.error(f"Failed to count records: {e}")
            return 0
    
    async def close(self):
        """Close Azure connection."""
        if self.blob_service_client:
            await self.blob_service_client.close()
            self._initialized = False