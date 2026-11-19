"""Enforce or refuse: a sandbox must not accept a policy it cannot keep.

A SecurityPolicy field that a backend has no way to enforce used to be
accepted and then ignored -- ``SecurityPolicy.strict()`` on a plain subprocess
reported COMPLETED for code that wrote files and opened sockets. A backend now
lists the restrictions it cannot provide and refuses them when it is built.
"""

from __future__ import annotations

from typing import List

from praisonaiagents.errors import PraisonAIError


class UnenforceablePolicyError(ValueError, PraisonAIError):
    """A SecurityPolicy asks for a restriction this sandbox backend cannot enforce."""


def require_enforceable(backend: str, problems: List[str], hint: str) -> None:
    """Raise UnenforceablePolicyError naming every field *backend* cannot keep."""
    if problems:
        raise UnenforceablePolicyError(
            f"{backend} cannot enforce SecurityPolicy({', '.join(problems)}). {hint}"
        )


def subprocess_problems(policy) -> List[str]:
    """Restrictions a plain host subprocess has no mechanism for."""
    return [
        f"{field}=False"
        for field in ("allow_network", "allow_file_write")
        if not getattr(policy, field, True)
    ]
