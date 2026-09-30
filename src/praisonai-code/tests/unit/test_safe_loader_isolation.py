"""Regression tests for _safe_loader per-load sys.modules isolation.

Guards the multi-tenant fix from #5157 gap 3: concurrent/repeated loads of the
same user .py file must not clobber each other's sys.modules slot, a failed
exec must not pop another load's live module, and successful loads must not
accumulate entries in long-lived processes.
"""

from __future__ import annotations

import sys

import pytest

from praisonai_code._safe_loader import (
    LocalToolsDisabled,
    load_user_module,
    load_user_module_strict,
)


@pytest.fixture(autouse=True)
def allow_local_tools(monkeypatch):
    monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")


def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body)
    return path


def test_no_fixed_key_leak(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write(tmp_path, "tools.py", "VALUE = 1\n")

    load_user_module(path, name="tools")

    assert "tools" not in sys.modules
    assert not any(
        k.startswith("praisonai_userload::") for k in sys.modules
    )


def test_successful_load_does_not_accumulate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write(tmp_path, "tools.py", "VALUE = 1\n")

    before = len(sys.modules)
    for _ in range(5):
        module = load_user_module(path, name="tools")
        assert module is not None and module.VALUE == 1
    after = len(sys.modules)

    assert after == before


def test_concurrent_loads_get_distinct_identities(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write(tmp_path, "tools.py", "VALUE = 1\n")

    m1 = load_user_module(path, name="tools")
    m2 = load_user_module(path, name="tools")

    assert m1 is not m2
    assert m1.__name__ != m2.__name__


def test_failed_exec_leaves_other_load_untouched(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    good = _write(tmp_path, "good.py", "VALUE = 1\n")
    bad = _write(tmp_path, "bad.py", "raise RuntimeError('boom')\n")

    live = load_user_module(good, name="tools")
    assert live is not None and live.VALUE == 1

    with pytest.raises(RuntimeError):
        load_user_module(bad, name="tools")

    assert live.VALUE == 1
    assert not any(
        k.startswith("praisonai_userload::") for k in sys.modules
    )


def test_strict_loader_matches_isolation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = _write(tmp_path, "tools.py", "VALUE = 1\n")

    before = len(sys.modules)
    m1 = load_user_module_strict(path, name="tools")
    m2 = load_user_module_strict(path, name="tools")
    after = len(sys.modules)

    assert m1 is not m2
    assert m1.__name__ != m2.__name__
    assert after == before
    assert "tools" not in sys.modules


def test_strict_loader_failed_exec_cleans_up(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = _write(tmp_path, "bad.py", "raise RuntimeError('boom')\n")

    with pytest.raises(RuntimeError):
        load_user_module_strict(bad, name="tools")

    assert not any(
        k.startswith("praisonai_userload::") for k in sys.modules
    )


def test_strict_loader_blocked_when_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)
    path = _write(tmp_path, "tools.py", "VALUE = 1\n")

    with pytest.raises(LocalToolsDisabled):
        load_user_module_strict(path, name="tools")
