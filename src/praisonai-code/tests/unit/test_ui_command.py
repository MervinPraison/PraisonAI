from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from praisonai_code.cli.commands.ui import _launch_aiui_app


def test_launch_aiui_copies_default_app_using_utf8(tmp_path, monkeypatch):
    """Regression test for Windows UnicodeDecodeError when copying
    bundled default_app.py.
    """

    # Create a fake bundled UI app containing UTF-8 characters.
    bundled = tmp_path / "default_app.py"
    expected = '"""Hello — café 😀 中文"""\n'
    bundled.write_text(expected, encoding="utf-8")

    # Redirect ~/.praisonai to our temporary directory.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Pretend the bundled file exists.
    with patch(
        "praisonai_code.cli.commands.ui._resolve_bundled_default_app",
        return_value=bundled,
    ), patch(
        "importlib.util.find_spec",
        return_value=object(),
    ), patch("praisonai_code.cli.commands.ui._run_server") as run_server:
        _launch_aiui_app(
            app_dir="ui",
            default_app_name="ui_chat",
            port=8081,
            host="127.0.0.1",
            app_file=None,
            reload=False,
            ui_name="Chat",
        )

    created = tmp_path / ".praisonai" / "ui" / "app.py"

    run_server.assert_called_once()
    stamp, content = created.read_text(encoding="utf-8").split("\n", 1)
    assert content == expected
    assert stamp == f"# praisonai-default-app sha256={sha256(expected.encode('utf-8')).hexdigest()}"
