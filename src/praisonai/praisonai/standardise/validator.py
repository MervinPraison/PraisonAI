"""
Artifact validation for the FDEP standardisation system.

Validates that features have all required artifacts:
- docs/concepts/{slug}.mdx
- docs/features/{slug}.mdx
- docs/cli/{slug}.mdx
- docs/sdk/praisonaiagents/{module}/{slug}.mdx
- examples/python/{slug}/{slug}-basic.py
- examples/python/{slug}/{slug}-advanced.py
"""

from pathlib import Path
from typing import Dict, List, Optional

from .config import StandardiseConfig
from .discovery import FeatureDiscovery
from .models import (
    ArtifactPath,
    ArtifactStatus,
    ArtifactType,
    FeatureSlug,
    ValidationResult,
)


class ArtifactValidator:
    """Validates that features have all required artifacts."""
    
    def __init__(self, config: StandardiseConfig, discovery: FeatureDiscovery):
        self.config = config
        self.discovery = discovery
    
    def validate_feature(self, slug: FeatureSlug) -> ValidationResult:
        """Validate all artifacts for a single feature."""
        missing = []
        present = []
        issues = []
        
        # Check each required artifact type
        for artifact_type in ArtifactType:
            if artifact_type == ArtifactType.MANIFEST:
                continue  # Manifest is optional
            
            artifact_path = self._get_expected_path(slug, artifact_type)
            if artifact_path is None:
                continue
            
            if artifact_path.exists:
                present.append(ArtifactPath(
                    artifact_type=artifact_type,
                    expected_path=artifact_path.expected_path,
                    actual_path=artifact_path.actual_path,
                    status=ArtifactStatus.PRESENT,
                ))
            else:
                missing.append(artifact_type)
                present.append(ArtifactPath(
                    artifact_type=artifact_type,
                    expected_path=artifact_path.expected_path,
                    actual_path=None,
                    status=ArtifactStatus.MISSING,
                ))
        
        is_valid = len(missing) == 0
        
        return ValidationResult(
            slug=slug,
            is_valid=is_valid,
            missing_artifacts=missing,
            present_artifacts=present,
            issues=issues,
        )
    
    def validate_all(self) -> Dict[str, ValidationResult]:
        """Validate all discovered features."""
        results = {}
        
        all_features = self.discovery.get_all_features()
        
        for slug in all_features:
            if self.config.feature_filter:
                if slug.normalised != self.config.feature_filter:
                    continue
            
            results[slug.normalised] = self.validate_feature(slug)
        
        return results
    
    def get_missing_artifacts(self) -> Dict[str, List[ArtifactType]]:
        """Get all missing artifacts across all features."""
        missing = {}
        
        results = self.validate_all()
        for slug_str, result in results.items():
            if result.missing_artifacts:
                missing[slug_str] = result.missing_artifacts
        
        return missing
    
    def _get_expected_path(self, slug: FeatureSlug, 
                           artifact_type: ArtifactType) -> Optional[ArtifactPath]:
        """Get the expected path for an artifact."""
        slug_str = slug.normalised
        
        if artifact_type == ArtifactType.DOCS_CONCEPT:
            if not self.config.docs_root:
                return None
            expected = self.config.docs_root / "concepts" / f"{slug_str}.mdx"
            actual = self._find_actual_path(expected, slug, "concepts")
            return ArtifactPath(
                artifact_type=artifact_type,
                expected_path=expected,
                actual_path=actual,
                status=ArtifactStatus.PRESENT if actual else ArtifactStatus.MISSING,
            )
        
        elif artifact_type == ArtifactType.DOCS_FEATURE:
            if not self.config.docs_root:
                return None
            expected = self.config.docs_root / "features" / f"{slug_str}.mdx"
            actual = self._find_actual_path(expected, slug, "features")
            return ArtifactPath(
                artifact_type=artifact_type,
                expected_path=expected,
                actual_path=actual,
                status=ArtifactStatus.PRESENT if actual else ArtifactStatus.MISSING,
            )
        
        elif artifact_type == ArtifactType.DOCS_CLI:
            if not self.config.docs_root:
                return None
            expected = self.config.docs_root / "cli" / f"{slug_str}.mdx"
            actual = self._find_actual_path(expected, slug, "cli")
            return ArtifactPath(
                artifact_type=artifact_type,
                expected_path=expected,
                actual_path=actual,
                status=ArtifactStatus.PRESENT if actual else ArtifactStatus.MISSING,
            )
        
        elif artifact_type == ArtifactType.DOCS_SDK:
            if not self.config.docs_root:
                return None
            # SDK docs are in docs/sdk/praisonaiagents/{module}/
            sdk_docs = self.config.docs_root / "sdk" / "praisonaiagents"
            expected = sdk_docs / slug_str / f"{slug_str}.mdx"
            actual = self._find_sdk_docs_path(slug, sdk_docs)
            return ArtifactPath(
                artifact_type=artifact_type,
                expected_path=expected,
                actual_path=actual,
                status=ArtifactStatus.PRESENT if actual else ArtifactStatus.MISSING,
            )
        
        elif artifact_type == ArtifactType.EXAMPLE_BASIC:
            if not self.config.examples_root:
                return None
            expected = self.config.examples_root / slug_str / f"{slug_str}-basic.py"
            actual = self._find_example_path(slug, "basic")
            return ArtifactPath(
                artifact_type=artifact_type,
                expected_path=expected,
                actual_path=actual,
                status=ArtifactStatus.PRESENT if actual else ArtifactStatus.MISSING,
            )
        
        elif artifact_type == ArtifactType.EXAMPLE_ADVANCED:
            if not self.config.examples_root:
                return None
            expected = self.config.examples_root / slug_str / f"{slug_str}-advanced.py"
            actual = self._find_example_path(slug, "advanced")
            return ArtifactPath(
                artifact_type=artifact_type,
                expected_path=expected,
                actual_path=actual,
                status=ArtifactStatus.PRESENT if actual else ArtifactStatus.MISSING,
            )
        
        return None
    
    def _find_actual_path(self, expected: Path, slug: FeatureSlug, 
                          doc_type: str) -> Optional[Path]:
        """Find the actual path, checking variants."""
        if expected.exists():
            return expected
        
        if not self.config.docs_root:
            return None
        
        # Check variants
        slug_str = slug.normalised
        variants = [
            slug_str,
            slug_str.replace("-", "_"),
            slug_str.replace("-", ""),
        ]
        
        # Add singular/plural variants
        from .models import SINGULAR_PLURAL_MAP
        for singular, plural in SINGULAR_PLURAL_MAP.items():
            if slug_str == plural:
                variants.append(singular)
            elif slug_str == singular:
                variants.append(plural)
        
        doc_dir = self.config.docs_root / doc_type
        if not doc_dir.exists():
            return None
        
        for variant in variants:
            path = doc_dir / f"{variant}.mdx"
            if path.exists():
                return path
        
        return None
    
    def _find_sdk_docs_path(self, slug: FeatureSlug, 
                            sdk_docs: Path) -> Optional[Path]:
        """Find SDK docs path, checking module directories."""
        if not sdk_docs.exists():
            return None
        
        slug_str = slug.normalised
        variants = [
            slug_str,
            slug_str.replace("-", "_"),
        ]
        
        # Check for module directory
        for variant in variants:
            module_dir = sdk_docs / variant
            if module_dir.exists() and module_dir.is_dir():
                # Look for any .mdx file in the module directory
                for mdx_file in module_dir.glob("*.mdx"):
                    return mdx_file
        
        return None
    
    def _find_example_path(self, slug: FeatureSlug, 
                           example_type: str) -> Optional[Path]:
        """Find example path, checking variants."""
        if not self.config.examples_root:
            return None
        
        slug_str = slug.normalised
        variants = [
            slug_str,
            slug_str.replace("-", "_"),
        ]
        
        for variant in variants:
            example_dir = self.config.examples_root / variant
            if not example_dir.exists():
                continue
            
            # Check for basic/advanced files with various naming patterns
            patterns = [
                f"{variant}-{example_type}.py",
                f"{variant}_{example_type}.py",
                f"{example_type}.py",
                f"{example_type}_{variant}.py",
            ]
            
            for pattern in patterns:
                path = example_dir / pattern
                if path.exists():
                    return path
            
            # If looking for basic, any simple example file counts
            if example_type == "basic":
                for py_file in example_dir.glob("*.py"):
                    if "advanced" not in py_file.name.lower():
                        return py_file
            
            # If looking for advanced, any advanced/complex example counts
            if example_type == "advanced":
                for py_file in example_dir.glob("*.py"):
                    name_lower = py_file.name.lower()
                    if any(x in name_lower for x in ["advanced", "complex", "multi"]):
                        return py_file
        
        return None
