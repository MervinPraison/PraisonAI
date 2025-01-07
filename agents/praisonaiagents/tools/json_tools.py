"""Tools for working with JSON files.

Usage:
from praisonaiagents.tools import json_tools
data = json_tools.read_json("data.json")

or
from praisonaiagents.tools import read_json, write_json, merge_json
data = read_json("data.json")
"""

import logging
from typing import List, Dict, Union, Optional, Any, Tuple
from importlib import util
import json
from datetime import datetime

class JSONTools:
    """Tools for working with JSON files."""
    
    def __init__(self):
        """Initialize JSONTools."""
        pass

    def read_json(
        self,
        filepath: str,
        encoding: str = 'utf-8',
        validate_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Read a JSON file with optional schema validation.
        
        Args:
            filepath: Path to JSON file
            encoding: File encoding
            validate_schema: Optional JSON schema for validation
            
        Returns:
            Dict with JSON data
        """
        try:
            # Read JSON file
            with open(filepath, 'r', encoding=encoding) as f:
                data = json.load(f)
            
            # Validate against schema if provided
            if validate_schema:
                if util.find_spec('jsonschema') is None:
                    error_msg = "jsonschema package is not available. Please install it using: pip install jsonschema"
                    logging.error(error_msg)
                    return {"error": error_msg}
                import jsonschema
                try:
                    jsonschema.validate(instance=data, schema=validate_schema)
                except jsonschema.exceptions.ValidationError as e:
                    error_msg = f"JSON validation failed: {str(e)}"
                    logging.error(error_msg)
                    return {"error": error_msg}
            
            return data
            
        except Exception as e:
            error_msg = f"Error reading JSON file {filepath}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def write_json(
        self,
        data: Union[Dict[str, Any], List[Any]],
        filepath: str,
        encoding: str = 'utf-8',
        indent: int = 2,
        sort_keys: bool = False,
        ensure_ascii: bool = False
    ) -> bool:
        """Write data to a JSON file.
        
        Args:
            data: Data to write
            filepath: Output file path
            encoding: File encoding
            indent: Number of spaces for indentation
            sort_keys: Sort dictionary keys
            ensure_ascii: Escape non-ASCII characters
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'w', encoding=encoding) as f:
                json.dump(
                    data,
                    f,
                    indent=indent,
                    sort_keys=sort_keys,
                    ensure_ascii=ensure_ascii
                )
            return True
        except Exception as e:
            error_msg = f"Error writing JSON file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def merge_json(
        self,
        files: List[str],
        output_file: str,
        merge_arrays: bool = True,
        overwrite_duplicates: bool = True
    ) -> bool:
        """Merge multiple JSON files.
        
        Args:
            files: List of JSON files to merge
            output_file: Output file path
            merge_arrays: Merge arrays instead of overwriting
            overwrite_duplicates: Overwrite duplicate keys
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if len(files) < 2:
                raise ValueError("At least two files are required for merging")
            
            # Read first file
            result = self.read_json(files[0])
            
            # Merge with remaining files
            for file in files[1:]:
                data = self.read_json(file)
                result = self._deep_merge(
                    result,
                    data,
                    merge_arrays=merge_arrays,
                    overwrite_duplicates=overwrite_duplicates
                )
            
            # Write merged result
            return self.write_json(result, output_file)
        except Exception as e:
            error_msg = f"Error merging JSON files: {str(e)}"
            logging.error(error_msg)
            return False

    def _deep_merge(
        self,
        dict1: Dict[str, Any],
        dict2: Dict[str, Any],
        merge_arrays: bool = True,
        overwrite_duplicates: bool = True
    ) -> Dict[str, Any]:
        """Deep merge two dictionaries.
        
        Args:
            dict1: First dictionary
            dict2: Second dictionary
            merge_arrays: Merge arrays instead of overwriting
            overwrite_duplicates: Overwrite duplicate keys
            
        Returns:
            Merged dictionary
        """
        result = dict1.copy()
        
        for key, value in dict2.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self._deep_merge(
                        result[key],
                        value,
                        merge_arrays=merge_arrays,
                        overwrite_duplicates=overwrite_duplicates
                    )
                elif isinstance(result[key], list) and isinstance(value, list):
                    if merge_arrays:
                        result[key].extend(value)
                    elif overwrite_duplicates:
                        result[key] = value
                elif overwrite_duplicates:
                    result[key] = value
            else:
                result[key] = value
        
        return result

    def validate_json(
        self,
        data: Union[Dict[str, Any], str],
        schema: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate JSON data against a schema.
        
        Args:
            data: JSON data or filepath
            schema: JSON schema for validation
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if util.find_spec('jsonschema') is None:
                error_msg = "jsonschema package is not available. Please install it using: pip install jsonschema"
                logging.error(error_msg)
                return False, error_msg
            import jsonschema

            # Load data if filepath provided
            if isinstance(data, str):
                with open(data, 'r') as f:
                    data = json.load(f)
            
            jsonschema.validate(instance=data, schema=schema)
            return True, None
            
        except jsonschema.exceptions.ValidationError as e:
            error_msg = f"JSON validation failed: {str(e)}"
            logging.error(error_msg)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Error validating JSON: {str(e)}"
            logging.error(error_msg)
            return False, error_msg

    def analyze_json(
        self,
        data: Union[Dict[str, Any], str],
        max_depth: int = 10
    ) -> Dict[str, Any]:
        """Analyze JSON data structure.
        
        Args:
            data: JSON data or filepath
            max_depth: Maximum depth to analyze
            
        Returns:
            Dict with analysis results
        """
        try:
            # Load data if filepath provided
            if isinstance(data, str):
                data = self.read_json(data)
            
            def analyze_value(value: Any, depth: int = 0) -> Dict[str, Any]:
                if depth >= max_depth:
                    return {'type': 'max_depth_reached'}
                
                result = {'type': type(value).__name__}
                
                if isinstance(value, dict):
                    result['size'] = len(value)
                    result['keys'] = list(value.keys())
                    if depth < max_depth - 1:
                        result['children'] = {
                            k: analyze_value(v, depth + 1)
                            for k, v in value.items()
                        }
                
                elif isinstance(value, list):
                    result['length'] = len(value)
                    if value:
                        result['element_types'] = list(set(
                            type(x).__name__ for x in value
                        ))
                        if depth < max_depth - 1:
                            result['sample_elements'] = [
                                analyze_value(x, depth + 1)
                                for x in value[:5]
                            ]
                
                elif isinstance(value, (int, float)):
                    result.update({
                        'value': value,
                        'is_integer': isinstance(value, int)
                    })
                
                elif isinstance(value, str):
                    result.update({
                        'length': len(value),
                        'sample': value[:100] if len(value) > 100 else value
                    })
                
                return result
            
            return {
                'analysis_time': datetime.now().isoformat(),
                'structure': analyze_value(data)
            }
        except Exception as e:
            error_msg = f"Error analyzing JSON: {str(e)}"
            logging.error(error_msg)
            return {}

    def transform_json(
        self,
        data: Union[Dict[str, Any], str],
        transformations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Transform JSON data using a list of operations.
        
        Args:
            data: JSON data or filepath
            transformations: List of transformation operations
            
        Returns:
            Transformed JSON data
        """
        try:
            # Load data if filepath provided
            if isinstance(data, str):
                data = self.read_json(data)
            
            result = data.copy()
            
            for transform in transformations:
                op = transform.get('operation')
                path = transform.get('path', '').split('.')
                value = transform.get('value')
                
                if op == 'set':
                    self._set_value(result, path, value)
                elif op == 'delete':
                    self._delete_value(result, path)
                elif op == 'rename':
                    old_path = path
                    new_path = value.split('.')
                    self._rename_key(result, old_path, new_path)
                elif op == 'move':
                    old_path = path
                    new_path = value.split('.')
                    self._move_value(result, old_path, new_path)
            
            return result
        except Exception as e:
            error_msg = f"Error transforming JSON: {str(e)}"
            logging.error(error_msg)
            return data

    def _set_value(self, data: Dict[str, Any], path: List[str], value: Any):
        """Set a value at the specified path."""
        current = data
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def _delete_value(self, data: Dict[str, Any], path: List[str]):
        """Delete a value at the specified path."""
        current = data
        for key in path[:-1]:
            if key not in current:
                return
            current = current[key]
        if path[-1] in current:
            del current[path[-1]]

    def _rename_key(
        self,
        data: Dict[str, Any],
        old_path: List[str],
        new_path: List[str]
    ):
        """Rename a key at the specified path."""
        value = self._get_value(data, old_path)
        if value is not None:
            self._delete_value(data, old_path)
            self._set_value(data, new_path, value)

    def _move_value(
        self,
        data: Dict[str, Any],
        old_path: List[str],
        new_path: List[str]
    ):
        """Move a value from one path to another."""
        self._rename_key(data, old_path, new_path)

    def _get_value(
        self,
        data: Dict[str, Any],
        path: List[str]
    ) -> Optional[Any]:
        """Get a value at the specified path."""
        current = data
        for key in path:
            if key not in current:
                return None
            current = current[key]
        return current

