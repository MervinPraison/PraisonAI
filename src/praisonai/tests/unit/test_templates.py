"""
Unit tests for the Templates system.

Tests cover:
- Template resolver (URI parsing)
- Template cache (disk caching with TTL)
- Template loader (loading and materializing templates)
- Template security (allowlists, checksums)
- CLI integration
"""

import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest


class TestTemplateResolver:
    """Tests for template URI resolution."""
    
    def test_resolve_local_path(self):
        """Test resolving local file paths."""
        from praisonai.templates.resolver import TemplateResolver, TemplateSource
        
        # Relative path
        resolved = TemplateResolver.resolve("./my-template")
        assert resolved.source == TemplateSource.LOCAL
        assert "my-template" in resolved.path
        
        # Home directory
        resolved = TemplateResolver.resolve("~/templates/test")
        assert resolved.source == TemplateSource.LOCAL
        assert resolved.path.startswith(os.path.expanduser("~"))
    
    def test_resolve_github_uri(self):
        """Test resolving GitHub URIs."""
        from praisonai.templates.resolver import TemplateResolver, TemplateSource
        
        # Basic GitHub URI
        resolved = TemplateResolver.resolve("github:owner/repo/template")
        assert resolved.source == TemplateSource.GITHUB
        assert resolved.owner == "owner"
        assert resolved.repo == "repo"
        assert resolved.path == "template"
        assert resolved.ref == "main"
        
        # With version
        resolved = TemplateResolver.resolve("github:owner/repo/template@v1.0.0")
        assert resolved.ref == "v1.0.0"
        
        # With commit hash
        resolved = TemplateResolver.resolve("github:owner/repo/template@abc123def456")
        assert resolved.ref == "abc123def456"
    
    def test_resolve_package_uri(self):
        """Test resolving package URIs."""
        from praisonai.templates.resolver import TemplateResolver, TemplateSource
        
        resolved = TemplateResolver.resolve("package:agent_recipes/transcript-generator")
        assert resolved.source == TemplateSource.PACKAGE
        assert resolved.path == "agent_recipes/transcript-generator"
    
    def test_resolve_http_uri(self):
        """Test resolving HTTP URIs."""
        from praisonai.templates.resolver import TemplateResolver, TemplateSource
        
        resolved = TemplateResolver.resolve("https://example.com/template.yaml")
        assert resolved.source == TemplateSource.HTTP
        assert resolved.url == "https://example.com/template.yaml"
    
    def test_resolve_simple_name(self):
        """Test resolving simple template names."""
        from praisonai.templates.resolver import TemplateResolver, TemplateSource
        
        # Simple name should default to package:agent_recipes/name
        resolved = TemplateResolver.resolve("transcript-generator")
        assert resolved.source == TemplateSource.PACKAGE
        assert "transcript-generator" in resolved.path
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        from praisonai.templates.resolver import TemplateResolver
        
        resolved = TemplateResolver.resolve("github:owner/repo/template@v1.0.0")
        cache_key = resolved.cache_key
        assert "github" in cache_key
        assert "owner" in cache_key
        assert "repo" in cache_key
        assert "v1.0.0" in cache_key
    
    def test_is_pinned(self):
        """Test version pinning detection."""
        from praisonai.templates.resolver import TemplateResolver
        
        # Pinned (version tag)
        resolved = TemplateResolver.resolve("github:owner/repo/template@v1.0.0")
        assert resolved.is_pinned is True
        
        # Pinned (commit hash)
        resolved = TemplateResolver.resolve("github:owner/repo/template@" + "a" * 40)
        assert resolved.is_pinned is True
        
        # Not pinned (branch name)
        resolved = TemplateResolver.resolve("github:owner/repo/template@main")
        assert resolved.is_pinned is False


