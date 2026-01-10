"""Tests for standardise models."""

from pathlib import Path

from praisonai.standardise.models import (
    FeatureSlug,
    ArtifactType,
    ArtifactStatus,
    SINGULAR_PLURAL_MAP,
    LEGACY_ALIASES,
)


class TestFeatureSlug:
    """Tests for FeatureSlug class."""
    
    def test_from_string_simple(self):
        """Test simple slug creation."""
        slug = FeatureSlug.from_string("guardrails")
        assert slug.normalised == "guardrails"
        assert slug.is_valid
        assert slug.validation_error is None
    
    def test_from_string_with_underscores(self):
        """Test slug with underscores converts to hyphens."""
        slug = FeatureSlug.from_string("my_feature")
        assert slug.normalised == "my-feature"
        assert slug.is_valid
    
    def test_from_string_uppercase(self):
        """Test uppercase is converted to lowercase."""
        slug = FeatureSlug.from_string("MyFeature")
        assert slug.normalised == "myfeature"
        assert slug.is_valid
    
    def test_from_string_with_extension(self):
        """Test file extensions are stripped."""
        slug = FeatureSlug.from_string("guardrails.py")
        assert slug.normalised == "guardrails"
        
        slug = FeatureSlug.from_string("guardrails.mdx")
        assert slug.normalised == "guardrails"
    
    def test_singular_to_plural_normalisation(self):
        """Test singular forms are normalised to plural."""
        slug = FeatureSlug.from_string("guardrail")
        assert slug.normalised == "guardrails"
        
        slug = FeatureSlug.from_string("agent")
        assert slug.normalised == "agents"
        
        slug = FeatureSlug.from_string("task")
        assert slug.normalised == "tasks"
    
    def test_legacy_alias_normalisation(self):
        """Test legacy aliases are normalised."""
        slug = FeatureSlug.from_string("rag")
        assert slug.normalised == "knowledge"
        
        slug = FeatureSlug.from_string("retrieval")
        assert slug.normalised == "knowledge"
    
    def test_invalid_slug_empty(self):
        """Test empty slug is invalid."""
        slug = FeatureSlug.from_string("")
        assert not slug.is_valid
        assert "empty" in slug.validation_error.lower()
    
    def test_invalid_slug_starts_with_number(self):
        """Test slug starting with number is invalid."""
        slug = FeatureSlug.from_string("123feature")
        assert not slug.is_valid
        assert "letter" in slug.validation_error.lower()
    
    def test_invalid_slug_special_chars(self):
        """Test slug with special characters is invalid."""
        slug = FeatureSlug.from_string("my@feature")
        assert not slug.is_valid
    
    def test_from_path_file(self):
        """Test slug from file path."""
        path = Path("/some/path/guardrails.py")
        slug = FeatureSlug.from_path(path, "sdk")
        assert slug.normalised == "guardrails"
    
    def test_from_path_directory(self):
        """Test slug from directory path."""
        path = Path("/some/path/guardrails")
        slug = FeatureSlug.from_path(path, "sdk")
        assert slug.normalised == "guardrails"
    
    def test_equality(self):
        """Test slug equality."""
        slug1 = FeatureSlug.from_string("guardrails")
        slug2 = FeatureSlug.from_string("guardrail")  # Normalises to guardrails
        assert slug1 == slug2
        
        slug3 = FeatureSlug.from_string("memory")
        assert slug1 != slug3
    
    def test_equality_with_string(self):
        """Test slug equality with string."""
        slug = FeatureSlug.from_string("guardrails")
        assert slug == "guardrails"
        assert slug == "GUARDRAILS"  # Case insensitive
    
    def test_hash(self):
        """Test slug hashing for use in sets/dicts."""
        slug1 = FeatureSlug.from_string("guardrails")
        slug2 = FeatureSlug.from_string("guardrail")
        
        # Should have same hash since they normalise to same value
        assert hash(slug1) == hash(slug2)
        
        # Can be used in sets
        slug_set = {slug1, slug2}
        assert len(slug_set) == 1
    
    def test_str(self):
        """Test string representation."""
        slug = FeatureSlug.from_string("guardrails")
        assert str(slug) == "guardrails"


class TestArtifactType:
    """Tests for ArtifactType enum."""
    
    def test_all_types_exist(self):
        """Test all required artifact types exist."""
        assert ArtifactType.DOCS_CONCEPT
        assert ArtifactType.DOCS_FEATURE
        assert ArtifactType.DOCS_CLI
        assert ArtifactType.DOCS_SDK
        assert ArtifactType.EXAMPLE_BASIC
        assert ArtifactType.EXAMPLE_ADVANCED
        assert ArtifactType.MANIFEST
    
    def test_values(self):
        """Test artifact type values."""
        assert ArtifactType.DOCS_CONCEPT.value == "docs_concept"
        assert ArtifactType.EXAMPLE_BASIC.value == "example_basic"


class TestArtifactStatus:
    """Tests for ArtifactStatus enum."""
    
    def test_all_statuses_exist(self):
        """Test all statuses exist."""
        assert ArtifactStatus.PRESENT
        assert ArtifactStatus.MISSING
        assert ArtifactStatus.DUPLICATE
        assert ArtifactStatus.OUTDATED


class TestMappings:
    """Tests for slug mapping constants."""
    
    def test_singular_plural_map_has_common_terms(self):
        """Test common terms are in the mapping."""
        assert "agent" in SINGULAR_PLURAL_MAP
        assert "task" in SINGULAR_PLURAL_MAP
        assert "guardrail" in SINGULAR_PLURAL_MAP
        assert "handoff" in SINGULAR_PLURAL_MAP
    
    def test_legacy_aliases_has_common_aliases(self):
        """Test common aliases are in the mapping."""
        assert "rag" in LEGACY_ALIASES
        assert "retrieval" in LEGACY_ALIASES
