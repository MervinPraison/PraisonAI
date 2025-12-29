"""
Tests for Recipe Registry, History, Security, and Policy modules.
"""

import json
import tarfile

import pytest


# ============================================================================
# Registry Tests
# ============================================================================

class TestLocalRegistry:
    """Tests for LocalRegistry."""
    
    @pytest.fixture
    def temp_registry(self, tmp_path):
        """Create a temporary registry."""
        from praisonai.recipe.registry import LocalRegistry
        return LocalRegistry(tmp_path / "registry")
    
    @pytest.fixture
    def sample_bundle(self, tmp_path):
        """Create a sample bundle for testing."""
        bundle_path = tmp_path / "test-recipe-1.0.0.praison"
        
        with tarfile.open(bundle_path, "w:gz") as tar:
            # Create manifest
            manifest = {
                "name": "test-recipe",
                "version": "1.0.0",
                "description": "Test recipe",
                "tags": ["test", "example"],
                "files": [],
            }
            
            import io
            manifest_bytes = json.dumps(manifest, indent=2).encode()
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
            
            # Add a dummy file
            content = b"# Test Recipe\nprint('hello')"
            file_info = tarfile.TarInfo(name="main.py")
            file_info.size = len(content)
            tar.addfile(file_info, io.BytesIO(content))
        
        return bundle_path
    
    def test_publish_and_pull(self, temp_registry, sample_bundle, tmp_path):
        """Test publishing and pulling a recipe."""
        # Publish
        result = temp_registry.publish(sample_bundle)
        
        assert result["name"] == "test-recipe"
        assert result["version"] == "1.0.0"
        assert "checksum" in result
        
        # Pull
        output_dir = tmp_path / "pulled"
        pull_result = temp_registry.pull("test-recipe", output_dir=output_dir)
        
        assert pull_result["name"] == "test-recipe"
        assert pull_result["version"] == "1.0.0"
        assert (output_dir / "test-recipe").exists()
    
    def test_list_recipes(self, temp_registry, sample_bundle):
        """Test listing recipes."""
        temp_registry.publish(sample_bundle)
        
        recipes = temp_registry.list_recipes()
        assert len(recipes) == 1
        assert recipes[0]["name"] == "test-recipe"
    
    def test_search_recipes(self, temp_registry, sample_bundle):
        """Test searching recipes."""
        temp_registry.publish(sample_bundle)
        
        # Search by name
        results = temp_registry.search("test")
        assert len(results) == 1
        
        # Search by tag
        results = temp_registry.search("example")
        assert len(results) == 1
        
        # Search with no match
        results = temp_registry.search("nonexistent")
        assert len(results) == 0
    
    def test_get_versions(self, temp_registry, sample_bundle, tmp_path):
        """Test getting versions."""
        temp_registry.publish(sample_bundle)
        
        versions = temp_registry.get_versions("test-recipe")
        assert "1.0.0" in versions
    
    def test_publish_duplicate_fails(self, temp_registry, sample_bundle):
        """Test that publishing duplicate version fails without force."""
        temp_registry.publish(sample_bundle)
        
        from praisonai.recipe.registry import RecipeExistsError
        with pytest.raises(RecipeExistsError):
            temp_registry.publish(sample_bundle)
    
    def test_publish_force_overwrites(self, temp_registry, sample_bundle):
        """Test that force=True overwrites existing version."""
        temp_registry.publish(sample_bundle)
        result = temp_registry.publish(sample_bundle, force=True)
        
        assert result["name"] == "test-recipe"
    
    def test_delete_recipe(self, temp_registry, sample_bundle):
        """Test deleting a recipe."""
        temp_registry.publish(sample_bundle)
        
        temp_registry.delete("test-recipe")
        
        recipes = temp_registry.list_recipes()
        assert len(recipes) == 0


# ============================================================================
# Run History Tests
# ============================================================================

