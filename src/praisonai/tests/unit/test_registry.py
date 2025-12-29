"""
Unit tests for recipe registry module.

Tests LocalRegistry, HttpRegistry, and server components.
"""

import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from praisonai.recipe.registry import (
    LocalRegistry,
    HttpRegistry,
    RemoteRegistry,
    get_registry,
    RegistryError,
    RecipeNotFoundError,
    RecipeExistsError,
    _calculate_checksum,
    _get_timestamp,
    _normalize_name,
    _validate_name,
    _validate_version,
    _atomic_write,
    _atomic_write_json,
    DEFAULT_REGISTRY_PATH,
    DEFAULT_REGISTRY_PORT,
)


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_get_timestamp(self):
        """Test timestamp generation."""
        ts = _get_timestamp()
        assert ts is not None
        assert "T" in ts  # ISO format
    
    def test_calculate_checksum(self, tmp_path):
        """Test checksum calculation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")
        
        checksum = _calculate_checksum(test_file)
        assert len(checksum) == 64  # SHA256 hex
        
        # Same content should give same checksum
        test_file2 = tmp_path / "test2.txt"
        test_file2.write_text("hello world")
        assert _calculate_checksum(test_file2) == checksum
    
    def test_normalize_name(self):
        """Test name normalization."""
        assert _normalize_name("My-Recipe") == "my-recipe"
        assert _normalize_name("my_recipe") == "my-recipe"
        assert _normalize_name("My.Recipe") == "my-recipe"
        assert _normalize_name("my--recipe") == "my-recipe"
    
    def test_validate_name(self):
        """Test name validation."""
        assert _validate_name("my-recipe") is True
        assert _validate_name("my_recipe") is True
        assert _validate_name("MyRecipe123") is True
        assert _validate_name("") is False
        assert _validate_name("-invalid") is False
        assert _validate_name("a" * 200) is False  # Too long
    
    def test_validate_version(self):
        """Test version validation."""
        assert _validate_version("1.0.0") is True
        assert _validate_version("0.1.0") is True
        assert _validate_version("1.0.0-alpha") is True
        assert _validate_version("1.0.0.beta1") is True
        assert _validate_version("") is False
        assert _validate_version("1.0") is False  # Missing patch
        assert _validate_version("invalid") is False
    
    def test_atomic_write(self, tmp_path):
        """Test atomic write."""
        test_file = tmp_path / "test.txt"
        _atomic_write(test_file, b"hello world")
        
        assert test_file.exists()
        assert test_file.read_bytes() == b"hello world"
    
    def test_atomic_write_json(self, tmp_path):
        """Test atomic JSON write."""
        test_file = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        _atomic_write_json(test_file, data)
        
        assert test_file.exists()
        loaded = json.loads(test_file.read_text())
        assert loaded == data


class TestLocalRegistry:
    """Test LocalRegistry class."""
    
    @pytest.fixture
    def registry(self, tmp_path):
        """Create a temporary registry."""
        return LocalRegistry(tmp_path / "registry")
    
    @pytest.fixture
    def sample_bundle(self, tmp_path):
        """Create a sample .praison bundle."""
        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        
        manifest = {
            "name": "test-recipe",
            "version": "1.0.0",
            "description": "A test recipe",
            "tags": ["test", "sample"],
            "author": "test",
            "files": ["recipe.yaml"],
        }
        
        (bundle_dir / "manifest.json").write_text(json.dumps(manifest))
        (bundle_dir / "recipe.yaml").write_text("name: test")
        
        bundle_path = tmp_path / "test-recipe-1.0.0.praison"
        with tarfile.open(bundle_path, "w:gz") as tar:
            tar.add(bundle_dir / "manifest.json", arcname="manifest.json")
            tar.add(bundle_dir / "recipe.yaml", arcname="recipe.yaml")
        
        return bundle_path
    
    def test_init_creates_structure(self, registry):
        """Test registry initialization creates directory structure."""
        assert registry.path.exists()
        assert registry.recipes_path.exists()
        assert registry.index_path.exists()
    
    def test_publish_bundle(self, registry, sample_bundle):
        """Test publishing a bundle."""
        result = registry.publish(sample_bundle)
        
        assert result["name"] == "test-recipe"
        assert result["version"] == "1.0.0"
        assert "checksum" in result
        assert "published_at" in result
    
    def test_publish_duplicate_fails(self, registry, sample_bundle):
        """Test publishing duplicate version fails."""
        registry.publish(sample_bundle)
        
        with pytest.raises(RecipeExistsError):
            registry.publish(sample_bundle)
    
    def test_publish_force_overwrites(self, registry, sample_bundle):
        """Test force publish overwrites existing."""
        registry.publish(sample_bundle)
        result = registry.publish(sample_bundle, force=True)
        
        assert result["name"] == "test-recipe"
    
    def test_publish_invalid_bundle(self, registry, tmp_path):
        """Test publishing invalid bundle fails."""
        invalid_bundle = tmp_path / "invalid.praison"
        invalid_bundle.write_text("not a tarball")
        
        with pytest.raises(RegistryError):
            registry.publish(invalid_bundle)
    
    def test_pull_recipe(self, registry, sample_bundle, tmp_path):
        """Test pulling a recipe."""
        registry.publish(sample_bundle)
        
        output_dir = tmp_path / "output"
        result = registry.pull("test-recipe", output_dir=output_dir)
        
        assert result["name"] == "test-recipe"
        assert result["version"] == "1.0.0"
        assert (output_dir / "test-recipe" / "manifest.json").exists()
    
    def test_pull_specific_version(self, registry, sample_bundle, tmp_path):
        """Test pulling specific version."""
        registry.publish(sample_bundle)
        
        output_dir = tmp_path / "output"
        result = registry.pull("test-recipe", version="1.0.0", output_dir=output_dir)
        
        assert result["version"] == "1.0.0"
    
    def test_pull_not_found(self, registry, tmp_path):
        """Test pulling non-existent recipe."""
        with pytest.raises(RecipeNotFoundError):
            registry.pull("nonexistent")
    
    def test_list_recipes(self, registry, sample_bundle):
        """Test listing recipes."""
        registry.publish(sample_bundle)
        
        recipes = registry.list_recipes()
        
        assert len(recipes) == 1
        assert recipes[0]["name"] == "test-recipe"
    
    def test_list_recipes_with_tags(self, registry, sample_bundle):
        """Test listing recipes filtered by tags."""
        registry.publish(sample_bundle)
        
        # Should find with matching tag
        recipes = registry.list_recipes(tags=["test"])
        assert len(recipes) == 1
        
        # Should not find with non-matching tag
        recipes = registry.list_recipes(tags=["nonexistent"])
        assert len(recipes) == 0
    
    def test_search_recipes(self, registry, sample_bundle):
        """Test searching recipes."""
        registry.publish(sample_bundle)
        
        # Search by name
        results = registry.search("test")
        assert len(results) == 1
        
        # Search by tag (search includes tags)
        results = registry.search("sample")
        assert len(results) == 1  # "sample" is in tags
        
        # Search for non-existent term
        results = registry.search("nonexistent")
        assert len(results) == 0
    
    def test_get_versions(self, registry, sample_bundle):
        """Test getting versions."""
        registry.publish(sample_bundle)
        
        versions = registry.get_versions("test-recipe")
        assert "1.0.0" in versions
    
    def test_get_info(self, registry, sample_bundle):
        """Test getting recipe info."""
        registry.publish(sample_bundle)
        
        info = registry.get_info("test-recipe")
        assert info["name"] == "test-recipe"
        assert info["version"] == "1.0.0"
    
    def test_delete_version(self, registry, sample_bundle):
        """Test deleting specific version."""
        registry.publish(sample_bundle)
        
        result = registry.delete("test-recipe", version="1.0.0")
        assert result is True
        
        with pytest.raises(RecipeNotFoundError):
            registry.get_info("test-recipe")
    
    def test_delete_all_versions(self, registry, sample_bundle):
        """Test deleting all versions."""
        registry.publish(sample_bundle)
        
        result = registry.delete("test-recipe")
        assert result is True
        
        with pytest.raises(RecipeNotFoundError):
            registry.get_versions("test-recipe")


class TestHttpRegistry:
    """Test HttpRegistry class."""
    
    @pytest.fixture
    def registry(self):
        """Create an HttpRegistry instance."""
        return HttpRegistry("http://localhost:7777", token="test-token")
    
    def test_init(self, registry):
        """Test initialization."""
        assert registry.url == "http://localhost:7777"
        assert registry.token == "test-token"
        assert registry.timeout == 30
    
    def test_get_headers(self, registry):
        """Test header generation."""
        headers = registry._get_headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == "Bearer test-token"
    
    def test_get_headers_no_token(self):
        """Test headers without token."""
        registry = HttpRegistry("http://localhost:7777")
        registry.token = None
        headers = registry._get_headers()
        assert "Authorization" not in headers
    
    @patch("urllib.request.urlopen")
    def test_health_check(self, mock_urlopen, registry):
        """Test health check."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"ok": true, "status": "healthy"}'
        mock_response.headers = {}
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        result = registry.health()
        assert result["ok"] is True
    
    @patch("urllib.request.urlopen")
    def test_list_recipes(self, mock_urlopen, registry):
        """Test listing recipes."""
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"recipes": [{"name": "test"}]}'
        mock_response.headers = {}
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        recipes = registry.list_recipes()
        assert len(recipes) == 1
    
    def test_remote_registry_alias(self):
        """Test RemoteRegistry is alias for HttpRegistry."""
        assert RemoteRegistry is HttpRegistry


