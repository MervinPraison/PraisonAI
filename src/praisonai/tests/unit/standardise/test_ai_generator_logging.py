"""Importing ai_generator with LOGLEVEL=debug must not touch the root logger."""

import os
import subprocess
import sys

import pytest

_CHECK = """
import logging, sys
{setup}
root = logging.getLogger()
before = (root.level, list(root.handlers))
import praisonai.standardise.ai_generator as m
assert (root.level, list(root.handlers)) == before, (before, root.level, root.handlers)
assert m.logger.level == logging.DEBUG
"""


@pytest.mark.parametrize("setup", [
    "",  # unconfigured root logger
    "logging.basicConfig(level=logging.WARNING, stream=sys.stderr)",  # host-configured
])
def test_debug_import_leaves_root_logger_alone(setup):
    env = {**os.environ, "LOGLEVEL": "debug"}
    result = subprocess.run(
        [sys.executable, "-c", _CHECK.format(setup=setup)],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
