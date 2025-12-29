#!/usr/bin/env python3
"""
PraisonAI Security Features Example

This example demonstrates:
1. SBOM (Software Bill of Materials) generation
2. Lockfile validation
3. Dependency auditing
4. PII redaction

Prerequisites:
- pip install praisonai

Usage:
    python security_example.py
"""

import json
import tempfile
from pathlib import Path


def create_sample_recipe(tmp_dir: Path) -> Path:
    """Create a sample recipe with dependencies."""
    recipe_dir = tmp_dir / "secure-recipe"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    
    # Create TEMPLATE.yaml
    import yaml
    template = {
        "name": "secure-recipe",
        "version": "1.0.0",
        "description": "A recipe with security features",
        "requires": {
            "tools": ["web_search", "file_reader"],
            "external": ["ffmpeg"],
            "env": ["OPENAI_API_KEY"],
        },
    }
    
    with open(recipe_dir / "TEMPLATE.yaml", "w") as f:
        yaml.dump(template, f)
    
    # Create lock directory with requirements
    lock_dir = recipe_dir / "lock"
    lock_dir.mkdir()
    
    with open(lock_dir / "requirements.lock", "w") as f:
        f.write("openai==1.0.0\n")
        f.write("requests==2.31.0\n")
        f.write("pydantic==2.0.0\n")
    
    return recipe_dir


def main():
    """Main example function."""
    print("=" * 60)
    print("PraisonAI Security Features Example")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create sample recipe
        print("\n1. Creating sample recipe with dependencies...")
        recipe_dir = create_sample_recipe(tmp_path)
        print(f"   Recipe created at: {recipe_dir}")
        
        # =====================================================
        # SBOM Generation
        # =====================================================
        print("\n" + "=" * 40)
        print("SBOM Generation")
        print("=" * 40)
        
        from praisonai.recipe.security import generate_sbom
        
        print("\n2. Generating CycloneDX SBOM...")
        sbom = generate_sbom(recipe_dir, format="cyclonedx")
        print(f"   Format: {sbom['bomFormat']}")
        print(f"   Spec Version: {sbom['specVersion']}")
        print(f"   Components: {len(sbom['components'])}")
        
        print("\n   Components:")
        for comp in sbom["components"][:5]:
            print(f"     - {comp['name']}@{comp['version']} ({comp['type']})")
        
        # Save SBOM
        sbom_path = tmp_path / "sbom.json"
        with open(sbom_path, "w") as f:
            json.dump(sbom, f, indent=2)
        print(f"\n   SBOM saved to: {sbom_path}")
        
        # =====================================================
        # Lockfile Validation
        # =====================================================
        print("\n" + "=" * 40)
        print("Lockfile Validation")
        print("=" * 40)
        
        from praisonai.recipe.security import validate_lockfile
        
        print("\n3. Validating lockfile...")
        result = validate_lockfile(recipe_dir)
        print(f"   Valid: {result['valid']}")
        print(f"   Lockfile: {result['lockfile']}")
        print(f"   Type: {result['lockfile_type']}")
        
        # Test strict validation without lockfile
        print("\n4. Testing strict validation on recipe without lockfile...")
        no_lock_dir = tmp_path / "no-lock-recipe"
        no_lock_dir.mkdir()
        
        result = validate_lockfile(no_lock_dir, strict=True)
        print(f"   Valid: {result['valid']}")
        print(f"   Errors: {result['errors']}")
        
        # =====================================================
        # Dependency Auditing
        # =====================================================
        print("\n" + "=" * 40)
        print("Dependency Auditing")
        print("=" * 40)
        
        from praisonai.recipe.security import audit_dependencies
        
        print("\n5. Auditing dependencies...")
        report = audit_dependencies(recipe_dir)
        print(f"   Recipe: {report['recipe']}")
        print(f"   Lockfile: {report['lockfile']}")
        print(f"   Dependencies: {len(report['dependencies'])}")
        print(f"   Vulnerabilities: {len(report['vulnerabilities'])}")
        print(f"   Warnings: {len(report['warnings'])}")
        print(f"   Passed: {report['passed']}")
        
        if report["warnings"]:
            print("\n   Warnings:")
            for warn in report["warnings"]:
                print(f"     - {warn}")
        
        # =====================================================
        # PII Redaction
        # =====================================================
        print("\n" + "=" * 40)
        print("PII Redaction")
        print("=" * 40)
        
        from praisonai.recipe.security import redact_pii, detect_pii
        
        # Sample data with PII
        sample_data = {
            "customer": {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "555-123-4567",
                "message": "Please contact me at john.doe@example.com",
            },
            "ticket_id": "T-12345",
        }
        
        print("\n6. Detecting PII in sample data...")
        detections = detect_pii(sample_data)
        print(f"   Found {len(detections)} PII instance(s):")
        for d in detections:
            print(f"     - {d['type']} at {d['path']}")
        
        print("\n7. Redacting PII...")
        policy = {
            "pii": {
                "mode": "redact",
                "fields": ["email", "phone"],
            }
        }
        
        redacted = redact_pii(sample_data, policy)
        print("   Original email:", sample_data["customer"]["email"])
        print("   Redacted email:", redacted["customer"]["email"])
        print("   Original phone:", sample_data["customer"]["phone"])
        print("   Redacted phone:", redacted["customer"]["phone"])
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    main()
