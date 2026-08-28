"""284 lines of working SSH training that nothing could reach.

`praisonai_train/remote/runner.py` implements the one capability unsloth has no
counterpart for — preflight, ship the job, start it detached, stream the log,
fetch the adapter, stop it — and had **zero call sites outside its own
package**. No command exposed it, so from a user's point of view the feature
did not exist.

These tests drive the CLI with a fake runner. They assert the wiring: that the
commands exist, that failures exit non-zero rather than printing and carrying
on, and that a run id survives long enough to be reattached to.
"""

import sys

import pytest
from typer.testing import CliRunner

from praisonai_train.cli import app as app_mod
from praisonai_train.cli.commands import remote as remote_cmd

runner = CliRunner()


class _FakeRun:
    def __init__(self, run_id="run-123"):
        self.host = "gpubox"
        self.run_id = run_id
        self.remote_dir = f"/home/me/.praisonai-train/{run_id}"
        self.log_path = f"{self.remote_dir}/train.log"


class _FakeHost:
    alias = "gpubox"

    def resolve_workdir(self):
        return "/home/me/.praisonai-train"


class _FakePreflight:
    def __init__(self, ok=True, why="no CUDA GPU found"):
        self.ok = ok
        self._why = why

    def why_not(self):
        return self._why


class _FakeRunner:
    """Records what the CLI asked for."""

    def __init__(self, ok=True, started=True, stopped=True, lines=("step 1", "done")):
        self.host = _FakeHost()
        self._ok = ok
        self._started = started
        self._stopped = stopped
        self._lines = lines
        self.calls = []

    def preflight(self, expect_gpus=1):
        self.calls.append(("preflight", expect_gpus))
        return _FakePreflight(self._ok)

    def start(self, config_path, dataset_path=None, run_id=None, expect_gpus=1, env=None):
        self.calls.append(("start", str(config_path), str(dataset_path), expect_gpus))
        if not self._started:
            from praisonai_train.remote.runner import RemoteError
            raise RemoteError("gpubox: no CUDA GPU found (nvidia-smi returned nothing)")
        return _FakeRun(run_id or "run-123")

    def tail(self, run, on_line, **kw):
        self.calls.append(("tail", run.run_id))
        for line in self._lines:
            on_line(line)

    def status(self, run):
        self.calls.append(("status", run.run_id))
        return "completed"

    def fetch(self, run, remote_rel, dest):
        self.calls.append(("fetch", run.run_id, remote_rel, str(dest)))
        return dest

    def stop(self, run):
        self.calls.append(("stop", run.run_id))
        return self._stopped


@pytest.fixture
def fake(monkeypatch):
    holder = {}

    def _install(**kw):
        r = _FakeRunner(**kw)
        holder["runner"] = r
        monkeypatch.setattr(remote_cmd, "_runner", lambda *a, **k: r)
        return r

    holder["install"] = _install
    return holder


# --------------------------------------------------------------------------- #
# Reachability — the whole point
# --------------------------------------------------------------------------- #
def test_remote_is_a_registered_command_group():
    assert "remote" in {g.name for g in app_mod.app.registered_groups}


def test_every_stage_of_the_workflow_has_a_command():
    names = {c.name or c.callback.__name__
             for c in remote_cmd.remote_app.registered_commands}
    assert {"preflight", "start", "tail", "status", "fetch", "stop"} <= names


# --------------------------------------------------------------------------- #
# preflight
# --------------------------------------------------------------------------- #
def test_a_ready_host_reports_success(fake):
    fake["install"](ok=True)
    result = runner.invoke(app_mod.app, ["remote", "preflight", "gpubox"])
    assert result.exit_code == 0, result.output


def test_an_unready_host_exits_non_zero_with_the_reason(fake):
    # "not ready" is an answer, not a crash — but it must not exit 0, or a
    # script will happily ship a job to a box that cannot run it.
    fake["install"](ok=False)
    result = runner.invoke(app_mod.app, ["remote", "preflight", "gpubox"])
    assert result.exit_code == 1
    assert "no CUDA GPU" in result.output


def test_the_gpu_count_reaches_the_runner(fake):
    r = fake["install"](ok=True)
    runner.invoke(app_mod.app, ["remote", "preflight", "gpubox", "--gpus", "2"])
    assert ("preflight", 2) in r.calls


