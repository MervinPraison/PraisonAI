"""Declared CLI options must do something, or not be declared.

An AST scan found 45 `typer.Option`/`Argument` parameters that never appear in
their own function body. These are the ones verified by running them: each was
accepted, validated by typer, and dropped.

Assertions are on behaviour and exit codes, never message text.
"""

import json
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner


def _invoke(app, args, **kwargs):
    return CliRunner().invoke(app, args, **kwargs)


def _group(name, fn):
    """A Typer app with `fn` registered as `name`.

    A second, inert command is registered too: Typer collapses a single-command
    app into a bare callback, which would make the command name be parsed as
    the first argument.
    """
    app = typer.Typer()
    app.command(name)(fn)

    @app.command("__filler")
    def _filler():  # pragma: no cover - never invoked
        pass

    return app


# ---------------------------------------------------------------------------
# memory clear -- destructive, advertised --force it ignored, and no prompt
# ---------------------------------------------------------------------------

class TestMemoryClearIsGuarded:

    @pytest.fixture
    def cleared(self, monkeypatch):
        """Capture the argv `memory clear` would hand the wrapper."""
        seen = []
        monkeypatch.setattr(
            "praisonai_code._wrapper_bridge.run_wrapper_command",
            lambda argv, feature=None: seen.append(list(argv)),
        )
        return seen

    def _app(self):
        from praisonai_code.cli.commands import memory as memory_module

        return _group("clear", memory_module.memory_clear)

    def test_without_force_and_without_confirmation_nothing_is_cleared(self, cleared):
        result = _invoke(self._app(), ["clear", "all"], input="n\n")
        assert cleared == [], "memory was wiped despite the user declining"
        assert result.exit_code != 0

    def test_without_force_and_no_stdin_nothing_is_cleared(self, cleared):
        result = _invoke(self._app(), ["clear", "all"], input="")
        assert cleared == [], "memory was wiped with no confirmation at all"
        assert result.exit_code != 0

    def test_confirming_clears(self, cleared):
        result = _invoke(self._app(), ["clear", "all"], input="y\n")
        assert result.exit_code == 0, result.output
        assert cleared and cleared[0][:3] == ["memory", "clear", "all"]

    def test_force_skips_the_prompt(self, cleared):
        result = _invoke(self._app(), ["clear", "all", "--force"], input="")
        assert result.exit_code == 0, result.output
        assert cleared and cleared[0][:3] == ["memory", "clear", "all"]

    def test_force_short_flag_skips_the_prompt(self, cleared):
        result = _invoke(self._app(), ["clear", "-f"], input="")
        assert result.exit_code == 0, result.output
        assert cleared

    def test_the_target_reaches_the_wrapper(self, cleared):
        """`clear all` was unreachable: the command always cleared short-term."""
        _invoke(self._app(), ["clear", "all", "-f"], input="")
        assert cleared[0][2] == "all"
        cleared.clear()
        _invoke(self._app(), ["clear", "-f"], input="")
        assert cleared[0][2] == "short"

    def test_an_unknown_target_is_rejected(self, cleared):
        result = _invoke(self._app(), ["clear", "banana", "-f"], input="")
        assert result.exit_code != 0
        assert cleared == []

    def test_user_id_still_reaches_the_wrapper(self, cleared):
        _invoke(self._app(), ["clear", "-f", "--user-id", "bob"], input="")
        assert "--user-id" in cleared[0] and "bob" in cleared[0]


# ---------------------------------------------------------------------------
# todo add --priority
# ---------------------------------------------------------------------------

class TestTodoAddPriority:

    @pytest.fixture
    def handler(self, tmp_path):
        from praisonai_code.cli.features.todo import TodoHandler

        return TodoHandler(workspace=str(tmp_path))

    def test_priority_is_stored(self, handler):
        todo = handler.action_add(["buy milk", "--priority", "high"])
        assert todo["priority"] == "high"

    def test_short_flag_is_stored(self, handler):
        assert handler.action_add(["x", "-p", "low"])["priority"] == "low"

    def test_equals_form_is_stored(self, handler):
        assert handler.action_add(["x", "--priority=high"])["priority"] == "high"

    def test_the_flag_never_lands_in_the_task_text(self, handler):
        todo = handler.action_add(["buy milk", "--priority", "high"])
        assert todo["task"] == "buy milk"

    def test_the_default_is_medium(self, handler):
        assert handler.action_add(["x"])["priority"] == "medium"

    def test_an_unknown_priority_is_rejected(self, handler):
        assert handler.action_add(["x", "-p", "urgent"]) == {}

    def test_the_typer_command_forwards_the_option(self, monkeypatch):
        seen = []
        monkeypatch.setattr(
            "praisonai_code._wrapper_bridge.run_wrapper_command",
            lambda argv, feature=None: seen.append(list(argv)),
        )
        from praisonai_code.cli.commands import todo as todo_module

        _invoke(_group("add", todo_module.todo_add),
                ["add", "buy milk", "--priority", "high"])
        assert seen and "--priority" in seen[0] and "high" in seen[0]