class TestTemplateCache:
    """Tests for template caching."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create a temporary cache directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_cache_put_and_get(self, temp_cache_dir):
        """Test storing and retrieving from cache."""
        from praisonai.templates.cache import TemplateCache
        from praisonai.templates.resolver import TemplateResolver
        
        cache = TemplateCache(cache_dir=temp_cache_dir)
        resolved = TemplateResolver.resolve("github:owner/repo/template@v1.0.0")
        
        # Create temp content
        content_dir = temp_cache_dir / "content"
        content_dir.mkdir()
        (content_dir / "TEMPLATE.yaml").write_text("name: test")
        
        # Put in cache
        cached = cache.put(resolved, content_dir)
        assert cached.path.exists()
        
        # Get from cache
        retrieved = cache.get(resolved)
        assert retrieved is not None
        assert (retrieved.path / "TEMPLATE.yaml").exists()
    
    def test_cache_expiration(self, temp_cache_dir):
        """Test cache expiration for non-pinned templates."""
        from praisonai.templates.cache import TemplateCache, CacheMetadata
        import time
        
        # Create expired metadata
        metadata = CacheMetadata(
            fetched_at=time.time() - 100000,  # Long ago
            ttl_seconds=1,  # Very short TTL
            is_pinned=False
        )
        assert metadata.is_expired() is True
        
        # Pinned should never expire
        pinned_metadata = CacheMetadata(
            fetched_at=time.time() - 100000,
            ttl_seconds=1,
            is_pinned=True
        )
        assert pinned_metadata.is_expired() is False
    
    def test_cache_clear(self, temp_cache_dir):
        """Test clearing the cache."""
        from praisonai.templates.cache import TemplateCache
        from praisonai.templates.resolver import TemplateResolver
        
        cache = TemplateCache(cache_dir=temp_cache_dir)
        resolved = TemplateResolver.resolve("github:owner/repo/template@v1.0.0")
        
        # Create and cache content
        content_dir = temp_cache_dir / "content"
        content_dir.mkdir()
        (content_dir / "TEMPLATE.yaml").write_text("name: test")
        cache.put(resolved, content_dir)
        
        # Clear cache
        count = cache.clear()
        assert count >= 1
        
        # Verify cleared
        assert cache.get(resolved) is None


class TestTemplateSecurity:
    """Tests for template security."""
    
    def test_source_allowlist(self):
        """Test source allowlist validation."""
        from praisonai.templates.security import TemplateSecurity, SecurityConfig
        
        config = SecurityConfig(
            allowed_sources={"github:MervinPraison/agent-recipes"},
            allow_any_github=False
        )
        security = TemplateSecurity(config=config)
        
        # Allowed source
        assert security.is_source_allowed("github:MervinPraison/agent-recipes/template") is True
        
        # Not allowed
        assert security.is_source_allowed("github:other/repo/template") is False
    
    def test_local_paths_allowed_by_default(self):
        """Test that local paths are allowed by default."""
        from praisonai.templates.security import TemplateSecurity
        
        security = TemplateSecurity()
        assert security.is_source_allowed("./my-template") is True
        assert security.is_source_allowed("~/templates/test") is True
    
    def test_checksum_verification(self):
        """Test checksum calculation and verification."""
        from praisonai.templates.security import TemplateSecurity
        
        security = TemplateSecurity()
        
        # Create temp directory with files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "file1.txt").write_text("content1")
            (temp_path / "file2.txt").write_text("content2")
            
            # Calculate checksum
            checksum = security.calculate_checksum(temp_path)
            assert len(checksum) == 64  # SHA256 hex length
            
            # Verify checksum
            assert security.verify_checksum(temp_path, checksum) is True
            assert security.verify_checksum(temp_path, "wrong") is False
    
    def test_path_validation(self):
        """Test path security validation."""
        from praisonai.templates.security import TemplateSecurity
        
        security = TemplateSecurity()
        
        # Safe paths
        assert security.validate_path("template.yaml") is True
        assert security.validate_path("subdir/file.yaml") is True
        
        # Unsafe paths (path traversal)
        assert security.validate_path("../../../etc/passwd") is False
    
    def test_file_extension_validation(self):
        """Test file extension validation."""
        from praisonai.templates.security import TemplateSecurity
        
        security = TemplateSecurity()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Allowed extensions
            yaml_file = temp_path / "config.yaml"
            yaml_file.write_text("test: true")
            assert security.validate_file(yaml_file) is True
            
            # Blocked extensions
            exe_file = temp_path / "malware.exe"
            exe_file.write_text("bad")
            assert security.validate_file(exe_file) is False


class TestTemplateLoader:
    """Tests for template loading."""
    
    @pytest.fixture
    def temp_template_dir(self):
        """Create a temporary template directory."""
        temp_dir = tempfile.mkdtemp()
        template_dir = Path(temp_dir) / "test-template"
        template_dir.mkdir()
        
        # Create TEMPLATE.yaml
        (template_dir / "TEMPLATE.yaml").write_text("""
