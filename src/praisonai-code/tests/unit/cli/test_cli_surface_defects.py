"""Regression gates for four CLI surface defects.

Each test pins one defect and fails against the code as it stood before the
accompanying fix:

1. ``praisonai hooks add`` printed "Unknown hooks action: add" and still exited
   ``0``, so a script that added a hook succeeded while doing nothing. The
   hooks Typer group also advertised ``add``/``remove`` (never implemented)
   while omitting ``init``/``stats`` (which work).
2. ``praisonai hooks list`` told users to create ``.praison/hooks.json`` while
   ``HooksManager.CONFIG_FILE`` is ``.praisonai/hooks.json``; ``hooks init``
   wrote that same wrong path, so init-then-list never saw the hooks.
3. ``praisonai plugins discover``'s empty state said "Create one with:
   praisonai plugins init <name>". There is no ``init`` command; it is
   ``create``.
4. ``praisonai call`` accepted only ``--model``/``--verbose``, so ``--public``
   (the ngrok exposure inbound PSTN requires) and ``--host`` were reachable
   only through environment variables.

Expected values are derived from the real source of truth --
``HooksManager.CONFIG_FILE`` and the Typer command registries -- rather than
restating a corrected literal, so they cannot drift the way the bugs did.

Note on shape: the legacy argparse layer deliberately parses an *empty* argv
under pytest (``build_argument_parser(in_test_env)``), so a CliRunner
invocation cannot exercise the legacy leg in-process. The delegation chain is
therefore pinned seam by seam, plus one real subprocess that reads the process
exit code directly.
"""

import argparse
import os
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from praisonaiagents.memory import HooksManager

import praisonai_code._wrapper_bridge as wrapper_bridge
import praisonai_code.cli.commands.call as call_command
import praisonai_code.cli.commands.hooks as hooks_command
import praisonai_code.cli.commands.plugins as plugins_command
from praisonai_code.cli.legacy import praison_ai as legacy


runner = CliRunner()


def _registered_names(app):
    return [cmd.name or cmd.callback.__name__ for cmd in app.registered_commands]


def _hooks_handler():
    from praisonai.cli.legacy.subcommand_handlers import handle_hooks_command

    return handle_hooks_command


@pytest.fixture()
def wrapper_argv(monkeypatch):
    """Capture the legacy argv a Typer stub hands to the wrapper."""
    calls = []
    monkeypatch.setattr(
        wrapper_bridge, "run_wrapper_command", lambda argv, *, feature: calls.append(list(argv))
    )
    return calls


# --------------------------------------------------------------------------
# Defect 1: an action that fails must not exit 0
# --------------------------------------------------------------------------

def test_unknown_hooks_action_returns_nonzero(tmp_path, monkeypatch):
    """The handler reports failure as an exit code, not just as printed text.

    ``None`` is not acceptable: the dispatcher does ``sys.exit(code or 0)``, so
    an implicit ``None`` return is exactly the original "exits 0" defect. The
    assertion therefore demands a real non-zero int.
    """
    monkeypatch.chdir(tmp_path)
    handler = _hooks_handler()
    for action in ("add", "remove", "definitely-not-an-action"):
        code = handler(None, action)
        assert isinstance(code, int) and code != 0, (
            f"hooks action {action!r} returned {code!r}; the dispatcher's "
            f"sys.exit({code!r} or 0) would report success"
        )


def test_known_hooks_actions_return_zero(tmp_path, monkeypatch):
    """The success path still reports success."""
    monkeypatch.chdir(tmp_path)
    handler = _hooks_handler()
    for action in ("list", "stats", "init", "help"):
        assert handler(None, action) == 0, action


def test_hooks_dispatch_propagates_handler_exit_code():
    """The legacy dispatcher must exit with the handler's code, not a fixed 0.

    Pins the ``sys.exit(0)`` one level above the handler, so fixing only the
    handler cannot leave the defect in place.
    """
    import inspect

    source = inspect.getsource(legacy)
    marker = "elif args.command == 'hooks':"
    assert marker in source, "hooks dispatch branch not found"
    branch = source.split(marker, 1)[1].split("elif args.command ==", 1)[0]
    assert "handle_hooks_command" in branch
    assert "sys.exit(0)" not in branch, (
        "hooks dispatch still exits 0 unconditionally; a failed action would "
        f"report success. Branch:\n{branch}"
    )


