"""Tests for standardise engine."""

from praisonai.standardise.config import StandardiseConfig
from praisonai.standardise.engine import StandardiseEngine


class TestStandardiseEngine:
    """Tests for StandardiseEngine class."""
    
    def test_check_returns_report(self, tmp_path):
        """Test that check returns a valid report."""
        # Create minimal structure
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        
        config = StandardiseConfig(
            project_root=tmp_path,
            sdk_root=sdk_root,
        )
        engine = StandardiseEngine(config)
        
        report = engine.check()
        
        assert report.timestamp
        assert report.features_scanned >= 1
    
    def test_report_text_format(self, tmp_path):
        """Test text report generation."""
        config = StandardiseConfig(project_root=tmp_path)
        engine = StandardiseEngine(config)
        
        output = engine.report(format="text")
        
        assert "Standardisation" in output
        assert "Summary" in output
    
    def test_report_json_format(self, tmp_path):
        """Test JSON report generation."""
        config = StandardiseConfig(project_root=tmp_path)
        engine = StandardiseEngine(config)
        
        output = engine.report(format="json")
        
        import json
        data = json.loads(output)
        assert "timestamp" in data
        assert "summary" in data
    
    def test_fix_dry_run(self, tmp_path):
        """Test fix in dry-run mode."""
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        
        config = StandardiseConfig(
            project_root=tmp_path,
            sdk_root=sdk_root,
            docs_root=docs_root,
            dry_run=True,
        )
        engine = StandardiseEngine(config)
        
        actions = engine.fix(apply=False)
        
        # Should have planned actions but no applied
        assert len(actions["applied"]) == 0
    
    def test_fix_apply(self, tmp_path):
        """Test fix with apply."""
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "concepts").mkdir()
        (docs_root / "features").mkdir()
        (docs_root / "cli").mkdir()
        
        examples_root = tmp_path / "examples"
        examples_root.mkdir()
        
        config = StandardiseConfig(
            project_root=tmp_path,
            sdk_root=sdk_root,
            docs_root=docs_root,
            examples_root=examples_root,
            dry_run=False,
            backup=False,
        )
        engine = StandardiseEngine(config)
        
        actions = engine.fix(feature="guardrails", apply=True)
        
        # Should have applied some actions
        assert len(actions["applied"]) > 0
    
    def test_init_feature(self, tmp_path):
        """Test initialising a new feature."""
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "concepts").mkdir()
        (docs_root / "features").mkdir()
        (docs_root / "cli").mkdir()
        
        examples_root = tmp_path / "examples"
        examples_root.mkdir()
        
        config = StandardiseConfig(
            project_root=tmp_path,
            docs_root=docs_root,
            examples_root=examples_root,
            dry_run=False,
        )
        engine = StandardiseEngine(config)
        
        created = engine.init("my-new-feature")
        
        # Should create multiple artifacts
        assert len(created) > 0
        assert "docs_concept" in created or "docs_feature" in created
    
    def test_init_invalid_slug(self, tmp_path):
        """Test init with invalid slug raises error."""
        config = StandardiseConfig(project_root=tmp_path)
        engine = StandardiseEngine(config)
        
        try:
            engine.init("123invalid")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "letter" in str(e).lower()
    
    def test_get_exit_code_no_issues(self, tmp_path):
        """Test exit code when no issues."""
        config = StandardiseConfig(project_root=tmp_path)
        engine = StandardiseEngine(config)
        
        report = engine.check()
        
        # With empty project, might have no issues
        exit_code = engine.get_exit_code(report)
        assert exit_code in [0, 1]  # Either no issues or issues found
    
    def test_backup_creation(self, tmp_path):
        """Test that backups are created."""
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        concepts = docs_root / "concepts"
        concepts.mkdir()
        
        # Create existing file
        existing = concepts / "guardrails.mdx"
        existing.write_text("existing content")
        
        config = StandardiseConfig(
            project_root=tmp_path,
            docs_root=docs_root,
            dry_run=False,
            backup=True,
        )
        engine = StandardiseEngine(config)
        
        # Trigger backup
        backup_path = engine._backup_file(existing)
        
        assert backup_path.exists()
        assert "guardrails" in backup_path.name


class TestStandardiseConfig:
    """Tests for StandardiseConfig class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = StandardiseConfig()
        
        assert config.dry_run is True
        assert config.backup is True
        assert config.force is False
        assert config.scope == "all"
        assert config.dedupe_mode == "prompt"
    
    def test_auto_detect_paths(self, tmp_path):
        """Test auto-detection of paths."""
        # Create structure
        (tmp_path / ".praison").mkdir()
        docs = tmp_path / "docs"
        docs.mkdir()
        examples = tmp_path / "examples" / "python"
        examples.mkdir(parents=True)
        
        config = StandardiseConfig(project_root=tmp_path)
        
        assert config.docs_root == docs
        assert config.examples_root == examples
    
    def test_from_env(self, monkeypatch):
        """Test loading config from environment."""
        monkeypatch.setenv("PRAISON_DRY_RUN", "false")
        monkeypatch.setenv("CI", "true")
        
        config = StandardiseConfig.from_env()
        
        assert config.dry_run is False
        assert config.ci_mode is True
