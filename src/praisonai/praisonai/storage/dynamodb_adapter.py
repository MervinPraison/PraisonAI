"""
DynamoDB Storage Adapter for PraisonAI.

Implements StorageBackendProtocol using AWS DynamoDB for NoSQL storage.
This is the wrapper implementation that contains the heavy AWS SDK dependency.
"""

import json
import time
from typing import Dict, Any, List, Optional


class DynamoDBStorageAdapter:
    """
    DynamoDB-based storage backend adapter.
    
    Uses AWS DynamoDB for scalable NoSQL data storage.
    Implements StorageBackendProtocol from praisonaiagents.storage.protocols.
    
    Example:
        ```python
        from praisonai.storage import DynamoDBStorageAdapter
        
        adapter = DynamoDBStorageAdapter(
            table_name="praisonai-storage",
            region_name="us-east-1"
        )
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """
    
    def __init__(
        self,
        table_name: str = "praisonai-storage",
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        read_capacity_units: int = 5,
        write_capacity_units: int = 5,
        auto_create_table: bool = True,
    ):
        """
        Initialize the DynamoDB storage adapter.
        
        Args:
            table_name: DynamoDB table name
            region_name: AWS region name
            aws_access_key_id: AWS access key ID (optional, can use env/IAM)
            aws_secret_access_key: AWS secret access key (optional, can use env/IAM)
            aws_session_token: AWS session token (optional)
            endpoint_url: Custom endpoint URL (for local DynamoDB)
            read_capacity_units: Read capacity units for table creation
            write_capacity_units: Write capacity units for table creation  
            auto_create_table: Whether to auto-create table if it doesn't exist
        """
        self.table_name = table_name
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token
        self.endpoint_url = endpoint_url
        self.read_capacity_units = read_capacity_units
        self.write_capacity_units = write_capacity_units
        self.auto_create_table = auto_create_table
        self._dynamodb = None
        self._table = None
    
    def _get_table(self):
        """Lazy initialize DynamoDB client and table."""
        if self._table is None:
            try:
                import boto3
                from botocore.exceptions import ClientError
            except ImportError:
                raise ImportError(
                    "DynamoDB storage adapter requires the 'boto3' package. "
                    "Install with: pip install 'praisonai[dynamodb]'"
                )
            
            # Build session/client parameters
            session_kwargs = {}
            if self.aws_access_key_id:
                session_kwargs["aws_access_key_id"] = self.aws_access_key_id
            if self.aws_secret_access_key:
                session_kwargs["aws_secret_access_key"] = self.aws_secret_access_key
            if self.aws_session_token:
                session_kwargs["aws_session_token"] = self.aws_session_token
            if self.region_name:
                session_kwargs["region_name"] = self.region_name
            
            # Create session and client
            session = boto3.Session(**session_kwargs)
            client_kwargs = {}
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url
                
            self._dynamodb = session.resource("dynamodb", **client_kwargs)
            self._table = self._dynamodb.Table(self.table_name)
            
            # Check if table exists and create if needed
            if self.auto_create_table:
                try:
                    self._table.load()
                except ClientError as e:
                    if e.response["Error"]["Code"] == "ResourceNotFoundException":
                        self._create_table()
                    else:
                        raise RuntimeError(f"Failed to access DynamoDB table: {e}") from e
                        
        return self._table
    
    def _create_table(self) -> None:
        """Create DynamoDB table if it doesn't exist."""
        try:
            table = self._dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {"AttributeName": "key", "KeyType": "HASH"},  # Partition key
                ],
                AttributeDefinitions=[
                    {"AttributeName": "key", "AttributeType": "S"},
                ],
                BillingMode="PROVISIONED",
                ProvisionedThroughput={
                    "ReadCapacityUnits": self.read_capacity_units,
                    "WriteCapacityUnits": self.write_capacity_units,
                },
            )
            
            # Wait for table to be created
            table.wait_until_exists()
            self._table = table
            
        except Exception as e:
            raise RuntimeError(f"Failed to create DynamoDB table: {e}") from e
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        table = self._get_table()
        
        try:
            # Convert data to JSON string for storage
            json_data = json.dumps(data, default=str, ensure_ascii=False)
            timestamp = int(time.time())
            
            table.put_item(
                Item={
                    "key": key,
                    "data": json_data,
                    "updated_at": timestamp,
                    "created_at": timestamp,
                }
            )
            
        except Exception as e:
            raise RuntimeError(f"Failed to save data to DynamoDB: {e}") from e
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        table = self._get_table()
        
        try:
            response = table.get_item(Key={"key": key})
            
            if "Item" in response:
                item = response["Item"]
                if "data" in item:
                    try:
                        return json.loads(item["data"])
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Invalid JSON data for key '{key}': {e}") from e
            return None
            
        except Exception as e:
            raise RuntimeError(f"Failed to load data from DynamoDB: {e}") from e
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        table = self._get_table()
        
        try:
            response = table.delete_item(
                Key={"key": key},
                ReturnValues="ALL_OLD"
            )
            
            # Return True if item was actually deleted
            return "Attributes" in response
            
        except Exception as e:
            raise RuntimeError(f"Failed to delete data from DynamoDB: {e}") from e
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        table = self._get_table()
        
        try:
            from boto3.dynamodb.conditions import Attr

            keys = []
            scan_kwargs: Dict[str, Any] = {
                "ProjectionExpression": "#k",
                "ExpressionAttributeNames": {"#k": "key"},
            }
            
            if prefix:
                scan_kwargs["FilterExpression"] = Attr("key").begins_with(prefix)
            
            # Scan table (note: can be expensive for large tables)
            response = table.scan(**scan_kwargs)
            keys.extend([item["key"] for item in response["Items"]])
            
            # Handle pagination
            while "LastEvaluatedKey" in response:
                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
                response = table.scan(**scan_kwargs)
                keys.extend([item["key"] for item in response["Items"]])
            
            return sorted(keys)
            
        except Exception as e:
            raise RuntimeError(f"Failed to list keys from DynamoDB: {e}") from e
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        table = self._get_table()
        
        try:
            response = table.get_item(
                Key={"key": key},
                ProjectionExpression="#k",
                ExpressionAttributeNames={"#k": "key"}
            )
            
            return "Item" in response
            
        except Exception as e:
            raise RuntimeError(f"Failed to check key existence in DynamoDB: {e}") from e
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        table = self._get_table()
        
        try:
            # First scan to get all keys
            scan_response = table.scan(ProjectionExpression="#k", ExpressionAttributeNames={"#k": "key"})
            items_to_delete = scan_response["Items"]
            
            # Handle pagination
            while "LastEvaluatedKey" in scan_response:
                scan_response = table.scan(
                    ProjectionExpression="#k",
                    ExpressionAttributeNames={"#k": "key"},
                    ExclusiveStartKey=scan_response["LastEvaluatedKey"]
                )
                items_to_delete.extend(scan_response["Items"])
            
            count = len(items_to_delete)
            
            # Delete items in batches (DynamoDB batch_writer handles batching)
            with table.batch_writer() as batch:
                for item in items_to_delete:
                    batch.delete_item(Key={"key": item["key"]})
            
            return count
            
        except Exception as e:
            raise RuntimeError(f"Failed to clear data from DynamoDB: {e}") from e
    
    def ping(self) -> bool:
        """Test connection to DynamoDB."""
        try:
            table = self._get_table()
            # Try to describe the table
            table.load()
            return True
        except Exception:
            return False
    
    def close(self) -> None:
        """Close DynamoDB resources."""
        # DynamoDB client connections are managed by boto3, no explicit close needed
        self._table = None
        self._dynamodb = None