# Create instance for direct function access
_json_tools = JSONTools()
read_json = _json_tools.read_json
write_json = _json_tools.write_json
merge_json = _json_tools.merge_json
validate_json = _json_tools.validate_json
analyze_json = _json_tools.analyze_json
transform_json = _json_tools.transform_json

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("JSONTools Demonstration")
    print("==================================================\n")
    
    # Sample data
    data1 = {
        'id': 1,
        'name': 'Alice',
        'scores': [95, 87, 92],
        'details': {
            'age': 25,
            'city': 'New York'
        }
    }
    
    data2 = {
        'id': 2,
        'name': 'Bob',
        'scores': [88, 90, 85],
        'details': {
            'age': 30,
            'country': 'USA'
        }
    }
    
    # 1. Write JSON files
    print("1. Writing JSON Files")
    print("------------------------------")
    success = write_json(data1, 'test1.json')
    print(f"First file written: {success}")
    success = write_json(data2, 'test2.json')
    print(f"Second file written: {success}")
    print()
    
    # 2. Read JSON file
    print("2. Reading JSON File")
    print("------------------------------")
    data = read_json('test1.json')
    print("Contents of test1.json:")
    print(json.dumps(data, indent=2))
    print()
    
    # 3. Merge JSON files
    print("3. Merging JSON Files")
    print("------------------------------")
    success = merge_json(['test1.json', 'test2.json'], 'merged.json')
    print(f"Files merged: {success}")
    if success:
        print("Merged contents:")
        print(json.dumps(read_json('merged.json'), indent=2))
    print()
    
    # 4. Validate JSON
    print("4. Validating JSON")
    print("------------------------------")
    schema = {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'name': {'type': 'string'},
            'scores': {
                'type': 'array',
                'items': {'type': 'number'}
            },
            'details': {
                'type': 'object',
                'properties': {
                    'age': {'type': 'integer'},
                    'city': {'type': 'string'}
                }
            }
        },
        'required': ['id', 'name']
    }
    
    is_valid, error = validate_json(data1, schema)
    print(f"Validation result: {is_valid}")
    if error:
        print(f"Validation error: {error}")
    print()
    
    # 5. Analyze JSON
    print("5. Analyzing JSON")
    print("------------------------------")
    analysis = analyze_json(data1)
    print("Analysis results:")
    print(json.dumps(analysis, indent=2))
    print()
    
    # 6. Transform JSON
    print("6. Transforming JSON")
    print("------------------------------")
    transformations = [
        {
            'operation': 'set',
            'path': 'details.status',
            'value': 'active'
        },
        {
            'operation': 'rename',
            'path': 'details.city',
            'value': 'details.location'
        }
    ]
    
    transformed = transform_json(data1, transformations)
    print("Transformed data:")
    print(json.dumps(transformed, indent=2))
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
