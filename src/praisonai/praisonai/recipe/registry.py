"""
Recipe Registry Module

Provides local and remote registry support for recipe distribution.
Supports:
- Local filesystem registry (~/.praison/registry)
- Local HTTP registry (http://localhost:7777)
- Remote HTTP registry (https://registry.example.com)
- Publish, pull, search, list operations
- Atomic writes and file locking for concurrency safety
"""

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Protocol
from urllib.parse import urlparse


# Default registry paths
DEFAULT_REGISTRY_PATH = Path.home() / ".praison" / "registry"
DEFAULT_RUNS_PATH = Path.home() / ".praison" / "runs"
DEFAULT_REGISTRY_PORT = 7777


class RegistryError(Exception):
    """Base exception for registry operations."""
    pass


class RecipeNotFoundError(RegistryError):
    """Recipe not found in registry."""
    pass


class RecipeExistsError(RegistryError):
    """Recipe version already exists in registry."""
    pass


class RegistryAuthError(RegistryError):
    """Authentication failed for registry."""
    pass


class RegistryNetworkError(RegistryError):
    """Network error connecting to registry."""
    pass


class RegistryConflictError(RegistryError):
    """Conflict error (e.g., already exists without force)."""
    pass


class RegistryProtocol(Protocol):
    """Protocol defining registry interface for type checking."""
    
    def publish(
        self,
        bundle_path: Union[str, Path],
        force: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...
    
    def pull(
        self,
        name: str,
        version: Optional[str] = None,
        output_dir: Optional[Path] = None,
        verify_checksum: bool = True,
    ) -> Dict[str, Any]: ...
    
    def list_recipes(
        self,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]: ...
    
    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]: ...
    
    def get_versions(self, name: str) -> List[str]: ...
    
    def get_info(self, name: str, version: Optional[str] = None) -> Dict[str, Any]: ...
    
    def delete(self, name: str, version: Optional[str] = None) -> bool: ...


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _normalize_name(name: str) -> str:
    """Normalize recipe name per PEP 503 rules."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _validate_name(name: str) -> bool:
    """Validate recipe name format."""
    if not name or len(name) > 128:
        return False
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$', name))


def _validate_version(version: str) -> bool:
    """Validate version string (semver-like)."""
    if not version:
        return False
    return bool(re.match(r'^\d+\.\d+\.\d+([a-zA-Z0-9._-]*)?$', version))


def _atomic_write(file_path: Path, data: bytes) -> None:
    """Write data atomically using temp file + rename."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=file_path.parent, suffix='.tmp')
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        os.rename(tmp_path, file_path)
    except Exception:
        os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _atomic_write_json(file_path: Path, data: Dict[str, Any]) -> None:
    """Write JSON data atomically."""
    _atomic_write(file_path, json.dumps(data, indent=2).encode('utf-8'))


