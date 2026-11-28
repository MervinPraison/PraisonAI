"""Package dependency direction follows the tier model (ARCHITECTURE.md section 2).

Tier 1 ``praisonaiagents`` depends on no other PraisonAI package. Tier 2 packages
depend only on ``praisonaiagents``: never on the ``praisonai`` wrapper (Tier 3),
and never on each other. Cross-tier access goes through lazy ``_*_bridge``
modules, not PyPI dependencies. The wrapper may depend on everything.

Optional extras follow the same rule. ``KNOWN_EXTRA_EXCEPTIONS`` lists the ones
that predate this test; it may only shrink, and a new entry needs the owner's
approval.
"""

import re
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    tomllib = pytest.importorskip("tomli")

SRC = Path(__file__).resolve().parents[3]

TIER1 = "praisonaiagents"
TIER2 = {
    "praisonai-code": "praisonai-code",
    "praisonai-bot": "praisonai-bot",
    "praisonai-train": "praisonai-train",
    "praisonai-browser": "praisonai-browser",
    "praisonai-mcp": "praisonai-mcp",
    "praisonai-sandbox": "praisonai-sandbox",
    "praisonai-deploy": "praisonai-deploy",
}
WRAPPER = "praisonai"
PRAISON_PACKAGES = {TIER1, WRAPPER, *TIER2.values()}

# (package, extra, dependency) triples that predate this test. May only shrink.
KNOWN_EXTRA_EXCEPTIONS = {
    # Opt-in sandbox backends for the core SDK.
    ("praisonaiagents", "sandbox", "praisonai-sandbox"),
}


def _name(requirement: str) -> str:
    return re.split(r"[\s\[<>=!~;]", requirement.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _project(directory: str) -> dict:
    with open(SRC / directory / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)["project"]


def _praison_deps(requirements, own):
    return [n for n in (_name(r) for r in requirements) if n in PRAISON_PACKAGES and n != own]


def _allowed(own: str) -> set:
    if own == TIER1:
        return set()
    if own in TIER2.values():
        return {TIER1}
    return PRAISON_PACKAGES - {own}  # the wrapper


DIRECTORIES = {TIER1: "praisonai-agents", **{v: k for k, v in TIER2.items()}}


@pytest.mark.parametrize("package", sorted(DIRECTORIES))
def test_required_dependencies_follow_tier_direction(package):
    project = _project(DIRECTORIES[package])
    bad = [d for d in _praison_deps(project.get("dependencies", []), package)
           if d not in _allowed(package)]
    assert not bad, (
        f"{package} must not depend on {bad}. Tier 2 packages depend only on "
        f"{TIER1}; reach other tiers through a lazy _*_bridge module."
    )


@pytest.mark.parametrize("package", sorted(DIRECTORIES))
def test_optional_extras_follow_tier_direction(package):
    project = _project(DIRECTORIES[package])
    bad = []
    for extra, requirements in project.get("optional-dependencies", {}).items():
        for dep in _praison_deps(requirements, package):
            if dep not in _allowed(package) and (package, extra, dep) not in KNOWN_EXTRA_EXCEPTIONS:
                bad.append(f"[{extra}] {dep}")
    assert not bad, (
        f"{package} extras must not depend on {bad}. Use a lazy _*_bridge module, "
        "or get the owner's approval and add the triple to KNOWN_EXTRA_EXCEPTIONS."
    )


def test_known_exceptions_still_exist():
    """Drop an exception from the list once the dependency is gone."""
    stale = []
    for package, extra, dep in KNOWN_EXTRA_EXCEPTIONS:
        reqs = _project(DIRECTORIES[package]).get("optional-dependencies", {}).get(extra, [])
        if dep not in {_name(r) for r in reqs}:
            stale.append((package, extra, dep))
    assert not stale, f"Remove fixed entries from KNOWN_EXTRA_EXCEPTIONS: {stale}"
