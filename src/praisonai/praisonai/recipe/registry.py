"""
Recipe Registry Module

Provides local and remote registry support for recipe distribution.
Supports:
- Local filesystem registry (~/.praison/registry)
- Remote HTTP registry (optional)
- Publish, pull, search, list operations
"""

import hashlib
import json
import os
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse


# Default registry paths
DEFAULT_REGISTRY_PATH = Path.home() / ".praison" / "registry"
DEFAULT_RUNS_PATH = Path.home() / ".praison" / "runs"


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


class RemoteRegistry:
    """
    Remote HTTP-based recipe registry client.
    
    Supports:
    - Token-based authentication
    - Publish/pull operations
    - Search and list
    """
    
    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize remote registry client.
        
        Args:
            url: Registry base URL
            token: Authentication token
            timeout: Request timeout in seconds
        """
        self.url = url.rstrip("/")
        self.token = token or os.environ.get("PRAISONAI_REGISTRY_TOKEN")
        self.timeout = timeout
    
    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to registry."""
        import urllib.request
        import urllib.error
        
        url = f"{self.url}{path}"
        headers = {"Content-Type": "application/json"}
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        body = json.dumps(data).encode() if data else None
        
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RegistryAuthError("Authentication failed")
            elif e.code == 404:
                raise RecipeNotFoundError(f"Not found: {path}")
            else:
                body = e.read().decode() if e.fp else ""
                raise RegistryError(f"Registry error ({e.code}): {body}")
        except urllib.error.URLError as e:
            raise RegistryError(f"Connection error: {e.reason}")
    
    def publish(
        self,
        bundle_path: Union[str, Path],
        force: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Publish bundle to remote registry."""
        bundle_path = Path(bundle_path)
        if not bundle_path.exists():
            raise RegistryError(f"Bundle not found: {bundle_path}")
        
        # For remote, we'd upload the file
        # This is a simplified implementation
        with open(bundle_path, "rb") as f:
            bundle_data = f.read()
        
        import base64
        encoded = base64.b64encode(bundle_data).decode()
        
        return self._request("POST", "/v1/recipes/publish", {
            "bundle": encoded,
            "force": force,
            "metadata": metadata or {},
        })
    
    def pull(
        self,
        name: str,
        version: Optional[str] = None,
        output_dir: Optional[Path] = None,
        verify_checksum: bool = True,
    ) -> Dict[str, Any]:
        """Pull recipe from remote registry."""
        version_str = f"@{version}" if version else ""
        result = self._request("GET", f"/v1/recipes/{name}{version_str}/download")
        
        # Decode and save bundle
        import base64
        bundle_data = base64.b64decode(result["bundle"])
        
        output_dir = Path(output_dir) if output_dir else Path.cwd()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        bundle_path = output_dir / f"{name}-{result['version']}.praison"
        with open(bundle_path, "wb") as f:
            f.write(bundle_data)
        
        # Extract
        recipe_dir = output_dir / name
        recipe_dir.mkdir(parents=True, exist_ok=True)
        
        with tarfile.open(bundle_path, "r:gz") as tar:
            tar.extractall(recipe_dir)
        
        return {
            "name": name,
            "version": result["version"],
            "path": str(recipe_dir),
            "bundle_path": str(bundle_path),
        }
    
    def list_recipes(self, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """List recipes from remote registry."""
        params = ""
        if tags:
            params = f"?tags={','.join(tags)}"
        return self._request("GET", f"/v1/recipes{params}").get("recipes", [])
    
    def search(self, query: str, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search recipes in remote registry."""
        params = f"?q={query}"
        if tags:
            params += f"&tags={','.join(tags)}"
        return self._request("GET", f"/v1/recipes/search{params}").get("results", [])


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
