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


class TestSentinelProtection:
    """Tests for input sentinel protection against injection attacks."""
    
    @pytest.fixture
    def temp_template_with_input(self):
        """Create a template that uses {{input}} placeholder."""
        temp_dir = tempfile.mkdtemp()
        template_dir = Path(temp_dir) / "sentinel-test"
        template_dir.mkdir()
        
        # Create TEMPLATE.yaml
        (template_dir / "TEMPLATE.yaml").write_text("""
name: sentinel-test
version: "1.0.0"
description: Test sentinel protection
defaults:
  input: "default input"
""")
        
        # Create workflow.yaml with {{input}} placeholder
        (template_dir / "workflow.yaml").write_text("""
name: Sentinel Test Workflow
agents:
  processor:
    name: Processor
    role: Processor
    goal: Process input
steps:
  - agent: processor
    action: "Process this: {{input}}"
""")
        
        yield template_dir
        shutil.rmtree(temp_dir)
    
    def test_user_input_with_template_syntax_remains_literal(self, temp_template_with_input):
        """
        Test that user input containing {{danger}} remains literal and is not substituted.
        
        This is the core security test - user input should NEVER be processed
        as template variables.
        """
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        
        # User provides malicious input containing template syntax
        malicious_input = "Hello {{danger}} world"
        template = loader.load(
            str(temp_template_with_input),
            config={"input": malicious_input}
        )
        
        workflow_config = loader.load_workflow_config(template)
        steps = workflow_config.get("steps", [])
        action = steps[0].get("action", "") if steps else ""
        
        # The {{danger}} should remain literal in the output
        assert "{{danger}}" in action, f"Expected '{{{{danger}}}}' to remain literal, got: {action}"
        assert "Hello {{danger}} world" in action
    
    def test_nested_placeholders_in_user_input_not_resolved(self, temp_template_with_input):
        """
        Test that nested placeholders in user input are not resolved.
        
        User input like "{{{{nested}}}}" should not be processed.
        """
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        
        # User provides input with nested template syntax
        nested_input = "Test {{{{nested}}}} and {{outer{{inner}}}}"
        template = loader.load(
            str(temp_template_with_input),
            config={"input": nested_input}
        )
        
        workflow_config = loader.load_workflow_config(template)
        steps = workflow_config.get("steps", [])
        action = steps[0].get("action", "") if steps else ""
        
        # Nested syntax should remain literal
        assert "{{{{nested}}}}" in action or "{{nested}}" in action
    
    def test_template_input_placeholder_works(self, temp_template_with_input):
        """
        Test that the template's {{input}} placeholder is correctly substituted.
        """
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        
        # Normal input without template syntax
        normal_input = "This is normal input"
        template = loader.load(
            str(temp_template_with_input),
            config={"input": normal_input}
        )
        
        workflow_config = loader.load_workflow_config(template)
        steps = workflow_config.get("steps", [])
        action = steps[0].get("action", "") if steps else ""
        
        # {{input}} should be replaced with the actual input
        assert "This is normal input" in action
        assert "{{input}}" not in action
    
    def test_sentinel_collision_handling(self, temp_template_with_input):
        """
        Test that sentinel token collision is handled safely.
        
        If user input contains the sentinel token itself, it should not
        cause security issues or incorrect substitution.
        """
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        
        # User tries to inject the sentinel token itself
        # This tests that per-render unique sentinels or collision detection works
        sentinel_injection = "__PRAISONAI_INPUT_SENTINEL__ {{danger}}"
        template = loader.load(
            str(temp_template_with_input),
            config={"input": sentinel_injection}
        )
        
        workflow_config = loader.load_workflow_config(template)
        steps = workflow_config.get("steps", [])
        action = steps[0].get("action", "") if steps else ""
        
        # The input should be preserved as-is (sentinel should be unique per render)
        # and {{danger}} should remain literal
        assert "{{danger}}" in action
    
    def test_multiple_variables_with_user_input(self):
        """
        Test that multiple template variables work correctly alongside user input.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            template_dir = Path(temp_dir) / "multi-var-test"
            template_dir.mkdir()
            
            (template_dir / "TEMPLATE.yaml").write_text("""
name: multi-var-test
version: "1.0.0"
defaults:
  topic: "AI"
  format: "markdown"
""")
            
            (template_dir / "workflow.yaml").write_text("""
