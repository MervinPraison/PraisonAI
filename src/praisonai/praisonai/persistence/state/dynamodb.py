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
    
    def _hash_field(self, item: dict) -> Dict[str, Any]:
        """Extract the hash map from a stored item.

        Hash fields live in a native DynamoDB ``Map`` attribute (``hash``) so
        individual fields can be updated atomically. Falls back to the legacy
        JSON-string ``value`` for items written before this store used a map.
        """
        if not item:
            return {}
        hashed = item.get("hash")
        if isinstance(hashed, dict):
            return hashed
        value = item.get("value")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}
        return value if isinstance(value, dict) else {}

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        response = self._table.get_item(Key={"pk": key})
        item = response.get("Item")
        if not item or (item.get("ttl") and item["ttl"] <= int(time.time())):
            return None
        return self._hash_field(item).get(field)
    
    def _seed_hash_map(self, key: str) -> None:
        """Ensure the native ``hash`` map exists, migrating legacy data.

        A single ``UpdateExpression`` cannot both create the parent map and set
        a nested field, so seed it first. If the item was written by the legacy
        implementation (hash stored as a JSON string in ``value``) migrate those
        fields into the native map so they remain visible after field updates.
        """
        response = self._table.get_item(Key={"pk": key})
        item = response.get("Item")
        if item and isinstance(item.get("hash"), dict):
            return
        seed = self._hash_field(item) if item else {}
        self._table.update_item(
            Key={"pk": key},
            UpdateExpression="SET #h = if_not_exists(#h, :seed)",
            ExpressionAttributeNames={"#h": "hash"},
            ExpressionAttributeValues={":seed": seed},
        )

    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash.

        Uses an atomic ``UpdateExpression`` on a native map attribute so
        concurrent writers to different fields of the same key do not clobber
        each other.
        """
        self._seed_hash_map(key)
        self._table.update_item(
            Key={"pk": key},
            UpdateExpression="SET #h.#f = :val, updated_at = :now",
            ExpressionAttributeNames={"#h": "hash", "#f": field},
            ExpressionAttributeValues={":val": value, ":now": int(time.time())},
        )
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        response = self._table.get_item(Key={"pk": key})
        item = response.get("Item")
        if not item or (item.get("ttl") and item["ttl"] <= int(time.time())):
            return {}
        return dict(self._hash_field(item))
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash.

        Uses an atomic ``REMOVE`` UpdateExpression so it does not clobber
        concurrent writes to other fields of the same key.
        """
        if not fields:
            return 0
        response = self._table.get_item(Key={"pk": key})
        item = response.get("Item")
        if not item:
            return 0
        current = self._hash_field(item)
        present = [f for f in fields if f in current]
        if not present:
            return 0
        # Migrate legacy JSON-string hashes into the native map so the REMOVE
        # below actually mutates the stored representation.
        if not isinstance(item.get("hash"), dict):
            self._table.update_item(
                Key={"pk": key},
                UpdateExpression="SET #h = if_not_exists(#h, :seed)",
                ExpressionAttributeNames={"#h": "hash"},
                ExpressionAttributeValues={":seed": current},
            )
        names = {f"#f{i}": f for i, f in enumerate(present)}
        expr = "REMOVE " + ", ".join(f"#h.{n}" for n in names)
        try:
            self._table.update_item(
                Key={"pk": key},
                UpdateExpression=expr,
                ExpressionAttributeNames={"#h": "hash", **names},
                ConditionExpression="attribute_exists(pk)",
            )
            return len(present)
        except Exception:
            return 0
    
    def close(self) -> None:
        """Close the store."""
        pass  # boto3 handles cleanup
