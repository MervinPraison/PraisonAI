"""Unit tests for YAML CLI backend parsing.

Tests the ``_resolve_yaml_cli_backend`` helper directly so the parse/resolve
logic can be validated without constructing a full ``AgentsGenerator`` and
exercising unrelated framework code paths.
"""

import logging
import yaml
from unittest.mock import MagicMock, patch

from praisonai.agents_generator import _resolve_yaml_cli_backend


def _logger():
    return logging.getLogger("test_yaml_cli_backend")


def _role_details(yaml_text):
    """Extract the first role's details dict from a YAML snippet."""
    config = yaml.safe_load(yaml_text)
    return next(iter(config['roles'].values()))


def test_yaml_cli_backend_string():
    """YAML ``cli_backend: claude-code`` resolves via registry."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    cli_backend: claude-code
"""
    details = _role_details(yaml_content)

    with patch('praisonai.cli_backends.resolve_cli_backend') as mock_resolve:
        mock_backend = MagicMock()
        mock_resolve.return_value = mock_backend

        resolved = _resolve_yaml_cli_backend(details.get('cli_backend'), _logger())

    assert resolved is mock_backend
    mock_resolve.assert_called_once_with('claude-code')


def test_yaml_cli_backend_dict():
    """YAML ``cli_backend: {id, overrides}`` passes overrides through."""
    yaml_content = """
framework: praisonai
topic: coding
roles:
  coder:
    role: Code refactorer
    goal: Refactor Python modules
    backstory: Senior engineer
    cli_backend:
      id: claude-code
      overrides:
        timeout_ms: 60000
"""
    details = _role_details(yaml_content)

    with patch('praisonai.cli_backends.resolve_cli_backend') as mock_resolve:
        mock_backend = MagicMock()
        mock_resolve.return_value = mock_backend

        resolved = _resolve_yaml_cli_backend(details.get('cli_backend'), _logger())

    assert resolved is mock_backend
    mock_resolve.assert_called_once_with('claude-code', overrides={'timeout_ms': 60000})


def test_yaml_cli_backend_dict_missing_id():
    """Dict without ``id`` key yields ``None`` and logs a warning (no raise)."""
    details = _role_details("""
framework: praisonai
topic: coding
roles:
  coder:
    role: r
    goal: g
    backstory: b
    cli_backend:
      overrides:
        timeout_ms: 60000
""")
    logger = MagicMock()
    resolved = _resolve_yaml_cli_backend(details.get('cli_backend'), logger)
    assert resolved is None
    assert logger.warning.called


def test_yaml_no_cli_backend():
    """Missing ``cli_backend`` field yields ``None`` with no warning."""
    details = _role_details("""
framework: praisonai
topic: coding
roles:
  coder:
    role: r
    goal: g
    backstory: b
""")
    logger = MagicMock()
    resolved = _resolve_yaml_cli_backend(details.get('cli_backend'), logger)
    assert resolved is None
    logger.warning.assert_not_called()


def test_yaml_cli_backend_import_error():
    """When registry resolver raises ImportError, return ``None`` and warn."""
    logger = MagicMock()
    with patch(
        'praisonai.cli_backends.resolve_cli_backend',
        side_effect=ImportError("CLI backends not available"),
    ):
        resolved = _resolve_yaml_cli_backend('claude-code', logger)
    assert resolved is None
    assert logger.warning.called


def test_yaml_cli_backend_unknown_id():
    """Unknown backend id yields ``None`` after the registry raises ValueError."""
    logger = MagicMock()
    resolved = _resolve_yaml_cli_backend('does-not-exist', logger)
    assert resolved is None
    assert logger.warning.called


def test_yaml_cli_backend_invalid_type():
    """Non-str/dict value (e.g. int) yields ``None`` and logs a warning."""
    logger = MagicMock()
    resolved = _resolve_yaml_cli_backend(123, logger)
    assert resolved is None
    assert logger.warning.called


def test_yaml_cli_backend_registered_claude_code_resolves():
    """End-to-end: the shipped ``claude-code`` id really resolves without mocking."""
    resolved = _resolve_yaml_cli_backend('claude-code', _logger())
    assert resolved is not None
    assert hasattr(resolved, 'execute')
    assert hasattr(resolved, 'stream')
