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
    import praisonai.cli.output.console as console_module

    console_module._output_controller = None
    console_module._console = None
    try:
        from praisonai.cli.app import state
        state.output_controller = None
    except ImportError:
        pass
    yield
    console_module._output_controller = None
    console_module._console = None
    try:
        from praisonai.cli.app import state
        state.output_controller = None
    except ImportError:
        pass