# ---------------------------------------------------------------------------
# config list --scope
# ---------------------------------------------------------------------------

class TestConfigListScope:

    def _app(self):
        from praisonai_code.cli.commands import config as config_module

        return _group("list", config_module.config_list)

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        """An isolated home + project so both scopes have known content."""
        monkeypatch.delenv("PRAISONAI_PROJECT", raising=False)
        monkeypatch.delenv("PRAISONAI_CONFIG", raising=False)
        monkeypatch.delenv("PRAISONAI_CONFIG_CONTENT", raising=False)

        home = tmp_path / "home"
        (home / ".praisonai").mkdir(parents=True)
        (home / ".praisonai" / "config.yaml").write_text(
            "model:\n  default: from-the-user\n"
        )
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))

        proj = tmp_path / "proj"
        (proj / ".praisonai").mkdir(parents=True)
        (proj / ".praisonai" / "config.yaml").write_text(
            "model:\n  default: from-the-project\n"
        )
        monkeypatch.chdir(proj)

        # Force a fresh resolver rooted at this cwd.
        from praisonai_code.cli.configuration import resolver as resolver_module

        resolver_module.get_resolver(proj, reset=True)
        return proj

    def test_user_and_project_scopes_differ(self, project):
        user = _invoke(self._app(), ["list", "--scope", "user"]).output
        proj = _invoke(self._app(), ["list", "--scope", "project"]).output
        assert user != proj, "--scope user and --scope project are still identical"

    def test_project_scope_shows_the_project_value(self, project):
        out = _invoke(self._app(), ["list", "--scope", "project"]).output
        assert "from-the-project" in out

    def test_user_scope_shows_the_user_value_only(self, project):
        out = _invoke(self._app(), ["list", "--scope", "user"]).output
        assert "from-the-user" in out
        assert "from-the-project" not in out

    def test_an_unknown_scope_is_rejected(self, project):
        assert _invoke(self._app(), ["list", "--scope", "banana"]).exit_code != 0

    def test_all_scope_still_succeeds(self, project):
        assert _invoke(self._app(), ["list", "--scope", "all"]).exit_code == 0


# ---------------------------------------------------------------------------
# eval accuracy -n / --iterations
# ---------------------------------------------------------------------------

class TestEvalAccuracyIterations:

    def _argv(self, monkeypatch, args):
        seen = []
        monkeypatch.setattr(
            "praisonai_code._wrapper_bridge.run_wrapper_command",
            lambda argv, feature=None: seen.append(list(argv)),
        )
        from praisonai_code.cli.commands import eval as eval_module

        _invoke(_group("accuracy", eval_module.eval_accuracy), args)
        return seen[0] if seen else []

    def test_iterations_is_forwarded(self, monkeypatch):
        argv = self._argv(monkeypatch, [
            "accuracy", "a.yaml", "-i", "2+2", "-e", "4", "-n", "7",
        ])
        assert "--iterations" in argv
        assert argv[argv.index("--iterations") + 1] == "7"

    def test_the_agent_is_passed_as_the_named_option_the_wrapper_parses(
        self, monkeypatch
    ):
        """The wrapper's parser declares --agent; a bare positional was rejected."""
        argv = self._argv(monkeypatch, [
            "accuracy", "a.yaml", "-i", "x", "-e", "y",
        ])
        assert "--agent" in argv
        assert argv[argv.index("--agent") + 1] == "a.yaml"
        assert "a.yaml" not in argv[:2]

    def test_the_wrapper_parser_accepts_what_we_send(self, monkeypatch):
        """Parse the forwarded argv with the wrapper's own parser."""
        import argparse

        from praisonai.cli.features.eval import add_eval_parser_subcommands

        argv = self._argv(monkeypatch, [
            "accuracy", "a.yaml", "-i", "2+2", "-e", "4", "-n", "7",
        ])
        parser = argparse.ArgumentParser(prog="praisonai eval")
        add_eval_parser_subcommands(parser.add_subparsers(dest="eval_type"))
        parsed = parser.parse_args(argv[1:])
        assert parsed.iterations == 7
        assert parsed.agent == "a.yaml"


