from pathlib import Path

from praisonaiagents.tools._output_overflow import (
    spill,
    bounded_with_pointer,
    get_spill_dir,
)
from praisonaiagents.tools.shell_tools import ShellTools


def test_spill_writes_full_output(tmp_path):
    output = "line\n" * 5000
    path = spill(output, "stdout", spill_dir=str(tmp_path))
    assert path is not None
    assert path.exists()
    assert path.read_text(encoding="utf-8") == output


def test_bounded_with_pointer_includes_path_and_is_bounded(tmp_path):
    output = "MIDDLE_ERROR\n" + ("x" * 50000)
    path = tmp_path / "artifact.txt"
    path.write_text(output, encoding="utf-8")
    preview = bounded_with_pointer(output, 10000, path)
    # Preview stays bounded relative to the full output.
    assert len(preview) < len(output)
    assert str(path) in preview
    assert "read_file" in preview


def test_bounded_with_pointer_without_path_falls_back(tmp_path):
    output = "y" * 50000
    preview = bounded_with_pointer(output, 10000, None)
    assert "saved to" not in preview
    assert "showing first/last portions" in preview
    assert len(preview) < len(output)


def test_get_spill_dir_env(monkeypatch, tmp_path):
    target = tmp_path / "custom"
    monkeypatch.setenv("PRAISONAI_TOOL_OUTPUT_DIR", str(target))
    assert get_spill_dir() == target
    assert target.exists()


def test_handle_overflow_no_op_when_within_budget():
    tools = ShellTools()
    text = "short output"
    preview, path = tools._handle_overflow(text, "stdout", 10000, True, None)
    assert preview == text
    assert path is None


def test_handle_overflow_spills_and_preserves_middle(tmp_path):
    tools = ShellTools()
    # The critical error is in the middle — must remain retrievable.
    middle = "ASSERTION FAILED at the middle of the log"
    text = ("a" * 20000) + middle + ("b" * 20000)
    preview, path = tools._handle_overflow(
        text, "stdout", 10000, True, str(tmp_path)
    )
    assert path is not None
    saved = Path(path)
    assert saved.exists()
    assert middle in saved.read_text(encoding="utf-8")
    # Preview should NOT contain the buried middle, but must point to the file.
    assert middle not in preview
    assert str(saved) in preview


def test_handle_overflow_spill_disabled_backward_compat(tmp_path):
    tools = ShellTools()
    text = "z" * 40000
    preview, path = tools._handle_overflow(
        text, "stdout", 10000, False, str(tmp_path)
    )
    assert path is None
    assert "showing first/last portions" in preview


def test_handle_overflow_spill_write_failure_degrades_gracefully(monkeypatch):
    tools = ShellTools()
    text = "w" * 40000

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("tempfile.mkstemp", _boom)
    preview, path = tools._handle_overflow(text, "stdout", 10000, True, None)
    # No artifact, no exception, still a bounded legacy preview.
    assert path is None
    assert "showing first/last portions" in preview
    assert len(preview) < len(text)


def test_bounded_with_pointer_stays_within_budget(tmp_path):
    output = "q" * 50000
    path = tmp_path / "artifact.txt"
    path.write_text(output, encoding="utf-8")
    max_output_size = 10000
    preview = bounded_with_pointer(output, max_output_size, path)
    # Including the injected pointer, the preview must not exceed the budget.
    assert len(preview) <= max_output_size
