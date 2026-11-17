"""D-12: the praisonaiagents distribution declares its licence, classifiers and URLs."""

import os
import sys

import pytest

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib is 3.11+")
def test_pyproject_declares_licence_classifiers_and_urls():
    import tomllib
    with open(os.path.join(PKG_ROOT, "pyproject.toml"), "rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["license"] == {"text": "MIT"}
    assert "License :: OSI Approved :: MIT License" in project["classifiers"]
    assert {"Homepage", "Repository"} <= set(project["urls"])


def test_licence_file_ships_with_the_package():
    with open(os.path.join(PKG_ROOT, "LICENSE"), encoding="utf-8") as fh:
        assert fh.readline().strip() == "MIT License"
