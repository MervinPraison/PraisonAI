"""Shared fixtures for unit tests under tests/unit/."""

import pytest


@pytest.fixture(autouse=True)
def reset_cli_output_singletons():
    """Reset CLI output globals to avoid Rich/CliRunner stdout races under xdist.

    Rich caches a module-level Console bound to whatever sys.stdout was active
    when first created. async_tui and CliRunner both swap sys.stdout; on xdist
    workers that singleton can point at a closed buffer and Typer raises
    ValueError: I/O operation on closed file when reading invoke() output.
    """
    import sys

    import praisonai.cli.output.console as console_module

    def _reset_app_state():
        # Only reset if praisonai.cli.app is already loaded. Importing it here
        # could pull CLI module side effects into unrelated tests and mask real
        # import failures behind a broad except.
        app_module = sys.modules.get("praisonai.cli.app")
        if app_module is not None:
            app_module.state.output_controller = None

    console_module._output_controller = None
    console_module._console = None
    _reset_app_state()
    yield
    console_module._output_controller = None
    console_module._console = None
    _reset_app_state()
