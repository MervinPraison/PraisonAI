"""Five gaps at the package boundary, each invisible from inside the package.

None of these could fail a test that only imported praisonai_train and ran it:
they are about what the wheel declares, what the integrated CLI can reach, what
CI collects, and what the tool does to the directory you run it from.
"""

import inspect
import re
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
REPO = ROOT.parents[1]


# --------------------------------------------------------------------------- #
# 1. The invocation directory's config.yaml
# --------------------------------------------------------------------------- #
def test_an_existing_config_is_backed_up_before_being_overwritten(tmp_path, monkeypatch):
    """This writes ./config.yaml unconditionally, because the dispatcher reads
    only that path. Losing what was there is not required, and it has already
    happened -- to a file in this repo's own working tree.
    """
    from praisonai_train.cli.commands.train import _materialize_config

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("PRECIOUS: hand written\n")

    _materialize_config({"model_name": "m", "dataset": "d.jsonl"})

    assert (tmp_path / "config.yaml.bak").read_text() == "PRECIOUS: hand written\n"
    written = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert written["dataset"] == [{"name": "d.jsonl"}]


def test_no_backup_is_written_when_nothing_would_change(tmp_path, monkeypatch):
    # Re-running the same command should not litter .bak files.
    from praisonai_train.cli.commands.train import _materialize_config

    monkeypatch.chdir(tmp_path)
    _materialize_config({"model_name": "m"})
    _materialize_config({"model_name": "m"})
    assert not (tmp_path / "config.yaml.bak").exists()


def test_a_first_run_needs_no_backup(tmp_path, monkeypatch):
    from praisonai_train.cli.commands.train import _materialize_config

    monkeypatch.chdir(tmp_path)
    _materialize_config({"model_name": "m"})
    assert not (tmp_path / "config.yaml.bak").exists()


# --------------------------------------------------------------------------- #
# 2. The integrated CLI must reach every command
# --------------------------------------------------------------------------- #
def test_importing_the_train_module_alone_registers_every_command():
    """`praisonai train` exposed 6 of 15 commands and no `remote` group.

    The integrated CLI (praisonai_code/cli/app.py:429) imports
    `praisonai_train.cli.commands.train` and takes its `app`. Every other
    command registers as a side effect of importing `praisonai_train.cli.app`,
    which that path never touches -- so nine commands and a whole group were
    invisible from `praisonai`.
    """
    import importlib
    import sys

    for mod in [m for m in sys.modules if m.startswith("praisonai_train.cli")]:
        del sys.modules[mod]
    app = importlib.import_module("praisonai_train.cli.commands.train").app

    names = {c.name or c.callback.__name__ for c in app.registered_commands}
    for expected in ("llm", "models", "checkpoints", "infer", "serve",
                     "benchmark", "generate", "dedup", "validate"):
        assert expected in names, f"`praisonai train {expected}` is unreachable"
    assert "remote" in {g.name for g in app.registered_groups}


def test_one_broken_command_module_does_not_hide_the_others():
    # A missing optional dependency in one command must not take the rest down.
    src = inspect.getsource(
        __import__("praisonai_train.cli.commands.train", fromlist=["x"])
        ._register_sibling_commands)
    assert "except Exception" in src


# --------------------------------------------------------------------------- #
# 3. CI must actually collect the tests
# --------------------------------------------------------------------------- #
WORKFLOW = REPO / ".github" / "workflows" / "test-core.yml"


@pytest.mark.skipif(not WORKFLOW.exists(), reason="workflow not in this checkout")
def test_ci_collects_every_test_directory():
    """tests/unit/data/ -- 96 tests -- was collected by no workflow at all."""
    # Comments stripped first. The comment explaining this very fix sits
    # inside the shard block and contains "tests/unit/data/", so an assertion
    # over the raw text matches the explanation rather than the `paths:` value
    # and passes however the workflow is configured. Third time this exact
    # shape has come up, so it is spelled out.
    body = "\n".join(l for l in WORKFLOW.read_text().splitlines()
                     if not l.lstrip().startswith("#"))
    shard = body[body.index("- shard: train"):]
    shard = shard[:shard.index("- shard:", 10)]
    for directory in sorted(p.name for p in (ROOT / "tests" / "unit").iterdir()
                            if p.is_dir() and not p.name.startswith("_")):
        assert f"tests/unit/{directory}/" in shard, (
            f"tests/unit/{directory}/ is never collected by CI")


# --------------------------------------------------------------------------- #
# 4. The suite must run on the floor the package declares
# --------------------------------------------------------------------------- #
def test_tests_do_not_require_a_newer_python_than_pyproject_allows():
    """`requires-python = ">=3.10"` while two tests needed 3.11.

    CI pins 3.11, so this was invisible: a 3.10 user got collection errors from
    a package that claims to support them.
    """
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    floor = data["project"]["requires-python"]
    assert "3.10" in floor, f"floor moved to {floor}; update this test deliberately"

    only_311 = {"tomllib": "3.11", "sys.stdlib_module_names": "3.10"}
    for path in (ROOT / "tests").rglob("*.py"):
        text = path.read_text()
        for symbol in only_311:
            if symbol in text:
                assert re.search(r"ModuleNotFoundError|getattr\(sys,", text), (
                    f"{path.name} uses {symbol} with no fallback for the "
                    f"declared floor")


# --------------------------------------------------------------------------- #
# 5. Everything the llm path imports must be declared
# --------------------------------------------------------------------------- #
def test_the_llm_extra_declares_the_wrapper_it_hard_requires():
    """praison_ai.py:988 imports praisonai.cli.legacy... in parse_args().

    Neither praisonai-train nor praisonai-code declared `praisonai`, so
    `pip install "praisonai-train[llm]"` gave you an `llm` command that died at
    argument parsing. CI never saw it because it installs every package.
    """
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    llm = data["project"]["optional-dependencies"]["llm"]
    names = {re.split(r"[<>=!\[ ]", spec)[0] for spec in llm}
    assert "praisonai" in names, "the llm extra does not declare the wrapper"
    assert "praisonai-code" in names