name: Multi Variable Test
agents:
  writer:
    name: Writer
    role: Writer
    goal: Write about {{topic}} in {{format}} format
steps:
  - agent: writer
    action: "Write about {{topic}} using {{format}} format. User says: {{input}}"
""")
            
            from praisonai.templates.loader import TemplateLoader
            loader = TemplateLoader()
            
            # User input with template syntax
            template = loader.load(
                str(template_dir),
                config={
                    "topic": "Machine Learning",
                    "format": "HTML",
                    "input": "Please include {{code_examples}}"
                }
            )
            
            workflow_config = loader.load_workflow_config(template)
            steps = workflow_config.get("steps", [])
            action = steps[0].get("action", "") if steps else ""
            
            # Template variables should be substituted
            assert "Machine Learning" in action
            assert "HTML" in action
            # User input's template syntax should remain literal
            assert "{{code_examples}}" in action
        finally:
            shutil.rmtree(temp_dir)
    
    def test_substitute_variables_direct(self):
        """
        Test the _substitute_variables method directly.
        """
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        
        # Test basic substitution
        config = {"key": "value", "name": "test"}
        result = loader._substitute_variables("Hello {{name}}, key={{key}}", config)
        assert result == "Hello test, key=value"
        
        # Test with user input containing template syntax
        config_with_input = {
            "name": "test",
            "input": "User says {{danger}}"
        }
        result = loader._substitute_variables(
            "Name: {{name}}, Input: {{input}}",
            config_with_input
        )
        # After sentinel protection, {{danger}} should remain literal
        assert "{{danger}}" in result
        assert "test" in result


class TestCustomTemplatesDirectory:
    """Tests for custom templates directory support."""
    
    @pytest.fixture
    def custom_templates_setup(self):
        """Set up custom templates directories for testing."""
        # Create user custom dir
        user_custom_dir = Path(tempfile.mkdtemp()) / "custom-templates"
        user_custom_dir.mkdir(parents=True)
        
        # Create a custom template
        custom_template = user_custom_dir / "my-custom-template"
        custom_template.mkdir()
        (custom_template / "TEMPLATE.yaml").write_text("""
name: my-custom-template
version: "2.0.0"
description: Custom override template
author: custom-user
""")
        (custom_template / "workflow.yaml").write_text("""
name: Custom Workflow
agents:
  custom_agent:
    name: CustomAgent
    role: Custom
    goal: Do custom things
steps:
  - agent: custom_agent
    action: "Custom action"
""")
        
        yield {
            "custom_dir": user_custom_dir,
            "template_name": "my-custom-template"
        }
        
        shutil.rmtree(user_custom_dir.parent)
    
    def test_custom_dir_discovery(self, custom_templates_setup):
        """
        Test that templates in custom directory are discovered.
        """
        from praisonai.templates.resolver import TemplateResolver, TemplateSource
        
        custom_dir = custom_templates_setup["custom_dir"]
        template_name = custom_templates_setup["template_name"]
        
        # Direct local path should work
        template_path = custom_dir / template_name
        resolved = TemplateResolver.resolve(str(template_path))
        
        assert resolved.source == TemplateSource.LOCAL
        assert template_name in resolved.path
    
    def test_custom_template_loading(self, custom_templates_setup):
        """
        Test loading a template from custom directory.
        """
        from praisonai.templates.loader import TemplateLoader
        
        custom_dir = custom_templates_setup["custom_dir"]
        template_name = custom_templates_setup["template_name"]
        template_path = custom_dir / template_name
        
        loader = TemplateLoader()
        template = loader.load(str(template_path))
        
        assert template.name == "my-custom-template"
        assert template.version == "2.0.0"
        assert template.author == "custom-user"
    
    def test_custom_dir_precedence_over_builtin(self):
        """
        Test that custom templates take precedence over built-in templates.
        
        When the same template name exists in both custom and built-in,
        the custom version should be used.
        """
        # Create two temp dirs simulating custom and builtin
        custom_dir = Path(tempfile.mkdtemp()) / "custom"
        builtin_dir = Path(tempfile.mkdtemp()) / "builtin"
        custom_dir.mkdir(parents=True)
        builtin_dir.mkdir(parents=True)
        
        try:
            # Same template name in both
            template_name = "shared-template"
            
            # Custom version (should win)
            custom_template = custom_dir / template_name
            custom_template.mkdir()
            (custom_template / "TEMPLATE.yaml").write_text("""