# ---------------------------------------------------------------------------
# recipe judge --goal
# ---------------------------------------------------------------------------

class TestRecipeJudgeGoal:

    def test_judge_trace_accepts_an_explicit_goal(self):
        import inspect

        from praisonai.replay import ContextEffectivenessJudge

        sig = inspect.signature(ContextEffectivenessJudge.judge_trace)
        assert "recipe_goal" in sig.parameters

    def test_the_explicit_goal_reaches_the_report(self, monkeypatch):
        from praisonai.replay import ContextEffectivenessJudge

        judge = ContextEffectivenessJudge()
        # No events -> the report is built from the (empty) agent data, but the
        # goal must still be the one supplied.
        report = judge.judge_trace([], session_id="t", recipe_goal="ship the blog")
        assert report.recipe_goal == "ship the blog"

    def test_without_a_goal_the_report_carries_none(self):
        from praisonai.replay import ContextEffectivenessJudge

        report = ContextEffectivenessJudge().judge_trace([], session_id="t")
        assert not report.recipe_goal

    def _run_judge(self, monkeypatch, args):
        """Invoke `recipe judge` with the reader and judge stubbed out.

        Returns the kwargs the command handed ``judge_trace``.
        """
        import praisonai.replay as replay

        captured = {}

        class _Reader:
            def __init__(self, trace_id):
                pass

            def get_all(self):
                return [{"event": "one"}]

        class _Judge:
            def __init__(self, **kwargs):
                pass

            def judge_trace(self, events, **kwargs):
                captured.update(kwargs)
                return object()

        monkeypatch.setattr(replay, "ContextTraceReader", _Reader)
        monkeypatch.setattr(replay, "ContextEffectivenessJudge", _Judge)
        monkeypatch.setattr(replay, "format_judge_report", lambda r: "")

        from praisonai.cli.commands import recipe as recipe_module

        _invoke(_group("judge", recipe_module.recipe_judge), args)
        return captured

    def test_the_command_passes_its_goal_through(self, monkeypatch):
        captured = self._run_judge(
            monkeypatch, ["judge", "run-abc", "--goal", "ship the blog"]
        )
        assert captured.get("recipe_goal") == "ship the blog", (
            "recipe judge still drops --goal"
        )

    def test_without_the_option_no_goal_is_forced(self, monkeypatch):
        captured = self._run_judge(monkeypatch, ["judge", "run-abc"])
        assert not captured.get("recipe_goal")


# ---------------------------------------------------------------------------
# serve ui-gateway --agents (used in the command's own docstring example)
# ---------------------------------------------------------------------------

