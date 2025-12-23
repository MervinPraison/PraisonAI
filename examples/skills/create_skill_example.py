#!/usr/bin/env python3
"""
Example: Creating Skills with PraisonAI CLI

This example demonstrates how to create Agent Skills using the CLI.
"""

import subprocess
import tempfile
import os
from pathlib import Path


def example_create_skill_with_template():
    """Create a skill using template mode (no API key required)."""
    print("=" * 60)
    print("Example 1: Create skill with template")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run([
            "praisonai", "skills", "create",
            "--name", "my-template-skill",
            "--description", "A skill for processing text files",
            "--author", "example-team",
            "--license", "MIT",
            "--template",
            "--output-dir", tmpdir
        ], capture_output=True, text=True)
        
        print(result.stdout)
        if result.returncode == 0:
            skill_md = Path(tmpdir) / "my-template-skill" / "SKILL.md"
            print(f"\nGenerated SKILL.md:\n{skill_md.read_text()[:500]}...")
        else:
            print(f"Error: {result.stderr}")


def example_create_skill_with_ai():
    """Create a skill using AI generation (requires API key)."""
    print("\n" + "=" * 60)
    print("Example 2: Create skill with AI generation")
    print("=" * 60)
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Skipping: OPENAI_API_KEY not set")
        return
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run([
            "praisonai", "skills", "create",
            "--name", "csv-analyzer",
            "--description", "Analyze CSV files and generate statistical reports",
            "--output-dir", tmpdir
        ], capture_output=True, text=True)
        
        print(result.stdout)
        if result.returncode == 0:
            skill_md = Path(tmpdir) / "csv-analyzer" / "SKILL.md"
            print(f"\nGenerated SKILL.md:\n{skill_md.read_text()[:800]}...")
            
            # Check if script was generated
            script_path = Path(tmpdir) / "csv-analyzer" / "scripts" / "skill.py"
            if script_path.exists():
                print(f"\nGenerated skill.py:\n{script_path.read_text()[:500]}...")


def example_create_skill_with_script():
    """Create a skill with auto-generated Python script."""
    print("\n" + "=" * 60)
    print("Example 3: Create skill with script")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run([
            "praisonai", "skills", "create",
            "--name", "data-processor",
            "--description", "Process and transform data files",
            "--template",
            "--script",
            "--output-dir", tmpdir
        ], capture_output=True, text=True)
        
        print(result.stdout)
        if result.returncode == 0:
            script_path = Path(tmpdir) / "data-processor" / "scripts" / "skill.py"
            if script_path.exists():
                print(f"\nGenerated skill.py:\n{script_path.read_text()}")


if __name__ == "__main__":
    example_create_skill_with_template()
    example_create_skill_with_ai()
    example_create_skill_with_script()
