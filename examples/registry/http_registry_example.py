#!/usr/bin/env python3
"""
HTTP Recipe Registry Example

This example demonstrates:
1. Starting an HTTP registry server programmatically
2. Publishing recipes with token authentication
3. Listing and searching recipes via HTTP
4. Pulling recipes from HTTP registry

Requirements:
- praisonai installed
- No external API keys required (local registry only)

Environment Variables (optional):
- PRAISONAI_REGISTRY_TOKEN: Token for authentication
"""

import sys
import json
import time
import shutil
import tarfile
import tempfile
import subprocess
from pathlib import Path

def create_sample_recipe(output_dir: Path) -> Path:
    """Create a sample recipe for testing."""
    recipe_dir = output_dir / "sample-agent"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    
    # Create manifest.json
    manifest = {
        "name": "sample-agent",
        "version": "1.0.0",
        "description": "A sample agent recipe for registry testing",
        "tags": ["sample", "agent", "test"],
        "author": "praison",
        "files": ["recipe.yaml"]
    }
    (recipe_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    
    # Create recipe.yaml
    recipe_yaml = """
name: sample-agent
version: "1.0.0"
description: A sample agent recipe

agents:
  - name: assistant
    role: General Assistant
    goal: Help users with their questions
    instructions: You are a helpful assistant.

tasks:
  - name: respond
    description: Respond to user query
    agent: assistant
"""
    (recipe_dir / "recipe.yaml").write_text(recipe_yaml.strip())
    
    # Pack into .praison bundle
    bundle_path = output_dir / "sample-agent-1.0.0.praison"
    with tarfile.open(bundle_path, "w:gz") as tar:
        for file in recipe_dir.iterdir():
            tar.add(file, arcname=file.name)
    
    return bundle_path


def start_registry_server(port: int, registry_path: Path, token: str = None):
    """Start registry server in background process."""
    cmd = [
        sys.executable, "-c",
        f"""
import sys
sys.path.insert(0, '/Users/praison/praisonai-package/src/praisonai')
from praisonai.recipe.server import create_wsgi_app
from wsgiref.simple_server import make_server, WSGIRequestHandler
from pathlib import Path

class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass

app = create_wsgi_app(registry_path=Path("{registry_path}"), token={repr(token)})
server = make_server("127.0.0.1", {port}, app, handler_class=QuietHandler)
server.serve_forever()
"""
    ]
    
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc


def main():
    print("=" * 60)
    print("HTTP Recipe Registry Example")
    print("=" * 60)
    
    # Setup
    work_dir = Path(tempfile.mkdtemp(prefix="registry_example_"))
    registry_path = work_dir / "registry"
    pulled_dir = work_dir / "pulled"
    port = 7799
    token = "example-secret-token"
    
    print(f"\nWork directory: {work_dir}")
    print(f"Registry path: {registry_path}")
    print(f"Server port: {port}")
    print(f"Token: {'*' * len(token)} (redacted)")
    
    try:
        # 1. Create sample recipe
        print("\n[1] Creating sample recipe...")
        bundle_path = create_sample_recipe(work_dir)
        print(f"    ✓ Created bundle: {bundle_path.name}")
        
        # 2. Start HTTP registry server
        print("\n[2] Starting HTTP registry server...")
        server = start_registry_server(port, registry_path, token)
        time.sleep(1)  # Wait for server to start
        print(f"    ✓ Server running on http://127.0.0.1:{port}")
        
        # 3. Check health
        print("\n[3] Checking server health...")
        result = subprocess.run(
            ["curl", "-s", f"http://127.0.0.1:{port}/healthz"],
            capture_output=True, text=True
        )
        health = json.loads(result.stdout)
        print(f"    Status: {health['status']}")
        print(f"    Auth required: {health['auth_required']}")
        
        # 4. Publish WITHOUT token (should fail)
        print("\n[4] Publishing WITHOUT token (expect failure)...")
        result = subprocess.run(
            ["python3", "-m", "praisonai", "recipe", "publish", str(bundle_path),
             "--registry", f"http://127.0.0.1:{port}", "--json"],
            capture_output=True, text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        if result.returncode != 0 or "error" in result.stdout.lower() or "401" in result.stdout:
            print("    ✓ Correctly rejected (authentication required)")
        else:
            print(f"    ✗ Unexpected success: {result.stdout}")
        
        # 5. Publish WITH token (should succeed)
        print("\n[5] Publishing WITH token...")
        result = subprocess.run(
            ["python3", "-m", "praisonai", "recipe", "publish", str(bundle_path),
             "--registry", f"http://127.0.0.1:{port}", "--token", token, "--json"],
            capture_output=True, text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        try:
            data = json.loads(result.stdout)
            if data.get("ok"):
                print(f"    ✓ Published: {data['name']}@{data['version']}")
            else:
                print(f"    ✗ Failed: {result.stdout}")
                return 1
        except json.JSONDecodeError:
            print(f"    Output: {result.stdout}")
            print(f"    Stderr: {result.stderr}")
            return 1
        
        # 6. List recipes
        print("\n[6] Listing recipes from registry...")
        result = subprocess.run(
            ["python3", "-m", "praisonai", "recipe", "list",
             "--registry", f"http://127.0.0.1:{port}", "--json"],
            capture_output=True, text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        recipes = json.loads(result.stdout)
        print(f"    Found {len(recipes)} recipe(s):")
        for r in recipes:
            print(f"      - {r['name']} v{r['version']}: {r.get('description', '')[:40]}")
        
        # 7. Search recipes
        print("\n[7] Searching for 'agent'...")
        result = subprocess.run(
            ["python3", "-m", "praisonai", "recipe", "search", "agent",
             "--registry", f"http://127.0.0.1:{port}", "--json"],
            capture_output=True, text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        matches = json.loads(result.stdout)
        print(f"    Found {len(matches)} match(es)")
        
        # 8. Pull recipe
        print("\n[8] Pulling recipe...")
        pulled_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["python3", "-m", "praisonai", "recipe", "pull", "sample-agent",
             "--registry", f"http://127.0.0.1:{port}", "-o", str(pulled_dir), "--json"],
            capture_output=True, text=True,
            cwd="/Users/praison/praisonai-package/src/praisonai"
        )
        data = json.loads(result.stdout)
        if data.get("ok"):
            print(f"    ✓ Pulled to: {data['path']}")
            
            # Verify content
            manifest_path = Path(data['path']) / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text())
                print(f"    ✓ Verified: {manifest['name']}@{manifest['version']}")
        else:
            print(f"    ✗ Failed: {result.stdout}")
        
        print("\n" + "=" * 60)
        print("Example completed successfully!")
        print("=" * 60)
        
        # Cleanup
        server.terminate()
        server.wait()
        
    finally:
        # Clean up temp directory
        shutil.rmtree(work_dir, ignore_errors=True)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
