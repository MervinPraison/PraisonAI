"""
Example file-based action: system-info

Collects basic system information. Demonstrates the action file contract:
- Must define run(step, flags, cwd) → dict
- Return {"ok": True, "output": "..."} on success
- Return {"ok": False, "error": "..."} on failure

Place in: actions/system_info.py (next to workflow)
      or: .praison/actions/system_info.py (project-level)
"""

import platform
import os


def run(step, flags, cwd):
    """Collect system information."""
    info_parts = [
        f"OS: {platform.system()} {platform.release()}",
        f"Python: {platform.python_version()}",
        f"Machine: {platform.machine()}",
        f"CWD: {cwd}",
    ]

    # Optional: include env vars if requested via step config
    if step.get("show_env"):
        env_vars = step.get("show_env", "").split(",")
        for var in env_vars:
            var = var.strip()
            info_parts.append(f"{var}: {os.environ.get(var, '(not set)')}")

    return {"ok": True, "output": " | ".join(info_parts)}
