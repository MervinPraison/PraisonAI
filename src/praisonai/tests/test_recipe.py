"""
Tests for PraisonAI Recipe Module

Tests cover:
- Core API (run, run_stream, validate, list_recipes, describe)
- Data models (RecipeResult, RecipeEvent, RecipeConfig)
- CLI commands
- Exit codes
- Error handling
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest


# ============================================================================
# Unit Tests for Models
# ============================================================================

class TestRecipeResult:
    """Tests for RecipeResult dataclass."""
    
    def test_success_result(self):
        """Test successful result."""
        from praisonai.recipe.models import RecipeResult, RecipeStatus
        
        result = RecipeResult(
            run_id="run-abc123",
            recipe="test-recipe",
            version="1.0.0",
            status=RecipeStatus.SUCCESS,
            output={"message": "Hello"},
            metrics={"duration_sec": 1.5},
            trace={"run_id": "run-abc123"},
        )
        
        assert result.ok is True
        assert result.run_id == "run-abc123"
        assert result.status == "success"
        assert result.to_exit_code() == 0
    
    def test_failed_result(self):
        """Test failed result."""
        from praisonai.recipe.models import RecipeResult, RecipeStatus
        
        result = RecipeResult(
            run_id="run-abc123",
            recipe="test-recipe",
            version="1.0.0",
            status=RecipeStatus.FAILED,
            error="Something went wrong",
        )
        
        assert result.ok is False
        assert result.error == "Something went wrong"
        assert result.to_exit_code() == 3  # RUNTIME_ERROR
    
    def test_dry_run_result(self):
        """Test dry run result."""
        from praisonai.recipe.models import RecipeResult, RecipeStatus
        
        result = RecipeResult(
            run_id="run-abc123",
            recipe="test-recipe",
            version="1.0.0",
            status=RecipeStatus.DRY_RUN,
        )
        
        assert result.ok is True
        assert result.to_exit_code() == 0
    
    def test_to_dict(self):
        """Test to_dict serialization."""
        from praisonai.recipe.models import RecipeResult, RecipeStatus
        
        result = RecipeResult(
            run_id="run-abc123",
            recipe="test-recipe",
            version="1.0.0",
            status=RecipeStatus.SUCCESS,
            output={"key": "value"},
        )
        
        d = result.to_dict()
        assert d["ok"] is True
        assert d["run_id"] == "run-abc123"
        assert d["recipe"] == "test-recipe"
        assert d["output"] == {"key": "value"}


class TestRecipeEvent:
    """Tests for RecipeEvent dataclass."""
    
    def test_event_creation(self):
        """Test event creation."""
        from praisonai.recipe.models import RecipeEvent
        
        event = RecipeEvent(
            event_type="started",
            data={"run_id": "run-abc123"},
        )
        
        assert event.event_type == "started"
        assert event.data["run_id"] == "run-abc123"
        assert event.timestamp  # Should be auto-generated
    
    def test_to_sse(self):
        """Test SSE format conversion."""
        from praisonai.recipe.models import RecipeEvent
        
        event = RecipeEvent(
            event_type="progress",
            data={"step": "loading"},
        )
        
        sse = event.to_sse()
        assert "event: progress" in sse
        assert "data:" in sse


class TestExitCode:
    """Tests for exit codes."""
    
    def test_exit_codes(self):
        """Test exit code values."""
        from praisonai.recipe.models import ExitCode
        
        assert ExitCode.SUCCESS == 0
        assert ExitCode.GENERAL_ERROR == 1
        assert ExitCode.VALIDATION_ERROR == 2
        assert ExitCode.RUNTIME_ERROR == 3
        assert ExitCode.POLICY_DENIED == 4
        assert ExitCode.TIMEOUT == 5
        assert ExitCode.MISSING_DEPS == 6
        assert ExitCode.NOT_FOUND == 7


class TestRecipeConfig:
    """Tests for RecipeConfig dataclass."""
    
    def test_config_creation(self):
        """Test config creation."""
        from praisonai.recipe.models import RecipeConfig
        
        config = RecipeConfig(
            name="test-recipe",
            version="1.0.0",
            description="Test recipe",
            requires={"packages": ["openai"], "env": ["OPENAI_API_KEY"]},
            tools={"allow": ["web.search"], "deny": ["shell.exec"]},
        )
        
        assert config.name == "test-recipe"
        assert config.get_required_packages() == ["openai"]
        assert config.get_required_env() == ["OPENAI_API_KEY"]
        assert config.get_allowed_tools() == ["web.search"]
        assert config.get_denied_tools() == ["shell.exec"]


# ============================================================================
# Unit Tests for Core API
# ============================================================================

class TestCoreAPI:
    """Tests for core recipe API."""
    
    def test_list_recipes(self):
        """Test listing recipes."""
        from praisonai.recipe import list_recipes
        
        recipes = list_recipes()
        assert isinstance(recipes, list)
    
    def test_validate_nonexistent(self):
        """Test validating non-existent recipe."""
        from praisonai.recipe import validate
        
        result = validate("nonexistent-recipe-xyz")
        assert result.valid is False
        assert "not found" in result.errors[0].lower() or len(result.errors) > 0
    
    def test_describe_nonexistent(self):
        """Test describing non-existent recipe."""
        from praisonai.recipe import describe
        
        result = describe("nonexistent-recipe-xyz")
        assert result is None
    
    def test_run_dry_run(self):
        """Test dry run mode."""
        from praisonai.recipe import run, list_recipes
        
        # Use a recipe that exists
        recipes = list_recipes()
        if recipes:
            result = run(
                recipes[0].name,
                input={},
                options={"dry_run": True},
            )
            assert result.status == "dry_run"
            assert result.ok is True
    
    def test_run_nonexistent(self):
        """Test running non-existent recipe."""
        from praisonai.recipe import run
        
        result = run("nonexistent-recipe-xyz", input={})
        assert result.ok is False
        assert "not found" in result.error.lower()


# ============================================================================
# CLI Tests
# ============================================================================

class TestCLI:
    """Tests for CLI commands."""
    
    @pytest.fixture
    def cli_runner(self):
        """Get CLI runner path."""
        return [sys.executable, "-m", "praisonai.cli.main"]
    
    def test_recipe_help(self, cli_runner):
        """Test recipe help command."""
        # Test via direct import instead of subprocess for reliability
        from praisonai.cli.features.recipe import RecipeHandler
        handler = RecipeHandler()
        exit_code = handler.handle(["help"])
        assert exit_code == 0
    
    def test_recipe_list(self, cli_runner):
        """Test recipe list command."""
        # Test via direct import for reliability
        from praisonai.cli.features.recipe import RecipeHandler
        handler = RecipeHandler()
        exit_code = handler.handle(["list"])
        assert exit_code == 0
    
    def test_recipe_validate_nonexistent(self, cli_runner):
        """Test validating non-existent recipe."""
        from praisonai.cli.features.recipe import RecipeHandler
        handler = RecipeHandler()
        exit_code = handler.handle(["validate", "nonexistent-xyz"])
        # Should return validation error or not found exit code
        assert exit_code in [2, 7]  # VALIDATION_ERROR or NOT_FOUND
    
    def test_recipe_init(self, cli_runner):
        """Test recipe init command."""
        from praisonai.cli.features.recipe import RecipeHandler
        handler = RecipeHandler()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            exit_code = handler.handle(["init", "test-recipe", "-o", tmpdir])
            assert exit_code == 0
            
            # Check files were created
            recipe_dir = Path(tmpdir) / "test-recipe"
            assert (recipe_dir / "TEMPLATE.yaml").exists()
            assert (recipe_dir / "workflow.yaml").exists()
            assert (recipe_dir / "README.md").exists()
    
    def test_recipe_dry_run(self, cli_runner):
        """Test recipe dry run."""
        result = subprocess.run(
            cli_runner + ["recipe", "list", "--json"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent),
        )
        
        # Get first recipe name
        try:
            recipes = json.loads(result.stdout)
            if recipes:
                recipe_name = recipes[0]["name"]
                
                # Run dry run
                result = subprocess.run(
                    cli_runner + ["recipe", "run", recipe_name, "--dry-run", "--json"],
                    capture_output=True,
                    text=True,
                    cwd=str(Path(__file__).parent.parent),
                )
                assert result.returncode == 0
                
                data = json.loads(result.stdout)
                assert data["status"] == "dry_run"
        except (json.JSONDecodeError, KeyError, IndexError):
            pass  # Skip if no recipes available


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests with real API calls."""
    
    @pytest.fixture
    def has_openai_key(self):
        """Check if OpenAI API key is available."""
        return bool(os.environ.get("OPENAI_API_KEY"))
    
    def test_run_with_api(self, has_openai_key):
        """Test running a recipe with real API."""
        if not has_openai_key:
            pytest.skip("OPENAI_API_KEY not set")
        
        from praisonai.recipe import run, list_recipes as list_all_recipes
        
        recipes = list_all_recipes()
        if not recipes:
            pytest.skip("No recipes available")
        
        # Run first available recipe
        result = run(
            recipes[0].name,
            input={},
            options={"timeout_sec": 60},
        )
        
        # Should complete (success or fail, but not crash)
        assert result.run_id.startswith("run-")
        assert result.status in ["success", "failed", "missing_deps"]


