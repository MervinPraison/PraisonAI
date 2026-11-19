"""Recipe run ids, replay trace names and archive links stay inside their dirs.

``options.trace_name`` becomes the run id, which names the run-history folder
and the replay trace file. An archive extracted without the tarfile data
filter (older CPython) must not contain links.
"""

import io
import tarfile

import pytest

from praisonai.recipe.history import RunHistory, RunHistoryError
from praisonai.recipe.models import RecipeResult
from praisonai.recipe.registry import RegistryError, _safe_extractall

BAD_IDS = ["../../../../ESCAPED_RUN", "../x", "a/b", "/abs", ".."]


def _result(run_id):
    return RecipeResult(run_id=run_id, recipe="demo", version="1.0", status="success")


@pytest.mark.parametrize("run_id", BAD_IDS)
def test_history_refuses_run_id_outside_runs_dir(tmp_path, run_id):
    hist = RunHistory(path=tmp_path / "a" / "b" / "c" / "runs")
    with pytest.raises(RunHistoryError):
        hist.store(_result(run_id))
    with pytest.raises(RunHistoryError):
        hist.get(run_id)
    assert not any(p.name == "ESCAPED_RUN" for p in tmp_path.rglob("*"))
    assert not (tmp_path / "a" / "b" / "c" / "x").exists()


def test_history_plain_run_id_still_works(tmp_path):
    hist = RunHistory(path=tmp_path / "runs")
    hist.store(_result("my-trace_1"))
    assert hist.get("my-trace_1")["run_id"] == "my-trace_1"


@pytest.mark.parametrize("name", BAD_IDS)
def test_trace_path_refuses_names_outside_traces_dir(tmp_path, name):
    from praisonai.replay.storage import get_trace_path

    with pytest.raises(ValueError):
        get_trace_path(name, tmp_path / "traces")
    assert get_trace_path("run-1", tmp_path / "traces") == tmp_path / "traces" / "run-1.jsonl"


def test_links_refused_without_tar_data_filter(tmp_path, monkeypatch):
    """Chain a -> ., a/b -> .., then a/b/escaped.txt (link ordering)."""
    dest = tmp_path / "x" / "dest"
    dest.mkdir(parents=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, target in (("a", "."), ("a/b", "..")):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            tf.addfile(info)
        info = tarfile.TarInfo("a/b/escaped.txt")
        info.size = 3
        tf.addfile(info, io.BytesIO(b"pwn"))
    buf.seek(0)
    with tarfile.open(fileobj=buf) as tf:
        orig = tf.extractall
        tf.extractall = lambda path, **kw: orig(path) if not kw else (_ for _ in ()).throw(TypeError())
        with pytest.raises(RegistryError):
            _safe_extractall(tf, dest)
    assert not (tmp_path / "x" / "escaped.txt").exists()