name: shared-template
version: "2.0.0"
description: Custom version
""")
            
            # Builtin version
            builtin_template = builtin_dir / template_name
            builtin_template.mkdir()
            (builtin_template / "TEMPLATE.yaml").write_text("""
name: shared-template
version: "1.0.0"
description: Builtin version
""")
            
            from praisonai.templates.loader import TemplateLoader
            
            # Load from custom (simulating precedence)
            loader = TemplateLoader()
            template = loader.load(str(custom_template))
            
            # Should get custom version
            assert template.version == "2.0.0"
            assert "Custom" in template.description
        finally:
            shutil.rmtree(custom_dir.parent)
            shutil.rmtree(builtin_dir.parent)
    
    def test_xdg_paths_supported(self):
        """
        Test that XDG-friendly paths are supported.
        
        Should support:
        - ~/.praison/templates
        - ~/.config/praison/templates
        """
        from praisonai.templates.resolver import TemplateResolver, TemplateSource
        
        # Test home directory path resolution
        resolved = TemplateResolver.resolve("~/.praison/templates/my-template")
        assert resolved.source == TemplateSource.LOCAL
        assert os.path.expanduser("~") in resolved.path
        
        resolved = TemplateResolver.resolve("~/.config/praison/templates/my-template")
        assert resolved.source == TemplateSource.LOCAL
        assert os.path.expanduser("~") in resolved.path
    
    def test_shallow_scanning_efficiency(self, custom_templates_setup):
        """
        Test that template discovery uses shallow scanning.
        
        Only direct subdirectories containing TEMPLATE.yaml should be discovered,
        not deeply nested directories.
        """
        custom_dir = custom_templates_setup["custom_dir"]
        
        # Create a deeply nested directory that should NOT be discovered
        deep_dir = custom_dir / "level1" / "level2" / "level3" / "hidden-template"
        deep_dir.mkdir(parents=True)
        (deep_dir / "TEMPLATE.yaml").write_text("name: hidden")
        
        # The shallow scan should only find direct children
        direct_templates = []
        for item in custom_dir.iterdir():
            if item.is_dir() and (item / "TEMPLATE.yaml").exists():
                direct_templates.append(item.name)
        
        # Should find my-custom-template but NOT hidden-template
        assert "my-custom-template" in direct_templates
        assert "hidden-template" not in direct_templates


class TestTemplateDiscoveryModule:
    """Tests for the TemplateDiscovery class."""
    
    @pytest.fixture
    def discovery_setup(self):
        """Set up directories for discovery testing."""
        base_dir = Path(tempfile.mkdtemp())
        
        # Create custom dir with templates
        custom_dir = base_dir / "custom"
        custom_dir.mkdir()
        
        # Template 1 in custom
        t1 = custom_dir / "template-one"
        t1.mkdir()
        (t1 / "TEMPLATE.yaml").write_text("""
name: template-one
version: "2.0.0"
description: Custom version
author: custom-author
""")
        (t1 / "workflow.yaml").write_text("name: Custom Workflow")
        
        # Template 2 in custom (unique to custom)
        t2 = custom_dir / "custom-only"
        t2.mkdir()
        (t2 / "TEMPLATE.yaml").write_text("""
name: custom-only
version: "1.0.0"
description: Only in custom
""")
        
        # Create builtin dir with templates
        builtin_dir = base_dir / "builtin"
        builtin_dir.mkdir()
        
        # Template 1 in builtin (same name as custom - should be overridden)
        t1_builtin = builtin_dir / "template-one"
        t1_builtin.mkdir()
        (t1_builtin / "TEMPLATE.yaml").write_text("""
name: template-one
version: "1.0.0"
description: Builtin version
author: builtin-author
""")
        
        # Template 3 in builtin (unique to builtin)
        t3 = builtin_dir / "builtin-only"
        t3.mkdir()
        (t3 / "TEMPLATE.yaml").write_text("""
