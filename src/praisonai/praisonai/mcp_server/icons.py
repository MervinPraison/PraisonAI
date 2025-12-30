"""
MCP Icons and Rich Metadata

Implements icons and rich metadata support per MCP 2025-11-25 specification.

Features:
- Icon metadata for tools, resources, prompts, and server
- Support for SVG, PNG, and URL-based icons
- Icon validation and normalization
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class IconMetadata:
    """
    Icon metadata per MCP 2025-11-25.
    
    Icons can be:
    - URL to an image (SVG, PNG, etc.)
    - Data URI (base64 encoded)
    - Icon name from a standard icon set
    """
    url: Optional[str] = None
    data_uri: Optional[str] = None
    icon_name: Optional[str] = None
    alt_text: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP icon format."""
        if self.url:
            result = {"url": self.url}
        elif self.data_uri:
            result = {"url": self.data_uri}
        elif self.icon_name:
            result = {"name": self.icon_name}
        else:
            return {}
        
        if self.alt_text:
            result["alt"] = self.alt_text
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IconMetadata":
        """Create from dictionary."""
        url = data.get("url")
        data_uri = None
        
        if url and url.startswith("data:"):
            data_uri = url
            url = None
        
        return cls(
            url=url,
            data_uri=data_uri,
            icon_name=data.get("name"),
            alt_text=data.get("alt"),
        )
    
    @classmethod
    def from_url(cls, url: str, alt_text: Optional[str] = None) -> "IconMetadata":
        """Create from URL."""
        if url.startswith("data:"):
            return cls(data_uri=url, alt_text=alt_text)
        return cls(url=url, alt_text=alt_text)
    
    @classmethod
    def from_name(cls, name: str, alt_text: Optional[str] = None) -> "IconMetadata":
        """Create from icon name."""
        return cls(icon_name=name, alt_text=alt_text)
    
    def is_valid(self) -> bool:
        """Check if icon metadata is valid."""
        return bool(self.url or self.data_uri or self.icon_name)


def validate_icon_url(url: str) -> bool:
    """
    Validate an icon URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid
    """
    if not url:
        return False
    
    # Data URIs
    if url.startswith("data:"):
        # Basic data URI validation
        if not re.match(r'^data:image/[a-z]+;base64,', url):
            return False
        return True
    
    # HTTP(S) URLs
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False


def validate_icon_format(url: str) -> Optional[str]:
    """
    Get the format of an icon from its URL.
    
    Args:
        url: Icon URL
        
    Returns:
        Format string (svg, png, etc.) or None
    """
    if not url:
        return None
    
    # Data URI
    if url.startswith("data:"):
        match = re.match(r'^data:image/([a-z]+);', url)
        if match:
            return match.group(1)
        return None
    
    # URL extension
    path = urlparse(url).path.lower()
    for ext in ("svg", "png", "jpg", "jpeg", "gif", "webp", "ico"):
        if path.endswith(f".{ext}"):
            return ext
    
    return None


@dataclass
class RichMetadata:
    """
    Rich metadata for MCP entities.
    
    Extends basic metadata with icons and additional fields.
    """
    icon: Optional[IconMetadata] = None
    documentation_url: Optional[str] = None
    homepage_url: Optional[str] = None
    support_url: Optional[str] = None
    license: Optional[str] = None
    author: Optional[str] = None
    version: Optional[str] = None
    tags: Optional[list] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {}
        
        if self.icon and self.icon.is_valid():
            result["icon"] = self.icon.to_dict()
        
        if self.documentation_url:
            result["documentationUrl"] = self.documentation_url
        
        if self.homepage_url:
            result["homepageUrl"] = self.homepage_url
        
        if self.support_url:
            result["supportUrl"] = self.support_url
        
        if self.license:
            result["license"] = self.license
        
        if self.author:
            result["author"] = self.author
        
        if self.version:
            result["version"] = self.version
        
        if self.tags:
            result["tags"] = self.tags
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RichMetadata":
        """Create from dictionary."""
        icon = None
        if "icon" in data:
            icon = IconMetadata.from_dict(data["icon"])
        
        return cls(
            icon=icon,
            documentation_url=data.get("documentationUrl"),
            homepage_url=data.get("homepageUrl"),
            support_url=data.get("supportUrl"),
            license=data.get("license"),
            author=data.get("author"),
            version=data.get("version"),
            tags=data.get("tags"),
        )


def add_icon_to_schema(
    schema: Dict[str, Any],
    icon: IconMetadata,
) -> Dict[str, Any]:
    """
    Add icon metadata to an MCP schema.
    
    Args:
        schema: MCP tool/resource/prompt schema
        icon: Icon metadata
        
    Returns:
        Updated schema
    """
    if icon and icon.is_valid():
        schema["icon"] = icon.to_dict()
    return schema


def add_metadata_to_schema(
    schema: Dict[str, Any],
    metadata: RichMetadata,
) -> Dict[str, Any]:
    """
    Add rich metadata to an MCP schema.
    
    Args:
        schema: MCP schema
        metadata: Rich metadata
        
    Returns:
        Updated schema
    """
    meta_dict = metadata.to_dict()
    if meta_dict:
        schema["_meta"] = meta_dict
    return schema


# Standard icon names for common operations
STANDARD_ICONS = {
    "run": "play",
    "execute": "play",
    "search": "search",
    "read": "file-text",
    "write": "edit",
    "delete": "trash",
    "create": "plus",
    "update": "refresh",
    "list": "list",
    "get": "download",
    "send": "send",
    "config": "settings",
    "settings": "settings",
    "help": "help-circle",
    "info": "info",
    "warning": "alert-triangle",
    "error": "alert-circle",
    "success": "check-circle",
    "agent": "bot",
    "tool": "wrench",
    "resource": "database",
    "prompt": "message-square",
}


def get_standard_icon(operation: str) -> Optional[str]:
    """
    Get standard icon name for an operation.
    
    Args:
        operation: Operation name
        
    Returns:
        Icon name or None
    """
    # Check direct match
    if operation.lower() in STANDARD_ICONS:
        return STANDARD_ICONS[operation.lower()]
    
    # Check partial match
    for key, icon in STANDARD_ICONS.items():
        if key in operation.lower():
            return icon
    
    return None