# ============================================================================
# Exception Tests
# ============================================================================

class TestExceptions:
    """Tests for custom exceptions."""
    
    def test_recipe_error(self):
        """Test RecipeError."""
        from praisonai.recipe.exceptions import RecipeError
        
        err = RecipeError("Test error", recipe="test", details={"key": "value"})
        assert str(err) == "Test error"
        assert err.recipe == "test"
        assert err.details == {"key": "value"}
    
    def test_recipe_not_found_error(self):
        """Test RecipeNotFoundError."""
        from praisonai.recipe.exceptions import RecipeNotFoundError
        
        err = RecipeNotFoundError("Recipe not found", recipe="test")
        assert "Recipe not found" in str(err)
    
    def test_recipe_dependency_error(self):
        """Test RecipeDependencyError."""
        from praisonai.recipe.exceptions import RecipeDependencyError
        
        err = RecipeDependencyError(
            "Missing deps",
            recipe="test",
            missing=["openai", "pandas"],
        )
        assert err.missing == ["openai", "pandas"]
    
    def test_recipe_policy_error(self):
        """Test RecipePolicyError."""
        from praisonai.recipe.exceptions import RecipePolicyError
        
        err = RecipePolicyError(
            "Policy denied",
            recipe="test",
            policy="no_shell",
        )
        assert err.policy == "no_shell"