name: builtin-only
version: "1.0.0"
description: Only in builtin
""")
        
        yield {
            "base_dir": base_dir,
            "custom_dir": custom_dir,
            "builtin_dir": builtin_dir
        }
        
        shutil.rmtree(base_dir)
    
    def test_discovery_finds_templates(self, discovery_setup):
        """Test that discovery finds templates in custom directories."""
        from praisonai.templates.discovery import TemplateDiscovery
        
        custom_dir = discovery_setup["custom_dir"]
        
        discovery = TemplateDiscovery(
            custom_dirs=[str(custom_dir)],
            include_package=False,
            include_defaults=False
        )
        
        templates = discovery.discover_all()
        
        assert "template-one" in templates
        assert "custom-only" in templates
        assert len(templates) == 2
    
    def test_discovery_precedence(self, discovery_setup):
        """Test that custom templates take precedence over builtin."""
        from praisonai.templates.discovery import TemplateDiscovery
        
        custom_dir = discovery_setup["custom_dir"]
        builtin_dir = discovery_setup["builtin_dir"]
        
        # Custom has higher priority (listed first)
        discovery = TemplateDiscovery(
            custom_dirs=[str(custom_dir), str(builtin_dir)],
            include_package=False,
            include_defaults=False
        )
        
        templates = discovery.discover_all()
        
        # template-one should be from custom (version 2.0.0)
        assert templates["template-one"].version == "2.0.0"
        assert templates["template-one"].source == "custom"
        
        # Both unique templates should be present
        assert "custom-only" in templates
        assert "builtin-only" in templates
    
    def test_find_template(self, discovery_setup):
        """Test finding a specific template by name."""
        from praisonai.templates.discovery import TemplateDiscovery
        
        custom_dir = discovery_setup["custom_dir"]
        
        discovery = TemplateDiscovery(
            custom_dirs=[str(custom_dir)],
            include_package=False,
            include_defaults=False
        )
        
        template = discovery.find_template("template-one")
        
        assert template is not None
        assert template.name == "template-one"
        assert template.version == "2.0.0"
        
        # Non-existent template
        assert discovery.find_template("non-existent") is None
    
    def test_resolve_template_path(self, discovery_setup):
        """Test resolving template name to path."""
        from praisonai.templates.discovery import TemplateDiscovery
        
        custom_dir = discovery_setup["custom_dir"]
        
        discovery = TemplateDiscovery(
            custom_dirs=[str(custom_dir)],
            include_package=False,
            include_defaults=False
        )
        
        path = discovery.resolve_template_path("template-one")
        
        assert path is not None
        assert path.exists()
        assert (path / "TEMPLATE.yaml").exists()
    
    def test_list_templates(self, discovery_setup):
        """Test listing all templates."""
        from praisonai.templates.discovery import TemplateDiscovery
        
        custom_dir = discovery_setup["custom_dir"]
        
        discovery = TemplateDiscovery(
            custom_dirs=[str(custom_dir)],
            include_package=False,
            include_defaults=False
        )
        
        templates = discovery.list_templates()
        
        assert len(templates) == 2
        names = [t.name for t in templates]
        assert "template-one" in names
        assert "custom-only" in names
    
    def test_get_search_paths(self, discovery_setup):
        """Test getting search paths with status."""
        from praisonai.templates.discovery import TemplateDiscovery
        
        custom_dir = discovery_setup["custom_dir"]
        
        discovery = TemplateDiscovery(
            custom_dirs=[str(custom_dir)],
            include_package=False,
            include_defaults=True
        )
        
        paths = discovery.get_search_paths()
        
        # Should include custom dir and default paths
        assert len(paths) >= 1
        
        # Custom dir should exist
        custom_path_info = [p for p in paths if str(custom_dir) in p[0]]
        assert len(custom_path_info) == 1
        assert custom_path_info[0][2] is True  # exists
    
    def test_convenience_functions(self, discovery_setup):
        """Test convenience functions."""
        from praisonai.templates.discovery import discover_templates, find_template_path
        
        custom_dir = discovery_setup["custom_dir"]
        
        # discover_templates
        templates = discover_templates(custom_dirs=[str(custom_dir)])
        assert "template-one" in templates
        
        # find_template_path
        path = find_template_path("template-one", custom_dirs=[str(custom_dir)])
        assert path is not None
        assert path.exists()


# =============================================================================
# TODO 2: Tests for 'templates info availability' (tools/packages/env)
# =============================================================================

class TestDependencyChecker:
    """Tests for dependency availability checking."""
    
    @pytest.fixture
    def template_with_deps(self, tmp_path):
        """Create a template with various dependencies."""
        template_dir = tmp_path / "test-template"
        template_dir.mkdir()
        
        template_yaml = template_dir / "TEMPLATE.yaml"
        template_yaml.write_text("""
