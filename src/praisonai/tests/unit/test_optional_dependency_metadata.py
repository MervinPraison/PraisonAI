"""Regression tests for installable wrapper extras."""

from pathlib import Path

import toml


PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def test_google_adk_extra_avoids_legacy_frameworks_adk_pin():
    metadata = toml.loads(PYPROJECT.read_text(encoding="utf-8"))
    requirements = metadata["project"]["optional-dependencies"]["google-adk"]

    assert "praisonai-frameworks>=0.1.8" in requirements
    assert "google-adk[extensions]>=2.5,<3" in requirements
    assert not any(
        requirement.startswith("praisonai-frameworks[google-adk]")
        for requirement in requirements
    )