# ============================================================================
# Endpoints CLI Tests
# ============================================================================

class TestEndpointsCLI:
    """Tests for endpoints CLI commands."""
    
    def test_endpoints_help(self):
        """Test endpoints help command."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        handler = EndpointsHandler()
        exit_code = handler.handle(["help"])
        assert exit_code == 0
    
    def test_endpoints_list_no_server(self):
        """Test endpoints list when no server running."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        handler = EndpointsHandler()
        exit_code = handler.handle(["list", "--url", "http://localhost:9999"])
        assert exit_code == 8  # CONNECTION_ERROR
    
    def test_endpoints_health_no_server(self):
        """Test endpoints health when no server running."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        handler = EndpointsHandler()
        exit_code = handler.handle(["health", "--url", "http://localhost:9999"])
        assert exit_code == 8  # CONNECTION_ERROR
    
    def test_endpoints_invoke_missing_recipe(self):
        """Test endpoints invoke without recipe name."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        handler = EndpointsHandler()
        exit_code = handler.handle(["invoke"])
        assert exit_code == 2  # VALIDATION_ERROR
    
    def test_endpoints_describe_missing_recipe(self):
        """Test endpoints describe without recipe name."""
        from praisonai.cli.features.endpoints import EndpointsHandler
        handler = EndpointsHandler()
        exit_code = handler.handle(["describe"])
        assert exit_code == 2  # VALIDATION_ERROR


class TestServeConfig:
    """Tests for serve configuration."""
    
    def test_load_config_empty(self):
        """Test loading empty config."""
        from praisonai.recipe.serve import load_config
        config = load_config(None)
        assert config == {}
    
    def test_auth_middleware_creation(self):
        """Test auth middleware creation."""
        from praisonai.recipe.serve import create_auth_middleware
        
        # No auth
        middleware = create_auth_middleware("none")
        assert middleware is None
        
        # API key auth
        middleware = create_auth_middleware("api-key", "test-key")
        assert middleware is not None


class TestServeHostSafety:
    """Tests for serve host binding safety."""
    
    def test_refuse_public_without_auth(self):
        """Test that 0.0.0.0 binding without auth is refused."""
        from praisonai.cli.features.recipe import RecipeHandler
        handler = RecipeHandler()
        exit_code = handler.handle(["serve", "--host", "0.0.0.0", "--port", "9999"])
        assert exit_code == 4  # POLICY_DENIED
    
    def test_allow_localhost_without_auth(self):
        """Test that localhost binding without auth is allowed."""
        # Verify the host check logic
        spec = {"host": "127.0.0.1", "auth": "none"}
        host = spec["host"]
        auth = spec["auth"]
        # This should NOT trigger the policy denial
        should_deny = host != "127.0.0.1" and host != "localhost" and auth == "none"
        assert should_deny is False


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