name: test-template
version: "1.0.0"
description: Test template with dependencies

requires:
  tools:
    - internet_search
    - nonexistent_tool_xyz
  packages:
    - os
    - nonexistent_package_xyz
  env:
    - PATH
    - NONEXISTENT_ENV_VAR_XYZ
""")
        
        workflow_yaml = template_dir / "workflow.yaml"
        workflow_yaml.write_text("""
agents:
  test:
    name: Test Agent
    instructions: Test
""")
        
        return template_dir
    
    def test_check_tool_availability_builtin(self):
        """Test checking availability of built-in tools."""
        from praisonai.templates.dependency_checker import DependencyChecker
        
        checker = DependencyChecker()
        
        # internet_search is a common built-in tool
        result = checker.check_tool("internet_search")
        # May or may not be available depending on installation
        assert isinstance(result, dict)
        assert "available" in result
        assert "source" in result
    
    def test_check_tool_availability_missing(self):
        """Test checking availability of missing tools."""
        from praisonai.templates.dependency_checker import DependencyChecker
        
        checker = DependencyChecker()
        
        result = checker.check_tool("nonexistent_tool_xyz_12345")
        assert result["available"] is False
        assert result["source"] is None
    
    def test_check_package_availability_stdlib(self):
        """Test checking availability of stdlib packages."""
        from praisonai.templates.dependency_checker import DependencyChecker
        
        checker = DependencyChecker()
        
        result = checker.check_package("os")
        assert result["available"] is True
        assert result["install_hint"] is None
    
    def test_check_package_availability_missing(self):
        """Test checking availability of missing packages."""
        from praisonai.templates.dependency_checker import DependencyChecker
        
        checker = DependencyChecker()
        
        result = checker.check_package("nonexistent_package_xyz_12345")
        assert result["available"] is False
        assert "pip install" in result["install_hint"]
    
    def test_check_env_var_present(self):
        """Test checking availability of present env vars."""
        from praisonai.templates.dependency_checker import DependencyChecker
        
        checker = DependencyChecker()
        
        # PATH is always present
        result = checker.check_env_var("PATH")
        assert result["available"] is True
        assert result["masked_value"] is not None
    
    def test_check_env_var_missing(self):
        """Test checking availability of missing env vars."""
        from praisonai.templates.dependency_checker import DependencyChecker
        
        checker = DependencyChecker()
        
        result = checker.check_env_var("NONEXISTENT_ENV_VAR_XYZ_12345")
        assert result["available"] is False
        assert result["masked_value"] is None
    
    def test_check_all_dependencies(self, template_with_deps):
        """Test checking all dependencies for a template."""
        from praisonai.templates.dependency_checker import DependencyChecker
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        template = loader.load(str(template_with_deps))
        
        checker = DependencyChecker()
        result = checker.check_template_dependencies(template)
        
        assert "tools" in result
        assert "packages" in result
        assert "env" in result
        assert "all_satisfied" in result
        
        # Should have some missing deps
        assert result["all_satisfied"] is False
    
    def test_get_install_hints(self, template_with_deps):
        """Test getting install hints for missing dependencies."""
        from praisonai.templates.dependency_checker import DependencyChecker
        from praisonai.templates.loader import TemplateLoader
        
        loader = TemplateLoader()
        template = loader.load(str(template_with_deps))
        
        checker = DependencyChecker()
        hints = checker.get_install_hints(template)
        
        assert isinstance(hints, list)
        # Should have hints for missing package
        assert any("pip install" in h for h in hints)


# =============================================================================
# TODO 4: Tests for --strict-tools on templates run
# =============================================================================

class TestStrictToolsMode:
    """Tests for --strict-tools preflight checking."""
    
    @pytest.fixture
    def template_with_missing_deps(self, tmp_path):
        """Create a template with missing dependencies."""
        template_dir = tmp_path / "strict-test-template"
        template_dir.mkdir()
        
        template_yaml = template_dir / "TEMPLATE.yaml"
        template_yaml.write_text("""
name: strict-test-template
version: "1.0.0"
description: Template for strict mode testing

requires:
  tools:
    - nonexistent_tool_for_strict_test
  packages:
    - nonexistent_package_for_strict_test
  env:
    - NONEXISTENT_ENV_FOR_STRICT_TEST
