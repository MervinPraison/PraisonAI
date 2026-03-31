"""PraisonAI Flow — Visual workflow builder powered by Langflow.

This module provides Langflow integration with PraisonAI custom components
pre-loaded. Install with: pip install praisonai[flow]
"""

from __future__ import annotations

from pathlib import Path

# Components directory shipped with this package
# The PraisonAI/ subdirectory name becomes the sidebar category
COMPONENTS_DIR = str(Path(__file__).parent / "components")


def start_flow(
    *,
    port: int = 7860,
    host: str = "127.0.0.1",
    log_level: str = "error",
    backend_only: bool = False,
    open_browser: bool = True,
    env_file: str | None = None,
) -> None:
    """Start Langflow with PraisonAI components pre-loaded.

    Args:
        port: Port to listen on (default: 7860).
        host: Host to bind to (default: 127.0.0.1).
        log_level: Logging level (default: error).
        backend_only: Run without frontend UI.
        open_browser: Open browser on start.
        env_file: Path to .env file.
    """
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    # Inject PraisonAI components path
    existing = env.get("LANGFLOW_COMPONENTS_PATH", "")
    env["LANGFLOW_COMPONENTS_PATH"] = (
        f"{COMPONENTS_DIR};{existing}" if existing else COMPONENTS_DIR
    )

    cmd = [
        sys.executable, "-m", "langflow", "run",
        "--port", str(port),
        "--host", host,
        "--log-level", log_level,
    ]
    if backend_only:
        cmd.append("--backend-only")
    if env_file:
        cmd.extend(["--env-file", env_file])
    if not open_browser:
        cmd.append("--no-open")

    subprocess.run(cmd, env=env)
