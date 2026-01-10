"""
Manifest schema and storage for the FDEP standardisation system.

Manifests are stored in .praison/features/{slug}.yaml
"""

from pathlib import Path
from typing import List, Optional

from .models import FeatureManifest, FeatureSlug


class ManifestStorage:
    """Manages feature manifest files."""
    
    def __init__(self, manifest_dir: Optional[Path] = None):
        self.manifest_dir = manifest_dir or Path(".praison/features")
    
    def get_manifest_path(self, slug: FeatureSlug) -> Path:
        """Get the path to a manifest file."""
        return self.manifest_dir / f"{slug.normalised}.yaml"
    
    def load(self, slug: FeatureSlug) -> Optional[FeatureManifest]:
        """Load a manifest from disk."""
        path = self.get_manifest_path(slug)
        if not path.exists():
            return None
        
        try:
            import yaml
        except ImportError:
            return self._load_simple(path, slug)
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return FeatureManifest.from_dict(data)
        except Exception:
            return None
    
    def _load_simple(self, path: Path, slug: FeatureSlug) -> Optional[FeatureManifest]:
        """Simple YAML loading without PyYAML dependency."""
        try:
            content = path.read_text(encoding="utf-8")
            data = {}
            
            for line in content.split("\n"):
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    data[key] = value
            
            return FeatureManifest.from_dict(data)
        except Exception:
            return None
    
    def save(self, manifest: FeatureManifest) -> Path:
        """Save a manifest to disk."""
        path = self.get_manifest_path(manifest.slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            import yaml
            content = yaml.dump(manifest.to_dict(), default_flow_style=False, sort_keys=False)
        except ImportError:
            content = self._to_simple_yaml(manifest)
        
        path.write_text(content, encoding="utf-8")
        return path
    
    def _to_simple_yaml(self, manifest: FeatureManifest) -> str:
        """Convert manifest to simple YAML without PyYAML."""
        lines = []
        data = manifest.to_dict()
        
        for key, value in data.items():
            if value is None:
                continue
            if isinstance(value, list):
                if value:
                    lines.append(f"{key}:")
                    for item in value:
                        lines.append(f"  - {item}")
            elif isinstance(value, dict):
                if value:
                    lines.append(f"{key}:")
                    for k, v in value.items():
                        lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")
        
        return "\n".join(lines)
    
    def list_all(self) -> List[FeatureManifest]:
        """List all manifests."""
        manifests = []
        
        if not self.manifest_dir.exists():
            return manifests
        
        for yaml_file in self.manifest_dir.glob("*.yaml"):
            slug = FeatureSlug.from_path(yaml_file, "manifest")
            manifest = self.load(slug)
            if manifest:
                manifests.append(manifest)
        
        return manifests
    
    def delete(self, slug: FeatureSlug) -> bool:
        """Delete a manifest."""
        path = self.get_manifest_path(slug)
        if path.exists():
            path.unlink()
            return True
        return False
    
    def exists(self, slug: FeatureSlug) -> bool:
        """Check if a manifest exists."""
        return self.get_manifest_path(slug).exists()
    
    def create_default(self, slug: FeatureSlug, 
                       sdk_module: Optional[str] = None,
                       cli_commands: Optional[List[str]] = None) -> FeatureManifest:
        """Create a default manifest for a feature."""
        name = slug.normalised.replace("-", " ").title()
        
        return FeatureManifest(
            slug=slug,
            name=name,
            description=f"{name} feature for PraisonAI",
            status="stable",
            sdk_module=sdk_module or slug.normalised,
            cli_commands=cli_commands or [],
        )


# Schema for manifest validation
MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["slug", "name", "description"],
    "properties": {
        "slug": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9-]{0,62}[a-z0-9]$|^[a-z]$",
            "description": "Feature slug (lowercase alphanumeric + hyphens)",
        },
        "name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "description": "Human-readable feature name",
        },
        "description": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
            "description": "Brief description of the feature",
        },
        "status": {
            "type": "string",
            "enum": ["stable", "beta", "experimental", "deprecated"],
            "default": "stable",
        },
        "min_version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
            "description": "Minimum PraisonAI version required",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tags for categorisation",
        },
        "related_features": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Related feature slugs",
        },
        "sdk_module": {
            "type": "string",
            "description": "SDK module name (e.g., 'guardrails')",
        },
        "cli_commands": {
            "type": "array",
            "items": {"type": "string"},
            "description": "CLI commands for this feature",
        },
        "api_classes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Public API classes",
        },
        "artifacts": {
            "type": "object",
            "description": "Paths to artifacts",
            "additionalProperties": {"type": "string"},
        },
    },
}
