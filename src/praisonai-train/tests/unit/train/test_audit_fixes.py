"""Four defects an adversarial audit found in the eleven merged PRs.

Every one of them passed the suite that shipped it. The tests below are written
to fail if the defect returns, and each was checked by reintroducing it.
"""

import inspect
import io
import contextlib

import pytest

from praisonai_train import _hub
from praisonai_train.remote import runner as rr
from praisonai_train.train.llm import trainer as trainer_mod


# --------------------------------------------------------------------------- #
# 1. cpt silently lost the one value it exists to set
# --------------------------------------------------------------------------- #
def test_config_fields_include_a_plain_init_subclass():
    """`__dataclass_fields__` is INHERITED.

    UnslothTrainingArguments (unsloth/trainer.py:445) is a plain __init__
    subclass of TrainingArguments, so the attribute resolved to the PARENT's
    fields and never contained embedding_learning_rate. The drop-unknown filter
    then deleted it 45 lines after the cpt path set it -- along with
    max_seq_length and packing. Nothing raised; the run used the adapter's
    learning rate for the embeddings, which is the recipe the whole feature
    exists to avoid.
    """
    from dataclasses import make_dataclass

    Parent = make_dataclass("Parent", [("output_dir", object, None),
                                       ("learning_rate", object, None)])

    class Child(Parent):
        # Deliberately NO **kwargs: with one, the helper returns None (filter
        # nothing) and the assertion below would pass without the signature
        # scan ever running -- which is how the first version of this test
        # survived its own mutation.
        def __init__(self, embedding_learning_rate=None, output_dir=None):
            pass

    accepted = trainer_mod._accepted_config_fields(Child)
    assert accepted is not None, "the fake should be filterable"
    assert "embedding_learning_rate" in accepted, (
        "a value the class accepts would be filtered out")
    assert "learning_rate" in accepted, "the parent's own fields were lost"


def test_a_kwargs_config_filters_nothing():
    # A class taking **kwargs accepts anything; filtering against a partial
    # list would drop valid settings.
    class KW:
        def __init__(self, **kwargs):
            pass

    assert trainer_mod._accepted_config_fields(KW) is None


def test_a_real_dataclass_still_filters():
    from dataclasses import make_dataclass

    D = make_dataclass("D", [("a", object, None)])
    accepted = trainer_mod._accepted_config_fields(D)
    assert accepted is not None and "a" in accepted and "zzz" not in accepted


# --------------------------------------------------------------------------- #
# 2. remote start could never train
# --------------------------------------------------------------------------- #
def test_the_remote_launch_puts_the_config_behind_its_flag():
    """`llm` is `llm [DATASET] --config X`, not `llm CONFIG DATASET`.

    Passing config.yaml as the positional meant two positionals and exit 2
    before the GPU was touched -- or, with no dataset, config.yaml rewritten to
    name itself as the corpus.
    """
    runner = rr.RemoteRunner.__new__(rr.RemoteRunner)
    runner.host = rr.RemoteHost(alias="h", python="python3", workdir="~/w")
    run = rr.RemoteRun(host="h", run_id="run-1",
                       remote_dir="/w/run-1", log_path="/w/run-1/train.log")

    script = runner._launch_script(run, " ds.jsonl", None)

    assert "--config config.yaml" in script, "the config is not passed as an option"
    assert "llm config.yaml" not in script, "the config is still a positional"
    # And the dataset stays where `llm` expects it: positional, before the flag.
    assert script.index("ds.jsonl") < script.index("--config")


