"""Rich markup must never reach the user as literal [bold]...[/bold] text.

Both MCP CLIs define a ``_print_rich`` helper that renders markup when Rich is
installed and strips the tags when it is not. A bare ``print()`` carrying markup
bypasses that helper, so the user sees the raw tags.
"""
import io
import re
import contextlib
from pathlib import Path

import pytest

MARKUP = re.compile(r"\[/?(?:bold|red|green|yellow|cyan|dim|blue|magenta)[^\]]*\]")
CLI_FILES = [
    Path(__file__).resolve().parents[2] / "praisonai_mcp" / "mcp_server" / "cli.py",
    Path(__file__).resolve().parents[2] / "praisonai_mcp" / "mcp_server" / "recipe_cli.py",
]


def _bare_markup_prints(path: Path):
    """Lines calling the builtin print() with Rich markup in the argument."""
    hits = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("print(") and MARKUP.search(line):
            hits.append(f"{path.name}:{i}: {stripped[:90]}")
    return hits


@pytest.mark.parametrize("path", CLI_FILES, ids=lambda p: p.name)
def test_no_bare_print_of_rich_markup(path):
    """Static guard: markup must go through _print_rich, not builtin print."""
    assert path.exists(), f"missing {path}"
    hits = _bare_markup_prints(path)
    assert not hits, (
        f"{len(hits)} bare print() call(s) carry Rich markup and will show "
        "literal tags to the user:\n  " + "\n  ".join(hits)
    )


def test_control_probe_detector_actually_matches():
    """Control: the detector must fire on a known-bad line, else the scan is vacuous."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write('print(f"[bold]x[/bold]")\n')
        tmp = Path(fh.name)
    try:
        assert len(_bare_markup_prints(tmp)) == 1
    finally:
        tmp.unlink()


def test_list_recipes_output_has_no_literal_markup():
    """Runtime: real command output must not contain literal Rich tags."""
    from praisonai_mcp.mcp_server.recipe_cli import RecipeMCPCLI

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        RecipeMCPCLI().cmd_list_recipes([])
    out = buf.getvalue()
    leaked = MARKUP.findall(out)
    assert not leaked, f"literal Rich tags shown to user: {leaked[:6]}\n---\n{out[:400]}"
