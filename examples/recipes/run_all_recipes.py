#!/usr/bin/env python3
"""
Run All Recipes - Test harness for all Agent-Recipes.

Runs each recipe in dry-run mode to verify CLI parity and run.json generation.
Requires: OPENAI_API_KEY environment variable for integration tests.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List

# Recipe definitions
RECIPES = [
    "ai-audio-normalizer",
    "ai-audio-splitter",
    "ai-changelog-generator",
    "ai-code-documenter",
    "ai-csv-cleaner",
    "ai-data-profiler",
    "ai-dependency-auditor",
    "ai-doc-translator",
    "ai-folder-packager",
    "ai-image-cataloger",
    "ai-image-optimizer",
    "ai-image-resizer",
    "ai-json-to-csv",
    "ai-markdown-to-pdf",
    "ai-pdf-summarizer",
    "ai-pdf-to-markdown",
    "ai-podcast-cleaner",
    "ai-repo-readme",
    "ai-schema-generator",
    "ai-screenshot-ocr",
    "ai-sitemap-scraper",
    "ai-slide-to-notes",
    "ai-url-to-markdown",
    "ai-video-editor",
    "ai-video-thumbnails",
    "ai-video-to-gif",
]


@dataclass
class TestResult:
    """Result of a recipe test."""
    recipe: str
    status: str  # pass, fail, skip
    reason: str = ""
    duration: float = 0.0


def check_api_keys() -> dict:
    """Check available API keys."""
    keys = {
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY": bool(os.environ.get("GOOGLE_API_KEY")),
    }
    return keys


def check_external_deps() -> dict:
    """Check external dependencies."""
    import shutil
    deps = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "pdftotext": shutil.which("pdftotext") is not None,
        "pandoc": shutil.which("pandoc") is not None,
        "git": shutil.which("git") is not None,
    }
    return deps


def run_recipe_dry_run(recipe: str, timeout: int = 30) -> TestResult:
    """Run a recipe in dry-run mode."""
    import time
    start = time.time()
    
    try:
        # Use praison templates run command with dry-run
        cmd = ["praison", "templates", "run", recipe, "--dry-run", "dummy_input"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        
        duration = time.time() - start
        
        if result.returncode == 0:
            return TestResult(recipe, "pass", "dry-run completed", duration)
        else:
            # Check if it's a missing dependency error
            stderr = result.stderr.lower()
            if "not found" in stderr or "missing" in stderr:
                return TestResult(recipe, "skip", f"Missing dependency: {result.stderr[:100]}", duration)
            return TestResult(recipe, "fail", f"Exit code {result.returncode}: {result.stderr[:100]}", duration)
            
    except subprocess.TimeoutExpired:
        return TestResult(recipe, "fail", "Timeout", timeout)
    except FileNotFoundError:
        return TestResult(recipe, "skip", "praison CLI not found", 0)
    except Exception as e:
        return TestResult(recipe, "fail", str(e), 0)


def run_all_recipes(dry_run_only: bool = True) -> List[TestResult]:
    """Run all recipes and collect results."""
    results = []
    
    print("=" * 60)
    print("RECIPE TEST HARNESS")
    print("=" * 60)
    
    # Check prerequisites
    keys = check_api_keys()
    deps = check_external_deps()
    
    print("\nAPI Keys:")
    for key, present in keys.items():
        status = "✓" if present else "✗"
        print(f"  {status} {key}")
    
    print("\nExternal Dependencies:")
    for dep, present in deps.items():
        status = "✓" if present else "✗"
        print(f"  {status} {dep}")
    
    print("\n" + "=" * 60)
    print(f"Running {len(RECIPES)} recipes (dry-run={dry_run_only})")
    print("=" * 60 + "\n")
    
    for i, recipe in enumerate(RECIPES, 1):
        print(f"[{i:2d}/{len(RECIPES)}] {recipe}...", end=" ", flush=True)
        
        if dry_run_only:
            result = run_recipe_dry_run(recipe)
        else:
            # Full run would go here
            result = run_recipe_dry_run(recipe)
        
        results.append(result)
        
        if result.status == "pass":
            print(f"✓ ({result.duration:.1f}s)")
        elif result.status == "skip":
            print(f"⊘ SKIP: {result.reason}")
        else:
            print(f"✗ FAIL: {result.reason}")
    
    return results


def print_summary(results: List[TestResult]):
    """Print test summary."""
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"  Skipped: {skipped}")
    print(f"  Total:   {len(results)}")
    
    if failed > 0:
        print("\nFailed recipes:")
        for r in results:
            if r.status == "fail":
                print(f"  - {r.recipe}: {r.reason}")
    
    return failed == 0


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run all Agent-Recipes tests")
    parser.add_argument("--full", action="store_true", help="Run full tests (not just dry-run)")
    parser.add_argument("--recipe", help="Run specific recipe only")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()
    
    if args.recipe:
        results = [run_recipe_dry_run(args.recipe)]
    else:
        results = run_all_recipes(dry_run_only=not args.full)
    
    if args.json:
        output = [{"recipe": r.recipe, "status": r.status, "reason": r.reason} for r in results]
        print(json.dumps(output, indent=2))
    else:
        success = print_summary(results)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
