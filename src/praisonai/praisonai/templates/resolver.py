"""
Template URI Resolver

Parses and resolves template URIs to their source locations.
Supports: local paths, package refs, GitHub refs, HTTP URLs.
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class TemplateSource(Enum):
    """Supported template sources."""
    LOCAL = "local"
    PACKAGE = "package"
    GITHUB = "github"
    HTTP = "http"


@dataclass
class ResolvedTemplate:
    """Resolved template location."""
    source: TemplateSource
    path: str
    version: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    ref: Optional[str] = None
    url: Optional[str] = None
    
    @property
    def cache_key(self) -> str:
        """Generate a unique cache key for this template."""
        if self.source == TemplateSource.LOCAL:
            return f"local/{os.path.abspath(self.path)}"
        elif self.source == TemplateSource.PACKAGE:
            return f"package/{self.path}"
        elif self.source == TemplateSource.GITHUB:
            ref = self.ref or "main"
            return f"github/{self.owner}/{self.repo}/{self.path}@{ref}"
        elif self.source == TemplateSource.HTTP:
            return f"http/{self.url}"
        return f"unknown/{self.path}"
    
    @property
    def is_pinned(self) -> bool:
        """Check if this template reference is pinned (not 'latest')."""
        if self.source == TemplateSource.LOCAL:
            return True  # Local is always "pinned"
        if self.source == TemplateSource.PACKAGE:
            return True  # Package is always "pinned" to installed version
        if self.source == TemplateSource.GITHUB:
            # Pinned if ref is a commit hash (40 hex chars) or a version tag
            if self.ref and (
                re.match(r'^[a-f0-9]{40}$', self.ref) or
                re.match(r'^v?\d+\.\d+', self.ref)
            ):
                return True
            return False
        return False


class TemplateResolver:
    """
    Resolves template URIs to their source locations.
    
    Supported URI formats:
    - Local path: ./my-template, /absolute/path/template, ~/templates/my-template
    - Package ref: package:agent_recipes/transcript-generator
    - GitHub ref: github:owner/repo/template-name[@ref]
    - HTTP URL: https://example.com/template.yaml
    
    Legacy formats (also supported):
    - praison://local/./path
    - praison://package/name/template
    - praison://github/owner/repo/template@ref
    """
    
    # URI patterns
    GITHUB_PATTERN = re.compile(
        r'^(?:github:|praison://github/)([^/]+)/([^/]+)/([^@]+)(?:@(.+))?$'
    )
    PACKAGE_PATTERN = re.compile(
        r'^(?:package:|praison://package/)([^/]+)/(.+)$'
    )
    HTTP_PATTERN = re.compile(
        r'^(?:https?://|praison://https?/).+'
    )
    LOCAL_PATTERN = re.compile(
        r'^(?:praison://local/)?([.~]?/.+|/.+|[a-zA-Z]:\\.+)$'
    )
    
    @classmethod
    def resolve(cls, uri: str) -> ResolvedTemplate:
        """
        Resolve a template URI to its source location.
        
        Args:
            uri: Template URI string
            
        Returns:
            ResolvedTemplate with source details
            
        Raises:
            ValueError: If URI format is not recognized
        """
        uri = uri.strip()
        
        # Check GitHub pattern
        match = cls.GITHUB_PATTERN.match(uri)
        if match:
            owner, repo, path, ref = match.groups()
            return ResolvedTemplate(
                source=TemplateSource.GITHUB,
                path=path,
                owner=owner,
                repo=repo,
                ref=ref or "main"
            )
        
        # Check package pattern
        match = cls.PACKAGE_PATTERN.match(uri)
        if match:
            package, template = match.groups()
            return ResolvedTemplate(
                source=TemplateSource.PACKAGE,
                path=f"{package}/{template}"
            )
        
        # Check HTTP pattern
        if cls.HTTP_PATTERN.match(uri):
            # Extract actual URL
            url = uri
            if uri.startswith("praison://"):
                url = uri.replace("praison://", "")
            return ResolvedTemplate(
                source=TemplateSource.HTTP,
                path=url,
                url=url
            )
        
        # Check local pattern or assume local if nothing else matches
        if cls.LOCAL_PATTERN.match(uri) or os.path.exists(uri) or uri.startswith(("./", "../", "~/")):
            path = uri
            if uri.startswith("praison://local/"):
                path = uri.replace("praison://local/", "")
            # Expand user home
            path = os.path.expanduser(path)
            return ResolvedTemplate(
                source=TemplateSource.LOCAL,
                path=path
            )
        
        # Try as simple template name (assume package:agent_recipes/name)
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', uri):
            return ResolvedTemplate(
                source=TemplateSource.PACKAGE,
                path=f"agent_recipes/{uri}"
            )
        
        raise ValueError(
            f"Unrecognized template URI format: {uri}\n"
            "Supported formats:\n"
            "  - Local: ./path, /absolute/path, ~/path\n"
            "  - Package: package:agent_recipes/template-name\n"
            "  - GitHub: github:owner/repo/template[@ref]\n"
            "  - HTTP: https://example.com/template.yaml"
        )
    
    @classmethod
    def parse_version(cls, uri: str) -> Tuple[str, Optional[str]]:
        """
        Extract version/ref from a URI.
        
        Args:
            uri: Template URI string
            
        Returns:
            Tuple of (base_uri, version)
        """
        if "@" in uri and not uri.startswith("http"):
            parts = uri.rsplit("@", 1)
            return parts[0], parts[1]
        return uri, None
    
    @classmethod
    def build_github_uri(
        cls,
        owner: str,
        repo: str,
        template: str,
        ref: Optional[str] = None
    ) -> str:
        """Build a GitHub template URI."""
        uri = f"github:{owner}/{repo}/{template}"
        if ref:
            uri += f"@{ref}"
        return uri
    
    @classmethod
    def build_package_uri(cls, package: str, template: str) -> str:
        """Build a package template URI."""
        return f"package:{package}/{template}"
