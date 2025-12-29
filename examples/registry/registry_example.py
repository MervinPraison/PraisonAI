#!/usr/bin/env python3
"""
PraisonAI Recipe Registry Example

This example demonstrates how to:
1. Create and publish recipes to a local registry
2. Search and list recipes
3. Pull recipes from the registry

Prerequisites:
- pip install praisonai

Usage:
    python registry_example.py
"""

import json
import tarfile
import tempfile
from pathlib import Path


def create_sample_recipe(tmp_dir: Path) -> Path:
    """Create a sample recipe for demonstration."""
    recipe_dir = tmp_dir / "hello-world"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    
    # Create TEMPLATE.yaml
    template_content = """
name: hello-world
version: "1.0.0"
description: A simple hello world recipe
author: example
tags:
  - demo
  - hello
  - example

requires:
  env:
    - OPENAI_API_KEY

config:
  input:
    name:
      type: string
      required: true
      description: Name to greet
"""
    
    with open(recipe_dir / "TEMPLATE.yaml", "w") as f:
        f.write(template_content.strip())
    
    # Create main.py
    main_content = """
def greet(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("World"))
"""
    
    with open(recipe_dir / "main.py", "w") as f:
        f.write(main_content.strip())
    
    return recipe_dir


def pack_recipe(recipe_dir: Path, output_path: Path) -> Path:
    """Pack a recipe into a .praison bundle."""
    import hashlib
    import io
    from datetime import datetime, timezone
    
    with tarfile.open(output_path, "w:gz") as tar:
        manifest = {
            "name": "hello-world",
            "version": "1.0.0",
            "description": "A simple hello world recipe",
            "tags": ["demo", "hello", "example"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": [],
        }
        
        for file_path in recipe_dir.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                rel_path = file_path.relative_to(recipe_dir)
                tar.add(file_path, arcname=str(rel_path))
                
                with open(file_path, "rb") as f:
                    checksum = hashlib.sha256(f.read()).hexdigest()
                manifest["files"].append({
                    "path": str(rel_path),
                    "checksum": checksum,
                })
        
        manifest_bytes = json.dumps(manifest, indent=2).encode()
        manifest_info = tarfile.TarInfo(name="manifest.json")
        manifest_info.size = len(manifest_bytes)
        tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
    
    return output_path


def main():
    """Main example function."""
    print("=" * 60)
    print("PraisonAI Recipe Registry Example")
    print("=" * 60)
    
    # Use a temporary directory for the example
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create registry in temp directory
        registry_path = tmp_path / "registry"
        
        print("\n1. Creating local registry...")
        from praisonai.recipe.registry import LocalRegistry
        registry = LocalRegistry(registry_path)
        print(f"   Registry created at: {registry_path}")
        
        # Create and pack a sample recipe
        print("\n2. Creating sample recipe...")
        recipe_dir = create_sample_recipe(tmp_path)
        print(f"   Recipe created at: {recipe_dir}")
        
        print("\n3. Packing recipe into bundle...")
        bundle_path = tmp_path / "hello-world-1.0.0.praison"
        pack_recipe(recipe_dir, bundle_path)
        print(f"   Bundle created: {bundle_path}")
        
        # Publish to registry
        print("\n4. Publishing to registry...")
        result = registry.publish(bundle_path)
        print(f"   Published: {result['name']}@{result['version']}")
        print(f"   Checksum: {result['checksum'][:16]}...")
        
        # List recipes
        print("\n5. Listing recipes in registry...")
        recipes = registry.list_recipes()
        for r in recipes:
            print(f"   - {r['name']} ({r['version']}): {r['description']}")
        
        # Search recipes
        print("\n6. Searching for 'hello'...")
        results = registry.search("hello")
        print(f"   Found {len(results)} recipe(s)")
        
        # Get versions
        print("\n7. Getting versions of 'hello-world'...")
        versions = registry.get_versions("hello-world")
        print(f"   Versions: {versions}")
        
        # Pull recipe
        print("\n8. Pulling recipe from registry...")
        output_dir = tmp_path / "pulled"
        pull_result = registry.pull("hello-world", output_dir=output_dir)
        print(f"   Pulled to: {pull_result['path']}")
        
        # Verify pulled files
        print("\n9. Verifying pulled files...")
        pulled_recipe = output_dir / "hello-world"
        for f in pulled_recipe.iterdir():
            print(f"   - {f.name}")
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    main()
