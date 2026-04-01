"""
DynamoDB Storage Adapter for PraisonAI Agents.

Provides DynamoDBStorageAdapter implementing StorageBackendProtocol:
- Serverless NoSQL storage with AWS DynamoDB
- Auto-scaling and pay-per-use pricing
- Global secondary indexes for efficient queries  
- Automatic table creation with on-demand billing
- Thread-safe operations

Architecture:
- Uses lazy imports (boto3 package is optional)
- Implements StorageBackendProtocol
- Zero performance impact when not used
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class DynamoDBStorageAdapter:
    """
    DynamoDB-based storage adapter implementing StorageBackendProtocol.
    
    Uses AWS DynamoDB for serverless NoSQL storage with automatic scaling.
    Requires the `boto3` package (optional dependency).
    
    Features:
    - Serverless auto-scaling with on-demand billing
    - Global secondary indexes for efficient prefix queries
    - Automatic table creation with proper configuration
    - Strong consistency reads
    - Thread-safe operations
    - Built-in retry logic for throttling
    
    Example:
        ```python
        from praisonaiagents.storage import DynamoDBStorageAdapter
        
        adapter = DynamoDBStorageAdapter(
            table_name="praison-storage",
            region_name="us-east-1"
        )
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """
    
    def __init__(
        self,
        table_name: str = "praison-storage",
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,  # For local DynamoDB
        billing_mode: str = "PAY_PER_REQUEST",
        auto_create: bool = True,
        consistent_read: bool = True,
    ):
        """
        Initialize the DynamoDB storage adapter.
        
        Args:
            table_name: DynamoDB table name
            region_name: AWS region name
            aws_access_key_id: AWS access key (optional, uses default credentials)
            aws_secret_access_key: AWS secret key (optional, uses default credentials)
            endpoint_url: Custom endpoint URL (for local DynamoDB)
            billing_mode: Billing mode ("PAY_PER_REQUEST" or "PROVISIONED")
            auto_create: Create table if it doesn't exist
            consistent_read: Use strongly consistent reads
        """
        self.table_name = table_name
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.endpoint_url = endpoint_url
        self.billing_mode = billing_mode
        self.auto_create = auto_create
        self.consistent_read = consistent_read
        self._dynamodb = None
        self._table = None
        self._lock = threading.Lock()
    
    def _get_dynamodb(self):
        """Lazy initialize DynamoDB client."""
        if self._dynamodb is None:
            with self._lock:
                if self._dynamodb is None:  # Double-check pattern
                    try:
                        import boto3
                        from botocore.exceptions import NoCredentialsError, ClientError
                    except ImportError:
                        raise ImportError(
                            "DynamoDB storage adapter requires the 'boto3' package. "
                            "Install with: pip install praisonaiagents[dynamodb]"
                        )
                    
                    session_kwargs = {
                        'region_name': self.region_name,
                    }
                    
                    if self.aws_access_key_id and self.aws_secret_access_key:
                        session_kwargs.update({
                            'aws_access_key_id': self.aws_access_key_id,
                            'aws_secret_access_key': self.aws_secret_access_key,
                        })
                    
                    try:
                        session = boto3.Session(**session_kwargs)
                        
                        resource_kwargs = {}
                        if self.endpoint_url:
                            resource_kwargs['endpoint_url'] = self.endpoint_url
                            
                        self._dynamodb = session.resource('dynamodb', **resource_kwargs)
                        
                        # Test connection by listing tables
                        list(self._dynamodb.tables.limit(1))
                        logger.info(f"DynamoDB connection established: {self.region_name}")
                        
                        if self.auto_create:
                            self._create_table()
                            
                    except NoCredentialsError:
                        raise ValueError(
                            "AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY "
                            "environment variables or provide them explicitly."
                        )
                    except Exception as e:
                        logger.error(f"Failed to connect to DynamoDB: {e}")
                        raise
        
        return self._dynamodb
    
    def _get_table(self):
        """Get the DynamoDB table resource."""
        if self._table is None:
            dynamodb = self._get_dynamodb()
            self._table = dynamodb.Table(self.table_name)
        return self._table
    
    def _create_table(self):
        """Create DynamoDB table with proper configuration."""
        try:
            dynamodb = self._get_dynamodb()
            
            # Check if table already exists
            try:
                table = dynamodb.Table(self.table_name)
                table.wait_until_exists()
                logger.debug(f"DynamoDB table already exists: {self.table_name}")
                return
            except Exception:
                # Table doesn't exist, create it
                pass
            
            table_config = {
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
                        'AttributeType': 'S'
                    },
                    {
                        'AttributeName': 'key_prefix',
                        'AttributeType': 'S'
                    }
                ],
                'BillingMode': self.billing_mode,
            }
            
            # Add Global Secondary Index for prefix queries
            table_config['GlobalSecondaryIndexes'] = [
                {
                    'IndexName': 'KeyPrefixIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'key_prefix',
                            'KeyType': 'HASH'
                        },
                        {
                            'AttributeName': 'key',
                            'KeyType': 'RANGE'
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'KEYS_ONLY'
                    }
                }
            ]
            
            if self.billing_mode == 'PAY_PER_REQUEST':
                # Add billing mode for GSI
                table_config['GlobalSecondaryIndexes'][0]['BillingMode'] = 'PAY_PER_REQUEST'
            else:
                # Add provisioned throughput for GSI
                table_config['ProvisionedThroughput'] = {
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
                table_config['GlobalSecondaryIndexes'][0]['ProvisionedThroughput'] = {
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            
            table = dynamodb.create_table(**table_config)
            table.wait_until_exists()
            
            logger.info(f"Created DynamoDB table: {self.table_name}")
            
        except Exception as e:
            logger.error(f"Failed to create DynamoDB table: {e}")
            raise
    
    def _get_key_prefix(self, key: str, prefix_length: int = 3) -> str:
        """Generate key prefix for GSI queries."""
        return key[:prefix_length] if len(key) >= prefix_length else key
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        try:
            table = self._get_table()
            
            # Store as JSON string for compatibility
            json_data = json.dumps(data, default=str, ensure_ascii=False)
            current_time = int(time.time())
            
            # Store with key prefix for efficient prefix queries
            item = {
                'key': key,
                'key_prefix': self._get_key_prefix(key),
                'data': json_data,
                'created_at': current_time,
                'updated_at': current_time,
            }
            
            table.put_item(Item=item)
            logger.debug(f"Saved data to DynamoDB key: {key}")
            
        except Exception as e:
            logger.error(f"Failed to save data to DynamoDB key '{key}': {e}")
            raise
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        try:
            table = self._get_table()
            
            response = table.get_item(
                Key={'key': key},
                ConsistentRead=self.consistent_read
            )
            
            if 'Item' in response:
                json_data = response['Item']['data']
                try:
                    data = json.loads(json_data)
                    logger.debug(f"Loaded data from DynamoDB key: {key}")
                    return data
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON data for key '{key}': {e}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to load data from DynamoDB key '{key}': {e}")
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
            logger.error(f"Failed to delete DynamoDB key '{key}': {e}")
            return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        try:
            table = self._get_table()
            keys = []
            
            if prefix:
                # Use GSI for efficient prefix queries
                key_prefix = self._get_key_prefix(prefix)
                
                response = table.query(
                    IndexName='KeyPrefixIndex',
                    KeyConditionExpression='key_prefix = :prefix AND begins_with(#key, :full_prefix)',
                    ExpressionAttributeNames={'#key': 'key'},
                    ExpressionAttributeValues={
                        ':prefix': key_prefix,
                        ':full_prefix': prefix
                    },
                    ProjectionExpression='#key'
                )
                
                keys = [item['key'] for item in response['Items']]
                
                # Handle pagination
                while 'LastEvaluatedKey' in response:
                    response = table.query(
                        IndexName='KeyPrefixIndex',
                        KeyConditionExpression='key_prefix = :prefix AND begins_with(#key, :full_prefix)',
                        ExpressionAttributeNames={'#key': 'key'},
                        ExpressionAttributeValues={
                            ':prefix': key_prefix,
                            ':full_prefix': prefix
                        },
                        ProjectionExpression='#key',
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    keys.extend([item['key'] for item in response['Items']])
                    
            else:
                # Scan all items (expensive operation)
                response = table.scan(ProjectionExpression='#key', ExpressionAttributeNames={'#key': 'key'})
                keys = [item['key'] for item in response['Items']]
                
                # Handle pagination
                while 'LastEvaluatedKey' in response:
                    response = table.scan(
                        ProjectionExpression='#key',
                        ExpressionAttributeNames={'#key': 'key'},
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    keys.extend([item['key'] for item in response['Items']])
            
            keys.sort()
            logger.debug(f"Listed {len(keys)} DynamoDB keys with prefix: '{prefix}'")
            return keys
        except Exception as e:
            logger.error(f"Failed to list DynamoDB keys with prefix '{prefix}': {e}")
            return []
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        try:
            table = self._get_table()
            
            response = table.get_item(
                Key={'key': key},
                ProjectionExpression='#key',
                ExpressionAttributeNames={'#key': 'key'},
                ConsistentRead=self.consistent_read
            )
            
            return 'Item' in response
        except Exception as e:
            logger.error(f"Failed to check if DynamoDB key '{key}' exists: {e}")
            return False
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        try:
            table = self._get_table()
            
            # First, scan to get all keys
            response = table.scan(ProjectionExpression='#key', ExpressionAttributeNames={'#key': 'key'})
            items = response['Items']
            
            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(
                    ProjectionExpression='#key',
                    ExpressionAttributeNames={'#key': 'key'},
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response['Items'])
            
            # Batch delete items
            deleted_count = 0
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={'key': item['key']})
                    deleted_count += 1
            
            logger.info(f"Cleared {deleted_count} DynamoDB items from table '{self.table_name}'")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to clear DynamoDB table: {e}")
            return 0
    
    def count(self) -> int:
        """Get total number of stored items."""
        try:
            table = self._get_table()
            
            response = table.scan(Select='COUNT')
            count = response['Count']
            
            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(
                    Select='COUNT',
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                count += response['Count']
            
            return count
        except Exception as e:
            logger.error(f"Failed to count DynamoDB items: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get table statistics."""
        try:
            table = self._get_table()
            
            # Reload table to get latest statistics
            table.reload()
            
            return {
                "table_name": table.table_name,
                "table_status": table.table_status,
                "item_count": table.item_count,
                "table_size_bytes": table.table_size_bytes,
                "billing_mode": table.billing_mode_summary,
                "creation_date": table.creation_date_time.isoformat() if table.creation_date_time else None,
            }
        except Exception as e:
            logger.error(f"Failed to get DynamoDB table stats: {e}")
            return {}
    
    def close(self) -> None:
        """Close the DynamoDB connection (boto3 handles connection pooling)."""
        # boto3 handles connection pooling automatically
        self._dynamodb = None
        self._table = None
        logger.debug("DynamoDB adapter closed")


__all__ = ['DynamoDBStorageAdapter']