class TestServeUiGatewayAgents:
    """`--agents` was declared, used in the command's own docstring example,
    and never forwarded.

    The contract matters: ``run_integrated_gateway`` takes ``**configure_kwargs``
    and hands them to ``configure_host``, which declares
    ``agents: Optional[List[Any]]`` -- a PARSED LIST, not a file path, and not a
    parameter named ``agents_file``. An earlier attempt at this fix passed
    ``agents_file=<path>`` behind an ``inspect.signature`` guard, which could
    never match a ``**kwargs`` function and so rejected the option every time.
    These tests pin the real contract so that cannot recur.
    """

    AGENTS_YAML = (
        "agents:\n"
        "  - name: Writer\n"
        "    instructions: You write things\n"
        "    llm: gpt-4o-mini\n"
        "  - name: Editor\n"
        "    instructions: You edit things\n"
    )

    def _run(self, monkeypatch, args):
        captured = {}

        def _run_gateway(**kwargs):
            captured.update(kwargs)

        class _Mod:
            run_integrated_gateway = staticmethod(_run_gateway)

        monkeypatch.setattr(
            "praisonai_code._bot_bridge.import_bot_module", lambda name: _Mod
        )
        from praisonai_code.cli.commands import serve as serve_module

        result = _invoke(_group("ui-gateway", serve_module.serve_ui_gateway), args)
        return result, captured

    @pytest.fixture
    def agents_yaml(self, tmp_path):
        f = tmp_path / "agents.yaml"
        f.write_text(self.AGENTS_YAML)
        return str(f)

    def test_a_parsed_agent_list_reaches_the_gateway(self, monkeypatch, agents_yaml):
        result, captured = self._run(
            monkeypatch, ["ui-gateway", "--agents", agents_yaml]
        )
        assert result.exit_code == 0, result.output
        assert "agents" in captured, (
            "the gateway never received the agents; configure_host takes "
            "`agents`, not `agents_file`"
        )
        assert isinstance(captured["agents"], list)
        assert len(captured["agents"]) == 2

    def test_it_is_a_list_of_agents_not_the_path(self, monkeypatch, agents_yaml):
        _, captured = self._run(monkeypatch, ["ui-gateway", "--agents", agents_yaml])
        assert captured.get("agents_file") is None, (
            "passed a file path under a parameter configure_host does not declare"
        )
        assert [a.name for a in captured["agents"]] == ["Writer", "Editor"]

    def test_it_is_not_passed_when_not_supplied(self, monkeypatch):
        result, captured = self._run(monkeypatch, ["ui-gateway"])
        assert result.exit_code == 0, result.output
        assert "agents" not in captured

    def test_the_other_options_still_reach_the_gateway(self, monkeypatch):
        _, captured = self._run(
            monkeypatch, ["ui-gateway", "--style", "chat", "--title", "My App"]
        )
        assert captured["style"] == "chat"
        assert captured["title"] == "My App"

    def test_a_missing_file_fails_loudly(self, monkeypatch):
        result, captured = self._run(
            monkeypatch, ["ui-gateway", "--agents", "/no/such/agents.yaml"]
        )
        assert result.exit_code != 0
        assert captured == {}, "the gateway was started despite a bad --agents"

    def test_a_file_without_an_agents_list_fails_loudly(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("something_else: 1\n")
        result, captured = self._run(monkeypatch, ["ui-gateway", "--agents", str(bad)])
        assert result.exit_code != 0
        assert captured == {}

    def test_malformed_yaml_fails_loudly(self, monkeypatch, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("agents: [unclosed\n")
        result, captured = self._run(monkeypatch, ["ui-gateway", "--agents", str(bad)])
        assert result.exit_code != 0
        assert captured == {}

    def test_the_real_gateway_host_accepts_the_kwarg_we_send(self):
        """Pin the contract against the actual praisonai-bot signature.

        A unit test with a stub cannot catch "we pass a kwarg the real function
        rejects" -- which is exactly how the earlier attempt went wrong.
        """
        import inspect

        try:
            from praisonai_bot.integration.host_app import configure_host
        except Exception:
            pytest.skip("praisonai-bot not importable")

        params = inspect.signature(configure_host).parameters
        assert "agents" in params, "configure_host no longer takes `agents`"
        assert "agents_file" not in params


# ---------------------------------------------------------------------------
# up logs -- advertised three options, honoured none, and exited 0
# ---------------------------------------------------------------------------

class TestUpLogs:

    def _app(self):
        from praisonai_code.cli.commands import up as up_module

        return _group("logs", up_module.up_logs)

    def test_it_no_longer_reports_success(self):
        assert _invoke(self._app(), ["logs"]).exit_code != 0

    def test_it_no_longer_advertises_options_it_ignores(self):
        for flag in ("--service", "--follow", "--lines"):
            result = _invoke(self._app(), ["logs", flag, "x"])
            assert result.exit_code != 0, flag


# ---------------------------------------------------------------------------
# code --no-autonomy
# ---------------------------------------------------------------------------

class TestCodeNoAutonomy:

    def test_the_flag_reaches_the_tui_config(self):
        import ast
        import inspect
        import textwrap

        from praisonai_code.cli.commands import code as code_module

        src = textwrap.dedent(inspect.getsource(code_module.code_main))
        fn = next(
            n for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "code_main"
        )
        read = {
            n.id for n in ast.walk(fn)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }
        assert "autonomy" in read, "code still drops --no-autonomy"

    def test_the_resident_runner_honours_it(self):
        import argparse
        import ast
        import inspect
        import textwrap

        from praisonai_code.cli.commands import code as code_module

        src = textwrap.dedent(inspect.getsource(code_module._run_resident_code))
        assert "autonomy_mode=" in src, (
            "_run_resident_code builds AsyncTUIConfig without autonomy_mode"
        )

    def test_chat_and_code_agree_on_the_default(self):
        from praisonai_code.cli.interactive.async_tui import AsyncTUIConfig

        assert AsyncTUIConfig().autonomy_mode is True