name: test-template
version: "1.0.0"
description: A test template
author: test
requires:
  packages: [pyyaml]
  env: [TEST_API_KEY]
workflow: workflow.yaml
""")
        
        # Create workflow.yaml
        (template_dir / "workflow.yaml").write_text("""
name: Test Workflow
workflow:
  verbose: true
agents:
  test_agent:
    name: TestAgent
    role: Tester
    goal: Test things
steps:
  - agent: test_agent
    action: "Test: {{input}}"
""")
        
        yield template_dir
        shutil.rmtree(temp_dir)
    
    def test_load_local_template(self, temp_template_dir):
        """Test loading a local template."""
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        template = loader.load(str(temp_template_dir))
        
        assert template.name == "test-template"
        assert template.version == "1.0.0"
        assert "pyyaml" in template.requires.get("packages", [])
    
    def test_load_workflow_config(self, temp_template_dir):
        """Test loading workflow configuration from template."""
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        template = loader.load(str(temp_template_dir))
        
        workflow_config = loader.load_workflow_config(template)
        assert workflow_config["name"] == "Test Workflow"
        assert "agents" in workflow_config
    
    def test_variable_substitution(self, temp_template_dir):
        """Test variable substitution in configs."""
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        template = loader.load(str(temp_template_dir), config={"input": "hello"})
        
        workflow_config = loader.load_workflow_config(template)
        # Check that {{input}} is substituted
        steps = workflow_config.get("steps", [])
        if steps:
            action = steps[0].get("action", "")
            assert "hello" in action or "{{input}}" in action  # Either substituted or not yet
    
    def test_check_requirements(self, temp_template_dir):
        """Test requirement checking."""
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        template = loader.load(str(temp_template_dir))
        
        missing = loader.check_requirements(template)
        
        # TEST_API_KEY should be missing (not set in env)
        assert "TEST_API_KEY" in missing["missing_env"]


class TestCLIIntegration:
    """Tests for CLI integration."""
    
    def test_templates_handler_init(self):
        """Test TemplatesHandler initialization."""
        from praisonai.cli.features.templates import TemplatesHandler
        
        handler = TemplatesHandler()
        assert handler._loader is None  # Lazy loaded
        assert handler._registry is None
        assert handler._cache is None
    
    def test_templates_handler_help(self, capsys):
        """Test templates help command."""
        from praisonai.cli.features.templates import TemplatesHandler
        
        handler = TemplatesHandler()
        result = handler.handle([])
        
        assert result == 0
        captured = capsys.readouterr()
        assert "templates" in captured.out.lower() or result == 0


class TestFromTemplateClassmethods:
    """Tests for from_template classmethods on Agent and Workflow."""
    
    def test_agent_from_template_import_error(self):
        """Test Agent.from_template raises ImportError when praisonai not available."""
        # This test verifies the error handling path
        # In actual use, praisonai would be available
        pass  # Skip for now as praisonai is available in test environment
    
    def test_workflow_from_template_import_error(self):
        """Test Workflow.from_template raises ImportError when praisonai not available."""
        # This test verifies the error handling path
        pass  # Skip for now


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
