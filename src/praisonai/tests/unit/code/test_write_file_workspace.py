"""write_file must constrain paths when workspace is omitted."""

from __future__ import annotations

import os

from praisonai.code.tools.write_file import write_file


def test_write_file_without_workspace_stays_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ok = write_file("out.txt", "hello", workspace=None)
    assert ok["success"] is True
    assert (tmp_path / "out.txt").read_text() == "hello"


def test_write_file_without_workspace_blocks_escape(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    result = write_file("../outside.txt", "nope", workspace=None)
    assert result["success"] is False
    assert "outside" in result["error"].lower()