def test_json_output_is_machine_readable(fake):
    import json
    fake["install"](ok=True)
    result = runner.invoke(app_mod.app, ["remote", "preflight", "gpubox", "--json"])
    assert json.loads(result.output)["ok"] is True


def test_json_preflight_still_exits_non_zero_when_unready(fake):
    # A machine-readable "not ready" must not exit 0, or a script reading only
    # the exit status ships a job to a box that cannot run it.
    import json
    fake["install"](ok=False)
    result = runner.invoke(app_mod.app, ["remote", "preflight", "gpubox", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.output)["ok"] is False


# --------------------------------------------------------------------------- #
# start
# --------------------------------------------------------------------------- #
def test_start_ships_the_config_and_dataset(fake, tmp_path):
    r = fake["install"]()
    cfg = tmp_path / "config.yaml"; cfg.write_text("model_name: x\n")
    data = tmp_path / "train.jsonl"; data.write_text("{}\n")
    result = runner.invoke(app_mod.app, [
        "remote", "start", "gpubox", "-c", str(cfg), "-d", str(data), "--no-follow"])
    assert result.exit_code == 0, result.output
    started = [c for c in r.calls if c[0] == "start"][0]
    assert started[1] == str(cfg) and started[2] == str(data)


def test_start_prints_the_run_id_before_streaming(fake, tmp_path):
    """The id has to survive a Ctrl-C during --follow.

    Printing it only at the end would mean an interrupted follow leaves the
    user with a job running on a remote box and no handle to reattach or stop.
    """
    fake["install"]()
    cfg = tmp_path / "config.yaml"; cfg.write_text("model_name: x\n")
    result = runner.invoke(app_mod.app, [
        "remote", "start", "gpubox", "-c", str(cfg)])
    out = result.output
    assert "run-123" in out
    assert out.index("run-123") < out.index("step 1"), (
        "the run id is printed after the log; an interrupted follow loses it")
    assert "remote stop gpubox run-123" in out, "no way to stop it is shown"


def test_a_refused_start_exits_non_zero(fake, tmp_path):
    fake["install"](started=False)
    cfg = tmp_path / "config.yaml"; cfg.write_text("model_name: x\n")
    result = runner.invoke(app_mod.app, [
        "remote", "start", "gpubox", "-c", str(cfg)])
    assert result.exit_code == 1
    assert "no CUDA GPU" in result.output


def test_a_missing_config_is_refused_before_any_ssh(fake, tmp_path):
    r = fake["install"]()
    result = runner.invoke(app_mod.app, [
        "remote", "start", "gpubox", "-c", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0
    assert r.calls == [], "it tried to reach the host with no config to send"


# --------------------------------------------------------------------------- #
# reattach, fetch, stop
# --------------------------------------------------------------------------- #
def test_tail_reattaches_by_run_id(fake):
    r = fake["install"]()
    result = runner.invoke(app_mod.app, ["remote", "tail", "gpubox", "run-123"])
    assert result.exit_code == 0
    assert ("tail", "run-123") in r.calls
    assert "step 1" in result.output


def test_status_reports_how_it_ended(fake):
    fake["install"]()
    result = runner.invoke(app_mod.app, ["remote", "status", "gpubox", "run-123"])
    assert "completed" in result.output


def test_fetch_names_the_artifact_and_the_destination(fake, tmp_path):
    r = fake["install"]()
    result = runner.invoke(app_mod.app, [
        "remote", "fetch", "gpubox", "run-123", "lora_model", "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert ("fetch", "run-123", "lora_model", str(tmp_path)) in r.calls


def test_stopping_something_already_finished_says_so(fake):
    # Reporting success for a no-op would let a script believe it killed a run
    # that is still burning GPU hours.
    fake["install"](stopped=False)
    result = runner.invoke(app_mod.app, ["remote", "stop", "gpubox", "run-123"])
    assert "was not running" in result.output


# --------------------------------------------------------------------------- #
# resolve_workdir must let the remote shell expand ~
# --------------------------------------------------------------------------- #
def test_resolve_workdir_expands_tilde_instead_of_creating_a_dir_named_tilde(
        tmp_path, monkeypatch):
    """A `~` workdir must be expanded by the shell, not created literally.

    Quoting the workdir stopped `~` expanding, so `mkdir` made a directory
    literally named `~` and every derived path landed there. Run the commands
    locally through a real shell rooted at a fake HOME and assert the effect:
    no directory named `~`, and the resolved path carries no `~`.
    """
    import subprocess as _sp

    from praisonai_train.remote.runner import RemoteHost, _Completed

    home = tmp_path / "home"
    home.mkdir()

    class _LocalHost(RemoteHost):
        def run(self, command, timeout=None):
            proc = _sp.run(
                ["sh", "-c", command], capture_output=True, text=True,
                cwd=str(home), env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            )
            return _Completed(proc.returncode, proc.stdout or "", proc.stderr or "")

    host = _LocalHost(alias="local", workdir="~/x")
    resolved = host.resolve_workdir()

    assert not (home / "~").exists(), "a directory literally named '~' was created"
    assert "~" not in resolved, f"the resolved workdir still contains '~': {resolved!r}"
    assert (home / "x").is_dir(), "the expanded workdir was not created"


def test_resolve_workdir_rejects_a_shell_unsafe_workdir(tmp_path):
    from praisonai_train.remote.runner import RemoteError, RemoteHost

    host = RemoteHost(alias="local", workdir="~/x; rm -rf /")
    with pytest.raises(RemoteError):
        host.resolve_workdir()


def test_resolve_workdir_treats_a_leading_hyphen_as_a_path_not_an_option(
        tmp_path):
    """A workdir starting with `-` must reach mkdir/cd as a path, not a flag.

    `-rf` passes the character-class check, so without a `--` guard the remote
    `mkdir`/`cd` would parse it as options and either fail or misbehave. Run the
    commands through a real shell and assert the directory was created.
    """
    import subprocess as _sp

    from praisonai_train.remote.runner import RemoteHost, _Completed

    work = tmp_path / "work"
    work.mkdir()

    class _LocalHost(RemoteHost):
        def run(self, command, timeout=None):
            proc = _sp.run(
                ["sh", "-c", command], capture_output=True, text=True,
                cwd=str(work), env={"HOME": str(work), "PATH": "/usr/bin:/bin"},
            )
            return _Completed(proc.returncode, proc.stdout or "", proc.stderr or "")

    host = _LocalHost(alias="local", workdir="-rf")
    resolved = host.resolve_workdir()

    assert (work / "-rf").is_dir(), "a leading-hyphen workdir was not created"
    assert resolved.endswith("-rf"), f"unexpected resolved workdir: {resolved!r}"


# --------------------------------------------------------------------------- #
# The module has to exist
# --------------------------------------------------------------------------- #
def test_the_real_runner_imports():
    """The test that was missing, and the reason CI failed seven times.

    Every test above replaces `_runner` with a fake, so none of them ever
    imported `praisonai_train.remote.runner`. The module was untracked — present
    in a working tree, absent from the repo — and the mocks hid that completely:
    a green suite for a command that raised ModuleNotFoundError on every
    invocation.

    A fake is the right tool for the CLI's behaviour. It is the wrong tool for
    "does the thing I am faking exist", and that needs saying out loud once.
    """
    from praisonai_train.remote.runner import RemoteError, RemoteRun, RemoteRunner

    assert callable(RemoteRunner)
    assert issubclass(RemoteError, Exception)
    assert RemoteRun is not None


def test_the_runner_has_the_api_the_cli_calls():
    # The fake implements this shape; if the real one drifts from it, every
    # test above keeps passing against a contract nothing honours.
    from praisonai_train.remote.runner import RemoteRunner

    for name in ("preflight", "start", "tail", "status", "fetch", "stop"):
        assert callable(getattr(RemoteRunner, name, None)), (
            f"RemoteRunner has no {name}(), but the CLI calls it")


def test_the_runner_needs_no_dependency_beyond_the_standard_library():
    # It shells out to ssh/scp deliberately: an SSH library would be a new
    # dependency for a feature most users never touch.
    import ast
    import pathlib

    import praisonai_train.remote.runner as mod

    tree = ast.parse(pathlib.Path(mod.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    # sys.stdlib_module_names is 3.10+, but was only added for *some* names in
    # 3.10; fall back to a check that works on the declared floor.
    stdlib = set(getattr(sys, "stdlib_module_names", ()) or sys.builtin_module_names)
    third_party = imported - stdlib - {"praisonai_train"}
    assert not third_party, f"the runner pulls in {sorted(third_party)}"
