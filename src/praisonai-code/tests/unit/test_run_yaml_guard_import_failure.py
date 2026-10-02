"""Early wrapper import failures must preserve the YAML runner exit contract."""

import builtins
import os
from types import SimpleNamespace

import pytest
import typer

from praisonai_code.cli.commands import run


@pytest.mark.parametrize("previous", [None, "already-running"])
def test_import_failure_preserves_exit_and_previous_guard(monkeypatch, previous):
    errors = []
    monkeypatch.setattr(run, "get_output_controller", lambda: SimpleNamespace(
        emit_error=lambda **kwargs: errors.append(kwargs["message"]),
        print_error=lambda *args, **kwargs: None,
    ))
    if previous is None:
        monkeypatch.delenv(run._IN_MODERN_RUN_ENV, raising=False)
    else:
        monkeypatch.setenv(run._IN_MODERN_RUN_ENV, previous)
    original = builtins.__import__

    def missing_wrapper(name, *args, **kwargs):
        if name == "praisonai_code.cli.main":
            raise ImportError("wrapper unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_wrapper)
    with pytest.raises(typer.Exit) as exc:
        run._run_from_file("agents.yaml")
    assert exc.value.exit_code == 1
    assert errors == ["wrapper unavailable"]
    assert os.environ.get(run._IN_MODERN_RUN_ENV) == previous