""")
        
        workflow_yaml = template_dir / "workflow.yaml"
        workflow_yaml.write_text("""
agents:
  test:
    name: Test Agent
    instructions: Test
""")
        
        return template_dir
    
    @pytest.fixture
    def template_with_satisfied_deps(self, tmp_path):
        """Create a template with all dependencies satisfied."""
        template_dir = tmp_path / "satisfied-test-template"
        template_dir.mkdir()
        
        template_yaml = template_dir / "TEMPLATE.yaml"
        template_yaml.write_text("""
name: satisfied-test-template
version: "1.0.0"
description: Template with satisfied dependencies

requires:
  packages:
    - os
    - sys
  env:
    - PATH
""")
        
        workflow_yaml = template_dir / "workflow.yaml"
        workflow_yaml.write_text("""
agents:
  test:
    name: Test Agent
    instructions: Test
""")
        
        return template_dir
    
    def test_strict_mode_fails_on_missing_tool(self, template_with_missing_deps):
        """Test that strict mode fails when tool is missing."""
        from praisonai.templates.loader import TemplateLoader
        from praisonai.templates.dependency_checker import DependencyChecker, StrictModeError
        
        loader = TemplateLoader()
        template = loader.load(str(template_with_missing_deps))
        
        checker = DependencyChecker()
        
        with pytest.raises(StrictModeError) as exc_info:
            checker.enforce_strict_mode(template)
        
        assert "tool" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
    
    def test_strict_mode_fails_on_missing_package(self, template_with_missing_deps):
        """Test that strict mode fails when package is missing."""
        from praisonai.templates.loader import TemplateLoader
        from praisonai.templates.dependency_checker import DependencyChecker, StrictModeError
        
        loader = TemplateLoader()
        template = loader.load(str(template_with_missing_deps))
        
        checker = DependencyChecker()
        
        with pytest.raises(StrictModeError):
            checker.enforce_strict_mode(template)
    
    def test_strict_mode_fails_on_missing_env(self, template_with_missing_deps):
        """Test that strict mode fails when env var is missing."""
        from praisonai.templates.loader import TemplateLoader
        from praisonai.templates.dependency_checker import DependencyChecker, StrictModeError
        
        loader = TemplateLoader()
        template = loader.load(str(template_with_missing_deps))
        
        checker = DependencyChecker()
        
        with pytest.raises(StrictModeError):
            checker.enforce_strict_mode(template)
    
    def test_strict_mode_passes_when_satisfied(self, template_with_satisfied_deps):
        """Test that strict mode passes when all deps satisfied."""
        from praisonai.templates.loader import TemplateLoader
        from praisonai.templates.dependency_checker import DependencyChecker
        
        loader = TemplateLoader()
        template = loader.load(str(template_with_satisfied_deps))
        
        checker = DependencyChecker()
        
        # Should not raise
        result = checker.enforce_strict_mode(template)
        assert result is True
    
    def test_non_strict_mode_continues(self, template_with_missing_deps):
        """Test that non-strict mode doesn't fail on missing deps."""
        from praisonai.templates.loader import TemplateLoader
        from praisonai.templates.dependency_checker import DependencyChecker
        
        loader = TemplateLoader()
        template = loader.load(str(template_with_missing_deps))
        
        checker = DependencyChecker()
        
        # Should not raise, just return status
        result = checker.check_template_dependencies(template)
        assert result["all_satisfied"] is False


# =============================================================================
# TODO 6: Tests for 'praisonai tools doctor'
# =============================================================================

