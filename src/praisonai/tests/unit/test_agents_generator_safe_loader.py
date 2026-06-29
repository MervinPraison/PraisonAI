"""load_tools_from_module must use gated safe loader."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skip(reason="AgentsGenerator load_tools_from_module removed; tests need rewrite")


def test_load_tools_from_module_returns_empty_when_blocked():
    from praisonai.agents_generator import AgentsGenerator

    gen = object.__new__(AgentsGenerator)
    with patch(
        "praisonai._safe_loader.load_user_module", return_value=None
    ):
        assert gen.load_tools_from_module("/tmp/evil_tools.py") == {}
