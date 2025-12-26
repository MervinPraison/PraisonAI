"""
Template Registry

Handles fetching templates from remote sources (GitHub, HTTP).
All network operations are lazy and only performed when explicitly requested.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .resolver import ResolvedTemplate, TemplateResolver, TemplateSource
from .cache import TemplateCache, CachedTemplate


@dataclass
class TemplateInfo:
    """Information about a template."""
    name: str
    description: str
    version: str = "1.0.0"
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    requires: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    path: Optional[str] = None
    sha256: Optional[str] = None


class TemplateRegistry:
    """
    Registry for discovering and fetching templates.
    
    Supports:
    - GitHub repositories (via contents API or raw.githubusercontent.com)
    - HTTP URLs
    - Local package installations
    """
    
    GITHUB_API_BASE = "https://api.github.com"
    GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
    
    # Default recipes repository
    DEFAULT_OWNER = "MervinPraison"
    DEFAULT_REPO = "agent-recipes"
    
    def __init__(
        self,
        cache: Optional[TemplateCache] = None,
        github_token: Optional[str] = None,
        offline: bool = False
    ):
        """
        Initialize the registry.
        
        Args:
            cache: Template cache instance
            github_token: Optional GitHub token for API requests
            offline: If True, only use cached templates
        """
        self.cache = cache or TemplateCache()
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")
        self.offline = offline
        self._http_client = None
    
    @property
    def http_client(self):
        """Lazy-load HTTP client."""
        if self._http_client is None:
            try:
                import httpx
                self._http_client = httpx.Client(timeout=30.0)
            except ImportError:
                import urllib.request
                self._http_client = "urllib"
        return self._http_client
    
    def _make_request(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None
    ) -> bytes:
        """Make an HTTP request."""
        all_headers = headers or {}
        if self.github_token and "api.github.com" in url:
            all_headers["Authorization"] = f"token {self.github_token}"
        all_headers["User-Agent"] = "PraisonAI-Templates/1.0"
        
        if self.http_client == "urllib":
            import urllib.request
            req = urllib.request.Request(url, headers=all_headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()
        else:
            response = self.http_client.get(url, headers=all_headers)
            response.raise_for_status()
            return response.content
    
    def fetch_github_template(
        self,
        owner: str,
        repo: str,
        template_path: str,
        ref: str = "main"
    ) -> Path:
        """
        Fetch a template from GitHub.
        
        Args:
            owner: Repository owner
            repo: Repository name
            template_path: Path to template within repo
            ref: Git ref (branch, tag, or commit)
            
        Returns:
            Path to downloaded template directory
        """
        # Create temp directory for download
        temp_dir = Path(tempfile.mkdtemp(prefix="praison_template_"))
        
        # Fetch template files using GitHub API
        api_url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents/templates/{template_path}?ref={ref}"
        
        try:
            response = self._make_request(api_url)
            contents = json.loads(response)
            
            if isinstance(contents, list):
                # Directory listing
                for item in contents:
                    if item["type"] == "file":
                        file_content = self._fetch_github_file(item["download_url"])
                        file_path = temp_dir / item["name"]
                        file_path.write_bytes(file_content)
                    elif item["type"] == "dir":
                        # Recursively fetch subdirectory
                        subdir = temp_dir / item["name"]
                        subdir.mkdir(parents=True, exist_ok=True)
                        self._fetch_github_dir(
                            owner, repo, f"templates/{template_path}/{item['name']}", 
                            ref, subdir
                        )
            else:
                # Single file
                file_content = self._fetch_github_file(contents["download_url"])
                file_path = temp_dir / contents["name"]
                file_path.write_bytes(file_content)
                
        except Exception:
            # Fallback to raw.githubusercontent.com
            raw_url = f"{self.GITHUB_RAW_BASE}/{owner}/{repo}/{ref}/templates/{template_path}"
            self._fetch_raw_template(raw_url, temp_dir, template_path)
        
        return temp_dir
    
    def _fetch_github_file(self, url: str) -> bytes:
        """Fetch a single file from GitHub."""
        return self._make_request(url)
    
    def _fetch_github_dir(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        target_dir: Path
    ) -> None:
        """Recursively fetch a directory from GitHub."""
        api_url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={ref}"
        response = self._make_request(api_url)
        contents = json.loads(response)
        
        for item in contents:
            if item["type"] == "file":
                file_content = self._fetch_github_file(item["download_url"])
                file_path = target_dir / item["name"]
                file_path.write_bytes(file_content)
            elif item["type"] == "dir":
                subdir = target_dir / item["name"]
                subdir.mkdir(parents=True, exist_ok=True)
                self._fetch_github_dir(owner, repo, f"{path}/{item['name']}", ref, subdir)
    
    def _fetch_raw_template(
        self,
        base_url: str,
        target_dir: Path,
        template_name: str
    ) -> None:
        """Fetch template using raw URLs (fallback)."""
        # Try to fetch common template files
        files_to_try = [
            "TEMPLATE.yaml",
            "workflow.yaml", 
            "agents.yaml",
            "README.md"
        ]
        
        for filename in files_to_try:
            try:
                url = f"{base_url}/{filename}"
                content = self._make_request(url)
                (target_dir / filename).write_bytes(content)
            except Exception:
                continue
    
    def fetch_http_template(self, url: str) -> Path:
        """
        Fetch a template from an HTTP URL.
        
        Args:
            url: URL to template (YAML file or directory index)
            
        Returns:
            Path to downloaded template
        """
        temp_dir = Path(tempfile.mkdtemp(prefix="praison_template_"))
        
        content = self._make_request(url)
        
        # Determine filename from URL
        filename = url.split("/")[-1]
        if not filename.endswith((".yaml", ".yml")):
            filename = "TEMPLATE.yaml"
        
        (temp_dir / filename).write_bytes(content)
        
        return temp_dir
    
    def get_template(
        self,
        uri: str,
        offline: bool = False
    ) -> CachedTemplate:
        """
        Get a template by URI, fetching if necessary.
        
        Args:
            uri: Template URI
            offline: If True, only use cache
            
        Returns:
            CachedTemplate with path and metadata
            
        Raises:
            ValueError: If template not found
        """
        resolved = TemplateResolver.resolve(uri)
        use_offline = offline or self.offline
        
        # Check cache first
        cached = self.cache.get(resolved, offline=use_offline)
        if cached:
            return cached
        
        if use_offline:
            raise ValueError(
                f"Template not found in cache: {uri}\n"
                "Run without --offline to fetch from remote."
            )
        
        # Fetch based on source
        if resolved.source == TemplateSource.LOCAL:
            path = Path(resolved.path)
            if not path.exists():
                raise ValueError(f"Local template not found: {resolved.path}")
            return CachedTemplate(
                path=path,
                metadata=self.cache.put(resolved, path).metadata
            )
        
        elif resolved.source == TemplateSource.PACKAGE:
            # Try to find in installed package
            return self._get_package_template(resolved)
        
        elif resolved.source == TemplateSource.GITHUB:
            temp_dir = self.fetch_github_template(
                resolved.owner,
                resolved.repo,
                resolved.path,
                resolved.ref or "main"
            )
            # Calculate checksum
            sha256 = self._calculate_dir_checksum(temp_dir)
            return self.cache.put(resolved, temp_dir, sha256=sha256)
        
        elif resolved.source == TemplateSource.HTTP:
            temp_dir = self.fetch_http_template(resolved.url)
            sha256 = self._calculate_dir_checksum(temp_dir)
            return self.cache.put(resolved, temp_dir, sha256=sha256)
        
        raise ValueError(f"Unknown template source: {resolved.source}")
    
    def _get_package_template(self, resolved: ResolvedTemplate) -> CachedTemplate:
        """Get template from installed Python package."""
        parts = resolved.path.split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid package template path: {resolved.path}")
        
        package_name = parts[0]
        template_name = "/".join(parts[1:])
        
        try:
            # Try importlib.resources first (Python 3.9+)
            import importlib.resources as pkg_resources
            package = __import__(package_name)
            
            # Navigate to templates directory
            templates_path = Path(package.__file__).parent / "templates" / template_name
            if templates_path.exists():
                return CachedTemplate(
                    path=templates_path,
                    metadata=self.cache.put(resolved, templates_path).metadata
                )
        except (ImportError, AttributeError):
            pass
        
        # Try pkg_resources fallback
        try:
            import pkg_resources as pkg_res
            template_path = pkg_res.resource_filename(
                package_name, 
                f"templates/{template_name}"
            )
            if Path(template_path).exists():
                return CachedTemplate(
                    path=Path(template_path),
                    metadata=self.cache.put(resolved, Path(template_path)).metadata
                )
        except Exception:
            pass
        
        raise ValueError(
            f"Package template not found: {resolved.path}\n"
            f"Make sure package '{package_name}' is installed."
        )
    
    def _calculate_dir_checksum(self, directory: Path) -> str:
        """Calculate SHA256 checksum of directory contents."""
        hasher = hashlib.sha256()
        
        for file_path in sorted(directory.rglob("*")):
            if file_path.is_file() and not file_path.name.startswith("."):
                hasher.update(file_path.name.encode())
                hasher.update(file_path.read_bytes())
        
        return hasher.hexdigest()
    
    def list_remote_templates(
        self,
        owner: str = None,
        repo: str = None,
        ref: str = "main"
    ) -> List[TemplateInfo]:
        """
        List templates available in a GitHub repository.
        
        Args:
            owner: Repository owner (default: MervinPraison)
            repo: Repository name (default: agent-recipes)
            ref: Git ref
            
        Returns:
            List of TemplateInfo objects
        """
        owner = owner or self.DEFAULT_OWNER
        repo = repo or self.DEFAULT_REPO
        
        if self.offline:
            return []
        
        templates = []
        
        try:
            # Fetch templates directory listing
            api_url = f"{self.GITHUB_API_BASE}/repos/{owner}/{repo}/contents/templates?ref={ref}"
            response = self._make_request(api_url)
            contents = json.loads(response)
            
            for item in contents:
                if item["type"] == "dir":
                    # Try to fetch TEMPLATE.yaml for metadata
                    try:
                        template_url = f"{self.GITHUB_RAW_BASE}/{owner}/{repo}/{ref}/templates/{item['name']}/TEMPLATE.yaml"
                        template_content = self._make_request(template_url)
                        
                        import yaml
                        config = yaml.safe_load(template_content)
                        
                        templates.append(TemplateInfo(
                            name=config.get("name", item["name"]),
                            description=config.get("description", ""),
                            version=config.get("version", "1.0.0"),
                            author=config.get("author"),
                            tags=config.get("tags", []),
                            requires=config.get("requires", {}),
                            source=f"github:{owner}/{repo}/{item['name']}",
                            path=item["name"]
                        ))
                    except Exception:
                        # Fallback to basic info
                        templates.append(TemplateInfo(
                            name=item["name"],
                            description="",
                            source=f"github:{owner}/{repo}/{item['name']}",
                            path=item["name"]
                        ))
        except Exception:
            # Return empty list on error
            pass
        
        return templates
    
    def search_templates(
        self,
        query: str,
        owner: str = None,
        repo: str = None
    ) -> List[TemplateInfo]:
        """
        Search templates by name or tags.
        
        Args:
            query: Search query
            owner: Repository owner
            repo: Repository name
            
        Returns:
            List of matching TemplateInfo objects
        """
        all_templates = self.list_remote_templates(owner, repo)
        query_lower = query.lower()
        
        return [
            t for t in all_templates
            if query_lower in t.name.lower() or
               query_lower in t.description.lower() or
               any(query_lower in tag.lower() for tag in t.tags)
        ]


def list_templates(
    source: str = "all",
    offline: bool = False
) -> List[TemplateInfo]:
    """
    List available templates.
    
    Args:
        source: 'all', 'local', 'remote', or 'cached'
        offline: If True, only list cached templates
        
    Returns:
        List of TemplateInfo objects
    """
    registry = TemplateRegistry(offline=offline)
    templates = []
    
    if source in ("all", "cached"):
        # List cached templates
        cache = TemplateCache()
        for path, metadata in cache.list_cached():
            templates.append(TemplateInfo(
                name=path.name,
                description="(cached)",
                version=metadata.version or "unknown",
                source=str(path)
            ))
    
    if source in ("all", "remote") and not offline:
        # List remote templates
        remote = registry.list_remote_templates()
        templates.extend(remote)
    
    return templates


def search_templates(query: str, offline: bool = False) -> List[TemplateInfo]:
    """
    Search templates by query.
    
    Args:
        query: Search query
        offline: If True, only search cached templates
        
    Returns:
        List of matching TemplateInfo objects
    """
    registry = TemplateRegistry(offline=offline)
    return registry.search_templates(query)


def install_template(
    uri: str,
    offline: bool = False
) -> CachedTemplate:
    """
    Install (fetch and cache) a template.
    
    Args:
        uri: Template URI
        offline: If True, fail if not cached
        
    Returns:
        CachedTemplate with path and metadata
    """
    registry = TemplateRegistry(offline=offline)
    return registry.get_template(uri, offline=offline)