class TestRunHistory:
    """Tests for RunHistory."""
    
    @pytest.fixture
    def temp_history(self, tmp_path):
        """Create a temporary history storage."""
        from praisonai.recipe.history import RunHistory
        return RunHistory(tmp_path / "runs")
    
    @pytest.fixture
    def sample_result(self):
        """Create a sample RecipeResult."""
        from praisonai.recipe.models import RecipeResult, RecipeStatus
        return RecipeResult(
            run_id="run-test123",
            recipe="test-recipe",
            version="1.0.0",
            status=RecipeStatus.SUCCESS,
            output={"result": "hello"},
            metrics={"duration_sec": 1.5},
            trace={"session_id": "session-abc"},
        )
    
    def test_store_and_get(self, temp_history, sample_result):
        """Test storing and retrieving a run."""
        run_id = temp_history.store(
            result=sample_result,
            input_data={"query": "test"},
        )
        
        assert run_id == "run-test123"
        
        # Retrieve
        run_data = temp_history.get(run_id)
        assert run_data["recipe"] == "test-recipe"
        assert run_data["status"] == "success"
        assert run_data["input"]["query"] == "test"
    
    def test_list_runs(self, temp_history, sample_result):
        """Test listing runs."""
        temp_history.store(result=sample_result)
        
        runs = temp_history.list_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run-test123"
    
    def test_list_runs_filter_by_recipe(self, temp_history, sample_result):
        """Test filtering runs by recipe."""
        temp_history.store(result=sample_result)
        
        runs = temp_history.list_runs(recipe="test-recipe")
        assert len(runs) == 1
        
        runs = temp_history.list_runs(recipe="other-recipe")
        assert len(runs) == 0
    
    def test_export_run(self, temp_history, sample_result, tmp_path):
        """Test exporting a run."""
        temp_history.store(result=sample_result, input_data={"query": "test"})
        
        export_path = temp_history.export("run-test123", tmp_path / "export.json")
        
        assert export_path.exists()
        
        with open(export_path) as f:
            export_data = json.load(f)
        
        assert export_data["format"] == "praison-run-export"
        assert export_data["run"]["run_id"] == "run-test123"
    
    def test_delete_run(self, temp_history, sample_result):
        """Test deleting a run."""
        temp_history.store(result=sample_result)
        
        temp_history.delete("run-test123")
        
        runs = temp_history.list_runs()
        assert len(runs) == 0
    
    def test_get_stats(self, temp_history, sample_result):
        """Test getting storage stats."""
        temp_history.store(result=sample_result)
        
        stats = temp_history.get_stats()
        assert stats["total_runs"] == 1
        assert stats["total_size_bytes"] > 0


# ============================================================================
# Security Tests
# ============================================================================

class TestSBOM:
    """Tests for SBOM generation."""
    
    @pytest.fixture
    def sample_recipe(self, tmp_path):
        """Create a sample recipe directory."""
        recipe_dir = tmp_path / "test-recipe"
        recipe_dir.mkdir()
        
        # Create TEMPLATE.yaml
        template = {
            "name": "test-recipe",
            "version": "1.0.0",
            "requires": {
                "tools": ["web_search"],
                "external": ["ffmpeg"],
            },
        }
        
        import yaml
        with open(recipe_dir / "TEMPLATE.yaml", "w") as f:
            yaml.dump(template, f)
        
        # Create lock directory with requirements
        lock_dir = recipe_dir / "lock"
        lock_dir.mkdir()
        
        with open(lock_dir / "requirements.lock", "w") as f:
            f.write("openai==1.0.0\n")
            f.write("requests==2.31.0\n")
        
        return recipe_dir
    
    def test_generate_cyclonedx_sbom(self, sample_recipe):
        """Test generating CycloneDX SBOM."""
        from praisonai.recipe.security import generate_sbom
        
        sbom = generate_sbom(sample_recipe, format="cyclonedx")
        
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.4"
        assert len(sbom["components"]) > 0
    
    def test_generate_spdx_sbom(self, sample_recipe):
        """Test generating SPDX SBOM."""
        from praisonai.recipe.security import generate_sbom
        
        sbom = generate_sbom(sample_recipe, format="spdx")
        
        assert sbom["spdxVersion"] == "SPDX-2.3"
        assert len(sbom["packages"]) > 0


class TestLockfileValidation:
    """Tests for lockfile validation."""
    
    def test_validate_with_lockfile(self, tmp_path):
        """Test validation with lockfile present."""
        from praisonai.recipe.security import validate_lockfile
        
        recipe_dir = tmp_path / "recipe"
        recipe_dir.mkdir()
        lock_dir = recipe_dir / "lock"
        lock_dir.mkdir()
        
        with open(lock_dir / "requirements.lock", "w") as f:
            f.write("openai==1.0.0\n")
        
        result = validate_lockfile(recipe_dir)
        
        assert result["valid"] is True
        assert result["lockfile_type"] == "pip"
    
    def test_validate_without_lockfile_strict(self, tmp_path):
        """Test strict validation without lockfile."""
        from praisonai.recipe.security import validate_lockfile
        
        recipe_dir = tmp_path / "recipe"
        recipe_dir.mkdir()
        
        result = validate_lockfile(recipe_dir, strict=True)
        
        assert result["valid"] is False
        assert "No lockfile found" in result["errors"][0]


class TestAudit:
    """Tests for dependency auditing."""
    
    def test_audit_dependencies(self, tmp_path):
        """Test auditing dependencies."""
        from praisonai.recipe.security import audit_dependencies
        
        recipe_dir = tmp_path / "recipe"
        recipe_dir.mkdir()
        
        report = audit_dependencies(recipe_dir)
        
        assert "audited_at" in report
        assert "warnings" in report


class TestPIIRedaction:
    """Tests for PII redaction."""
    
    def test_redact_email(self):
        """Test redacting email addresses."""
        from praisonai.recipe.security import redact_pii
        
        data = {"message": "Contact me at test@example.com"}
        policy = {"pii": {"mode": "redact", "fields": ["email"]}}
        
        result = redact_pii(data, policy)
        
        assert "[REDACTED:email]" in result["message"]
        assert "test@example.com" not in result["message"]
    
    def test_redact_phone(self):
        """Test redacting phone numbers."""
        from praisonai.recipe.security import redact_pii
        
        data = {"phone": "123-456-7890"}
        policy = {"pii": {"mode": "redact", "fields": ["phone"]}}
        
        result = redact_pii(data, policy)
        
        assert "[REDACTED:phone]" in result["phone"]
    
    def test_detect_pii(self):
        """Test detecting PII without redacting."""
        from praisonai.recipe.security import detect_pii
        
        data = {
            "email": "test@example.com",
            "nested": {"phone": "123-456-7890"},
        }
        
        detections = detect_pii(data)
        
        assert len(detections) >= 2
        assert any(d["type"] == "email" for d in detections)
        assert any(d["type"] == "phone" for d in detections)


