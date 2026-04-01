"""
DynamoDB Storage Adapter for PraisonAI Agents.

Provides AWS DynamoDB-based storage implementation following StorageBackendProtocol.
Uses lazy imports for the optional boto3 dependency.

Example:
    ```python
    from praisonaiagents.storage import DynamoDBStorageAdapter
    
    adapter = DynamoDBStorageAdapter(
        table_name="praisonai-storage",
        region_name="us-east-1"
    )
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    ```
"""

import json
import time
import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class DynamoDBStorageAdapter:
    """
    AWS DynamoDB-based storage adapter implementing StorageBackendProtocol.
    
    Uses AWS DynamoDB for serverless, scalable NoSQL data storage.
    Requires the `boto3` package (optional dependency).
    Thread-safe with automatic table creation.
    """
    
    def __init__(
        self,
        table_name: str = "praisonai-storage",
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        billing_mode: str = "PAY_PER_REQUEST",
        read_capacity_units: int = 5,
        write_capacity_units: int = 5,
    ):
        """
        Initialize the DynamoDB storage adapter.
        
        Args:
            table_name: DynamoDB table name
            region_name: AWS region
            aws_access_key_id: AWS access key (optional, uses default credential chain)
            aws_secret_access_key: AWS secret key (optional, uses default credential chain)
            aws_session_token: AWS session token (optional)
            endpoint_url: Custom endpoint URL (for local DynamoDB)
            billing_mode: Billing mode (PAY_PER_REQUEST or PROVISIONED)
            read_capacity_units: Read capacity units (if PROVISIONED)
            write_capacity_units: Write capacity units (if PROVISIONED)
        """
        self.table_name = table_name
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token
        self.endpoint_url = endpoint_url
        self.billing_mode = billing_mode
        self.read_capacity_units = read_capacity_units
        self.write_capacity_units = write_capacity_units
        self._dynamodb = None
        self._table = None
        self._lock = threading.Lock()
    
    def _get_table(self):
        """Lazy initialize DynamoDB table with auto-creation."""
        if self._table is None:
            with self._lock:
                if self._table is None:  # Double-check locking
                    try:
                        import boto3
                        from botocore.exceptions import ClientError
                    except ImportError:
                        raise ImportError(
                            "DynamoDB storage adapter requires the 'boto3' package. "
                            "Install with: pip install praisonaiagents[dynamodb]"
                        )
                    
                    # Create session with optional credentials
                    session_kwargs = {"region_name": self.region_name}
                    if self.aws_access_key_id:
                        session_kwargs["aws_access_key_id"] = self.aws_access_key_id
                    if self.aws_secret_access_key:
                        session_kwargs["aws_secret_access_key"] = self.aws_secret_access_key
                    if self.aws_session_token:
                        session_kwargs["aws_session_token"] = self.aws_session_token
                    
                    session = boto3.Session(**session_kwargs)
                    
                    # Create DynamoDB resource
                    dynamodb_kwargs = {}
                    if self.endpoint_url:
                        dynamodb_kwargs["endpoint_url"] = self.endpoint_url
                    
                    self._dynamodb = session.resource('dynamodb', **dynamodb_kwargs)
                    
                    try:
                        # Try to get existing table
                        self._table = self._dynamodb.Table(self.table_name)
                        self._table.load()  # Test if table exists
                        logger.info(f"Connected to existing DynamoDB table: {self.table_name}")
                    except ClientError as e:
                        if e.response['Error']['Code'] == 'ResourceNotFoundException':
                            # Table doesn't exist, create it
                            self._create_table()
                        else:
                            logger.error(f"Failed to connect to DynamoDB table: {e}")
                            raise
                    except Exception as e:
                        logger.error(f"Failed to connect to DynamoDB: {e}")
                        raise
        
        return self._table
    
    def _create_table(self) -> None:
        """Create DynamoDB table if it doesn't exist."""
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is required for DynamoDB operations")
        
        try:
            table_kwargs = {
                'TableName': self.table_name,
                'KeySchema': [
                    {
                        'AttributeName': 'key',
                        'KeyType': 'HASH'  # Partition key
                    }
                ],
                'AttributeDefinitions': [
                    {
                        'AttributeName': 'key',
                        'AttributeType': 'S'  # String
                    }
                ]
            }
            
            if self.billing_mode == "PAY_PER_REQUEST":
                table_kwargs['BillingMode'] = 'PAY_PER_REQUEST'
            else:
                table_kwargs['BillingMode'] = 'PROVISIONED'
                table_kwargs['ProvisionedThroughput'] = {
                    'ReadCapacityUnits': self.read_capacity_units,
                    'WriteCapacityUnits': self.write_capacity_units
                }
            
            self._table = self._dynamodb.create_table(**table_kwargs)
            
            # Wait for table to be created
            self._table.wait_until_exists()
            logger.info(f"Created DynamoDB table: {self.table_name}")
            
        except Exception as e:
            logger.error(f"Failed to create DynamoDB table: {e}")
            raise
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        try:
            table = self._get_table()
            
            # DynamoDB item
            item = {
                'key': key,
                'data': json.dumps(data, default=str),
                'updated_at': int(time.time()),
                'ttl': int(time.time()) + (365 * 24 * 60 * 60)  # 1 year TTL
            }
            
            table.put_item(Item=item)
            logger.debug(f"Saved data to DynamoDB key: {key}")
            
        except Exception as e:
            logger.error(f"Failed to save data to DynamoDB key {key}: {e}")
            raise
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        try:
            table = self._get_table()
            
            response = table.get_item(Key={'key': key})
            
            if 'Item' in response:
                item = response['Item']
                if 'data' in item:
                    try:
                        return json.loads(item['data'])
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to decode JSON for key {key}: {e}")
                        return None
            return None
            
        except Exception as e:
            logger.error(f"Failed to load data from DynamoDB key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        try:
            table = self._get_table()
            
            response = table.delete_item(
                Key={'key': key},
                ReturnValues='ALL_OLD'
            )
            
            deleted = 'Attributes' in response
            if deleted:
                logger.debug(f"Deleted DynamoDB key: {key}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete DynamoDB key {key}: {e}")
            return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        try:
            table = self._get_table()
            
            # Scan is used because we need to filter by key prefix
            # For better performance, consider using a GSI with begins_with
            scan_kwargs = {
                'ProjectionExpression': '#k',
                'ExpressionAttributeNames': {'#k': 'key'}
            }
            
            if prefix:
                scan_kwargs['FilterExpression'] = 'begins_with(#k, :prefix)'
                scan_kwargs['ExpressionAttributeValues'] = {':prefix': prefix}
            
            keys = []
            
            # Handle pagination
            while True:
                response = table.scan(**scan_kwargs)
                
                for item in response.get('Items', []):
                    keys.append(item['key'])
                
                # Check if there are more items to scan
                if 'LastEvaluatedKey' not in response:
                    break
                
                scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
            
            return sorted(keys)
            
        except Exception as e:
            logger.error(f"Failed to list DynamoDB keys: {e}")
            return []
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        try:
            table = self._get_table()
            
            response = table.get_item(
                Key={'key': key},
                ProjectionExpression='#k',
                ExpressionAttributeNames={'#k': 'key'}
            )
            
            return 'Item' in response
            
        except Exception as e:
            logger.error(f"Failed to check existence of DynamoDB key {key}: {e}")
            return False
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        try:
            table = self._get_table()
            
            # Get all keys first
            keys = self.list_keys()
            count = 0
            
            # Delete in batches (DynamoDB batch write limit is 25)
            batch_size = 25
            for i in range(0, len(keys), batch_size):
                batch = keys[i:i + batch_size]
                
                with table.batch_writer() as batch_writer:
                    for key in batch:
                        batch_writer.delete_item(Key={'key': key})
                        count += 1
            
            logger.info(f"Cleared {count} items from DynamoDB")
            return count
            
        except Exception as e:
            logger.error(f"Failed to clear DynamoDB data: {e}")
            return 0
    
    def batch_save(self, items: Dict[str, Dict[str, Any]]) -> None:
        """
        Save multiple items in batch for better performance.
        
        Args:
            items: Dictionary mapping keys to data
        """
        try:
            table = self._get_table()
            
            # Process in batches of 25 (DynamoDB limit)
            batch_size = 25
            item_list = list(items.items())
            
            for i in range(0, len(item_list), batch_size):
                batch = item_list[i:i + batch_size]
                
                with table.batch_writer() as batch_writer:
                    for key, data in batch:
                        item = {
                            'key': key,
                            'data': json.dumps(data, default=str),
                            'updated_at': int(time.time()),
                            'ttl': int(time.time()) + (365 * 24 * 60 * 60)  # 1 year TTL
                        }
                        batch_writer.put_item(Item=item)
            
            logger.debug(f"Batch saved {len(items)} items to DynamoDB")
            
        except Exception as e:
            logger.error(f"Failed to batch save to DynamoDB: {e}")
            raise
    
    def get_table_info(self) -> Dict[str, Any]:
        """Get table information and statistics."""
        try:
            table = self._get_table()
            
            return {
                'table_name': table.table_name,
                'table_status': table.table_status,
                'item_count': table.item_count,
                'table_size_bytes': table.table_size_bytes,
                'billing_mode': self.billing_mode,
                'region': self.region_name
            }
            
        except Exception as e:
            logger.error(f"Failed to get DynamoDB table info: {e}")
            return {}
    
    def close(self) -> None:
        """Close DynamoDB connection (no-op for boto3)."""
        # Boto3 handles connection management automatically
        self._dynamodb = None
        self._table = None
        logger.debug("DynamoDB adapter closed")


__all__ = ['DynamoDBStorageAdapter']