def test_hooks_group_advertises_only_actions_the_handler_accepts(tmp_path, monkeypatch, wrapper_argv):
    """Every registered hooks subcommand must map to an action that succeeds.

    ``add``/``remove`` were registered but unimplemented. This goes red if
    either comes back, and equally if a registered command stops working.
    """
    names = _registered_names(hooks_command.app)
    assert names, "hooks group registers no commands"

    for name in names:
        wrapper_argv.clear()
        result = runner.invoke(hooks_command.app, [name])
        assert result.exit_code == 0, f"{name}: {result.output}"
        assert wrapper_argv, f"'hooks {name}' dispatched nothing"
        argv = wrapper_argv[0]
        assert argv[0] == "hooks"
        action = argv[1]

        monkeypatch.chdir(tmp_path)
        assert _hooks_handler()(None, action) == 0, (
            f"'praisonai hooks {name}' is advertised but the handler rejects "
            f"action {action!r}"
        )


def test_hooks_add_exits_nonzero_end_to_end(tmp_path):
    """Read the real process exit code, not a message.

    This is the user-visible contract: ``praisonai hooks add`` must not report
    success while doing nothing.
    """
    pytest.importorskip("praisonai")
    proc = subprocess.run(
        [sys.executable, "-m", "praisonai", "hooks", "add", "myhook", "--event", "BEFORE_TOOL"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode != 0, (
        "'praisonai hooks add' exited 0 while adding nothing.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


# --------------------------------------------------------------------------
# Defect 2: the advertised hooks path must be the one that is read
# --------------------------------------------------------------------------

def test_no_hooks_message_names_the_real_config_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert _hooks_handler()(None, "list") == 0
    out = capsys.readouterr().out
    assert HooksManager.CONFIG_FILE in out, (
        f"'hooks list' advertises a path that is not "
        f"{HooksManager.CONFIG_FILE!r}: {out!r}"
    )


def test_hooks_init_writes_the_file_the_manager_loads(tmp_path, monkeypatch):
    """init -> list must round-trip: init wrote a path list never read."""
    monkeypatch.chdir(tmp_path)
    assert _hooks_handler()(None, "init") == 0

    expected = tmp_path / HooksManager.CONFIG_FILE.replace("/", os.sep)
    assert expected.is_file(), (
        f"hooks init did not create {expected}; created instead: "
        f"{sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('hooks.json'))}"
    )

    manager = HooksManager(workspace_path=str(tmp_path))
    assert manager.get_stats().get("total_hooks", 0) > 0, (
        "hooks written by 'hooks init' are invisible to HooksManager"
    )


# --------------------------------------------------------------------------
# Defect 3: the plugin-creation hint must name a registered command
# --------------------------------------------------------------------------

def test_plugin_create_hint_names_a_registered_command():
    advertised = plugins_command._plugin_create_command_name()
    assert advertised in _registered_names(plugins_command.app), (
        f"'praisonai plugins {advertised}' is advertised but not registered; "
        f"registered: {_registered_names(plugins_command.app)}"
    )


def test_plugins_discover_empty_state_hint_resolves(monkeypatch):
    """The empty-state hint must name a command the plugins app really has."""
    from praisonaiagents.plugins import discovery

    monkeypatch.setattr(discovery, "discover_plugins", lambda *a, **k: [])
    result = runner.invoke(plugins_command.app, ["discover"])
    assert result.exit_code == 0, result.output

    hint_line = next(
        (line for line in result.output.splitlines() if "Create one with:" in line),
        None,
    )
    assert hint_line is not None, result.output
    advertised = hint_line.split("praisonai plugins", 1)[1].split()[0]
    assert advertised in _registered_names(plugins_command.app), (
        f"empty-state hint advertises 'praisonai plugins {advertised}', which "
        f"is not registered: {_registered_names(plugins_command.app)}"
    )


# --------------------------------------------------------------------------
# Defect 4: --public/--port/--host must reach the call server
# --------------------------------------------------------------------------

def _run_server_capture(monkeypatch):
    call_mod = pytest.importorskip("praisonai.api.call")
    captured = {}

    def fake_run_server(port, host="127.0.0.1", use_public=False):
        captured.update(port=port, host=host, use_public=use_public)

    monkeypatch.setattr(call_mod, "run_server", fake_run_server)
    return call_mod, captured


@pytest.mark.parametrize(
    "cli_args, expected_call_argv",
    [
        ([], []),
        (["--public"], ["--public"]),
        (["--port", "9111"], ["--port", "9111"]),
        (["--host", "0.0.0.0"], ["--host", "0.0.0.0"]),
        (
            ["--public", "--host", "0.0.0.0", "--port", "9111"],
            ["--public", "--port", "9111", "--host", "0.0.0.0"],
        ),
    ],
)
def test_call_command_forwards_server_options(cli_args, expected_call_argv, monkeypatch, wrapper_argv):
    """Leg 1: the Typer command must accept and forward the server options."""
    result = runner.invoke(call_command.app, cli_args)
    assert result.exit_code == 0, result.output
    assert wrapper_argv, "call command dispatched nothing"
    legacy_argv = wrapper_argv[0]
    assert legacy_argv[0] == "call"

    # Leg 2: the legacy dispatcher maps its parsed args onto the call server's
    # own argv. Reconstruct the args the legacy parser would produce.
    parsed = argparse.Namespace(
        public="--public" in legacy_argv,
        port=int(legacy_argv[legacy_argv.index("--port") + 1]) if "--port" in legacy_argv else 8005,
        host=legacy_argv[legacy_argv.index("--host") + 1] if "--host" in legacy_argv else "127.0.0.1",
    )
    assert legacy._build_call_args(parsed, argv=legacy_argv) == expected_call_argv


@pytest.mark.parametrize(
    "cli_args, expected",
    [
        ([], {"port": 8090, "host": "127.0.0.1", "use_public": False}),
        (["--public"], {"port": 8090, "host": "127.0.0.1", "use_public": True}),
        (["--port", "9111"], {"port": 9111, "host": "127.0.0.1", "use_public": False}),
        (
            ["--host", "0.0.0.0", "--port", "9111"],
            {"port": 9111, "host": "0.0.0.0", "use_public": False},
        ),
    ],
)
def test_call_options_reach_run_server(cli_args, expected, monkeypatch, wrapper_argv):
    """Full chain: Typer options -> legacy argv -> api.call.main -> run_server.

    Plain ``praisonai call`` must keep the call server's own default port
    (``$PORT``, else 8090); the shared argparse ``--port`` default is 8005, so
    forwarding it unconditionally would silently retarget the port.
    """
    monkeypatch.delenv("PORT", raising=False)
    call_mod, captured = _run_server_capture(monkeypatch)

    assert runner.invoke(call_command.app, cli_args).exit_code == 0
    legacy_argv = wrapper_argv[0]
    parsed = argparse.Namespace(
        public="--public" in legacy_argv,
        port=int(legacy_argv[legacy_argv.index("--port") + 1]) if "--port" in legacy_argv else 8005,
        host=legacy_argv[legacy_argv.index("--host") + 1] if "--host" in legacy_argv else "127.0.0.1",
    )
    call_mod.main(legacy._build_call_args(parsed, argv=legacy_argv))

    assert captured == expected


def test_public_bind_disables_the_auth_escape_hatch(monkeypatch):
    """--public must not open an unauthenticated surface.

    ``run_server`` forces ``0.0.0.0`` under ``--public`` and publishes it as
    ``PRAISONAI_CALL_BIND_HOST``; the ``PRAISONAI_CALL_AUTH=disabled`` escape
    hatch is honoured only for a loopback bind, so exposing the server
    publicly cannot also switch authentication off.
    """
    import asyncio

    fastapi = pytest.importorskip("fastapi")
    from praisonai.api import agent_invoke

    monkeypatch.setenv("PRAISONAI_CALL_AUTH", "disabled")
    monkeypatch.setenv("PRAISONAI_CALL_BIND_HOST", "0.0.0.0")
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(agent_invoke.verify_token(request=None, authorization=None))
    assert exc.value.status_code == 503


def test_run_server_publishes_the_public_bind_host(monkeypatch):
    """The bind host the auth guard reads must reflect the --public override."""
    call_mod = pytest.importorskip("praisonai.api.call")

    monkeypatch.setattr(call_mod, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(call_mod, "setup_public_url", lambda port: "https://example.ngrok.app")
    monkeypatch.delenv("PRAISONAI_CALL_BIND_HOST", raising=False)

    seen = {}
    fake_uvicorn = type("_U", (), {"run": staticmethod(lambda app, **kw: seen.update(kw))})
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(call_mod, "build_call_app", lambda **kw: object())

    # A user asking for --public with a loopback --host must still end up bound
    # (and reported) as 0.0.0.0, so PRAISONAI_CALL_AUTH=disabled stays refused.
    call_mod.run_server(port=9111, host="127.0.0.1", use_public=True)
    assert seen["host"] == "0.0.0.0"
    assert os.environ["PRAISONAI_CALL_BIND_HOST"] == "0.0.0.0"
