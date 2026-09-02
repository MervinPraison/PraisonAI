"""Guard against dangling lazy-command module paths (issue #4693).

``praisonai_code.cli.app._LAZY_COMMANDS`` is the authoritative registry that
maps each CLI command to the module providing its Typer sub-app. Wrapper-,
bot-, train-, browser-, mcp- and deploy-resident commands keep placeholder
``.commands.*`` paths (they are re-routed to their external package at
invocation time), so only *non-resident* entries are expected to resolve
against ``praisonai_code.cli``.

This test imports every non-resident lazy-command module so a genuinely
dangling path fails in CI rather than at first use.

A second parametrised test mirrors ``get_command()``'s resident dispatch: when
the owning package (``praisonai``, ``praisonai_bot``, ``praisonai_train``,
``praisonai_browser``, ``praisonai_mcp`` or ``praisonai_deploy``) is installed —
as in the full monorepo CI — it imports the absolute ``…​.cli.commands.<name>``
target the router re-routes to and asserts the attribute exists. This covers the
``schedule`` re-route (praisonai-code → ``praisonai.cli.commands.schedule`` after
``66dcb788a``) that the non-resident test intentionally excludes. It skips
gracefully in a standalone ``praisonai-code`` install where those packages are
absent.
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


def _resident_lazy_commands():
    resident_groups = (
        (cli_app._WRAPPER_RESIDENT_COMMANDS, "praisonai", cli_app.wrapper_available),
        (cli_app._BOT_RESIDENT_COMMANDS, "praisonai_bot", cli_app.bot_package_available),
        (cli_app._TRAIN_RESIDENT_COMMANDS, "praisonai_train", cli_app.train_package_available),
        (cli_app._BROWSER_RESIDENT_COMMANDS, "praisonai_browser", cli_app.browser_package_available),
        (cli_app._MCP_RESIDENT_COMMANDS, "praisonai_mcp", cli_app.mcp_package_available),
        (cli_app._DEPLOY_RESIDENT_COMMANDS, "praisonai_deploy", cli_app.deploy_package_available),
    )
    deploy_names = cli_app._DEPLOY_RESIDENT_COMMANDS
    seen = set()
    for names, root, available in resident_groups:
        for name in names:
            if name in seen:
                continue
            if name in cli_app._LAZY_COMMANDS:
                # Wrapper/bot/train/browser/mcp residents are dispatched through
                # ``_LAZY_COMMANDS`` using its declared attribute name.
                attr_name = cli_app._LAZY_COMMANDS[name][1]
            elif name in deploy_names:
                # Deploy commands are dispatched separately with a hardcoded
                # ``app`` attribute and are absent from ``_LAZY_COMMANDS``.
                attr_name = "app"
            else:
                # ``app``/``standardise`` are resident but handled outside the
                # generic ``_LAZY_COMMANDS`` dispatch path, so skip them here.
                continue
            seen.add(name)
            yield name, f"{root}.cli.commands.{name}", attr_name, available


@pytest.mark.parametrize(
    "name,module_path,attr_name,available",
    list(_resident_lazy_commands()),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_resident_lazy_command_module_resolves(name, module_path, attr_name, available):
    if not available():
        pytest.skip(f"owning package for resident command {name!r} not installed")
    module = importlib.import_module(module_path)
    assert hasattr(module, attr_name), (
        f"resident command {name!r} re-routes to {module_path}:{attr_name} "
        f"but attribute {attr_name!r} is missing"
    )
