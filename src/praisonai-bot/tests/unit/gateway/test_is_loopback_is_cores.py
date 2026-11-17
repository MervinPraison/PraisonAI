"""The gateway uses core's is_loopback instead of a second copy (G-21)."""

import pytest

from praisonai_bot.gateway import origin_check
from praisonaiagents.gateway.protocols import is_loopback as core_is_loopback


def test_origin_check_reexports_core_function():
    assert origin_check.is_loopback is core_is_loopback


@pytest.mark.parametrize("host,expected", [
    ("localhost", True), ("127.0.0.1", True), ("127.0.0.2", True), ("::1", True),
    ("0.0.0.0", False), ("10.0.0.1", False), ("example.com", False), ("", False),
])
def test_loopback_answers_are_unchanged(host, expected):
    assert origin_check.is_loopback(host) is expected
