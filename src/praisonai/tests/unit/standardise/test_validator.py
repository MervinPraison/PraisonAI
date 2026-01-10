"""Tests for standardise validator."""

from praisonai.standardise.config import StandardiseConfig
from praisonai.standardise.discovery import FeatureDiscovery
from praisonai.standardise.validator import ArtifactValidator
from praisonai.standardise.models import ArtifactType, FeatureSlug


class TestArtifactValidator:
    """Tests for ArtifactValidator class."""
    
    def test_validate_feature_all_present(self, tmp_path):
        """Test validation when all artifacts are present."""
        # Create complete feature structure
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        
        (docs_root / "concepts").mkdir()
        (docs_root / "concepts" / "guardrails.mdx").touch()
        
        (docs_root / "features").mkdir()
        (docs_root / "features" / "guardrails.mdx").touch()
        
        (docs_root / "cli").mkdir()
        (docs_root / "cli" / "guardrails.mdx").touch()
        
        sdk_docs = docs_root / "sdk" / "praisonaiagents" / "guardrails"
        sdk_docs.mkdir(parents=True)
        (sdk_docs / "guardrails.mdx").touch()
        
        examples_root = tmp_path / "examples"
        examples_root.mkdir()
        guardrails_examples = examples_root / "guardrails"
        guardrails_examples.mkdir()
        (guardrails_examples / "guardrails-basic.py").touch()
        (guardrails_examples / "guardrails-advanced.py").touch()
        
        config = StandardiseConfig(docs_root=docs_root, examples_root=examples_root)
        discovery = FeatureDiscovery(config)
        validator = ArtifactValidator(config, discovery)
        
        slug = FeatureSlug.from_string("guardrails")
        result = validator.validate_feature(slug)
        
        assert result.is_valid
        assert len(result.missing_artifacts) == 0
    
    def test_validate_feature_missing_artifacts(self, tmp_path):
        """Test validation when some artifacts are missing."""
        # Create partial feature structure
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        
        (docs_root / "concepts").mkdir()
        (docs_root / "concepts" / "guardrails.mdx").touch()
        
        # Missing: features, cli, sdk docs, examples
        
        config = StandardiseConfig(docs_root=docs_root)
        discovery = FeatureDiscovery(config)
        validator = ArtifactValidator(config, discovery)
        
        slug = FeatureSlug.from_string("guardrails")
        result = validator.validate_feature(slug)
        
        assert not result.is_valid
        assert len(result.missing_artifacts) > 0
        assert ArtifactType.DOCS_FEATURE in result.missing_artifacts
    
    def test_validate_all(self, tmp_path):
        """Test validating all discovered features."""
        # Create structure with multiple features
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        (sdk_root / "memory").mkdir()
        
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        (docs_root / "concepts").mkdir()
        (docs_root / "concepts" / "guardrails.mdx").touch()
        # memory has no docs
        
        config = StandardiseConfig(sdk_root=sdk_root, docs_root=docs_root)
        discovery = FeatureDiscovery(config)
        validator = ArtifactValidator(config, discovery)
        
        results = validator.validate_all()
        
        assert "guardrails" in results
        assert "memory" in results
    
    def test_get_missing_artifacts(self, tmp_path):
        """Test getting all missing artifacts."""
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        (sdk_root / "memory").mkdir()
        
        config = StandardiseConfig(sdk_root=sdk_root)
        discovery = FeatureDiscovery(config)
        validator = ArtifactValidator(config, discovery)
        
        missing = validator.get_missing_artifacts()
        
        # Both features should have missing artifacts
        assert len(missing) >= 2
    
    def test_finds_variant_paths(self, tmp_path):
        """Test that validator finds files with variant naming."""
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        
        (docs_root / "cli").mkdir()
        # Using singular form
        (docs_root / "cli" / "guardrail.mdx").touch()
        
        config = StandardiseConfig(docs_root=docs_root)
        discovery = FeatureDiscovery(config)
        validator = ArtifactValidator(config, discovery)
        
        slug = FeatureSlug.from_string("guardrails")
        artifact_path = validator._find_actual_path(
            docs_root / "cli" / "guardrails.mdx",
            slug,
            "cli"
        )
        
        # Should find the singular variant
        assert artifact_path is not None
        assert artifact_path.exists()
    
    def test_feature_filter(self, tmp_path):
        """Test that feature filter limits validation."""
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        (sdk_root / "memory").mkdir()
        (sdk_root / "knowledge").mkdir()
        
        config = StandardiseConfig(sdk_root=sdk_root, feature_filter="guardrails")
        discovery = FeatureDiscovery(config)
        validator = ArtifactValidator(config, discovery)
        
        results = validator.validate_all()
        
        # Only guardrails should be validated
        assert len(results) == 1
        assert "guardrails" in results
