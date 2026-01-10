"""
PraisonAI Standardise Module

Feature Docs/Examples Protocol (FDEP) implementation for standardising
documentation and examples across the PraisonAI ecosystem.

All imports are lazy-loaded for zero performance impact.
"""

__all__ = [
    # Models
    "FeatureSlug",
    "FeatureManifest",
    "ArtifactStatus",
    "ValidationResult",
    "DuplicateCluster",
    "DriftReport",
    # Engine
    "StandardiseEngine",
    "FeatureDiscovery",
    "ArtifactValidator",
    "DedupeDetector",
    "DriftDetector",
    "TemplateGenerator",
    "ReportGenerator",
    # Config
    "StandardiseConfig",
    # AI Generation
    "AIGenerator",
    "ExampleVerifier",
]


def __getattr__(name: str):
    """Lazy loading of standardise components."""
    if name in ("FeatureSlug", "FeatureManifest", "ArtifactStatus", 
                "ValidationResult", "DuplicateCluster", "DriftReport"):
        from .models import (
            FeatureSlug, FeatureManifest, ArtifactStatus,
            ValidationResult, DuplicateCluster, DriftReport
        )
        return locals()[name]
    
    if name == "StandardiseEngine":
        from .engine import StandardiseEngine
        return StandardiseEngine
    
    if name == "FeatureDiscovery":
        from .discovery import FeatureDiscovery
        return FeatureDiscovery
    
    if name == "ArtifactValidator":
        from .validator import ArtifactValidator
        return ArtifactValidator
    
    if name == "DedupeDetector":
        from .dedupe import DedupeDetector
        return DedupeDetector
    
    if name == "DriftDetector":
        from .drift import DriftDetector
        return DriftDetector
    
    if name == "TemplateGenerator":
        from .templates import TemplateGenerator
        return TemplateGenerator
    
    if name == "ReportGenerator":
        from .reports import ReportGenerator
        return ReportGenerator
    
    if name == "StandardiseConfig":
        from .config import StandardiseConfig
        return StandardiseConfig
    
    if name == "AIGenerator":
        from .ai_generator import AIGenerator
        return AIGenerator
    
    if name == "ExampleVerifier":
        from .example_verifier import ExampleVerifier
        return ExampleVerifier
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
