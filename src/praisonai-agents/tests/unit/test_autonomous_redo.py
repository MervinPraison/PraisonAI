import asyncio

import pytest

from praisonaiagents import Agent


@pytest.mark.parametrize("async_run", [False, True])
def test_autonomous_undo_redo_restores_actual_files(tmp_path, monkeypatch, async_run):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "changed.txt").write_text("before")
    (tmp_path / "deleted.txt").write_text("old")
    (tmp_path / ".env").write_text("secret")
    agent = Agent(name="redo", autonomy={"enabled": True, "snapshot": True, "track_changes": True})

    async def edit(prompt, *args, **kwargs):
        (tmp_path / "changed.txt").write_text("after")
        (tmp_path / "deleted.txt").unlink()
        (tmp_path / "created.txt").write_text("new")
        return "<promise>DONE</promise>"

    monkeypatch.setattr(agent, "achat", edit)
    if async_run:
        asyncio.run(agent.run_autonomous_async("edit", max_iterations=1, completion_promise="DONE"))
    else:
        agent.run_autonomous("edit", max_iterations=1, completion_promise="DONE")
    for _ in range(2):
        assert agent.undo()
        assert (tmp_path / "changed.txt").read_text() == "before"
        assert (tmp_path / "deleted.txt").read_text() == "old"
        assert not (tmp_path / "created.txt").exists()
        assert (tmp_path / ".env").read_text() == "secret"
        assert agent.redo()
        assert (tmp_path / "changed.txt").read_text() == "after"
        assert not (tmp_path / "deleted.txt").exists()
        assert (tmp_path / "created.txt").read_text() == "new"
        assert (tmp_path / ".env").read_text() == "secret"


def test_snapshot_restore_failure_does_not_consume_stacks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    file = tmp_path / "file.txt"
    file.write_text("before")
    agent = Agent(name="redo", autonomy={"enabled": True, "snapshot": True, "track_changes": True})
    agent._take_pre_autonomous_snapshot()
    file.write_text("after")
    original_restore = agent._file_snapshot.restore
    monkeypatch.setattr(agent._file_snapshot, "restore", lambda *args: False)
    assert not agent.undo()
    assert len(agent._snapshot_stack) == 1
    assert agent._redo_stack == []
    assert file.read_text() == "after"
    monkeypatch.setattr(agent._file_snapshot, "restore", original_restore)
    assert agent.undo()
    monkeypatch.setattr(agent._file_snapshot, "restore", lambda *args: False)
    assert not agent.redo()
    assert len(agent._redo_stack) == 1
    assert file.read_text() == "before"
    monkeypatch.setattr(agent._file_snapshot, "restore", original_restore)
    assert agent.redo()
    assert file.read_text() == "after"


def test_multiple_autonomous_runs_undo_redo_in_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    file = tmp_path / "file.txt"
    file.write_text("zero")
    agent = Agent(name="redo", autonomy={"enabled": True, "snapshot": True, "track_changes": True})

    async def edit(prompt, *args, **kwargs):
        file.write_text(prompt.splitlines()[0])
        return "<promise>DONE</promise>"

    monkeypatch.setattr(agent, "achat", edit)
    for value in ("one", "two"):
        agent.run_autonomous(value, max_iterations=1, completion_promise="DONE")
    for action, expected in ((agent.undo, "one"), (agent.undo, "zero"),
                             (agent.redo, "one"), (agent.redo, "two")):
        assert action()
        assert file.read_text() == expected


def test_undo_creation_from_empty_snapshot_and_redo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = Agent(name="redo", autonomy={"enabled": True, "snapshot": True, "track_changes": True})
    file = tmp_path / "new.txt"

    async def edit(prompt, *args, **kwargs):
        file.write_text("new")
        return "<promise>DONE</promise>"

    monkeypatch.setattr(agent, "achat", edit)
    agent.run_autonomous("create", max_iterations=1, completion_promise="DONE")
    assert agent.undo()
    assert not file.exists()
    assert agent.redo()
    assert file.read_text() == "new"


def test_invalid_snapshot_does_not_delete_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    file = tmp_path / "file.txt"
    file.write_text("keep")
    agent = Agent(name="redo", autonomy={"enabled": True, "snapshot": True, "track_changes": True})
    assert not agent._file_snapshot.restore("not-a-commit")
    assert file.read_text() == "keep"