def test_the_recorded_pid_owns_the_trainer_signalable_by_group(tmp_path):
    """The pid file must name the process that owns the trainer's group.

    `$!` in the outer shell caught the transient subshell that backgrounded the
    whole `&&` list -- a process that can exit while training runs on, at which
    point `status` reports `unknown`. The launch now records the pid of the
    wrapper that owns the trainer and, where `setsid` exists, makes that wrapper
    a process-group leader so its children (dataloader workers, torchrun ranks)
    share one group. `status` probes the recorded pid and `stop` resolves that
    pid's group and signals ``-$pgid`` -- so a TERM reaches the trainer through
    the group rather than a wrapper that would never forward it.

    Run the real launch script under /bin/sh with a stand-in trainer that
    records its own pid, then assert the recorded pid owns the trainer (it is
    the trainer's parent) and that a TERM to the recorded pid's group actually
    reaches the trainer (it stops).
    """
    import os
    import signal
    import subprocess
    import time

    # A stand-in "trainer" invoked in place of the python interpreter: it
    # records its own pid and parent, and lingers so the processes are still
    # around to inspect and signal.
    stub = tmp_path / "fake-trainer"
    stub.write_text(
        "#!/bin/sh\n"
        f"echo $$ > {tmp_path / 'trainer_pid'}\n"
        f"ps -o ppid= -p $$ | tr -d ' ' > {tmp_path / 'trainer_ppid'}\n"
        "sleep 30\n"
    )
    os.chmod(stub, 0o755)

    runner = rr.RemoteRunner.__new__(rr.RemoteRunner)
    runner.host = rr.RemoteHost(alias="h", python=str(stub),
                                workdir=str(tmp_path))
    run = rr.RemoteRun(host="h", run_id="run-1", remote_dir=str(tmp_path),
                       log_path=str(tmp_path / "train.log"))

    script = runner._launch_script(run, "", None)
    subprocess.run(["/bin/sh", "-c", script], cwd=str(tmp_path), check=True)

    pid_file = tmp_path / "train.pid"
    trainer_pid_file = tmp_path / "trainer_pid"
    trainer_ppid_file = tmp_path / "trainer_ppid"
    # Wait for CONTENT, not for existence. `>` creates the target before the
    # command on its left produces a byte, so `ps ... > trainer_ppid` leaves an
    # empty file for as long as `ps` takes to run. Breaking on existence read
    # that empty file and compared '' to the recorded pid -- a real intermittent
    # failure in CI, not a slow machine: the window is the runtime of `ps`.
    def _settled(path):
        try:
            return path.read_text().strip() != ""
        except OSError:
            return False

    for _ in range(50):
        if all(_settled(f) for f in (pid_file, trainer_pid_file, trainer_ppid_file)):
            break
        time.sleep(0.1)
    assert pid_file.exists(), "no pid was recorded"
    assert trainer_pid_file.exists(), "the stand-in trainer never ran"
    # Named separately from the equality below, so a timeout reads as "the
    # trainer never reported its parent" rather than as the ownership bug this
    # test exists to catch.
    assert _settled(trainer_ppid_file), (
        "the stand-in trainer never recorded its parent pid within 5s")

    recorded = pid_file.read_text().strip()
    trainer_pid = trainer_pid_file.read_text().strip()
    trainer_ppid = trainer_ppid_file.read_text().strip()
    try:
        # The recorded pid must own the trainer: it is the trainer's parent, so
        # `status` probes a live process and `stop` can resolve its group.
        assert trainer_ppid == recorded, (
            f"recorded pid {recorded} does not own the trainer "
            f"(trainer's parent is {trainer_ppid})")

        # A TERM to the recorded pid's group must actually stop the trainer:
        # prove `stop`'s group signal reaches the work, not a non-forwarding
        # wrapper that would leave the trainer orphaned.
        os.killpg(os.getpgid(int(recorded)), signal.SIGTERM)
        for _ in range(50):
            try:
                os.kill(int(trainer_pid), 0)
            except OSError:
                break
            time.sleep(0.1)
        else:
            raise AssertionError(
                f"trainer {trainer_pid} survived TERM to recorded pid "
                f"{recorded}'s group -- stop does not reach the trainer")
    finally:
        # Leave no descendants behind regardless of assertion outcome.
        for stray in (recorded, trainer_pid):
            try:
                os.kill(int(stray), signal.SIGKILL)
            except (OSError, ValueError):
                pass


# --------------------------------------------------------------------------- #
# 3. remote command injection and path traversal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    "x;touch /tmp/pwned",      # the reported injection
    "$(id)",
    "`id`",
    "a b",
    "../escape",
    "/absolute",
    "",
    "-leading-dash",
])
def test_a_run_id_that_is_not_an_identifier_is_refused(bad):
    with pytest.raises(rr.RemoteError):
        rr.validate_run_id(bad)


def test_a_normal_run_id_is_accepted():
    assert rr.validate_run_id("run-1787667005") == "run-1787667005"
    assert rr.validate_run_id("my_run.2") == "my_run.2"


@pytest.mark.parametrize("bad", [
    "../../../../etc/passwd",   # passed the existence check and copied back
    "/etc/passwd",
    "a/../../b",
    "",
    "   ",
])
def test_a_fetch_path_leaving_the_run_directory_is_refused(bad):
    with pytest.raises(rr.RemoteError):
        rr.validate_remote_rel(bad)


def test_fetch_validates_before_building_the_remote_path():
    # Calling the validator in a test proves nothing if fetch never calls it.
    src = inspect.getsource(rr.RemoteRunner.fetch)
    check = src.index("validate_remote_rel")
    build = src.index('remote_abs = f"')
    assert check < build, "the path is built before it is checked"


def test_a_normal_fetch_path_is_accepted():
    assert rr.validate_remote_rel("lora_model") == "lora_model"
    assert rr.validate_remote_rel("outputs/checkpoint-100") == "outputs/checkpoint-100"


def test_the_scp_target_is_quoted_for_the_remote_shell():
    # The far half of an scp target is expanded by a shell on the other side,
    # so passing it as one argv element is not enough.
    src = inspect.getsource(rr.RemoteRunner._ship)
    assert "shlex.quote(remote_abs)" in src, "the scp target is unquoted"


def test_start_validates_the_run_id_before_touching_the_host():
    src = inspect.getsource(rr.RemoteRunner.start)
    assert "validate_run_id" in src


# --------------------------------------------------------------------------- #
# 4. hf_private failed open
# --------------------------------------------------------------------------- #
def _private(value):
    with contextlib.redirect_stdout(io.StringIO()):
        return _hub.hub_push_kwargs({"hf_private": value})["private"]


@pytest.mark.parametrize("value", [None, "private", "y", "enabled", 5, "", "maybe", []])
def test_anything_unparseable_keeps_the_repository_private(value):
    """The flag's whole purpose is "do not publish this".

    The generic coercion read anything outside {true,1,yes,on} as False, so
    hf_private: private -- a near miss someone would plausibly write -- made
    the repository public.
    """
    assert _private(value) is True, f"{value!r} published the model"


@pytest.mark.parametrize("value", ["false", "no", "0", "off", False])
def test_publishing_still_works_when_asked_plainly(value):
    assert _private(value) is False


def test_an_unparseable_value_says_what_it_did():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _hub.hub_push_kwargs({"hf_private": "enabled"})
    out = buf.getvalue()
    assert "PRIVATE" in out and "hf_private: false" in out, (
        f"the decision was made silently: {out!r}")
