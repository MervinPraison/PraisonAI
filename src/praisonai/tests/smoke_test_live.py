#!/usr/bin/env python3
"""
Live Smoke Tests for PraisonAI Recipe System

These tests require real API keys and should NOT be run in CI by default.
Guard with: RUN_LIVE_TESTS=1

Usage:
    RUN_LIVE_TESTS=1 OPENAI_API_KEY=... python -m pytest tests/smoke_test_live.py -v
    
Or run directly:
    RUN_LIVE_TESTS=1 OPENAI_API_KEY=... python tests/smoke_test_live.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Skip all tests if RUN_LIVE_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="Live tests require RUN_LIVE_TESTS=1"
)


def require_openai_key():
    """Check that OPENAI_API_KEY is set."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY required for live tests")


class TestLiveRecipeExecution:
    """Live tests for recipe execution with real API keys."""
    
    @pytest.fixture
    def simple_recipe(self, tmp_path):
        """Create a simple recipe that uses OpenAI."""
        recipe_dir = tmp_path / "simple-llm-test"
        recipe_dir.mkdir()
        
        template = """
name: simple-llm-test
version: "1.0.0"
description: Simple LLM test recipe

requires:
  env:
    - OPENAI_API_KEY

config:
  input:
    prompt:
      type: string
      required: true
      description: Prompt to send to LLM

agents:
  - name: assistant
    role: Assistant
    goal: Answer the user's question
    backstory: You are a helpful assistant.
    llm:
      model: gpt-4o-mini
    tools: []
"""
        
        with open(recipe_dir / "TEMPLATE.yaml", "w") as f:
            f.write(template.strip())
        
        return recipe_dir
    
    def test_python_api_execution(self, simple_recipe):
        """Test recipe execution via Python API."""
        require_openai_key()
        
        # This would require the recipe to be discoverable
        # For now, test that the API is callable
        from praisonai import recipe
        
        # List recipes (should work without API key)
        recipes = recipe.list_recipes()
        assert isinstance(recipes, list)
        
        # Validate a recipe (dry run)
        # Note: This tests the API structure, not actual LLM execution
        result = recipe.validate("nonexistent-recipe")
        assert result is not None
        assert hasattr(result, "valid")
    
    def test_cli_list_command(self):
        """Test CLI list command."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.main", "recipe", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        assert result.returncode == 0
        # Should output valid JSON
        try:
            data = json.loads(result.stdout)
            assert "recipes" in data or isinstance(data, list)
        except json.JSONDecodeError:
            # May output non-JSON if no recipes found
            pass
    
    def test_cli_help_command(self):
        """Test CLI help command."""
        result = subprocess.run(
            [sys.executable, "-m", "praisonai.cli.main", "recipe", "help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0
        assert "praisonai recipe" in result.stdout.lower() or "praisonai recipe" in result.stdout


class TestLiveRegistryWorkflow:
    """Live tests for registry publish/pull workflow."""
    
    def test_local_registry_workflow(self, tmp_path):
        """Test full publish/pull workflow with local registry."""
        import tarfile
        import io
        
        # Create a test recipe bundle
        recipe_dir = tmp_path / "test-recipe"
        recipe_dir.mkdir()
        
        template = """
