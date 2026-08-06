"""Tests for command frontmatter parity and positional ``$1..$n`` arguments.

Covers the minimal, contained additions to the custom command loader:
- new frontmatter fields ``argument-hint``, ``model`` and ``tools``
  (a.k.a. ``allowed-tools``) parsed onto ``CustomCommand``;
- shell-style positional ``$1..$n`` interpolation alongside ``$ARGUMENTS``;
- legacy two-field command files remain unchanged.
"""

from pathlib import Path

from praisonai_code.cli.features.custom_definitions import (
    CustomDefinitionsDiscovery,
    TemplateInterpolator,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_frontmatter_new_fields_parsed(tmp_path):
    cmd_file = tmp_path / "commands" / "review.md"
    _write(
        cmd_file,
        "---\n"
        "description: Review a PR\n"
        "argument-hint: <pr-number> [reviewer]\n"
        "model: gpt-4o\n"
        "allowed-tools: [read, grep]\n"
        "---\n"
        "Review PR $1 assigned to $2.\n",
    )

    discovery = CustomDefinitionsDiscovery()
    cmd = discovery._load_command(cmd_file, source="project")

    assert cmd is not None
    assert cmd.description == "Review a PR"
    assert cmd.argument_hint == "<pr-number> [reviewer]"
    assert cmd.model == "gpt-4o"
    assert cmd.tools == ["read", "grep"]


def test_frontmatter_tools_key_and_string_form(tmp_path):
    cmd_file = tmp_path / "commands" / "c.md"
    _write(
        cmd_file,
        "---\n"
        "description: x\n"
        "tools: read, edit bash\n"
        "---\n"
        "body\n",
    )
    cmd = CustomDefinitionsDiscovery()._load_command(cmd_file, source="project")
    assert cmd.tools == ["read", "edit", "bash"]


def test_legacy_two_field_command_unchanged(tmp_path):
    cmd_file = tmp_path / "commands" / "legacy.md"
    _write(
        cmd_file,
        "---\n"
        "description: legacy command\n"
        "allow_shell: false\n"
        "---\n"
        "Do the thing with $ARGUMENTS.\n",
    )
    cmd = CustomDefinitionsDiscovery()._load_command(cmd_file, source="project")
    assert cmd.description == "legacy command"
    assert cmd.allow_shell is False
    assert cmd.argument_hint is None
    assert cmd.model is None
    assert cmd.tools is None


def test_positional_substitution_basic():
    out = TemplateInterpolator.interpolate("PR $1 by $2", "42 alice")
    assert out == "PR 42 by alice"


def test_positional_out_of_range_is_empty():
    out = TemplateInterpolator.interpolate("a=$1 b=$2 c=$3", "one two")
    assert out == "a=one b=two c="


def test_positional_and_arguments_together():
    out = TemplateInterpolator.interpolate("first=$1 all=$ARGUMENTS", "x y z")
    assert out == "first=x all=x y z"


def test_positional_respects_quotes():
    out = TemplateInterpolator.interpolate("msg=$1", '"hello world" extra')
    assert out == "msg=hello world"


def test_positional_does_not_double_substitute_user_dollar_one():
    # A user argument that itself contains ``$1`` must not be re-interpolated.
    out = TemplateInterpolator.interpolate("val=$ARGUMENTS", "$1 literal")
    assert out == "val=$1 literal"


def test_positional_escapes_shell_substitution():
    # A positional token carrying $(...) must be escaped, never executed. The
    # token is quoted so it survives argument splitting as one unit.
    out = TemplateInterpolator.interpolate("x=$1", '"$(rm -rf /)"')
    assert out == r"x=\$(rm -rf /)"
