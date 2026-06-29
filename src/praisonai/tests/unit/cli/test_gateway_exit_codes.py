"""CLI integration tests for the gateway restart-intent exit codes (#2437).

The pure classifier is covered in praisonai-agents; these tests assert the
wrapper ``GatewayHandler.start`` returns the correct *supervisor-facing* exit
code for the integration paths reviewers flagged:

* a missing / malformed / schema-invalid ``gateway.yaml`` must be FATAL (78),
  never restartable (75), so a misconfig does not crash-loop;
* a broken ``--agents`` file must be FATAL (78), not a silent success (0) that
  starts an empty gateway looking healthy to a supervisor.
"""

import pytest

from praisonai.cli.features.gateway import GatewayHandler
from praisonaiagents.gateway import (
    GATEWAY_FATAL_CONFIG_EXIT_CODE,
    GATEWAY_OK_EXIT_CODE,
    GATEWAY_RESTART_EXIT_CODE,
)


def test_missing_gateway_yaml_is_fatal(tmp_path):
    handler = GatewayHandler()
    missing = tmp_path / "does_not_exist.yaml"
    code = handler.start(config_file=str(missing))
    assert code == GATEWAY_FATAL_CONFIG_EXIT_CODE


def test_empty_gateway_yaml_is_fatal(tmp_path):
    handler = GatewayHandler()
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("")  # empty -> load_gateway_config raises ValueError
    code = handler.start(config_file=str(cfg))
    assert code == GATEWAY_FATAL_CONFIG_EXIT_CODE


def test_schema_invalid_gateway_yaml_is_fatal(tmp_path):
    handler = GatewayHandler()
    cfg = tmp_path / "gateway.yaml"
    # Valid YAML mapping but missing the required agents/channels sections.
    cfg.write_text("gateway:\n  host: 127.0.0.1\n")
    code = handler.start(config_file=str(cfg))
    assert code == GATEWAY_FATAL_CONFIG_EXIT_CODE


def test_missing_agents_file_is_fatal(tmp_path):
    handler = GatewayHandler()
    missing = tmp_path / "agents.yaml"
    code = handler.start(agent_file=str(missing))
    assert code == GATEWAY_FATAL_CONFIG_EXIT_CODE


def test_agents_file_without_agents_section_is_fatal(tmp_path):
    handler = GatewayHandler()
    agents = tmp_path / "agents.yaml"
    agents.write_text("not_agents: []\n")
    code = handler.start(agent_file=str(agents))
    assert code == GATEWAY_FATAL_CONFIG_EXIT_CODE


def test_agents_file_with_non_mapping_entry_is_fatal(tmp_path):
    # A truthy 'agents' list with a non-mapping item (e.g. ["bad"]) used to
    # raise AttributeError on .get(), routing through classify_exit_reason to
    # the restart code (75) and crash-looping forever. It must be FATAL (78).
    handler = GatewayHandler()
    agents = tmp_path / "agents.yaml"
    agents.write_text("agents:\n  - bad\n")
    code = handler.start(agent_file=str(agents))
    assert code == GATEWAY_FATAL_CONFIG_EXIT_CODE


def test_agents_section_not_a_list_is_fatal(tmp_path):
    handler = GatewayHandler()
    agents = tmp_path / "agents.yaml"
    agents.write_text("agents:\n  name: bad\n")
    code = handler.start(agent_file=str(agents))
    assert code == GATEWAY_FATAL_CONFIG_EXIT_CODE


def test_load_agents_raises_fatal_config_error(tmp_path):
    from praisonai.cli.features.gateway import FatalConfigError

    handler = GatewayHandler()
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FatalConfigError):
        handler._load_agents_from_file(str(missing))


def test_exit_codes_are_distinct():
    # The whole point of #2437: a misconfig must not look like a transient blip.
    assert GATEWAY_OK_EXIT_CODE == 0
    assert GATEWAY_FATAL_CONFIG_EXIT_CODE != GATEWAY_RESTART_EXIT_CODE
