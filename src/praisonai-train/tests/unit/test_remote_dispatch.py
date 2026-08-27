"""`praisonai-train llm` sends the job elsewhere when the config says so.

The RemoteRunner is replaced, so nothing here opens an ssh connection. What is
under test is the decision and what gets handed over -- not the transport.
"""

import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from praisonai_train.cli.commands import train as train_cmd  # noqa: E402


class FakeRun:
    run_id = "run-fake"


class FakeRunner:
    """Records what it was asked to do."""

    instances = []

    def __init__(self, host, python, workdir):
        self.host, self.python, self.workdir = host, python, workdir
        self.started_with = None
        self.tailed = False
        self.state = "done"
        FakeRunner.instances.append(self)

    def start(self, config_path=None, dataset_path=None, expect_gpus=1, **_):
        self.started_with = {"config": pathlib.Path(config_path),
                             "dataset": dataset_path, "gpus": expect_gpus}
        return FakeRun()

    def tail(self, run, on_line=None):
        self.tailed = True

    def status(self, run):
        return self.state


@pytest.fixture(autouse=True)
def _fake_runner(monkeypatch):
    FakeRunner.instances = []
    import praisonai_train.remote.runner as runner_mod
    monkeypatch.setattr(runner_mod, "RemoteRunner", FakeRunner)
    yield


def _config(tmp_path, body):
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


def _dispatch(resolved, overrides=None, dataset=None):
    return train_cmd._dispatch_remote(resolved, overrides or {}, None, dataset)


class TestTheDecision:
    def test_a_local_config_does_not_dispatch(self):
        assert _dispatch({"model_name": "m"}) is False
        assert FakeRunner.instances == []

    def test_a_remote_block_dispatches(self):
        assert _dispatch({"model_name": "m", "remote": {"host": "gpubox"}}) is True
        assert len(FakeRunner.instances) == 1
        assert FakeRunner.instances[0].host == "gpubox"

    def test_a_flag_dispatches_without_any_yaml(self):
        assert _dispatch({"model_name": "m"}, {"host": "gpubox"}) is True
        assert FakeRunner.instances[0].host == "gpubox"

    def test_the_run_is_followed_and_its_status_reported(self):
        _dispatch({"remote": {"host": "gpubox"}})
        assert FakeRunner.instances[0].tailed, "the log was never streamed"


class TestWhatIsHandedOver:
    def test_the_shipped_config_carries_the_resolved_settings(self, tmp_path):
        _dispatch({"model_name": "unsloth/tiny", "lora_r": 32,
                   "remote": {"host": "gpubox"}})
        shipped = FakeRunner.instances[0].started_with["config"]
        sent = yaml.safe_load(shipped.read_text())
        assert sent["model_name"] == "unsloth/tiny"
        assert sent["lora_r"] == 32

    def test_the_remote_block_is_not_shipped(self):
        # Otherwise the far side reads its own config, finds a host, and
        # dispatches again.
        _dispatch({"model_name": "m", "remote": {"host": "gpubox"}})
        shipped = FakeRunner.instances[0].started_with["config"]
        sent = yaml.safe_load(shipped.read_text())
        assert "remote" not in sent, f"the remote block was shipped: {sent}"

    def test_it_does_not_write_config_yaml_into_the_working_directory(
            self, tmp_path, monkeypatch):
        # Training elsewhere must not rewrite a file where the user is standing.
        monkeypatch.chdir(tmp_path)
        _dispatch({"model_name": "m", "remote": {"host": "gpubox"}})
        assert not (tmp_path / "config.yaml").exists(), (
            "a remote run clobbered ./config.yaml")

    def test_the_gpu_expectation_is_passed_through(self):
        _dispatch({"remote": {"host": "gpubox", "gpus": 4}})
        assert FakeRunner.instances[0].started_with["gpus"] == 4

    def test_the_interpreter_and_workdir_are_passed_through(self):
        _dispatch({"remote": {"host": "h", "python": "/opt/py",
                              "workdir": "~/runs"}})
        made = FakeRunner.instances[0]
        assert made.python == "/opt/py"
        assert made.workdir == "~/runs"


class TestFailure:
    def test_a_run_that_ends_failed_is_reported_as_failure(self, monkeypatch):
        import typer

        class Failing(FakeRunner):
            def status(self, run):
                return "failed"

        import praisonai_train.remote.runner as runner_mod
        monkeypatch.setattr(runner_mod, "RemoteRunner", Failing)
        with pytest.raises(typer.Exit):
            _dispatch({"remote": {"host": "gpubox"}})

    def test_bad_remote_settings_exit_rather_than_training_locally(self):
        import typer
        with pytest.raises(typer.Exit):
            _dispatch({"remote": {"host": "gpu; rm -rf /"}})
        assert FakeRunner.instances == [], "it tried to connect anyway"


class TestTheCommandActuallyDispatches:
    """Driving `train_llm` itself, not the helper underneath it.

    The tests above call _dispatch_remote directly, so deleting the call site
    in train_llm left every one of them passing while the remote option did
    nothing at all. These go through the command.
    """

    def test_llm_with_a_remote_config_never_reaches_the_local_trainer(
            self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _config(tmp_path, {"model_name": "unsloth/tiny",
                                    "dataset": "d.json",
                                    "remote": {"host": "gpubox"}})

        # If the local path were taken it would import the heavy runner. Make
        # that unmistakable rather than merely slow.
        def _boom(*_a, **_k):
            raise AssertionError("the local trainer was reached for a remote run")

        monkeypatch.setattr(train_cmd, "import_code_module", _boom, raising=False)
        train_cmd.train_llm(config=config)

        assert len(FakeRunner.instances) == 1, "the run was not sent anywhere"
        assert FakeRunner.instances[0].host == "gpubox"

    def test_llm_with_the_flag_and_no_yaml_dispatches(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _config(tmp_path, {"model_name": "unsloth/tiny", "dataset": "d.json"})
        train_cmd.train_llm(config=config, remote_host="gpubox")
        assert len(FakeRunner.instances) == 1
        assert FakeRunner.instances[0].host == "gpubox"

    def test_llm_without_remote_settings_does_not_dispatch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _config(tmp_path, {"model_name": "unsloth/tiny", "dataset": "d.json"})
        # Stop before the heavy import; the point is only that nothing was sent.
        monkeypatch.setattr(train_cmd, "import_code_module",
                            lambda *_a, **_k: (_ for _ in ()).throw(ImportError("no")),
                            raising=False)
        try:
            train_cmd.train_llm(config=config)
        except Exception:
            pass
        assert FakeRunner.instances == [], "a local run was sent to a remote host"

    def test_dry_run_shows_the_remote_block_and_sends_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _config(tmp_path, {"model_name": "unsloth/tiny",
                                    "remote": {"host": "gpubox"}})
        train_cmd.train_llm(config=config, dry_run=True)
        assert FakeRunner.instances == [], "--dry-run started a real run"
