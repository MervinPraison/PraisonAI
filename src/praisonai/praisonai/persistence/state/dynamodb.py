"""
DynamoDB implementation of StateStore.

Requires: boto3
Install: pip install boto3
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


class DynamoDBStateStore(StateStore):
    """
    DynamoDB-based state store.
    
    Example:
        store = DynamoDBStateStore(
            table_name="praisonai_state",
            region="us-east-1"
        )
    """
    
    def __init__(
        self,
        table_name: str = "praisonai_state",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        auto_create_table: bool = True,
    ):
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for DynamoDB support. "
                "Install with: pip install boto3"
            )
        
        region = region or os.getenv("AWS_REGION", "us-east-1")
        
        self._dynamodb = boto3.resource(
            "dynamodb",
            region_name=region,
            endpoint_url=endpoint_url,
        )
        self._client = boto3.client(
            "dynamodb",
            region_name=region,
            endpoint_url=endpoint_url,
        )
        self.table_name = table_name
        
        if auto_create_table:
            self._create_table()
        
        self._table = self._dynamodb.Table(table_name)
        logger.info(f"Connected to DynamoDB table: {table_name}")
    
    def _create_table(self) -> None:
        """Create table if not exists."""
        try:
            self._client.describe_table(TableName=self.table_name)
        except self._client.exceptions.ResourceNotFoundException:
            self._client.create_table(
                TableName=self.table_name,
                KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            waiter = self._client.get_waiter("table_exists")
            waiter.wait(TableName=self.table_name)
            
            # Enable TTL
            self._client.update_time_to_live(
                TableName=self.table_name,
                TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"}
            )
            logger.info(f"Created DynamoDB table: {self.table_name}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        response = self._table.get_item(Key={"pk": key})
        item = response.get("Item")
        
        if not item:
            return None
        
        # Check TTL
        if item.get("ttl") and item["ttl"] <= int(time.time()):
            return None
        
        value = item.get("value")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set a value with optional TTL."""
        item = {
            "pk": key,
            "value": json.dumps(value) if not isinstance(value, str) else value,
            "updated_at": int(time.time()),
        }
        
        if ttl:
            item["ttl"] = int(time.time()) + ttl
        
        self._table.put_item(Item=item)
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        response = self._table.delete_item(
            Key={"pk": key},
            ReturnValues="ALL_OLD"
        )
        return "Attributes" in response
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        response = self._table.get_item(
            Key={"pk": key},
            ProjectionExpression="pk,#t",
            ExpressionAttributeNames={"#t": "ttl"}
        )
        item = response.get("Item")
        if not item:
            return False
        if item.get("ttl") and item["ttl"] <= int(time.time()):
            return False
        return True
    
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        # DynamoDB scan is expensive, use with caution
        response = self._table.scan(ProjectionExpression="pk")
        keys = [item["pk"] for item in response.get("Items", [])]
        
        if pattern != "*":
            import fnmatch
            keys = [k for k in keys if fnmatch.fnmatch(k, pattern)]
        
        return keys
    
    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds."""
        response = self._table.get_item(
            Key={"pk": key},
            ProjectionExpression="#t",
            ExpressionAttributeNames={"#t": "ttl"}
        )
        item = response.get("Item")
        if not item or "ttl" not in item:
            return None
        
        remaining = item["ttl"] - int(time.time())
        if remaining <= 0:
            return None
        return remaining
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        try:
            self._table.update_item(
                Key={"pk": key},
                UpdateExpression="SET #t = :ttl",
                ExpressionAttributeNames={"#t": "ttl"},
                ExpressionAttributeValues={":ttl": int(time.time()) + ttl},
                ConditionExpression="attribute_exists(pk)"
            )
            return True
        except self._client.exceptions.ConditionalCheckFailedException:
            return False
    
    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        value = self.get(key)
        if not isinstance(value, dict):
            return None
        return value.get(field)
    
    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash."""
        current = self.get(key)
        if not isinstance(current, dict):
            current = {}
        current[field] = value
        self.set(key, current)
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        value = self.get(key)
        if not isinstance(value, dict):
            return {}
        return value
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash."""
        current = self.get(key)
        if not isinstance(current, dict):
            return 0
        count = 0
        for field in fields:
            if field in current:
                del current[field]
                count += 1
        if count > 0:
            self.set(key, current)
        return count
    
    def close(self) -> None:
        """Close the store."""
        pass  # boto3 handles cleanup
