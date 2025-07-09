"""Base classes for file manipulation tools to reduce duplication.

This module provides base classes and common functionality for all file-based tools
(CSV, JSON, XML, YAML, Excel) to eliminate code duplication and ensure consistent
error handling and validation across all file operations.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar
from pathlib import Path
import json
from importlib import util

T = TypeVar('T')

class BaseFileToolError(Exception):
    """Base exception for file tool errors."""
    pass

class BaseFileTool:
    """Base class for all file-based tools (CSV, JSON, XML, YAML, Excel).
    
    Provides common functionality for:
    - Path validation and normalization
    - Safe file reading and writing with error handling
    - Logging setup
    - Common utility methods
    """
    
    def __init__(self):
        """Initialize base file tool with logger."""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @staticmethod
    def _validate_path(filepath: str) -> str:
        """
        Validate and normalize a file path to prevent path traversal attacks.
        
        Args:
            filepath: Path to validate
            
        Returns:
            str: Normalized absolute path
            
        Raises:
            ValueError: If path contains suspicious patterns
        """
        # Normalize the path
        normalized = os.path.normpath(filepath)
        absolute = os.path.abspath(normalized)
        
        # Check for suspicious patterns
        if '..' in filepath or filepath.startswith('~'):
            raise ValueError(f"Suspicious path pattern detected: {filepath}")
        
        return absolute
    
    def _check_module(self, module_name: str, install_name: Optional[str] = None) -> Optional[Any]:
        """
        Check if a module is available and provide installation instructions if not.
        
        Args:
            module_name: Name of the module to import
            install_name: Package name for pip install (if different from module_name)
            
        Returns:
            Imported module or None if not available
        """
        if util.find_spec(module_name) is None:
            package = install_name or module_name
            error_msg = f"{module_name} package is not available. Please install it using: pip install {package}"
            self.logger.error(error_msg)
            return None
        
        import importlib
        return importlib.import_module(module_name)
    
    def _safe_file_operation(
        self, 
        operation: Callable[[], T], 
        filepath: str,
        operation_type: str = "processing"
    ) -> Union[T, Dict[str, str]]:
        """
        Safely execute a file operation with consistent error handling.
        
        Args:
            operation: Function to execute
            filepath: Path to the file being operated on
            operation_type: Type of operation for error messages
            
        Returns:
            Result of the operation or error dict
        """
        try:
            return operation()
        except FileNotFoundError:
            error_msg = f"File not found: {filepath}"
            self.logger.error(error_msg)
            return {"error": error_msg}
        except PermissionError:
            error_msg = f"Permission denied accessing file {filepath}"
            self.logger.error(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Error {operation_type} file {filepath}: {str(e)}"
            self.logger.error(error_msg)
            return {"error": error_msg}
    
    def _read_file_with_encoding(
        self,
        filepath: str,
        encoding: str = 'utf-8',
        mode: str = 'r'
    ) -> Union[str, bytes, Dict[str, str]]:
        """
        Read file content with specified encoding.
        
        Args:
            filepath: Path to file
            encoding: File encoding
            mode: Read mode ('r' for text, 'rb' for binary)
            
        Returns:
            File content or error dict
        """
        validated_path = self._validate_path(filepath)
        
        def read_op():
            with open(validated_path, mode, encoding=encoding if 'b' not in mode else None) as f:
                return f.read()
        
        return self._safe_file_operation(read_op, filepath, "reading")
    
    def _write_file_with_encoding(
        self,
        filepath: str,
        content: Union[str, bytes],
        encoding: str = 'utf-8',
        mode: str = 'w'
    ) -> Union[bool, Dict[str, str]]:
        """
        Write content to file with specified encoding.
        
        Args:
            filepath: Path to file
            content: Content to write
            encoding: File encoding
            mode: Write mode ('w' for text, 'wb' for binary)
            
        Returns:
            True if successful, error dict otherwise
        """
        validated_path = self._validate_path(filepath)
        
        def write_op():
            # Create parent directories if they don't exist
            Path(validated_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(validated_path, mode, encoding=encoding if 'b' not in mode else None) as f:
                f.write(content)
            return True
        
        return self._safe_file_operation(write_op, filepath, "writing")
    
    def file_exists(self, filepath: str) -> bool:
        """Check if a file exists."""
        try:
            validated_path = self._validate_path(filepath)
            return os.path.exists(validated_path)
        except ValueError:
            return False


class BaseStructuredFileTool(BaseFileTool):
    """Base class for structured file formats (JSON, YAML, XML).
    
    Provides common functionality for files that represent structured data
    with defined schemas and serialization formats.
    """
    
    def _safe_parse(
        self,
        filepath: str,
        parse_func: Callable[[Any], T],
        encoding: str = 'utf-8',
        **parse_kwargs
    ) -> Union[T, Dict[str, str]]:
        """
        Safely parse a structured file.
        
        Args:
            filepath: Path to file
            parse_func: Function to parse file content
            encoding: File encoding
            **parse_kwargs: Additional arguments for parse function
            
        Returns:
            Parsed data or error dict
        """
        validated_path = self._validate_path(filepath)
        
        def parse_op():
            with open(validated_path, 'r', encoding=encoding) as f:
                return parse_func(f, **parse_kwargs)
        
        return self._safe_file_operation(parse_op, filepath, "parsing")
    
    def _safe_dump(
        self,
        filepath: str,
        data: Any,
        dump_func: Callable[[Any, Any], None],
        encoding: str = 'utf-8',
        **dump_kwargs
    ) -> Union[bool, Dict[str, str]]:
        """
        Safely dump data to a structured file.
        
        Args:
            filepath: Path to file
            data: Data to dump
            dump_func: Function to dump data
            encoding: File encoding
            **dump_kwargs: Additional arguments for dump function
            
        Returns:
            True if successful, error dict otherwise
        """
        validated_path = self._validate_path(filepath)
        
        def dump_op():
            # Create parent directories if they don't exist
            Path(validated_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(validated_path, 'w', encoding=encoding) as f:
                dump_func(data, f, **dump_kwargs)
            return True
        
        return self._safe_file_operation(dump_op, filepath, "writing")
    
    def validate_schema(
        self,
        data: Any,
        schema: Dict[str, Any],
        schema_type: str = "jsonschema"
    ) -> Union[bool, Dict[str, str]]:
        """
        Validate data against a schema.
        
        Args:
            data: Data to validate
            schema: Schema to validate against
            schema_type: Type of schema (jsonschema, xmlschema, etc.)
            
        Returns:
            True if valid, error dict otherwise
        """
        if schema_type == "jsonschema":
            jsonschema = self._check_module('jsonschema')
            if not jsonschema:
                return {"error": "jsonschema module not available"}
            
            try:
                jsonschema.validate(instance=data, schema=schema)
                return True
            except jsonschema.exceptions.ValidationError as e:
                error_msg = f"Validation failed: {str(e)}"
                self.logger.error(error_msg)
                return {"error": error_msg}
        
        return {"error": f"Unsupported schema type: {schema_type}"}


class BaseTabularFileTool(BaseFileTool):
    """Base class for tabular file formats (CSV, Excel).
    
    Provides common functionality for files that represent tabular data
    with rows and columns.
    """
    
    def _get_pandas(self) -> Optional[Any]:
        """Get pandas module, providing installation instructions if needed."""
        return self._check_module('pandas')
    
    def _dataframe_to_dict_list(self, df: 'pd.DataFrame') -> List[Dict[str, Any]]:
        """Convert pandas DataFrame to list of dictionaries."""
        return df.to_dict('records')
    
    def _dict_list_to_dataframe(self, data: List[Dict[str, Any]]) -> Optional['pd.DataFrame']:
        """Convert list of dictionaries to pandas DataFrame."""
        pd = self._get_pandas()
        if pd is None:
            return None
        return pd.DataFrame(data)
    
    def _clean_numeric_columns(self, df: 'pd.DataFrame', columns: Optional[List[str]] = None) -> 'pd.DataFrame':
        """Clean and convert numeric columns."""
        pd = self._get_pandas()
        if pd is None or df is None:
            return df
        
        if columns is None:
            # Try to infer numeric columns
            columns = df.select_dtypes(include=['object']).columns.tolist()
        
        for col in columns:
            if col in df.columns:
                # Try to convert to numeric, coercing errors to NaN
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df


# Convenience function to get install instructions
def get_install_instructions(tool_type: str) -> str:
    """Get installation instructions for required packages by tool type."""
    instructions = {
        'csv': 'pip install pandas',
        'excel': 'pip install pandas openpyxl xlsxwriter',
        'json': 'pip install jsonschema',  # For schema validation
        'yaml': 'pip install pyyaml',
        'xml': 'pip install lxml',
    }
    return instructions.get(tool_type.lower(), 'pip install pandas')