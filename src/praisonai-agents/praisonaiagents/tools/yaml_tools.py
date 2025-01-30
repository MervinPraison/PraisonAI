"""Tools for working with YAML files.

Usage:
from praisonaiagents.tools import yaml_tools
data = yaml_tools.read_yaml("config.yaml")

or
from praisonaiagents.tools import read_yaml, write_yaml, merge_yaml
data = read_yaml("config.yaml")
"""

import logging
from typing import List, Dict, Union, Optional, Any
from importlib import util
import os
from copy import deepcopy

class YAMLTools:
    """Tools for working with YAML files."""
    
    def __init__(self):
        """Initialize YAMLTools."""
        self._check_dependencies()
        
    def _check_dependencies(self):
        """Check if required packages are installed."""
        missing = []
        for package, module in [('pyyaml', 'yaml'), ('jsonschema', 'jsonschema')]:
            if util.find_spec(module) is None:
                missing.append(package)
        
        if missing:
            raise ImportError(
                f"Required packages not available. Please install: {', '.join(missing)}\n"
                f"Run: pip install {' '.join(missing)}"
            )

    def read_yaml(
        self,
        filepath: str,
        safe_load: bool = True,
        encoding: str = 'utf-8'
    ) -> Optional[Union[Dict[str, Any], List[Any]]]:
        """Read a YAML file."""
        try:
            if util.find_spec('yaml') is None:
                error_msg = "pyyaml package is not available. Please install it using: pip install pyyaml"
                logging.error(error_msg)
                return None

            # Import yaml only when needed
            import yaml
            
            with open(filepath, 'r', encoding=encoding) as f:
                if safe_load:
                    return yaml.safe_load(f)
                return yaml.load(f, Loader=yaml.FullLoader)
        except Exception as e:
            error_msg = f"Error reading YAML file {filepath}: {str(e)}"
            logging.error(error_msg)
            return None

    def write_yaml(
        self,
        data: Union[Dict[str, Any], List[Any]],
        filepath: str,
        default_flow_style: bool = False,
        encoding: str = 'utf-8',
        sort_keys: bool = False,
        allow_unicode: bool = True
    ) -> bool:
        """Write data to YAML file."""
        try:
            if util.find_spec('yaml') is None:
                error_msg = "pyyaml package is not available. Please install it using: pip install pyyaml"
                logging.error(error_msg)
                return False

            # Import yaml only when needed
            import yaml
            
            with open(filepath, 'w', encoding=encoding) as f:
                yaml.dump(
                    data,
                    f,
                    default_flow_style=default_flow_style,
                    sort_keys=sort_keys,
                    allow_unicode=allow_unicode
                )
            return True
        except Exception as e:
            error_msg = f"Error writing YAML file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def merge_yaml(
        self,
        files: List[str],
        output_file: Optional[str] = None,
        strategy: str = 'deep'
    ) -> Union[Dict[str, Any], List[Any], None]:
        """Merge multiple YAML files."""
        try:
            if util.find_spec('yaml') is None:
                error_msg = "pyyaml package is not available. Please install it using: pip install pyyaml"
                logging.error(error_msg)
                return None

            def deep_merge(source: dict, destination: dict) -> dict:
                """Deep merge two dictionaries."""
                for key, value in source.items():
                    if key in destination:
                        if isinstance(value, dict) and isinstance(destination[key], dict):
                            destination[key] = deep_merge(value, destination[key])
                        elif isinstance(value, list) and isinstance(destination[key], list):
                            destination[key].extend(value)
                        else:
                            destination[key] = value
                    else:
                        destination[key] = value
                return destination
            
            result = {}
            for file in files:
                data = self.read_yaml(file)
                if data is None:
                    continue
                
                if strategy == 'deep':
                    if isinstance(data, dict):
                        result = deep_merge(data, result)
                    elif isinstance(data, list):
                        if not result:
                            result = []
                        result.extend(data)
                else:  # shallow
                    if isinstance(data, dict):
                        result.update(data)
                    elif isinstance(data, list):
                        if not result:
                            result = []
                        result.extend(data)
            
            if output_file:
                self.write_yaml(result, output_file)
            
            return result
        except Exception as e:
            error_msg = f"Error merging YAML files: {str(e)}"
            logging.error(error_msg)
            return None

    def validate_yaml(
        self,
        data: Union[Dict[str, Any], List[Any], str],
        schema: Dict[str, Any]
    ) -> bool:
        """Validate YAML data against a schema."""
        try:
            if util.find_spec('jsonschema') is None:
                error_msg = "jsonschema package is not available. Please install it using: pip install jsonschema"
                logging.error(error_msg)
                return False

            # Import jsonschema only when needed
            from jsonschema import validate, ValidationError
            
            # Load data if file path
            if isinstance(data, str):
                data = self.read_yaml(data)
                if data is None:
                    return False
            
            try:
                validate(instance=data, schema=schema)
                return True
            except ValidationError as e:
                logging.error(f"YAML validation error: {str(e)}")
                return False
        except Exception as e:
            error_msg = f"Error validating YAML: {str(e)}"
            logging.error(error_msg)
            return False

    def analyze_yaml(
        self,
        data: Union[Dict[str, Any], List[Any], str]
    ) -> Optional[Dict[str, Any]]:
        """Analyze YAML data structure."""
        try:
            # Load data if file path
            if isinstance(data, str):
                data = self.read_yaml(data)
                if data is None:
                    return None
            
            def analyze_value(value: Any) -> Dict[str, Any]:
                """Analyze a single value."""
                result = {
                    'type': type(value).__name__,
                    'size': len(value) if hasattr(value, '__len__') else 1
                }
                
                if isinstance(value, dict):
                    result['keys'] = list(value.keys())
                    result['nested_types'] = {
                        k: type(v).__name__
                        for k, v in value.items()
                    }
                elif isinstance(value, list):
                    result['element_types'] = list(set(
                        type(x).__name__ for x in value
                    ))
                
                return result
            
            result = {
                'structure': analyze_value(data),
                'stats': {
                    'total_keys': sum(1 for _ in self._walk_dict(data))
                    if isinstance(data, dict) else len(data)
                }
            }
            
            return result
        except Exception as e:
            error_msg = f"Error analyzing YAML: {str(e)}"
            logging.error(error_msg)
            return None

    def _walk_dict(self, d: Dict[str, Any]) -> Any:
        """Walk through nested dictionary."""
        for k, v in d.items():
            yield k
            if isinstance(v, dict):
                yield from self._walk_dict(v)

    def transform_yaml(
        self,
        data: Union[Dict[str, Any], List[Any], str],
        operations: List[Dict[str, Any]]
    ) -> Optional[Union[Dict[str, Any], List[Any]]]:
        """Transform YAML data using specified operations."""
        try:
            # Load data if file path
            if isinstance(data, str):
                data = self.read_yaml(data)
                if data is None:
                    return None
            
            result = deepcopy(data)
            
            for op in operations:
                op_type = op.get('type')
                path = op.get('path', '')
                value = op.get('value')
                
                if not op_type:
                    continue
                
                # Split path into parts
                parts = [p for p in path.split('/') if p]
                
                # Get reference to target location
                target = result
                parent = None
                last_key = None
                
                for part in parts[:-1]:
                    if isinstance(target, dict):
                        if part not in target:
                            target[part] = {}
                        parent = target
                        target = target[part]
                        last_key = part
                    elif isinstance(target, list):
                        idx = int(part)
                        while len(target) <= idx:
                            target.append({})
                        parent = target
                        target = target[idx]
                        last_key = idx
                
                if parts:
                    last_part = parts[-1]
                    if isinstance(target, dict):
                        if op_type == 'set':
                            target[last_part] = value
                        elif op_type == 'delete':
                            target.pop(last_part, None)
                        elif op_type == 'append' and isinstance(target.get(last_part), list):
                            target[last_part].append(value)
                    elif isinstance(target, list):
                        idx = int(last_part)
                        if op_type == 'set':
                            while len(target) <= idx:
                                target.append(None)
                            target[idx] = value
                        elif op_type == 'delete' and idx < len(target):
                            del target[idx]
                        elif op_type == 'append':
                            target.append(value)
                else:
                    if op_type == 'set':
                        result = value
                    elif op_type == 'append' and isinstance(result, list):
                        result.append(value)
            
            return result
        except Exception as e:
            error_msg = f"Error transforming YAML: {str(e)}"
            logging.error(error_msg)
            return None