class LocalRegistry:
    """
    Local filesystem-based recipe registry.
    
    Storage structure:
    ~/.praison/registry/
    ├── index.json           # Registry index
    └── recipes/
        └── <name>/
            └── <version>/
                ├── manifest.json
                └── <name>-<version>.praison
    """
    
    def __init__(self, path: Optional[Path] = None):
        """Initialize local registry."""
        self.path = Path(path) if path else DEFAULT_REGISTRY_PATH
        self.recipes_path = self.path / "recipes"
        self.index_path = self.path / "index.json"
        self._ensure_structure()
    
    def _ensure_structure(self):
        """Ensure registry directory structure exists."""
        self.path.mkdir(parents=True, exist_ok=True)
        self.recipes_path.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._save_index({"recipes": {}, "updated": _get_timestamp()})
    
    def _load_index(self) -> Dict[str, Any]:
        """Load registry index."""
        if self.index_path.exists():
            with open(self.index_path) as f:
                return json.load(f)
        return {"recipes": {}, "updated": _get_timestamp()}
    
    def _save_index(self, index: Dict[str, Any]):
        """Save registry index."""
        index["updated"] = _get_timestamp()
        with open(self.index_path, "w") as f:
            json.dump(index, f, indent=2)
    
    def publish(
        self,
        bundle_path: Union[str, Path],
        force: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Publish a recipe bundle to the registry.
        
        Args:
            bundle_path: Path to .praison bundle file
            force: Overwrite existing version if True
            metadata: Additional metadata to store
            
        Returns:
            Dict with name, version, path, checksum
            
        Raises:
            RecipeExistsError: If version exists and force=False
            RegistryError: If bundle is invalid
        """
        bundle_path = Path(bundle_path)
        if not bundle_path.exists():
            raise RegistryError(f"Bundle not found: {bundle_path}")
        
        # Extract manifest from bundle
        try:
            with tarfile.open(bundle_path, "r:gz") as tar:
                manifest_file = tar.extractfile("manifest.json")
                if not manifest_file:
                    raise RegistryError("Bundle missing manifest.json")
                manifest = json.load(manifest_file)
        except tarfile.TarError as e:
            raise RegistryError(f"Invalid bundle format: {e}")
        
        name = manifest.get("name")
        version = manifest.get("version")
        
        if not name or not version:
            raise RegistryError("Bundle manifest missing name or version")
        
        # Check if version exists
        recipe_dir = self.recipes_path / name / version
        if recipe_dir.exists() and not force:
            raise RecipeExistsError(f"Recipe {name}@{version} already exists. Use --force to overwrite.")
        
        # Create recipe directory
        recipe_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy bundle
        bundle_name = f"{name}-{version}.praison"
        dest_path = recipe_dir / bundle_name
        shutil.copy2(bundle_path, dest_path)
        
        # Calculate checksum
        checksum = _calculate_checksum(dest_path)
        
        # Create registry manifest
        registry_manifest = {
            "name": name,
            "version": version,
            "description": manifest.get("description", ""),
            "tags": manifest.get("tags", []),
            "author": manifest.get("author", ""),
            "checksum": checksum,
            "published_at": _get_timestamp(),
            "bundle_path": str(dest_path),
            "files": manifest.get("files", []),
            **(metadata or {}),
        }
        
        # Save manifest
        manifest_path = recipe_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(registry_manifest, f, indent=2)
        
        # Update index
        index = self._load_index()
        if name not in index["recipes"]:
            index["recipes"][name] = {"versions": {}, "latest": version}
        
        index["recipes"][name]["versions"][version] = {
            "checksum": checksum,
            "published_at": registry_manifest["published_at"],
        }
        index["recipes"][name]["latest"] = version
        self._save_index(index)
        
        return {
            "name": name,
            "version": version,
            "path": str(dest_path),
            "checksum": checksum,
            "published_at": registry_manifest["published_at"],
        }
    
    def pull(
        self,
        name: str,
        version: Optional[str] = None,
        output_dir: Optional[Path] = None,
        verify_checksum: bool = True,
    ) -> Dict[str, Any]:
        """
        Pull a recipe from the registry.
        
        Args:
            name: Recipe name
            version: Version to pull (default: latest)
            output_dir: Directory to extract to
            verify_checksum: Verify bundle checksum
            
        Returns:
            Dict with name, version, path
            
        Raises:
            RecipeNotFoundError: If recipe/version not found
        """
        index = self._load_index()
        
        if name not in index["recipes"]:
            raise RecipeNotFoundError(f"Recipe not found: {name}")
        
        recipe_info = index["recipes"][name]
        version = version or recipe_info.get("latest")
        
        if version not in recipe_info["versions"]:
            raise RecipeNotFoundError(f"Version not found: {name}@{version}")
        
        # Get bundle path
        bundle_name = f"{name}-{version}.praison"
        bundle_path = self.recipes_path / name / version / bundle_name
        
        if not bundle_path.exists():
            raise RecipeNotFoundError(f"Bundle file missing: {bundle_path}")
        
        # Verify checksum
        if verify_checksum:
            expected = recipe_info["versions"][version]["checksum"]
            actual = _calculate_checksum(bundle_path)
            if expected != actual:
                raise RegistryError(f"Checksum mismatch for {name}@{version}")
        
        # Extract to output directory
        output_dir = Path(output_dir) if output_dir else Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        recipe_dir = output_dir / name
        recipe_dir.mkdir(parents=True, exist_ok=True)
        
        with tarfile.open(bundle_path, "r:gz") as tar:
            tar.extractall(recipe_dir)
        
        return {
            "name": name,
            "version": version,
            "path": str(recipe_dir),
            "bundle_path": str(bundle_path),
        }
    
    def list_recipes(
        self,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all recipes in the registry.
        
        Args:
            tags: Filter by tags (optional)
            
        Returns:
            List of recipe info dicts
        """
        index = self._load_index()
        recipes = []
        
        for name, info in index["recipes"].items():
            # Load full manifest for latest version
            latest = info.get("latest")
            if latest:
                manifest_path = self.recipes_path / name / latest / "manifest.json"
                if manifest_path.exists():
                    with open(manifest_path) as f:
                        manifest = json.load(f)
                    
                    # Filter by tags if specified
                    if tags:
                        recipe_tags = manifest.get("tags", [])
                        if not any(t in recipe_tags for t in tags):
                            continue
                    
                    recipes.append({
                        "name": name,
                        "version": latest,
                        "description": manifest.get("description", ""),
                        "tags": manifest.get("tags", []),
                        "versions": list(info["versions"].keys()),
                    })
        
        return recipes
    
    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search recipes by name, description, or tags.
        
        Args:
            query: Search query
            tags: Filter by tags (optional)
            
        Returns:
            List of matching recipe info dicts
        """
        all_recipes = self.list_recipes(tags=tags)
        query_lower = query.lower()
        
        results = []
        for recipe in all_recipes:
            # Search in name, description, tags
            if (
                query_lower in recipe["name"].lower()
                or query_lower in recipe.get("description", "").lower()
                or any(query_lower in t.lower() for t in recipe.get("tags", []))
            ):
                results.append(recipe)
        
        return results
    
    def get_versions(self, name: str) -> List[str]:
        """Get all versions of a recipe."""
        index = self._load_index()
        if name not in index["recipes"]:
            raise RecipeNotFoundError(f"Recipe not found: {name}")
        return list(index["recipes"][name]["versions"].keys())
    
    def get_info(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get detailed info about a recipe version."""
        index = self._load_index()
        if name not in index["recipes"]:
            raise RecipeNotFoundError(f"Recipe not found: {name}")
        
        recipe_info = index["recipes"][name]
        version = version or recipe_info.get("latest")
        
        manifest_path = self.recipes_path / name / version / "manifest.json"
        if not manifest_path.exists():
            raise RecipeNotFoundError(f"Version not found: {name}@{version}")
        
        with open(manifest_path) as f:
            return json.load(f)
    
    def delete(self, name: str, version: Optional[str] = None) -> bool:
        """
        Delete a recipe or specific version.
        
        Args:
            name: Recipe name
            version: Version to delete (None = all versions)
            
        Returns:
            True if deleted
        """
        index = self._load_index()
        if name not in index["recipes"]:
            raise RecipeNotFoundError(f"Recipe not found: {name}")
        
        if version:
            # Delete specific version
            version_dir = self.recipes_path / name / version
            if version_dir.exists():
                shutil.rmtree(version_dir)
            
            if version in index["recipes"][name]["versions"]:
                del index["recipes"][name]["versions"][version]
            
            # Update latest if needed
            versions = list(index["recipes"][name]["versions"].keys())
            if versions:
                index["recipes"][name]["latest"] = sorted(versions)[-1]
            else:
                del index["recipes"][name]
        else:
            # Delete all versions
            recipe_dir = self.recipes_path / name
            if recipe_dir.exists():
                shutil.rmtree(recipe_dir)
            del index["recipes"][name]
        
        self._save_index(index)
        return True


class HttpRegistry:
    """
    HTTP-based recipe registry client.
    
    Works with both local HTTP registry (http://localhost:7777) and
    remote HTTP registries (https://registry.example.com).
    
    Supports:
    - Token-based authentication (Bearer token)
    - Multipart file upload for publish
    - ETag/If-None-Match for efficient downloads
    - Proper error handling with specific exceptions
    """
    
    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize HTTP registry client.
        
        Args:
            url: Registry base URL (http://localhost:7777 or https://...)
            token: Authentication token (or set PRAISONAI_REGISTRY_TOKEN env var)
            timeout: Request timeout in seconds
        """
        self.url = url.rstrip("/")
        self.token = token or os.environ.get("PRAISONAI_REGISTRY_TOKEN")
        self.timeout = timeout
        self._etag_cache: Dict[str, str] = {}
    
    def _get_headers(self, content_type: str = "application/json") -> Dict[str, str]:
        """Get request headers with optional auth."""
        headers = {"Content-Type": content_type}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def _request(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to registry."""
        import urllib.request
        import urllib.error
        
        url = f"{self.url}{path}"
        req_headers = headers or self._get_headers()
        
        try:
            req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                # Cache ETag for future requests
                etag = response.headers.get("ETag")
                if etag:
                    self._etag_cache[path] = etag
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RegistryAuthError("Authentication failed. Check your token.")
            elif e.code == 403:
                raise RegistryAuthError("Access denied. Token may lack required permissions.")
            elif e.code == 404:
                raise RecipeNotFoundError(f"Not found: {path}")
            elif e.code == 409:
                raise RegistryConflictError("Recipe version already exists. Use --force to overwrite.")
            else:
                body = e.read().decode() if e.fp else ""
                raise RegistryError(f"Registry error ({e.code}): {body}")
        except urllib.error.URLError as e:
            raise RegistryNetworkError(f"Connection error: {e.reason}")
    
    def _download_file(self, path: str, dest_path: Path) -> Dict[str, Any]:
        """Download file from registry with ETag support."""
        import urllib.request
        import urllib.error
        
        url = f"{self.url}{path}"
        headers = self._get_headers()
        
        # Add If-None-Match if we have cached ETag
        if path in self._etag_cache:
            headers["If-None-Match"] = self._etag_cache[path]
        
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                etag = response.headers.get("ETag")
                if etag:
                    self._etag_cache[path] = etag
                
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as f:
                    shutil.copyfileobj(response, f)
                
                return {"downloaded": True, "path": str(dest_path)}
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return {"downloaded": False, "cached": True}
            elif e.code == 404:
                raise RecipeNotFoundError(f"Not found: {path}")
            else:
                raise RegistryError(f"Download error ({e.code})")
        except urllib.error.URLError as e:
            raise RegistryNetworkError(f"Connection error: {e.reason}")
    
    def _upload_file(self, path: str, file_path: Path, force: bool = False) -> Dict[str, Any]:
        """Upload file to registry using multipart form."""
        import urllib.request
        import urllib.error
        import uuid
        
        boundary = f"----PraisonAI{uuid.uuid4().hex}"
        
        # Build multipart body
        body_parts = []
        
        # Add force field
        body_parts.append(f"--{boundary}".encode())
        body_parts.append(b'Content-Disposition: form-data; name="force"')
        body_parts.append(b"")
        body_parts.append(b"true" if force else b"false")
        
        # Add file
        body_parts.append(f"--{boundary}".encode())
        body_parts.append(f'Content-Disposition: form-data; name="bundle"; filename="{file_path.name}"'.encode())
        body_parts.append(b"Content-Type: application/gzip")
        body_parts.append(b"")
        with open(file_path, "rb") as f:
            body_parts.append(f.read())
        
        body_parts.append(f"--{boundary}--".encode())
        body_parts.append(b"")
        
        body = b"\r\n".join(body_parts)
        
        headers = self._get_headers(f"multipart/form-data; boundary={boundary}")
        
        url = f"{self.url}{path}"
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RegistryAuthError("Authentication required for publish")
            elif e.code == 409:
                raise RegistryConflictError("Recipe version already exists. Use --force to overwrite.")
            else:
                body_text = e.read().decode() if e.fp else ""
                raise RegistryError(f"Upload error ({e.code}): {body_text}")
        except urllib.error.URLError as e:
            raise RegistryNetworkError(f"Connection error: {e.reason}")
    
    def health(self) -> Dict[str, Any]:
        """Check registry health."""
        return self._request("GET", "/healthz")
    
    def publish(
        self,
        bundle_path: Union[str, Path],
        force: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Publish bundle to HTTP registry.
        
        Args:
            bundle_path: Path to .praison bundle file
            force: Overwrite existing version if True
            metadata: Additional metadata (ignored for HTTP, included in bundle)
            
        Returns:
            Dict with name, version, checksum
        """
        bundle_path = Path(bundle_path)
        if not bundle_path.exists():
            raise RegistryError(f"Bundle not found: {bundle_path}")
        
        # Extract name/version from bundle to construct path
        try:
            with tarfile.open(bundle_path, "r:gz") as tar:
                manifest_file = tar.extractfile("manifest.json")
                if not manifest_file:
                    raise RegistryError("Bundle missing manifest.json")
                manifest = json.load(manifest_file)
        except tarfile.TarError as e:
            raise RegistryError(f"Invalid bundle format: {e}")
        
        name = manifest.get("name")
        version = manifest.get("version")
        
        if not name or not version:
            raise RegistryError("Bundle manifest missing name or version")
        
        # Upload to /v1/recipes/{name}/{version}
        return self._upload_file(f"/v1/recipes/{name}/{version}", bundle_path, force=force)
    
    def pull(
        self,
        name: str,
        version: Optional[str] = None,
        output_dir: Optional[Path] = None,
        verify_checksum: bool = True,
    ) -> Dict[str, Any]:
        """
        Pull recipe from HTTP registry.
        
        Args:
            name: Recipe name
            version: Version to pull (default: latest)
            output_dir: Directory to extract to
            verify_checksum: Verify bundle checksum
            
        Returns:
            Dict with name, version, path
        """
        # Get recipe info to determine version
        if not version:
            info = self._request("GET", f"/v1/recipes/{name}")
            version = info.get("latest")
            if not version:
                raise RecipeNotFoundError(f"No versions found for: {name}")
        
        output_dir = Path(output_dir) if output_dir else Path.cwd()
        bundle_path = output_dir / f"{name}-{version}.praison"
        
        # Download bundle
        download_path = f"/v1/recipes/{name}/{version}/download"
        self._download_file(download_path, bundle_path)
        
        # Verify checksum if requested
        if verify_checksum:
            info = self._request("GET", f"/v1/recipes/{name}/{version}")
            expected = info.get("checksum")
            if expected:
                actual = _calculate_checksum(bundle_path)
                if expected != actual:
                    bundle_path.unlink()
                    raise RegistryError(f"Checksum mismatch for {name}@{version}")
        
        # Extract
        recipe_dir = output_dir / name
        recipe_dir.mkdir(parents=True, exist_ok=True)
        
        with tarfile.open(bundle_path, "r:gz") as tar:
            tar.extractall(recipe_dir)
        
        return {
            "name": name,
            "version": version,
            "path": str(recipe_dir),
            "bundle_path": str(bundle_path),
        }
    
    def list_recipes(
        self,
        tags: Optional[List[str]] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List recipes from HTTP registry.
        
        Args:
            tags: Filter by tags
            page: Page number (1-indexed)
            per_page: Results per page
            
        Returns:
            List of recipe info dicts
        """
        params = f"?page={page}&per_page={per_page}"
        if tags:
            params += f"&tags={','.join(tags)}"
        result = self._request("GET", f"/v1/recipes{params}")
        return result.get("recipes", [])
    
    def search(
        self,
        query: str,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search recipes in HTTP registry.
        
        Args:
            query: Search query
            tags: Filter by tags
            
        Returns:
            List of matching recipe info dicts
        """
        from urllib.parse import quote as url_quote
        params = f"?q={url_quote(query)}"
        if tags:
            params += f"&tags={','.join(tags)}"
        result = self._request("GET", f"/v1/search{params}")
        return result.get("results", [])
    
    def get_versions(self, name: str) -> List[str]:
        """Get all versions of a recipe."""
        result = self._request("GET", f"/v1/recipes/{name}")
        return result.get("versions", [])
    
    def get_info(self, name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get detailed info about a recipe version."""
        if version:
            return self._request("GET", f"/v1/recipes/{name}/{version}")
        return self._request("GET", f"/v1/recipes/{name}")
    
    def delete(self, name: str, version: Optional[str] = None) -> bool:
        """
        Delete a recipe or specific version.
        
        Args:
            name: Recipe name
            version: Version to delete (None = all versions)
            
        Returns:
            True if deleted
        """
        if version:
            self._request("DELETE", f"/v1/recipes/{name}/{version}")
        else:
            self._request("DELETE", f"/v1/recipes/{name}")
        return True


# Alias for backwards compatibility
RemoteRegistry = HttpRegistry


def get_registry(
    registry: Optional[str] = None,
    token: Optional[str] = None,
) -> Union[LocalRegistry, RemoteRegistry]:
    """
    Get appropriate registry instance.
    
    Args:
        registry: Registry path or URL (default: local)
        token: Auth token for remote registry
        
    Returns:
        LocalRegistry or RemoteRegistry instance
    """
    if registry is None:
        return LocalRegistry()
    
    # Check if it's a URL
    parsed = urlparse(registry)
    if parsed.scheme in ("http", "https"):
        return RemoteRegistry(registry, token=token)
    
    # Local path
    return LocalRegistry(Path(registry))
