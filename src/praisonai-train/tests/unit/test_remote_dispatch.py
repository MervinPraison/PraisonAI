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
        # The vocabulary the real runner speaks, not one invented here. It
        # returned "done" before, and the dispatch compared against "failed"
        # with ==, so a run that ended "failed (exit 1)" was reported as a
        # success and the fake agreed with the bug.
        self.state = "completed"
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

    def test_a_dataset_named_only_in_the_config_is_shipped(self, tmp_path):
        # No positional dataset argument, but the resolved config names a local
        # file. It must still be copied, or the remote process gets a path that
        # exists only on this machine.
        data = tmp_path / "d.json"
        data.write_text("[]", encoding="utf-8")
        _dispatch({"remote": {"host": "gpubox"}, "dataset": str(data)})
        sent = FakeRunner.instances[0].started_with["dataset"]
        assert sent is not None and pathlib.Path(sent) == data

    def test_a_non_local_dataset_is_not_shipped(self, tmp_path):
        # A HuggingFace id (or a path already on the far side) is not a file to
        # copy.
        _dispatch({"remote": {"host": "gpubox"}, "dataset": "org/dataset"})
        assert FakeRunner.instances[0].started_with["dataset"] is None

    def test_a_list_form_local_dataset_is_shipped(self, tmp_path):
        # The trainer's canonical shape is a list of mappings, and a `name`
        # that is a local file is loaded from disk. The string-only fallback
        # missed it, so the file never reached the host and the run failed on a
        # path that exists only here.
        data = tmp_path / "d.json"
        data.write_text("[]", encoding="utf-8")
        _dispatch({"remote": {"host": "gpubox"},
                   "dataset": [{"name": str(data)}]})
        sent = FakeRunner.instances[0].started_with["dataset"]
        assert sent is not None and pathlib.Path(sent) == data

    def test_a_list_form_data_files_local_dataset_is_shipped(self, tmp_path):
        # `data_files` names the local file explicitly, with `name` free to be
        # a label. The trainer loads `data_files`, so it is what must ship.
        data = tmp_path / "d.jsonl"
        data.write_text("", encoding="utf-8")
        _dispatch({"remote": {"host": "gpubox"},
                   "dataset": [{"name": "my-set", "data_files": str(data)}]})
        sent = FakeRunner.instances[0].started_with["dataset"]
        assert sent is not None and pathlib.Path(sent) == data

    def test_a_list_form_hub_dataset_is_not_shipped(self, tmp_path):
        # A hub id in list form is not a local file; nothing to copy.
        _dispatch({"remote": {"host": "gpubox"},
                   "dataset": [{"name": "org/dataset"}]})
        assert FakeRunner.instances[0].started_with["dataset"] is None

    def test_the_gpu_expectation_is_passed_through(self):
        _dispatch({"remote": {"host": "gpubox", "gpus": 4}})
        assert FakeRunner.instances[0].started_with["gpus"] == 4

    def test_the_interpreter_and_workdir_are_passed_through(self):
        _dispatch({"remote": {"host": "h", "python": "/opt/py",
                              "workdir": "~/runs"}})
        made = FakeRunner.instances[0]
        assert made.python == "/opt/py"
        assert made.workdir == "~/runs"


class TestTheStatusVocabulary:
    """The fake must speak the language the real runner speaks."""

    def test_the_fake_only_returns_states_the_runner_can_return(self):
        # Read from disk, not through the module: the autouse fixture has
        # already swapped RemoteRunner for the fake, so inspecting the
        # attribute would have this test confirm the fake agrees with itself.
        source = (pathlib.Path(__file__).resolve().parents[2]
                  / "praisonai_train" / "remote" / "runner.py").read_text()
        for word in ("completed", "running", "unknown"):
            assert word in source, (
                f"the runner no longer reports {word!r}; the fakes here are "
                "built on that vocabulary")
        assert "failed (exit" in source, (
            "the runner no longer reports 'failed (exit N)' -- the dispatch "
            "matches that shape by prefix")

    @pytest.mark.parametrize("state", ["failed (exit 1)", "failed (exit 137)"])
    def test_a_failed_run_is_a_failure_however_it_is_spelled(self, state, monkeypatch):
        import typer

        class Failing(FakeRunner):
            def status(self, run):
                return state

        import praisonai_train.remote.runner as runner_mod
        monkeypatch.setattr(runner_mod, "RemoteRunner", Failing)
        with pytest.raises(typer.Exit):
            _dispatch({"remote": {"host": "gpubox"}})

    def test_a_completed_run_is_not_a_failure(self, monkeypatch):
        class Completed(FakeRunner):
            def status(self, run):
                return "completed"

        import praisonai_train.remote.runner as runner_mod
        monkeypatch.setattr(runner_mod, "RemoteRunner", Completed)
        assert _dispatch({"remote": {"host": "gpubox"}}) is True


class TestFailure:
    def test_a_run_that_ends_failed_is_reported_as_failure(self, monkeypatch):
        import typer

        class Failing(FakeRunner):
            def status(self, run):
                return "failed (exit 1)"

        import praisonai_train.remote.runner as runner_mod
        monkeypatch.setattr(runner_mod, "RemoteRunner", Failing)
        with pytest.raises(typer.Exit):
            _dispatch({"remote": {"host": "gpubox"}})

    def test_a_failed_status_with_an_exit_code_is_reported_as_failure(self, monkeypatch):
        # status() returns "failed (exit N)", not a bare "failed". An equality
        # check matched neither and reported a failed run as success.
        import typer

        class Failing(FakeRunner):
            def status(self, run):
                return "failed (exit 1)"

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

        import praisonai_train._code_bridge as bridge
        monkeypatch.setattr(bridge, "import_code_module", _boom)
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
        import typer

        import praisonai_train._code_bridge as bridge
        monkeypatch.setattr(bridge, "import_code_module",
                            lambda *_a, **_k: (_ for _ in ()).throw(ImportError("no")))
        # The ImportError is surfaced as a typer.Exit; asserting it keeps this
        # test honest -- a blind `except Exception` would pass even if the
        # command failed for an unrelated reason before the local trainer.
        with pytest.raises(typer.Exit):
            train_cmd.train_llm(config=config)
        assert FakeRunner.instances == [], "a local run was sent to a remote host"

    def test_dry_run_shows_the_remote_block_and_sends_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        config = _config(tmp_path, {"model_name": "unsloth/tiny",
                                    "remote": {"host": "gpubox"}})
        train_cmd.train_llm(config=config, dry_run=True)
        assert FakeRunner.instances == [], "--dry-run started a real run"
