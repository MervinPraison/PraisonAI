from pathlib import Path
import tempfile


def test_get_file_info_with_workspace():
    from praisonaiagents.workspace import Workspace
    from praisonaiagents.tools.file_tools import FileTools

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Workspace(root=Path(tmpdir))
        file_tools = FileTools(workspace=workspace)
        target = Path(tmpdir) / "sample.txt"
        target.write_text("hello", encoding="utf-8")

        info = file_tools.get_file_info("sample.txt")

        assert info["name"] == "sample.txt"
        assert info["size"] == 5
        assert info["is_file"] is True
