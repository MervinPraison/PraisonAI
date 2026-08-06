"""Tests for bridging file-based custom slash commands into bot chats (#3729).

The custom-command convention (``.praisonai/commands/{name}.md`` with
``$ARGUMENTS`` / ``@file`` / gated ``!`bash```) has historically only surfaced
in the code REPL/TUI. These tests exercise the shared
:class:`CustomCommandResolver` (consumed by every bot adapter via
``ChatCommandMixin``) directly — no platform SDK required — asserting the
bot-appropriate safety posture: shell off by default, project-scope only,
allow-listable, builtin precedence.
"""

import textwrap

import pytest

from praisonai_bot.bots._commands import (
    CustomCommandResolver,
    build_custom_command_resolver,
    _EntryPointCommand,
)


def _write_command(root, name, body, source="project"):
    base = root / ".praisonai" / "commands"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{name}.md").write_text(textwrap.dedent(body))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A temp project dir with a ``.praisonai/commands`` folder, cwd'd into."""
    # Make the temp dir look like the project root so ``_find_project_dirs``
    # stops walking up into the real repo.
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_project_command_runs_in_bot_chat(project):
    """`/greet Alice` renders $ARGUMENTS from a fixture command file."""
    _write_command(
        project,
        "greet",
        """\
        ---
        description: Greet a person
        ---
        Say hello to $ARGUMENTS in a friendly way.
        """,
    )
    resolver = CustomCommandResolver()
    rendered = resolver.render("greet", "Alice")
    assert rendered is not None
    assert "Alice" in rendered
    assert "$ARGUMENTS" not in rendered


def test_shell_preprocessing_off_by_default_in_bots(project):
    """A command with allow_shell frontmatter must NOT execute shell in bots."""
    _write_command(
        project,
        "danger",
        """\
        ---
        description: Attempts shell
        allow_shell: true
        ---
        The secret is !`echo SHELL_EXECUTED_MARKER`.
        """,
    )
    # Default resolver: shell off regardless of the command's own frontmatter.
    resolver = CustomCommandResolver()
    rendered = resolver.render("danger", "")
    assert rendered is not None
    # The literal command text remains (it came from the source) but the shell
    # was NOT executed: the ``!`` live-substitution marker is dropped so the
    # segment renders as inert backticks rather than the command's stdout.
    assert "!`echo SHELL_EXECUTED_MARKER`" not in rendered
    assert "`echo SHELL_EXECUTED_MARKER`" in rendered


def test_shell_opt_in_enables_execution(project):
    """`allow_shell` on the resolver opts the deployment into execution."""
    _write_command(
        project,
        "shellcmd",
        """\
        ---
        allow_shell: true
        ---
        Output: !`echo HELLO`
        """,
    )
    resolver = CustomCommandResolver(allow_shell=True)
    rendered = resolver.render("shellcmd", "")
    assert rendered is not None
    assert "HELLO" in rendered


def test_expose_allowlist(project):
    """A non-listed command is not exposed (falls through to normal chat)."""
    _write_command(project, "alpha", "Alpha body $ARGUMENTS")
    _write_command(project, "beta", "Beta body $ARGUMENTS")
    resolver = CustomCommandResolver(expose=["alpha"])
    assert resolver.get_command("alpha") is not None
    assert resolver.get_command("beta") is None
    names = {c.name for c in resolver.list_commands()}
    assert names == {"alpha"}


def test_help_merge_descriptions(project):
    """/help merge: exposed custom commands carry their descriptions."""
    _write_command(
        project,
        "deploy",
        """\
        ---
        description: Deploy checklist
        ---
        Run the deploy checklist for $ARGUMENTS.
        """,
    )
    resolver = CustomCommandResolver()
    descriptions = resolver.descriptions()
    assert descriptions.get("deploy") == "Deploy checklist"


def test_unknown_command_returns_none(project):
    resolver = CustomCommandResolver()
    assert resolver.render("does-not-exist", "") is None
    assert resolver.get_command("does-not-exist") is None


def test_entrypoint_command_resolvable(project, monkeypatch):
    """A command contributed via the entry-point group is resolvable."""
    import praisonai_bot.bots._commands as commands_mod

    ep_cmd = _EntryPointCommand(
        name="plugincmd",
        template="Plugin says hi to $ARGUMENTS",
        description="From a plugin",
    )
    monkeypatch.setattr(
        commands_mod,
        "_discover_entry_point_commands",
        lambda: {"plugincmd": ep_cmd},
    )
    resolver = CustomCommandResolver()
    rendered = resolver.render("plugincmd", "Bob")
    assert rendered is not None
    assert "Bob" in rendered
    assert resolver.descriptions().get("plugincmd") == "From a plugin"


def test_file_command_overrides_entrypoint(project, monkeypatch):
    """File/project command wins over an entry-point command on collision."""
    import praisonai_bot.bots._commands as commands_mod

    _write_command(project, "dup", "FILE body $ARGUMENTS")
    ep_cmd = _EntryPointCommand(name="dup", template="EP body $ARGUMENTS")
    monkeypatch.setattr(
        commands_mod,
        "_discover_entry_point_commands",
        lambda: {"dup": ep_cmd},
    )
    resolver = CustomCommandResolver()
    rendered = resolver.render("dup", "x")
    assert rendered is not None
    assert "FILE body" in rendered
    assert "EP body" not in rendered


def test_build_resolver_from_config():
    """The config builder maps the ``commands`` block to resolver knobs."""

    class _Commands:
        allow_shell = True
        expose = ["a", "b"]
        include_user_scope = True

    class _Config:
        commands = _Commands()

    resolver = build_custom_command_resolver(_Config())
    assert resolver.allow_shell is True
    assert resolver.expose == {"a", "b"}
    assert resolver.include_user_scope is True


def test_builtin_precedence_and_help_merge(project):
    """Shared mixin merges file commands into /help but builtins keep precedence."""
    from praisonai_bot.bots._protocol_mixin import ChatCommandMixin

    _write_command(project, "deploy", "Deploy $ARGUMENTS")
    # A file command colliding with a builtin name must be shadowed.
    _write_command(project, "status", "Custom status $ARGUMENTS")

    class _Bot(ChatCommandMixin):
        def __init__(self):
            self._command_handlers = {}
            self._command_info = {}
            self._command_channels = {}
            self._custom_command_resolver = CustomCommandResolver()

    bot = _Bot()
    names = [c.name for c in bot.list_commands()]
    # Builtin /status stays builtin (only listed once, not shadowed by file).
    assert names.count("status") == 1
    # The non-colliding file command is merged in.
    assert "deploy" in names
    # Dispatch renders the file command body.
    assert bot.render_custom_command("deploy", "prod") == "Deploy prod"


def test_build_resolver_defaults_when_no_config():
    """No ``commands`` block → safe defaults (shell off, all project, no user)."""

    class _Config:
        commands = None

    resolver = build_custom_command_resolver(_Config())
    assert resolver.allow_shell is False
    assert resolver.expose is None
    assert resolver.include_user_scope is False