class TestGetRegistry:
    """Test get_registry factory function."""
    
    def test_default_returns_local(self):
        """Test default returns LocalRegistry."""
        registry = get_registry()
        assert isinstance(registry, LocalRegistry)
    
    def test_http_url_returns_http(self):
        """Test HTTP URL returns HttpRegistry."""
        registry = get_registry("http://localhost:7777")
        assert isinstance(registry, HttpRegistry)
    
    def test_https_url_returns_http(self):
        """Test HTTPS URL returns HttpRegistry."""
        registry = get_registry("https://registry.example.com")
        assert isinstance(registry, HttpRegistry)
    
    def test_path_returns_local(self, tmp_path):
        """Test path returns LocalRegistry."""
        registry = get_registry(str(tmp_path))
        assert isinstance(registry, LocalRegistry)
    
    def test_token_passed_to_http(self):
        """Test token is passed to HttpRegistry."""
        registry = get_registry("http://localhost:7777", token="secret")
        assert registry.token == "secret"


class TestConstants:
    """Test module constants."""
    
    def test_default_registry_path(self):
        """Test default registry path."""
        assert DEFAULT_REGISTRY_PATH == Path.home() / ".praison" / "registry"
    
    def test_default_registry_port(self):
        """Test default registry port."""
        assert DEFAULT_REGISTRY_PORT == 7777