name: test-registry-recipe
version: "1.0.0"
description: Test recipe for registry
"""
        with open(recipe_dir / "TEMPLATE.yaml", "w") as f:
            f.write(template.strip())
        
        # Create bundle
        bundle_path = tmp_path / "test-registry-recipe-1.0.0.praison"
        with tarfile.open(bundle_path, "w:gz") as tar:
            manifest = {
                "name": "test-registry-recipe",
                "version": "1.0.0",
                "description": "Test recipe for registry",
                "files": [],
            }
            
            manifest_bytes = json.dumps(manifest, indent=2).encode()
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
            
            tar.add(recipe_dir / "TEMPLATE.yaml", arcname="TEMPLATE.yaml")
        
        # Create local registry
        registry_path = tmp_path / "registry"
        
        from praisonai.recipe.registry import LocalRegistry
        
        registry = LocalRegistry(registry_path)
        
        # Publish
        result = registry.publish(bundle_path)
        assert result["name"] == "test-registry-recipe"
        assert result["version"] == "1.0.0"
        
        # List
        recipes = registry.list_recipes()
        assert len(recipes) == 1
        assert recipes[0]["name"] == "test-registry-recipe"
        
        # Search
        results = registry.search("test")
        assert len(results) == 1
        
        # Pull
        output_dir = tmp_path / "pulled"
        registry.pull("test-registry-recipe", output_dir=output_dir)
        assert (output_dir / "test-registry-recipe").exists()
        
        # Verify pulled content
        assert (output_dir / "test-registry-recipe" / "TEMPLATE.yaml").exists()


class TestLiveRunHistory:
    """Live tests for run history storage."""
    
    def test_run_history_workflow(self, tmp_path):
        """Test run history store/list/export workflow."""
        from praisonai.recipe.history import RunHistory
        from praisonai.recipe.models import RecipeResult, RecipeStatus
        
        history = RunHistory(tmp_path / "runs")
        
        # Store a run
        result = RecipeResult(
            run_id="live-test-run-001",
            recipe="test-recipe",
            version="1.0.0",
            status=RecipeStatus.SUCCESS,
            output={"message": "Live test completed"},
            metrics={"duration_sec": 0.5},
            trace={"session_id": "live-test-session"},
        )
        
        run_id = history.store(result, input_data={"test": True})
        assert run_id == "live-test-run-001"
        
        # List runs
        runs = history.list_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == "live-test-run-001"
        
        # Get run
        run_data = history.get("live-test-run-001")
        assert run_data["recipe"] == "test-recipe"
        assert run_data["input"]["test"] is True
        
        # Export
        export_path = history.export("live-test-run-001", tmp_path / "export.json")
        assert export_path.exists()
        
        with open(export_path) as f:
            export_data = json.load(f)
        assert export_data["format"] == "praison-run-export"


class TestLiveSecurity:
    """Live tests for security features."""
    
    def test_sbom_generation(self, tmp_path):
        """Test SBOM generation."""
        from praisonai.recipe.security import generate_sbom
        
        # Create a recipe with dependencies
        recipe_dir = tmp_path / "sbom-test"
        recipe_dir.mkdir()
        
        import yaml
        template = {
            "name": "sbom-test",
            "version": "1.0.0",
            "requires": {"tools": ["web_search"]},
        }
        with open(recipe_dir / "TEMPLATE.yaml", "w") as f:
            yaml.dump(template, f)
        
        # Generate SBOM
        sbom = generate_sbom(recipe_dir, format="cyclonedx")
        
        assert sbom["bomFormat"] == "CycloneDX"
        assert len(sbom["components"]) > 0
    
    def test_pii_redaction(self, tmp_path):
        """Test PII redaction."""
        from praisonai.recipe.security import redact_pii, detect_pii
        
        data = {
            "email": "test@example.com",
            "phone": "555-123-4567",
            "message": "Contact me at user@domain.com",
        }
        
        # Detect
        detections = detect_pii(data)
        assert len(detections) >= 2
        
        # Redact
        policy = {"pii": {"mode": "redact", "fields": ["email", "phone"]}}
        redacted = redact_pii(data, policy)
        
        assert "[REDACTED:email]" in redacted["email"]
        assert "[REDACTED:phone]" in redacted["phone"]


class TestLivePolicy:
    """Live tests for policy packs."""
    
    def test_policy_workflow(self, tmp_path):
        """Test policy pack workflow."""
        from praisonai.recipe.policy import PolicyPack, get_default_policy, PolicyDeniedError
        
        # Get default policy
        policy = get_default_policy("dev")
        assert policy.name == "default-dev"
        
        # Check tool permissions
        assert policy.check_tool("web.search") is True
        
        with pytest.raises(PolicyDeniedError):
            policy.check_tool("shell.exec")
        
        # Save and load policy
        policy_file = tmp_path / "test-policy.yaml"
        policy.save(policy_file)
        
        loaded = PolicyPack.load(policy_file)
        assert loaded.name == policy.name


def run_smoke_tests():
    """Run smoke tests directly (not via pytest)."""
    print("=" * 60)
    print("PraisonAI Live Smoke Tests")
    print("=" * 60)
    
    if os.environ.get("RUN_LIVE_TESTS") != "1":
        print("\nSkipping: Set RUN_LIVE_TESTS=1 to run")
        return 0
    
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        tests = [
            ("Registry Workflow", TestLiveRegistryWorkflow().test_local_registry_workflow),
            ("Run History", TestLiveRunHistory().test_run_history_workflow),
            ("SBOM Generation", TestLiveSecurity().test_sbom_generation),
            ("PII Redaction", TestLiveSecurity().test_pii_redaction),
            ("Policy Workflow", TestLivePolicy().test_policy_workflow),
        ]
        
        passed = 0
        failed = 0
        
        for name, test_func in tests:
            try:
                print(f"\n[TEST] {name}...", end=" ")
                test_func(tmp_path)
                print("✓ PASSED")
                passed += 1
            except Exception as e:
                print(f"✗ FAILED: {e}")
                failed += 1
        
        print("\n" + "=" * 60)
        print(f"Results: {passed} passed, {failed} failed")
        print("=" * 60)
        
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_smoke_tests())