# Create instance for direct function access
_yaml_tools = YAMLTools()
read_yaml = _yaml_tools.read_yaml
write_yaml = _yaml_tools.write_yaml
merge_yaml = _yaml_tools.merge_yaml
validate_yaml = _yaml_tools.validate_yaml
analyze_yaml = _yaml_tools.analyze_yaml
transform_yaml = _yaml_tools.transform_yaml

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("YAMLTools Demonstration")
    print("==================================================\n")
    
    # Sample data
    data1 = {
        'server': {
            'host': 'localhost',
            'port': 8080,
            'debug': True
        },
        'database': {
            'url': 'postgresql://localhost:5432/db',
            'pool_size': 5
        }
    }
    
    data2 = {
        'server': {
            'workers': 4,
            'timeout': 30
        },
        'logging': {
            'level': 'INFO',
            'file': 'app.log'
        }
    }
    
    # 1. Write YAML files
    print("1. Writing YAML Files")
    print("------------------------------")
    success1 = write_yaml(data1, 'config1.yaml')
    success2 = write_yaml(data2, 'config2.yaml')
    print(f"First file written: {success1}")
    print(f"Second file written: {success2}")
    print()
    
    # 2. Read YAML file
    print("2. Reading YAML File")
    print("------------------------------")
    config = read_yaml('config1.yaml')
    print("YAML content:")
    print(config)
    print()
    
    # 3. Merge YAML files
    print("3. Merging YAML Files")
    print("------------------------------")
    merged = merge_yaml(['config1.yaml', 'config2.yaml'])
    print("Merged content:")
    print(merged)
    print()
    
    # 4. Analyze YAML
    print("4. Analyzing YAML")
    print("------------------------------")
    analysis = analyze_yaml(merged)
    print("Analysis results:")
    print(analysis)
    print()
    
    # 5. Transform YAML
    print("5. Transforming YAML")
    print("------------------------------")
    operations = [
        {
            'type': 'set',
            'path': 'server/host',
            'value': '0.0.0.0'
        },
        {
            'type': 'delete',
            'path': 'server/debug'
        },
        {
            'type': 'set',
            'path': 'logging/handlers',
            'value': ['console', 'file']
        }
    ]
    transformed = transform_yaml(merged, operations)
    print("Transformed content:")
    print(transformed)
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
    
    # Cleanup
    for file in ['config1.yaml', 'config2.yaml']:
        if os.path.exists(file):
            os.remove(file)
