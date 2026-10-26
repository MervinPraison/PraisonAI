"""Path validation for async jobs agent file references."""

from __future__ import annotations

import os
from typing import Optional


def validate_agent_file_path(agent_file: Optional[str]) -> Optional[str]:
    """Restrict agent_file to PRAISONAI_JOBS_AGENT_ROOT (default: the cwd).

    Safe by default: without an explicit root, callers can only reference
    files under the server's working directory. Operators who need a wider
    scope set PRAISONAI_JOBS_AGENT_ROOT explicitly.
    """
    if not agent_file:
        return agent_file

    root = os.environ.get("PRAISONAI_JOBS_AGENT_ROOT") or os.getcwd()

    resolved = os.path.realpath(os.path.abspath(agent_file))
    root_resolved = os.path.realpath(os.path.abspath(root))
    if resolved != root_resolved and not resolved.startswith(root_resolved.rstrip(os.sep) + os.sep):
        raise ValueError(
            f"agent_file must be within PRAISONAI_JOBS_AGENT_ROOT ({root_resolved})"
        )
    return agent_file
