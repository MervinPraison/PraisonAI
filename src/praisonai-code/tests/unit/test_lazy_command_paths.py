"""Guard against dangling lazy-command module paths (issue #4693).

``praisonai_code.cli.app._LAZY_COMMANDS`` is the authoritative registry that
maps each CLI command to the module providing its Typer sub-app. Wrapper-,
bot-, train-, browser-, mcp- and deploy-resident commands keep placeholder
``.commands.*`` paths (they are re-routed to their external package at
invocation time), so only *non-resident* entries are expected to resolve
against ``praisonai_code.cli``.

This test imports every non-resident lazy-command module so a genuinely
dangling path fails in CI rather than at first use.
"""

import importlib

import pytest

from praisonai_code.cli import app as cli_app


def _non_resident_lazy_commands():
    resident = (
        cli_app._WRAPPER_RESIDENT_COMMANDS
        | cli_app._BOT_RESIDENT_COMMANDS
        | cli_app._TRAIN_RESIDENT_COMMANDS
        | cli_app._BROWSER_RESIDENT_COMMANDS
        | cli_app._MCP_RESIDENT_COMMANDS
        | cli_app._DEPLOY_RESIDENT_COMMANDS
    )
    for name, (module_path, attr_name, _desc) in cli_app._LAZY_COMMANDS.items():
        if name in resident:
            continue
        yield name, module_path, attr_name


@pytest.mark.parametrize(
    "name,module_path,attr_name",
    list(_non_resident_lazy_commands()),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_non_resident_lazy_command_module_resolves(name, module_path, attr_name):
    module = importlib.import_module(module_path, cli_app.__package__)
    assert hasattr(module, attr_name), (
        f"lazy command {name!r} maps to {module_path}:{attr_name} "
        f"but attribute {attr_name!r} is missing"
    )


def test_special_command_modules_resolve():
    for name, (module_path, attr_name, _desc) in cli_app._SPECIAL_COMMANDS.items():
        module = importlib.import_module(module_path, cli_app.__package__)
        assert hasattr(module, attr_name), (
            f"special command {name!r} maps to {module_path}:{attr_name} "
            f"but attribute {attr_name!r} is missing"
        )