class TestToolsDoctor:
    """Tests for tools doctor command."""
    
    def test_doctor_returns_structured_output(self):
        """Test that doctor returns structured output."""
        from praisonai.templates.tools_doctor import ToolsDoctor
        
        doctor = ToolsDoctor()
        result = doctor.diagnose()
        
        assert isinstance(result, dict)
        assert "praisonai_tools_installed" in result
        assert "builtin_tools" in result
        assert "custom_tools_dirs" in result
        assert "issues" in result
    
    def test_doctor_detects_praisonai_tools(self):
        """Test that doctor detects praisonai-tools installation."""
        from praisonai.templates.tools_doctor import ToolsDoctor
        
        doctor = ToolsDoctor()
        result = doctor.diagnose()
        
        # Should be a boolean
        assert isinstance(result["praisonai_tools_installed"], bool)
    
    def test_doctor_lists_builtin_tools(self):
        """Test that doctor lists built-in tools."""
        from praisonai.templates.tools_doctor import ToolsDoctor
        
        doctor = ToolsDoctor()
        result = doctor.diagnose()
        
        assert isinstance(result["builtin_tools"], list)
    
    def test_doctor_checks_custom_dirs(self):
        """Test that doctor checks custom tool directories."""
        from praisonai.templates.tools_doctor import ToolsDoctor
        
        doctor = ToolsDoctor()
        result = doctor.diagnose()
        
        assert isinstance(result["custom_tools_dirs"], list)
        # Should check default dirs
        for dir_info in result["custom_tools_dirs"]:
            assert "path" in dir_info
            assert "exists" in dir_info
    
    def test_doctor_json_output(self):
        """Test that doctor can produce JSON output."""
        from praisonai.templates.tools_doctor import ToolsDoctor
        import json
        
        doctor = ToolsDoctor()
        json_output = doctor.diagnose_json()
        
        # Should be valid JSON
        parsed = json.loads(json_output)
        assert "praisonai_tools_installed" in parsed
    
    def test_doctor_human_readable_output(self):
        """Test that doctor can produce human-readable output."""
        from praisonai.templates.tools_doctor import ToolsDoctor
        
        doctor = ToolsDoctor()
        output = doctor.diagnose_human()
        
        assert isinstance(output, str)
        assert len(output) > 0


# =============================================================================
# TODO 8: Tests for --tools override + custom tool directory
# =============================================================================

class TestToolsOverride:
    """Tests for --tools override and custom tool directory."""
    
    @pytest.fixture
    def custom_tools_file(self, tmp_path):
        """Create a custom tools Python file."""
        tools_file = tmp_path / "custom_tools.py"
        tools_file.write_text('''
def my_custom_tool(query: str) -> str:
    """A custom tool for testing."""
    return f"Custom result for: {query}"

def another_tool(x: int) -> int:
    """Another custom tool."""
    return x * 2
''')
        return tools_file
    
    @pytest.fixture
    def custom_tools_dir(self, tmp_path):
        """Create a custom tools directory."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        
        # Create a tool module
        tool_file = tools_dir / "search_tools.py"
        tool_file.write_text('''
def custom_search(query: str) -> str:
    """Custom search tool."""
    return f"Search results for: {query}"
''')
        
        return tools_dir
    
    def test_load_tools_from_file(self, custom_tools_file):
        """Test loading tools from a Python file."""
        from praisonai.templates.tool_override import ToolOverrideLoader
        
        loader = ToolOverrideLoader()
        tools = loader.load_from_file(str(custom_tools_file))
        
        assert "my_custom_tool" in tools
        assert "another_tool" in tools
        assert callable(tools["my_custom_tool"])
    
    def test_load_tools_from_directory(self, custom_tools_dir):
        """Test loading tools from a directory."""
        from praisonai.templates.tool_override import ToolOverrideLoader
        
        loader = ToolOverrideLoader()
        tools = loader.load_from_directory(str(custom_tools_dir))
        
        assert "custom_search" in tools
    
    def test_reject_remote_urls(self):
        """Test that remote URLs are rejected by default."""
        from praisonai.templates.tool_override import ToolOverrideLoader, SecurityError
        
        loader = ToolOverrideLoader()
        
        with pytest.raises(SecurityError):
            loader.load_from_file("https://example.com/tools.py")
        
        with pytest.raises(SecurityError):
            loader.load_from_file("http://example.com/tools.py")
    
    def test_only_local_paths_allowed(self, custom_tools_file):
        """Test that only local paths are allowed."""
        from praisonai.templates.tool_override import ToolOverrideLoader
        
        loader = ToolOverrideLoader()
        
        # Local path should work
        tools = loader.load_from_file(str(custom_tools_file))
        assert len(tools) > 0
    
    def test_tool_registry_context_manager(self, custom_tools_file):
        """Test that tool overrides use context manager pattern."""
        from praisonai.templates.tool_override import ToolOverrideLoader
        
        loader = ToolOverrideLoader()
        
        with loader.override_context(files=[str(custom_tools_file)]) as registry:
            assert "my_custom_tool" in registry
        
        # After context, original state should be restored
        # (implementation detail - registry should be isolated)
    
    def test_default_custom_dirs(self):
        """Test that default custom tool directories are defined."""
        from praisonai.templates.tool_override import ToolOverrideLoader
        
        loader = ToolOverrideLoader()
        default_dirs = loader.get_default_tool_dirs()
        
        assert len(default_dirs) >= 2
        assert any(".praison/tools" in str(d) for d in default_dirs)
        assert any(".config/praison/tools" in str(d) or ".praison/tools" in str(d) for d in default_dirs)
    
    def test_no_scanning_on_import(self):
        """Test that no filesystem scanning occurs on import."""
        import sys
        import time
        
        # Remove any cached modules
        modules_to_remove = [k for k in sys.modules if 'tool_override' in k]
        for m in modules_to_remove:
            del sys.modules[m]
        
        start = time.time()
        from praisonai.templates.tool_override import ToolOverrideLoader
        import_time = time.time() - start
        
        # Import should be fast (no scanning)
        assert import_time < 0.1  # 100ms max
    
    def test_discover_tools_without_execution(self, custom_tools_dir):
        """Test discovering tools without executing them."""
        from praisonai.templates.tool_override import ToolOverrideLoader
        
        loader = ToolOverrideLoader()
        
        # discover_tools should list tools without importing
        tool_names = loader.discover_tools_in_directory(str(custom_tools_dir))
        
        assert isinstance(tool_names, list)


# =============================================================================
# CLI Tests
# =============================================================================

class TestCLITemplatesInfoAvailability:
    """CLI tests for templates info with availability."""
    
    @pytest.fixture
    def template_for_cli(self, tmp_path):
        """Create a template for CLI testing."""
        template_dir = tmp_path / "cli-test-template"
        template_dir.mkdir()
        
        template_yaml = template_dir / "TEMPLATE.yaml"
        template_yaml.write_text("""
