"""Tests for standardise discovery."""

from praisonai.standardise.config import StandardiseConfig
from praisonai.standardise.discovery import FeatureDiscovery
from praisonai.standardise.models import FeatureSlug


class TestFeatureDiscovery:
    """Tests for FeatureDiscovery class."""
    
    def test_discover_sdk_features(self, tmp_path):
        """Test discovering features from SDK modules."""
        # Create mock SDK structure
        sdk_root = tmp_path / "praisonaiagents"
        sdk_root.mkdir()
        
        (sdk_root / "guardrails").mkdir()
        (sdk_root / "memory").mkdir()
        (sdk_root / "knowledge").mkdir()
        (sdk_root / "__pycache__").mkdir()  # Should be skipped
        
        config = StandardiseConfig(sdk_root=sdk_root)
        discovery = FeatureDiscovery(config)
        
        features = discovery.discover_sdk_features()
        
        assert len(features) == 3
        slugs = {str(f) for f in features}
        assert "guardrails" in slugs
        assert "memory" in slugs
        assert "knowledge" in slugs
    
    def test_discover_cli_features(self, tmp_path):
        """Test discovering features from CLI files."""
        # Create mock CLI structure
        cli_root = tmp_path / "cli"
        cli_root.mkdir()
        features_dir = cli_root / "features"
        features_dir.mkdir()
        
        (features_dir / "guardrail.py").touch()
        (features_dir / "memory.py").touch()
        (features_dir / "__init__.py").touch()  # Should be skipped
        
        config = StandardiseConfig(cli_root=cli_root)
        discovery = FeatureDiscovery(config)
        
        features = discovery.discover_cli_features()
        
        assert len(features) == 2
        slugs = {str(f) for f in features}
        assert "guardrails" in slugs  # Normalised from guardrail
        assert "memory" in slugs
    
    def test_discover_docs_features(self, tmp_path):
        """Test discovering features from docs pages."""
        # Create mock docs structure
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        
        concepts = docs_root / "concepts"
        concepts.mkdir()
        (concepts / "guardrails.mdx").touch()
        (concepts / "memory.mdx").touch()
        
        features = docs_root / "features"
        features.mkdir()
        (features / "knowledge.mdx").touch()
        
        config = StandardiseConfig(docs_root=docs_root)
        discovery = FeatureDiscovery(config)
        
        features_found = discovery.discover_docs_features()
        
        slugs = {str(f) for f in features_found}
        assert "guardrails" in slugs
        assert "memory" in slugs
        assert "knowledge" in slugs
    
    def test_discover_example_features(self, tmp_path):
        """Test discovering features from examples."""
        # Create mock examples structure
        examples_root = tmp_path / "examples"
        examples_root.mkdir()
        
        (examples_root / "guardrails").mkdir()
        (examples_root / "memory").mkdir()
        (examples_root / "__pycache__").mkdir()  # Should be skipped
        
        config = StandardiseConfig(examples_root=examples_root)
        discovery = FeatureDiscovery(config)
        
        features = discovery.discover_example_features()
        
        assert len(features) == 2
        slugs = {str(f) for f in features}
        assert "guardrails" in slugs
        assert "memory" in slugs
    
    def test_get_all_features(self, tmp_path):
        """Test getting union of all features."""
        # Create mock structure with overlapping features
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        (sdk_root / "memory").mkdir()
        
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        concepts = docs_root / "concepts"
        concepts.mkdir()
        (concepts / "guardrails.mdx").touch()
        (concepts / "knowledge.mdx").touch()
        
        config = StandardiseConfig(sdk_root=sdk_root, docs_root=docs_root)
        discovery = FeatureDiscovery(config)
        
        all_features = discovery.get_all_features()
        
        slugs = {str(f) for f in all_features}
        assert "guardrails" in slugs
        assert "memory" in slugs
        assert "knowledge" in slugs
    
    def test_get_feature_sources(self, tmp_path):
        """Test getting sources for a specific feature."""
        # Create mock structure with explicit cli_root that doesn't have guardrails
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        concepts = docs_root / "concepts"
        concepts.mkdir()
        (concepts / "guardrails.mdx").touch()
        
        # Create empty cli root to ensure no CLI features found
        cli_root = tmp_path / "cli"
        cli_root.mkdir()
        (cli_root / "features").mkdir()
        
        config = StandardiseConfig(sdk_root=sdk_root, docs_root=docs_root, cli_root=cli_root)
        discovery = FeatureDiscovery(config)
        
        slug = FeatureSlug.from_string("guardrails")
        sources = discovery.get_feature_sources(slug)
        
        assert sources["sdk"] is True
        assert sources["docs"] is True
        assert sources["cli"] is False
        assert sources["examples"] is False
    
    def test_find_docs_pages(self, tmp_path):
        """Test finding all docs pages for a feature."""
        # Create mock docs with multiple pages for same feature
        docs_root = tmp_path / "docs"
        docs_root.mkdir()
        
        concepts = docs_root / "concepts"
        concepts.mkdir()
        (concepts / "guardrails.mdx").touch()
        
        features = docs_root / "features"
        features.mkdir()
        (features / "guardrails.mdx").touch()
        
        cli = docs_root / "cli"
        cli.mkdir()
        (cli / "guardrail.mdx").touch()  # Singular variant
        
        config = StandardiseConfig(docs_root=docs_root)
        discovery = FeatureDiscovery(config)
        
        slug = FeatureSlug.from_string("guardrails")
        pages = discovery.find_docs_pages(slug)
        
        assert len(pages) >= 2  # At least concepts and features
    
    def test_find_examples(self, tmp_path):
        """Test finding example files for a feature."""
        # Create mock examples
        examples_root = tmp_path / "examples"
        examples_root.mkdir()
        
        guardrails_dir = examples_root / "guardrails"
        guardrails_dir.mkdir()
        (guardrails_dir / "guardrails-basic.py").touch()
        (guardrails_dir / "guardrails-advanced.py").touch()
        
        config = StandardiseConfig(examples_root=examples_root)
        discovery = FeatureDiscovery(config)
        
        slug = FeatureSlug.from_string("guardrails")
        examples = discovery.find_examples(slug)
        
        assert len(examples) == 2
    
    def test_caching(self, tmp_path):
        """Test that discovery results are cached."""
        sdk_root = tmp_path / "sdk"
        sdk_root.mkdir()
        (sdk_root / "guardrails").mkdir()
        
        config = StandardiseConfig(sdk_root=sdk_root)
        discovery = FeatureDiscovery(config)
        
        # First call
        features1 = discovery.discover_sdk_features()
        
        # Add another directory
        (sdk_root / "memory").mkdir()
        
        # Second call should return cached result
        features2 = discovery.discover_sdk_features()
        
        assert features1 is features2  # Same object (cached)
