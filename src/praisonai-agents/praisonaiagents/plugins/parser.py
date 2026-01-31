"""
Plugin Header Parser for Single-File Plugins.

Parses WordPress-style docstring headers from Python plugin files.

Format:
    '''
    Plugin Name: My Plugin
    Description: What it does
    Version: 1.0.0
    Author: Your Name
    Hooks: before_tool, after_tool
    Dependencies: requests, aiohttp
    '''

This is the SIMPLEST possible plugin format - just a Python file
with a docstring header at the top.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any


class PluginParseError(Exception):
    """Error parsing plugin header."""
    pass


@dataclass
class PluginMetadata:
    """Metadata extracted from plugin header."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: Optional[str] = None
    hooks: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "hooks": self.hooks,
            "dependencies": self.dependencies,
            "path": self.path,
        }


def parse_plugin_header(content: str) -> Dict[str, Any]:
    """Parse WordPress-style plugin header from file content.
    
    Extracts metadata from the module docstring at the top of the file.
    
    Args:
        content: Python file content as string
        
    Returns:
        Dictionary with parsed metadata
        
    Raises:
        PluginParseError: If header is missing or invalid
        
    Example:
        >>> content = '''\"\"\"
        ... Plugin Name: Weather Tools
        ... Description: Get weather
        ... Version: 1.0.0
        ... \"\"\"
        ... '''
        >>> parse_plugin_header(content)
        {'name': 'Weather Tools', 'description': 'Get weather', 'version': '1.0.0'}
    """
    # Extract docstring - supports both triple-double and triple-single quotes
    docstring_pattern = r'^[\s]*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')'
    match = re.match(docstring_pattern, content, re.DOTALL)
    
    if not match:
        raise PluginParseError(
            "Plugin file must start with a docstring header. "
            "Example:\n"
            '"""\n'
            "Plugin Name: My Plugin\n"
            "Description: What it does\n"
            "Version: 1.0.0\n"
            '"""'
        )
    
    # Get the docstring content (from either quote style)
    docstring = match.group(1) or match.group(2)
    
    # Parse key: value pairs
    metadata = {}
    
    # Normalize field names (WordPress-style to Python-style)
    field_mapping = {
        "plugin name": "name",
        "plugin_name": "name",
        "description": "description",
        "version": "version",
        "author": "author",
        "hooks": "hooks",
        "dependencies": "dependencies",
        "deps": "dependencies",
    }
    
    for line in docstring.strip().split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue
        
        # Split on first colon only
        key, value = line.split(':', 1)
        key = key.strip().lower()
        value = value.strip()
        
        # Map to standard field name
        field_name = field_mapping.get(key)
        if field_name:
            # Handle list fields (comma-separated)
            if field_name in ("hooks", "dependencies"):
                if value:
                    metadata[field_name] = [v.strip() for v in value.split(',') if v.strip()]
                else:
                    metadata[field_name] = []
            else:
                metadata[field_name] = value
    
    # Validate required fields
    if "name" not in metadata:
        raise PluginParseError(
            "Plugin header must include 'Plugin Name' field. "
            "Example:\n"
            '"""\n'
            "Plugin Name: My Plugin\n"
            '"""'
        )
    
    return metadata


def parse_plugin_header_from_file(filepath: str) -> Dict[str, Any]:
    """Parse plugin header from a file path.
    
    Args:
        filepath: Path to the Python plugin file
        
    Returns:
        Dictionary with parsed metadata including 'path' field
        
    Raises:
        PluginParseError: If file cannot be read or header is invalid
        FileNotFoundError: If file does not exist
    """
    path = Path(filepath)
    
    if not path.exists():
        raise FileNotFoundError(f"Plugin file not found: {filepath}")
    
    if not path.suffix == '.py':
        raise PluginParseError(f"Plugin must be a Python file (.py): {filepath}")
    
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        raise PluginParseError(f"Cannot read plugin file: {e}")
    
    metadata = parse_plugin_header(content)
    metadata["path"] = str(path.resolve())
    
    return metadata


def create_plugin_metadata(data: Dict[str, Any]) -> PluginMetadata:
    """Create PluginMetadata from parsed dictionary.
    
    Args:
        data: Dictionary from parse_plugin_header()
        
    Returns:
        PluginMetadata instance
    """
    return PluginMetadata(
        name=data.get("name", "Unknown"),
        description=data.get("description", ""),
        version=data.get("version", "1.0.0"),
        author=data.get("author"),
        hooks=data.get("hooks", []),
        dependencies=data.get("dependencies", []),
        path=data.get("path"),
    )
