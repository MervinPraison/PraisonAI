"""
DynamoDB storage backend for PraisonAI Agents.

This module provides AWS DynamoDB-based storage implementation for serverless
applications with automatic scaling and high availability.
"""

import time
import json
import asyncio
from typing import Any, Dict, List, Optional
from decimal import Decimal
from .base import BaseStorage

try:
    import boto3
    from boto3.dynamodb.conditions import Key, Attr
    from botocore.exceptions import ClientError, NoCredentialsError
    DYNAMODB_AVAILABLE = True
except ImportError:
    DYNAMODB_AVAILABLE = False
    boto3 = None


class DynamoDBStorage(BaseStorage):
    """
    DynamoDB storage backend implementation.
    
    Provides serverless storage with automatic scaling, global tables support,
    and strong consistency guarantees.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize DynamoDB storage.
        
        Args:
            config: Configuration dictionary with keys:
                - table_name: DynamoDB table name (required)
                - region: AWS region (default: "us-east-1")
                - aws_access_key_id: AWS access key (optional if using IAM roles)
                - aws_secret_access_key: AWS secret key (optional if using IAM roles)
                - aws_profile: AWS profile name (optional)
                - endpoint_url: Custom endpoint URL for testing (optional)
                - read_capacity: Read capacity units (default: 5)
                - write_capacity: Write capacity units (default: 5)
                - enable_streams: Enable DynamoDB streams (default: False)
                - ttl_attribute: Attribute name for TTL (optional)
                - consistent_read: Use strongly consistent reads (default: False)
        """
        if not DYNAMODB_AVAILABLE:
            raise ImportError(
                "DynamoDB storage requires boto3. "
                "Install with: pip install boto3"
            )
        
        super().__init__(config)
        
        self.table_name = config.get("table_name")
        if not self.table_name:
            raise ValueError("table_name is required for DynamoDB storage")
        
        self.region = config.get("region", "us-east-1")
        self.aws_access_key_id = config.get("aws_access_key_id")
        self.aws_secret_access_key = config.get("aws_secret_access_key")
        self.aws_profile = config.get("aws_profile")
        self.endpoint_url = config.get("endpoint_url")
        self.read_capacity = config.get("read_capacity", 5)
        self.write_capacity = config.get("write_capacity", 5)
        self.enable_streams = config.get("enable_streams", False)
        self.ttl_attribute = config.get("ttl_attribute")
        self.consistent_read = config.get("consistent_read", False)
        
        # Initialize session and client
        self.session = None
        self.dynamodb = None
        self.table = None
        self._initialized = False
    
    def _convert_decimals(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DynamoDB Decimal objects to float for JSON serialization."""
        if isinstance(item, dict):
            return {k: self._convert_decimals(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [self._convert_decimals(v) for v in item]
        elif isinstance(item, Decimal):
            return float(item)
        else:
            return item
    
    def _prepare_item(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare item for DynamoDB by converting floats to Decimals."""
        def convert_floats(obj):
            if isinstance(obj, dict):
                return {k: convert_floats(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_floats(v) for v in obj]
            elif isinstance(obj, float):
                return Decimal(str(obj))
            else:
                return obj
        
        return convert_floats(data)
    
    async def _ensure_connection(self):
        """Ensure DynamoDB connection is established."""
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
                
                # Create DynamoDB resource
                dynamodb_kwargs = {}
                if self.endpoint_url:
                    dynamodb_kwargs["endpoint_url"] = self.endpoint_url
                
                self.dynamodb = self.session.resource("dynamodb", **dynamodb_kwargs)
                
                # Get or create table
                await self._ensure_table()
                
                self._initialized = True
                self.logger.info(f"Connected to DynamoDB table: {self.table_name}")
                
            except NoCredentialsError as e:
                self.logger.error(f"AWS credentials not found: {e}")
                raise
            except Exception as e:
                self.logger.error(f"Failed to connect to DynamoDB: {e}")
                raise
    
    async def _ensure_table(self):
        """Ensure DynamoDB table exists, create if necessary."""
        loop = asyncio.get_event_loop()
        
        try:
            # Check if table exists
            self.table = self.dynamodb.Table(self.table_name)
            await loop.run_in_executor(None, self.table.load)
            
            self.logger.info(f"Using existing DynamoDB table: {self.table_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Table doesn't exist, create it
                await self._create_table()
            else:
                raise
    
    async def _create_table(self):
        """Create DynamoDB table."""
        loop = asyncio.get_event_loop()
        
        try:
            table_kwargs = {
                "TableName": self.table_name,
                "KeySchema": [
                    {"AttributeName": "id", "KeyType": "HASH"}
                ],
                "AttributeDefinitions": [
                    {"AttributeName": "id", "AttributeType": "S"}
                ],
                "BillingMode": "PROVISIONED",
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": self.read_capacity,
                    "WriteCapacityUnits": self.write_capacity
                }
            }
            
            # Add streams if enabled
            if self.enable_streams:
                table_kwargs["StreamSpecification"] = {
                    "StreamEnabled": True,
                    "StreamViewType": "NEW_AND_OLD_IMAGES"
                }
            
            # Create table
            self.table = await loop.run_in_executor(
                None, self.dynamodb.create_table, **table_kwargs
            )
            
            # Wait for table to be active
            await loop.run_in_executor(None, self.table.wait_until_exists)
            
            # Enable TTL if configured
            if self.ttl_attribute:
                await self._enable_ttl()
            
            self.logger.info(f"Created DynamoDB table: {self.table_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to create DynamoDB table: {e}")
            raise
    
    async def _enable_ttl(self):
        """Enable TTL on the table."""
        loop = asyncio.get_event_loop()
        
        try:
            client = self.session.client("dynamodb")
            await loop.run_in_executor(
                None,
                client.update_time_to_live,
                {
                    "TableName": self.table_name,
                    "TimeToLiveSpecification": {
                        "AttributeName": self.ttl_attribute,
                        "Enabled": True
                    }
                }
            )
            self.logger.info(f"Enabled TTL on attribute: {self.ttl_attribute}")
            
        except Exception as e:
            self.logger.error(f"Failed to enable TTL: {e}")
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                self.table.get_item,
                {
                    "Key": {"id": key},
                    "ConsistentRead": self.consistent_read
                }
            )
            
            if "Item" in response:
                item = self._convert_decimals(response["Item"])
                return item
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to read key {key}: {e}")
            return None
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # Prepare item
            item = data.copy()
            item["id"] = key
            item["updated_at"] = time.time()
            
            if "created_at" not in item:
                item["created_at"] = item["updated_at"]
            
            # Add TTL if configured
            if self.ttl_attribute and self.ttl_attribute not in item:
                # Default TTL of 30 days if not specified
                ttl_seconds = 30 * 24 * 60 * 60
                item[self.ttl_attribute] = int(time.time() + ttl_seconds)
            
            # Convert to DynamoDB format
            item = self._prepare_item(item)
            
            # Put item
            await loop.run_in_executor(
                None,
                self.table.put_item,
                {"Item": item}
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                self.table.delete_item,
                {
                    "Key": {"id": key},
                    "ReturnValues": "ALL_OLD"
                }
            )
            
            return "Attributes" in response
            
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for records matching the query.
        
        Note: DynamoDB search capabilities are limited without GSIs.
        This implementation scans the table and filters client-side.
        For production use, consider creating appropriate GSIs.
        """
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # Build filter expression
            filter_expression = None
            expression_values = {}
            
            # Text search in content (basic contains operation)
            if "text" in query:
                filter_expression = Attr("content").contains(query["text"])
            
            # Metadata search
            if "metadata" in query:
                for key, value in query["metadata"].items():
                    attr_expr = Attr(f"metadata.{key}").eq(value)
                    if filter_expression:
                        filter_expression = filter_expression & attr_expr
                    else:
                        filter_expression = attr_expr
            
            # Time range filters
            if "created_after" in query:
                attr_expr = Attr("created_at").gte(query["created_after"])
                if filter_expression:
                    filter_expression = filter_expression & attr_expr
                else:
                    filter_expression = attr_expr
            
            if "created_before" in query:
                attr_expr = Attr("created_at").lte(query["created_before"])
                if filter_expression:
                    filter_expression = filter_expression & attr_expr
                else:
                    filter_expression = attr_expr
            
            # Perform scan with filter
            scan_kwargs = {}
            if filter_expression:
                scan_kwargs["FilterExpression"] = filter_expression
            
            # Add limit
            limit = query.get("limit", 100)
            scan_kwargs["Limit"] = limit
            
            response = await loop.run_in_executor(
                None,
                self.table.scan,
                scan_kwargs
            )
            
            items = [self._convert_decimals(item) for item in response.get("Items", [])]
            
            # Sort by updated_at descending
            items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            
            return items
            
        except Exception as e:
            self.logger.error(f"Failed to search: {e}")
            return []
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            scan_kwargs = {
                "ProjectionExpression": "id"
            }
            
            if limit:
                scan_kwargs["Limit"] = limit
            
            response = await loop.run_in_executor(
                None,
                self.table.scan,
                scan_kwargs
            )
            
            keys = [item["id"] for item in response.get("Items", [])]
            
            # Apply prefix filter if specified
            if prefix:
                keys = [key for key in keys if key.startswith(prefix)]
            
            return keys
            
        except Exception as e:
            self.logger.error(f"Failed to list keys: {e}")
            return []
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            # Scan for all items
            response = await loop.run_in_executor(
                None,
                self.table.scan,
                {"ProjectionExpression": "id"}
            )
            
            # Delete all items
            with self.table.batch_writer() as batch:
                for item in response.get("Items", []):
                    await loop.run_in_executor(
                        None,
                        batch.delete_item,
                        {"Key": {"id": item["id"]}}
                    )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
    
    async def batch_write(self, records: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Optimized batch write for DynamoDB."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        results = {}
        
        try:
            current_time = time.time()
            
            # DynamoDB batch_writer handles batching automatically
            with self.table.batch_writer() as batch:
                for key, data in records.items():
                    item = data.copy()
                    item["id"] = key
                    item["updated_at"] = current_time
                    
                    if "created_at" not in item:
                        item["created_at"] = current_time
                    
                    if self.ttl_attribute and self.ttl_attribute not in item:
                        ttl_seconds = 30 * 24 * 60 * 60
                        item[self.ttl_attribute] = int(time.time() + ttl_seconds)
                    
                    item = self._prepare_item(item)
                    
                    await loop.run_in_executor(
                        None,
                        batch.put_item,
                        {"Item": item}
                    )
                    
                    results[key] = True
                    
        except Exception as e:
            self.logger.error(f"Failed batch write: {e}")
            for key in records.keys():
                results[key] = False
        
        return results
    
    async def batch_read(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Optimized batch read for DynamoDB."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        results = {key: None for key in keys}
        
        try:
            # DynamoDB batch_get_item has a limit of 100 items
            chunk_size = 100
            
            for i in range(0, len(keys), chunk_size):
                chunk_keys = keys[i:i + chunk_size]
                
                request_items = {
                    self.table_name: {
                        "Keys": [{"id": key} for key in chunk_keys],
                        "ConsistentRead": self.consistent_read
                    }
                }
                
                client = self.session.client("dynamodb")
                response = await loop.run_in_executor(
                    None,
                    client.batch_get_item,
                    {"RequestItems": request_items}
                )
                
                # Process responses
                for item in response.get("Responses", {}).get(self.table_name, []):
                    # Convert from DynamoDB format
                    from boto3.dynamodb.types import TypeDeserializer
                    deserializer = TypeDeserializer()
                    deserialized = {k: deserializer.deserialize(v) for k, v in item.items()}
                    
                    key = deserialized["id"]
                    results[key] = self._convert_decimals(deserialized)
                    
        except Exception as e:
            self.logger.error(f"Failed batch read: {e}")
        
        return results
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                self.table.get_item,
                {
                    "Key": {"id": key},
                    "ProjectionExpression": "id",
                    "ConsistentRead": self.consistent_read
                }
            )
            
            return "Item" in response
            
        except Exception as e:
            self.logger.error(f"Failed to check existence of key {key}: {e}")
            return False
    
    async def count(self) -> int:
        """Count total number of records in storage."""
        await self._ensure_connection()
        
        loop = asyncio.get_event_loop()
        
        try:
            response = await loop.run_in_executor(
                None,
                self.table.scan,
                {"Select": "COUNT"}
            )
            
            return response.get("Count", 0)
            
        except Exception as e:
            self.logger.error(f"Failed to count records: {e}")
            return 0