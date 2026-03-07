"""
Example file-based action: line-count

Counts lines in files matching a pattern. Demonstrates how actions
receive step config and flags from the workflow YAML.

Usage in workflow:
  - name: Count lines
    action: line-count
    pattern: "*.py"
    directory: src/
"""

import os
from pathlib import Path


def run(step, flags, cwd):
    """Count lines in files matching a glob pattern."""
    pattern = step.get("pattern", "*.py")
    directory = step.get("directory", ".")
    target = Path(cwd) / directory

    if not target.exists():
        return {"ok": False, "error": f"Directory not found: {target}"}

    total_lines = 0
    file_count = 0

    for filepath in target.rglob(pattern):
        if filepath.is_file():
            try:
                total_lines += len(filepath.read_text().splitlines())
                file_count += 1
            except (UnicodeDecodeError, PermissionError):
                continue

    return {
        "ok": True,
        "output": f"{file_count} files, {total_lines} lines ({pattern} in {directory})",
    }
