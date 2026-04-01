"""
DynamoDB Storage Adapter for PraisonAI Agents.

Provides DynamoDB-based storage backend implementing StorageBackendProtocol.
Uses lazy imports for the boto3 dependency to avoid module-level import overhead.

Example:
    ```python
    from praisonaiagents.storage import DynamoDBStorageAdapter
    
    # Basic usage with defaults
    adapter = DynamoDBStorageAdapter()
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    
    # Custom DynamoDB configuration
    adapter = DynamoDBStorageAdapter(
        table_name="my-praisonai-storage",
        region_name="us-west-2",
        aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
        aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    )
    ```
"""

import json
import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class DynamoDBStorageAdapter:
    """
    DynamoDB-based storage backend implementing StorageBackendProtocol.
    
    Stores data as items in a DynamoDB table with efficient key-based access.
    Thread-safe with automatic table creation.
    """
    
    def __init__(
        self,
        table_name: str = "praisonai-storage",
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize DynamoDB storage adapter.
        
        Args:
            table_name: DynamoDB table name
            region_name: AWS region name (optional, uses AWS default)
            aws_access_key_id: AWS access key ID (optional, uses AWS credentials chain)
            aws_secret_access_key: AWS secret access key (optional, uses AWS credentials chain)
            aws_session_token: AWS session token (optional, for temporary credentials)
            endpoint_url: Custom endpoint URL (optional, for local DynamoDB)
            **kwargs: Additional boto3 session parameters
        """
        self.table_name = table_name
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token
        self.endpoint_url = endpoint_url
        self.session_kwargs = kwargs
        self._dynamodb = None
        self._table = None
        self._lock = threading.Lock()
    
    def _get_table(self):
        """Get DynamoDB table with lazy initialization."""
        if self._table is None:
            with self._lock:
                if self._table is None:
                    try:
                        import boto3
                        from botocore.exceptions import ClientError
                        self._boto3 = boto3
                        self._ClientError = ClientError
                    except ImportError:
                        raise ImportError(
                            "boto3 not installed. Install with: pip install praisonaiagents[dynamodb]"
                        )
                    
                    # Create session and DynamoDB resource
                    try:
                        session_config = {
                            'region_name': self.region_name,
                            'aws_access_key_id': self.aws_access_key_id,
                            'aws_secret_access_key': self.aws_secret_access_key,
                            'aws_session_token': self.aws_session_token,
                            **self.session_kwargs
                        }
                        
                        # Remove None values
                        session_config = {k: v for k, v in session_config.items() if v is not None}
                        
                        session = self._boto3.Session(**session_config)
                        
                        dynamodb_config = {}
                        if self.endpoint_url:
                            dynamodb_config['endpoint_url'] = self.endpoint_url
                        
                        self._dynamodb = session.resource('dynamodb', **dynamodb_config)
                        
                        # Ensure table exists
                        self._ensure_table()
                        
                        self._table = self._dynamodb.Table(self.table_name)
                        
                    except Exception as e:
                        self._dynamodb = None
                        self._table = None
                        raise ConnectionError(f"Failed to connect to DynamoDB: {e}")
        
        return self._table
    
    def _ensure_table(self):
        """Create DynamoDB table if it doesn't exist."""
        try:
            # Check if table exists
            table = self._dynamodb.Table(self.table_name)
            table.load()  # This will raise an exception if table doesn't exist
            logger.debug(f"DynamoDB table already exists: {self.table_name}")
            
        except self._ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Table doesn't exist, create it
                try:
                    table = self._dynamodb.create_table(
                        TableName=self.table_name,
                        KeySchema=[
                            {
                                'AttributeName': 'key',
                                'KeyType': 'HASH'  # Partition key
                            }
                        ],
                        AttributeDefinitions=[
                            {
                                'AttributeName': 'key',
                                'AttributeType': 'S'
                            }
                        ],
                        BillingMode='PAY_PER_REQUEST'  # On-demand pricing
                    )
                    
                    # Wait for table to be created
                    table.wait_until_exists()
                    logger.info(f"Created DynamoDB table: {self.table_name}")
                    
                except Exception as create_error:
                    logger.error(f"Failed to create DynamoDB table: {create_error}")
                    raise
            else:
                logger.error(f"Unexpected error checking DynamoDB table: {e}")
                raise
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """
        Save data to DynamoDB.
        
        Args:
            key: Unique identifier for the data
            data: Dictionary to save
            
        Raises:
            ConnectionError: If DynamoDB is unavailable
            ValueError: If data cannot be serialized
        """
        table = self._get_table()
        
        try:
            # Convert data to JSON string for storage
            json_data = json.dumps(data, default=str)
            
            item = {
                'key': key,
                'data': json_data
            }
            
            table.put_item(Item=item)
            logger.debug(f"Saved data to DynamoDB key: {key}")
            
        except Exception as e:
            logger.error(f"Failed to save data to DynamoDB key {key}: {e}")
            raise
    
    def load(self, key: str) -> Any:
        """
        Load data from DynamoDB.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            The stored data, or None if not found
            
        Raises:
            ConnectionError: If DynamoDB is unavailable
            ValueError: If stored data is invalid JSON
        """
        table = self._get_table()
        
        try:
            response = table.get_item(Key={'key': key})
            
            if 'Item' not in response:
                logger.debug(f"No data found for DynamoDB key: {key}")
                return None
            
            json_data = response['Item']['data']
            data = json.loads(json_data)
            logger.debug(f"Loaded data from DynamoDB key: {key}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to load data from DynamoDB key {key}: {e}")
            raise
    
    def delete(self, key: str) -> bool:
        """
        Delete data from DynamoDB.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ConnectionError: If DynamoDB is unavailable
        """
        table = self._get_table()
        
        try:
            # Use conditional delete to check if item existed
            response = table.delete_item(
                Key={'key': key},
                ReturnValues='ALL_OLD'
            )
            
            success = 'Attributes' in response
            if success:
                logger.debug(f"Deleted DynamoDB key: {key}")
            else:
                logger.debug(f"DynamoDB key not found for deletion: {key}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete DynamoDB key {key}: {e}")
            raise
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """
        List all keys, optionally filtered by prefix.
        
        Args:
            prefix: Optional prefix to filter keys
            
        Returns:
            List of matching keys
            
        Raises:
            ConnectionError: If DynamoDB is unavailable
        """
        table = self._get_table()
        
        try:
            keys = []
            
            # Scan the table to get all keys
            scan_kwargs = {
                'ProjectionExpression': '#key_attr',
                'ExpressionAttributeNames': {'#key_attr': 'key'}
            }
            
            # Add filter expression for prefix if provided
            if prefix:
                scan_kwargs['FilterExpression'] = 'begins_with(#key_attr, :prefix)'
                scan_kwargs['ExpressionAttributeValues'] = {':prefix': prefix}
            
            # Handle pagination
            response = table.scan(**scan_kwargs)
            keys.extend([item['key'] for item in response.get('Items', [])])
            
            while 'LastEvaluatedKey' in response:
                scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
                response = table.scan(**scan_kwargs)
                keys.extend([item['key'] for item in response.get('Items', [])])
            
            logger.debug(f"Found {len(keys)} keys matching prefix: {prefix}")
            return sorted(keys)
            
        except Exception as e:
            logger.error(f"Failed to list DynamoDB keys with prefix {prefix}: {e}")
            raise
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in DynamoDB.
        
        Args:
            key: Unique identifier to check
            
        Returns:
            True if exists, False otherwise
            
        Raises:
            ConnectionError: If DynamoDB is unavailable
        """
        table = self._get_table()
        
        try:
            response = table.get_item(
                Key={'key': key},
                ProjectionExpression='#key_attr',
                ExpressionAttributeNames={'#key_attr': 'key'}
            )
            
            exists = 'Item' in response
            logger.debug(f"DynamoDB key {'exists' if exists else 'does not exist'}: {key}")
            return exists
            
        except Exception as e:
            logger.error(f"Failed to check existence of DynamoDB key {key}: {e}")
            raise
    
    def close(self) -> None:
        """Close DynamoDB connections if open."""
        # boto3 resources don't need explicit closing, but we can clear references
        if self._dynamodb is not None:
            try:
                logger.debug("Cleared DynamoDB resource references")
            except Exception as e:
                logger.warning(f"Error clearing DynamoDB references: {e}")
            finally:
                self._dynamodb = None
                self._table = None


__all__ = ["DynamoDBStorageAdapter"]