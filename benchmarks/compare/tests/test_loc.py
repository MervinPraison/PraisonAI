import loc

FIXTURE = '''"""Module docstring
spanning lines."""
# a comment
import os

URL = os.environ["X"]  # bench:config


def build():
    """Docstring."""

    return dict(
        a=1,  # trailing comment
        b=2,
    )
'''


def test_counts_code_lines_and_tokens():
    # import os | def build(): | return dict( | a=1, | b=2, | )
    assert loc.count(FIXTURE) == {"lines": 6, "tokens": 19}


def test_scenario_files_count():
    from pathlib import Path

    for path in (Path(loc.__file__).parent / "scenarios" / "team3").glob("*.py"):
        c = loc.count(path.read_text())
        assert c["lines"] > 0 and c["tokens"] > 0, path