# ============================================================================
# Policy Tests
# ============================================================================

class TestPolicyPack:
    """Tests for PolicyPack."""
    
    def test_default_policy(self):
        """Test default policy."""
        from praisonai.recipe.policy import get_default_policy
        
        policy = get_default_policy("dev")
        
        assert policy.name == "default-dev"
        assert "shell.exec" in policy.denied_tools
    
    def test_check_tool_allowed(self):
        """Test checking allowed tool."""
        from praisonai.recipe.policy import PolicyPack
        
        policy = PolicyPack(config={
            "tools": {"allow": ["web.search"], "deny": []},
        })
        
        assert policy.check_tool("web.search") is True
    
    def test_check_tool_denied(self):
        """Test checking denied tool."""
        from praisonai.recipe.policy import PolicyPack, PolicyDeniedError
        
        policy = PolicyPack(config={
            "tools": {"allow": [], "deny": ["shell.exec"]},
        })
        
        with pytest.raises(PolicyDeniedError):
            policy.check_tool("shell.exec")
    
    def test_load_policy_from_file(self, tmp_path):
        """Test loading policy from file."""
        from praisonai.recipe.policy import PolicyPack
        
        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text("""
name: test-policy
tools:
  allow:
    - web.search
  deny:
    - shell.exec
pii:
  mode: redact
  fields:
    - email
""")
        
        policy = PolicyPack.load(policy_file)
        
        assert policy.name == "test-policy"
        assert "web.search" in policy.allowed_tools
        assert policy.pii_mode == "redact"
    
    def test_save_policy(self, tmp_path):
        """Test saving policy to file."""
        from praisonai.recipe.policy import PolicyPack
        
        policy = PolicyPack(name="test", config={
            "tools": {"allow": ["web.search"]},
        })
        
        output_path = tmp_path / "output.yaml"
        policy.save(output_path)
        
        assert output_path.exists()
        
        # Reload and verify
        loaded = PolicyPack.load(output_path)
        assert "web.search" in loaded.allowed_tools


# ============================================================================
# CLI Tests
# ============================================================================

class TestRecipeCLI:
    """Tests for recipe CLI commands."""
    
    def test_publish_help(self):
        """Test publish command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_publish")
    
    def test_pull_help(self):
        """Test pull command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_pull")
    
    def test_sbom_help(self):
        """Test sbom command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_sbom")
    
    def test_audit_help(self):
        """Test audit command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_audit")
    
    def test_sign_help(self):
        """Test sign command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_sign")
    
    def test_verify_help(self):
        """Test verify command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_verify")
    
    def test_runs_help(self):
        """Test runs command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_runs")
    
    def test_policy_help(self):
        """Test policy command exists."""
        from praisonai.cli.features.recipe import RecipeHandler
        
        handler = RecipeHandler()
        assert hasattr(handler, "cmd_policy")


# ============================================================================
# Integration Tests
# ============================================================================

class TestRegistryIntegration:
    """Integration tests for registry workflow."""
    
    def test_full_publish_pull_workflow(self, tmp_path):
        """Test complete publish and pull workflow."""
        from praisonai.recipe.registry import LocalRegistry
        
        # Create registry
        registry = LocalRegistry(tmp_path / "registry")
        
        # Create a recipe directory
        recipe_dir = tmp_path / "my-recipe"
        recipe_dir.mkdir()
        
        import yaml
        with open(recipe_dir / "TEMPLATE.yaml", "w") as f:
            yaml.dump({
                "name": "my-recipe",
                "version": "1.0.0",
                "description": "My test recipe",
            }, f)
        
        with open(recipe_dir / "main.py", "w") as f:
            f.write("print('hello')")
        
        # Pack the recipe
        bundle_path = tmp_path / "my-recipe-1.0.0.praison"
        with tarfile.open(bundle_path, "w:gz") as tar:
            manifest = {
                "name": "my-recipe",
                "version": "1.0.0",
                "description": "My test recipe",
                "files": [],
            }
            
            import io
            manifest_bytes = json.dumps(manifest, indent=2).encode()
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
            
            for f in recipe_dir.iterdir():
                tar.add(f, arcname=f.name)
        
        # Publish
        pub_result = registry.publish(bundle_path)
        assert pub_result["name"] == "my-recipe"
        
        # List
        recipes = registry.list_recipes()
        assert len(recipes) == 1
        
        # Pull
        output_dir = tmp_path / "pulled"
        registry.pull("my-recipe", output_dir=output_dir)
        assert (output_dir / "my-recipe").exists()