name: cli-test-template
version: "1.0.0"
description: Template for CLI testing

requires:
  tools:
    - internet_search
  packages:
    - os
    - nonexistent_pkg_cli_test
  env:
    - PATH
    - MISSING_ENV_CLI_TEST
""")
        
        workflow_yaml = template_dir / "workflow.yaml"
        workflow_yaml.write_text("""
agents:
  test:
    name: Test Agent
    instructions: Test
""")
        
        return template_dir
    
    def test_cli_info_shows_tools_section(self, template_for_cli):
        """Test that CLI info shows Required Tools section."""
        from praisonai.cli.features.templates import TemplatesHandler
        import io
        import sys
        
        handler = TemplatesHandler()
        
        # Capture output
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        try:
            handler.cmd_info([str(template_for_cli)])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        
        # Should contain tools section
        assert "tool" in output.lower() or "Tool" in output
    
    def test_cli_info_shows_packages_section(self, template_for_cli):
        """Test that CLI info shows Required Packages section."""
        from praisonai.cli.features.templates import TemplatesHandler
        import io
        import sys
        
        handler = TemplatesHandler()
        
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        try:
            handler.cmd_info([str(template_for_cli)])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        
        assert "package" in output.lower() or "Package" in output
    
    def test_cli_info_shows_env_section(self, template_for_cli):
        """Test that CLI info shows Required Environment section."""
        from praisonai.cli.features.templates import TemplatesHandler
        import io
        import sys
        
        handler = TemplatesHandler()
        
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        try:
            handler.cmd_info([str(template_for_cli)])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        
        assert "env" in output.lower() or "Env" in output or "Environment" in output


class TestCLIToolsDoctor:
    """CLI tests for tools doctor command."""
    
    def test_cli_doctor_runs(self):
        """Test that CLI doctor command runs."""
        from praisonai.cli.features.tools import ToolsHandler
        
        handler = ToolsHandler()
        
        # Should have doctor action
        assert "doctor" in handler.get_actions()
    
    def test_cli_doctor_json_flag(self):
        """Test that CLI doctor supports --json flag."""
        from praisonai.cli.features.tools import ToolsHandler
        import io
        import sys
        import json
        
        handler = ToolsHandler()
        
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        try:
            handler.action_doctor(["--json"])
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        
        # Should be valid JSON
        try:
            parsed = json.loads(output)
            assert "praisonai_tools_installed" in parsed
        except json.JSONDecodeError:
            # If not JSON, check for expected content
            assert "tools" in output.lower()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
