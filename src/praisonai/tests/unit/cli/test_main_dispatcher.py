"""Unit tests for the unified CLI dispatcher in `praisonai.__main__`.

The dispatcher is Typer-first with a legacy fallback for bare prompts and
YAML invocations. It must:

  - Short-circuit on ``--version`` / ``-V`` before importing any heavy
    Typer or legacy modules (so version reporting stays fast even with
    broken optional deps).
  - Route ``--help`` / ``-h`` to Typer (so help text auto-discovers
    subcommands).
  - Route bare argv (no positional) to Typer.
  - Auto-discover registered Typer commands via Click introspection,
    cached behind a thread-safe lock that does not poison on failure.
  - Route the first non-flag positional through the discovered command
    set: known commands → Typer; everything else (prompts, YAML paths,
    legacy flags) → legacy.
  - Always restore ``sys.argv`` after dispatch — Typer mutates argv and
    legacy invocations also rewrite it.
  - Skip global flags (``--verbose``, ``-o`` + value, etc.) when looking
    for the first positional command.
"""

import os
import sys
import tempfile
import threading
import unittest
from typing import ClassVar, FrozenSet
from unittest import mock

import praisonai.__main__ as dispatcher


class TestFindFirstCommand(unittest.TestCase):
    """``_find_first_command`` skips global flags + value-flag values."""

    def test_returns_first_positional(self):
        self.assertEqual(dispatcher._find_first_command(["chat", "hello"]), "chat")

    def test_skips_leading_flags(self):
        self.assertEqual(dispatcher._find_first_command(["--verbose", "ui"]), "ui")
        self.assertEqual(dispatcher._find_first_command(["--debug", "--json", "chat"]), "chat")

    def test_skips_value_flags_and_their_values(self):
        # --output-format json should not be treated as the command.
        self.assertEqual(
            dispatcher._find_first_command(["--output-format", "json", "chat"]),
            "chat",
        )
        self.assertEqual(
            dispatcher._find_first_command(["-o", "yaml", "ui"]),
            "ui",
        )

    def test_only_flags_returns_none(self):
        self.assertIsNone(dispatcher._find_first_command(["--verbose", "--debug"]))

    def test_empty_argv_returns_none(self):
        self.assertIsNone(dispatcher._find_first_command([]))

    def test_yaml_path_returned_as_first(self):
        self.assertEqual(
            dispatcher._find_first_command(["agents.yaml"]),
            "agents.yaml",
        )

    def test_freetext_prompt_returned_as_first(self):
        # Whole token returned, including the embedded space.
        self.assertEqual(
            dispatcher._find_first_command(["Build a weather agent"]),
            "Build a weather agent",
        )


class TestLooksLikeBarePrompt(unittest.TestCase):
    """``_looks_like_bare_prompt`` gates the modern `run` forwarder.

    True for a non-YAML first positional token whose flags (if any) are all
    accepted by the modern ``run`` command — so ``praisonai "hello"`` and
    ``praisonai "fix bug" --model x`` reach Typer `run`, while ``.yaml``
    workflows and invocations bearing a legacy-only flag stay on legacy.
    """

    def setUp(self):
        dispatcher._run_option_names_cache = None

    def tearDown(self):
        dispatcher._run_option_names_cache = None

    def test_plain_prompt_is_bare(self):
        argv = ["Build a weather agent"]
        first = dispatcher._find_first_command(argv)
        self.assertTrue(dispatcher._looks_like_bare_prompt(argv, first))

    def test_single_word_prompt_is_bare(self):
        argv = ["hello"]
        first = dispatcher._find_first_command(argv)
        self.assertTrue(dispatcher._looks_like_bare_prompt(argv, first))

    def test_yaml_token_is_not_bare(self):
        for token in ("agents.yaml", "agents.yml", "AGENTS.YAML"):
            argv = [token]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(
                dispatcher._looks_like_bare_prompt(argv, first),
                f"{token!r} should not be treated as a bare prompt",
            )

    def test_run_supported_flag_is_bare(self):
        # A prompt combined with a flag ``run`` accepts reaches the modern
        # engine (the core fix for issue #3462).
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m", "--continue", "-c", "--output", "-o"},
                          {"--model", "-m", "--output", "-o"}),
        ):
            for argv in (
                ["fix the auth bug", "--model", "gpt-4o"],
                ["summarise this", "--continue"],
                ["diagnose", "--output", "json"],
                ["do it", "--model=gpt-4o"],
            ):
                first = dispatcher._find_first_command(argv)
                self.assertTrue(
                    dispatcher._looks_like_bare_prompt(argv, first),
                    f"{argv!r} should route to the modern run engine",
                )

    def test_legacy_only_flag_is_not_bare(self):
        # A flag ``run`` does not implement keeps the invocation on legacy.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ):
            argv = ["Do something", "--serve"]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(dispatcher._looks_like_bare_prompt(argv, first))

    def test_mixed_flags_with_one_legacy_is_not_bare(self):
        # All flags must be run-supported; a single unrecognised one → legacy.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ):
            argv = ["Do something", "--model", "x", "--serve"]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(dispatcher._looks_like_bare_prompt(argv, first))

    def test_flag_with_failed_discovery_is_not_bare(self):
        # If run option discovery fails, fall back to the conservative rule:
        # any flag routes to legacy.
        with mock.patch.object(
            dispatcher, "_get_run_option_names", return_value=None
        ):
            argv = ["Do something", "--model", "x"]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(dispatcher._looks_like_bare_prompt(argv, first))

    def test_leading_run_supported_flag_is_bare(self):
        # A leading run-supported flag (e.g. ``--verbose``) followed by a bare
        # prompt now reaches the modern run engine.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--verbose", "-v"}, set()),
        ):
            argv = ["--verbose", "hello"]
            first = dispatcher._find_first_command(argv)
            self.assertTrue(dispatcher._looks_like_bare_prompt(argv, first))

    def test_leading_legacy_flag_is_not_bare(self):
        # A leading legacy-only flag keeps the invocation on legacy.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ):
            argv = ["--serve", "hello"]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(dispatcher._looks_like_bare_prompt(argv, first))

    def test_no_positional_is_not_bare(self):
        self.assertFalse(dispatcher._looks_like_bare_prompt([], None))

    def test_legacy_colliding_short_opts_stay_on_legacy(self):
        # Greptile P1 (valid): ``-s``/``-f`` mean different things in legacy
        # (``--save``/``--file``) vs modern (``--session``/``--framework``).
        # Even though the *name* is in the modern option set, their presence must
        # keep a previously-legacy prompt on legacy to avoid silent semantic
        # reinterpretation. Long forms remain unaffected (tested elsewhere).
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=(
                {"--session", "-s", "--framework", "-f"},
                {"--session", "-s", "--framework", "-f"},
            ),
        ):
            for argv in (
                ["do research", "-s"],
                ["read this", "-f", "input.txt"],
            ):
                first = dispatcher._find_first_command(argv)
                self.assertFalse(
                    dispatcher._looks_like_bare_prompt(argv, first),
                    f"{argv!r} carries a legacy-colliding short option and must "
                    f"stay on legacy",
                )

    def test_long_form_of_colliding_opts_still_modern(self):
        # The long forms are unambiguous, so ``--session``/``--framework`` still
        # reach the modern engine even though their short forms are quarantined.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=(
                {"--session", "-s", "--framework", "-f"},
                {"--session", "-s", "--framework", "-f"},
            ),
        ):
            for argv in (
                ["resume it", "--session", "abc"],
                ["build it", "--framework", "crewai"],
            ):
                first = dispatcher._find_first_command(argv)
                self.assertTrue(
                    dispatcher._looks_like_bare_prompt(argv, first),
                    f"{argv!r} uses unambiguous long forms and should reach the "
                    f"modern engine",
                )

    def test_value_taking_flag_with_dash_prefixed_value_is_bare(self):
        # Regression guard for the Greptile P1: a value-taking run option whose
        # separated value begins with ``-`` (e.g. ``--session -abc``,
        # ``--output -json``) must NOT be mis-classified as an unsupported flag.
        # The whole invocation is run-supported and must reach the modern engine.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=(
                {"--session", "-s", "--output", "-o"},
                {"--session", "-s", "--output", "-o"},
            ),
        ):
            # ``-o`` is used for the short-form case (not ``-s``): ``-s`` is a
            # legacy-colliding short option quarantined to legacy, so it would
            # not reach the modern engine regardless of its value — a separate
            # concern from the dash-prefixed-value handling under test here.
            for argv in (
                ["fix the bug", "--session", "-abc"],
                ["diagnose", "--output", "-json"],
                ["summarise", "-o", "-weird-id"],
            ):
                first = dispatcher._find_first_command(argv)
                self.assertTrue(
                    dispatcher._looks_like_bare_prompt(argv, first),
                    f"{argv!r} is fully run-supported and should reach the "
                    f"modern engine even though the value starts with '-'",
                )

    def test_dash_value_then_unsupported_flag_is_not_bare(self):
        # The value is skipped, but a genuinely unsupported *following* flag
        # still forces legacy — the value-awareness must not swallow real flags.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--session", "-s"}, {"--session", "-s"}),
        ):
            argv = ["fix the bug", "--session", "-abc", "--serve"]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(dispatcher._looks_like_bare_prompt(argv, first))


class TestLooksLikeYamlRunTarget(unittest.TestCase):
    """``_looks_like_yaml_run_target`` gates the modern `run` YAML forwarder.

    True for a ``.yaml``/``.yml`` first positional whose flags (if any) are all
    accepted by the modern ``run`` command — so ``praisonai agents.yaml`` and
    ``praisonai agents.yaml --continue --output json`` reach Typer `run`, while
    a YAML invocation bearing a legacy-only flag stays on legacy (#3793).
    """

    def setUp(self):
        dispatcher._run_option_names_cache = None

    def tearDown(self):
        dispatcher._run_option_names_cache = None

    def test_flagless_yaml_is_run_target(self):
        for token in ("agents.yaml", "agents.yml", "AGENTS.YAML"):
            argv = [token]
            first = dispatcher._find_first_command(argv)
            self.assertTrue(
                dispatcher._looks_like_yaml_run_target(argv, first),
                f"{token!r} should route to the modern run engine",
            )

    def test_non_yaml_token_is_not_run_target(self):
        argv = ["Build a weather agent"]
        first = dispatcher._find_first_command(argv)
        self.assertFalse(dispatcher._looks_like_yaml_run_target(argv, first))

    def test_yaml_with_run_supported_flags_is_run_target(self):
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=(
                {"--continue", "-c", "--output", "-o", "--session", "-s"},
                {"--output", "-o", "--session", "-s"},
            ),
        ):
            for argv in (
                ["agents.yaml", "--continue"],
                ["agents.yaml", "--output", "json"],
                ["agents.yaml", "--session", "abc123"],
                ["agents.yaml", "--continue", "--output=json"],
            ):
                first = dispatcher._find_first_command(argv)
                self.assertTrue(
                    dispatcher._looks_like_yaml_run_target(argv, first),
                    f"{argv!r} should route to the modern run engine",
                )

    def test_yaml_with_legacy_only_flag_is_not_run_target(self):
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ):
            argv = ["agents.yaml", "--serve"]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(dispatcher._looks_like_yaml_run_target(argv, first))

    def test_yaml_with_failed_discovery_and_flag_is_not_run_target(self):
        with mock.patch.object(
            dispatcher, "_get_run_option_names", return_value=None
        ):
            argv = ["agents.yaml", "--model", "x"]
            first = dispatcher._find_first_command(argv)
            self.assertFalse(dispatcher._looks_like_yaml_run_target(argv, first))

    def test_yaml_with_legacy_colliding_short_opt_stays_on_legacy(self):
        # Greptile P1 (valid): ``praisonai agents.yaml -s`` (legacy ``--save``)
        # and ``agents.yaml -f input.txt`` (legacy ``--file``) must NOT be
        # reinterpreted as modern ``--session``/``--framework``. Their presence
        # keeps the YAML workflow on legacy.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=(
                {"--session", "-s", "--framework", "-f"},
                {"--session", "-s", "--framework", "-f"},
            ),
        ):
            for argv in (
                ["agents.yaml", "-s"],
                ["agents.yaml", "-f", "input.txt"],
            ):
                first = dispatcher._find_first_command(argv)
                self.assertFalse(
                    dispatcher._looks_like_yaml_run_target(argv, first),
                    f"{argv!r} carries a legacy-colliding short option and must "
                    f"stay on legacy",
                )

    def test_yaml_with_long_form_of_colliding_opt_is_run_target(self):
        # Unambiguous long forms still reach the modern engine.
        with mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=(
                {"--session", "-s", "--framework", "-f"},
                {"--session", "-s", "--framework", "-f"},
            ),
        ):
            for argv in (
                ["agents.yaml", "--session", "abc"],
                ["agents.yaml", "--framework", "crewai"],
            ):
                first = dispatcher._find_first_command(argv)
                self.assertTrue(
                    dispatcher._looks_like_yaml_run_target(argv, first),
                    f"{argv!r} uses unambiguous long forms and should reach the "
                    f"modern engine",
                )

    def test_no_positional_is_not_run_target(self):
        self.assertFalse(dispatcher._looks_like_yaml_run_target([], None))


class TestFlagNames(unittest.TestCase):
    """``_flag_names`` extracts option names, value-aware when told which
    options consume a following value."""

    def test_bare_dash_tokens_are_all_flags_without_value_opts(self):
        # Conservative default: every dash-prefixed token is an option name.
        self.assertEqual(
            dispatcher._flag_names(["p", "--model", "gpt-4o", "--verbose"]),
            ["--model", "--verbose"],
        )

    def test_equals_form_split_to_name(self):
        self.assertEqual(
            dispatcher._flag_names(["p", "--model=gpt-4o"]),
            ["--model"],
        )

    def test_value_opt_skips_dash_prefixed_value(self):
        # The value of a value-taking option is skipped even when it starts
        # with a dash, so it is not reported as a separate flag.
        self.assertEqual(
            dispatcher._flag_names(
                ["p", "--session", "-abc", "--model", "-x"],
                {"--session", "--model"},
            ),
            ["--session", "--model"],
        )

    def test_value_opt_equals_form_needs_no_lookahead(self):
        # ``--session=-abc`` carries its value inline; the next token is a flag.
        self.assertEqual(
            dispatcher._flag_names(
                ["p", "--session=-abc", "--stream"], {"--session"}
            ),
            ["--session", "--stream"],
        )


class TestGetTyperCommandsCache(unittest.TestCase):
    """``_get_typer_commands`` caches its result under a lock and does
    not poison the cache on failure."""

    def setUp(self):
        # Reset module-level cache between tests.
        dispatcher._typer_commands_cache = None

    def tearDown(self):
        dispatcher._typer_commands_cache = None

    def test_returns_set_on_success(self):
        result = dispatcher._get_typer_commands()
        self.assertIsInstance(result, set)
        # Cache is populated after a successful call.
        self.assertIsNotNone(dispatcher._typer_commands_cache)

    def test_cache_is_reused_on_second_call(self):
        first = dispatcher._get_typer_commands()
        second = dispatcher._get_typer_commands()
        self.assertIs(first, second)

    def test_failure_does_not_poison_cache(self):
        """If discovery fails, the next caller must be allowed to retry."""
        with mock.patch(
            "praisonai.cli.app.get_command_names",
            side_effect=ImportError("simulated optional dep missing"),
        ):
            result = dispatcher._get_typer_commands()
        # Failed discovery returns an empty set ...
        self.assertEqual(result, set())
        # ... but the cache stays None so a subsequent call can retry.
        self.assertIsNone(dispatcher._typer_commands_cache)

    def test_concurrent_callers_get_same_result(self):
        """No double-initialization under contention."""
        results = []
        errors = []

        def worker():
            try:
                results.append(dispatcher._get_typer_commands())
            except Exception as e:  # pragma: no cover - unexpected
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # All threads must observe the same cached set object.
        first = results[0]
        for r in results[1:]:
            self.assertIs(r, first)


class TestVersionShortCircuit(unittest.TestCase):
    """``--version`` / ``-V`` must print and return without importing
    Typer or legacy modules."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_long_flag_prints_version(self):
        sys.argv = ["praisonai", "--version"]
        with mock.patch("builtins.print") as mock_print:
            dispatcher.main()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("PraisonAI version", printed)

    def test_short_flag_prints_version(self):
        sys.argv = ["praisonai", "-V"]
        with mock.patch("builtins.print") as mock_print:
            dispatcher.main()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("PraisonAI version", printed)

    def test_version_does_not_import_typer_or_legacy(self):
        """The version path is on the hot import path; it must stay light.

        We deliberately avoid ``mock.patch("praisonai.cli.app.register_commands")``
        and friends here: ``mock.patch`` with a dotted target imports the
        target module when the patch context is entered, which would
        defeat the invariant under test. Instead, evict any cached
        ``praisonai.cli.*`` modules from ``sys.modules`` before invoking
        ``main()`` and assert they remain absent afterwards.
        """
        sys.argv = ["praisonai", "--version"]
        cli_mods = [m for m in list(sys.modules) if m.startswith("praisonai.cli")]
        saved = {m: sys.modules.pop(m) for m in cli_mods}
        try:
            with mock.patch("builtins.print"):
                dispatcher.main()
            still_loaded = [m for m in sys.modules if m.startswith("praisonai.cli")]
            self.assertEqual(
                still_loaded, [],
                f"--version must not import praisonai.cli.*, but loaded: {still_loaded}",
            )
        finally:
            sys.modules.update(saved)


class TestMainRouting(unittest.TestCase):
    """``main()`` routes argv to version / Typer / legacy according to
    routing rules 1-5 from the module docstring."""

    def setUp(self):
        self._saved_argv = sys.argv
        dispatcher._typer_commands_cache = None
        dispatcher._run_option_names_cache = None

    def tearDown(self):
        sys.argv = self._saved_argv
        dispatcher._typer_commands_cache = None
        dispatcher._run_option_names_cache = None

    def test_help_flag_routes_to_typer(self):
        sys.argv = ["praisonai", "--help"]
        with mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_short_help_flag_routes_to_typer(self):
        sys.argv = ["praisonai", "-h"]
        with mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_no_args_routes_to_typer(self):
        sys.argv = ["praisonai"]
        with mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_only_global_flags_routes_to_typer(self):
        """Argv with only flags (no positional command) → Typer for global flag handling."""
        sys.argv = ["praisonai", "--verbose"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_known_typer_command_routes_to_typer(self):
        sys.argv = ["praisonai", "fake-cmd", "--opt"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"fake-cmd"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once()
        run_legacy.assert_not_called()

    def test_freetext_prompt_routes_to_typer_run(self):
        # A bare free-text prompt now reaches the modern Typer `run` engine
        # (session continuity, --output modes, credential gate) instead of the
        # legacy path — rewritten to ``run <prompt>``.
        sys.argv = ["praisonai", "Create a weather app"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(["run", "Create a weather app"])
        run_legacy.assert_not_called()

    def test_multi_token_prompt_joined_into_single_run_argument(self):
        # An unquoted multi-word prompt arrives as several argv tokens. The
        # modern `run` command takes a single positional ``target``, so the
        # dispatcher must join the tokens into one argument — otherwise Typer
        # would reject the extra positionals or the agent would receive only
        # the first word. Regression guard for Greptile P1 (multi-token prompt).
        sys.argv = ["praisonai", "build", "a", "weather", "agent"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(["run", "build a weather agent"])
        run_legacy.assert_not_called()

    def test_bare_prompt_with_run_flag_routes_to_typer_run(self):
        # A prompt combined with a run-supported flag reaches the modern engine,
        # forwarded as ``run "<prompt>" <flag> <value>`` (issue #3462 core fix).
        sys.argv = ["praisonai", "fix the auth bug", "--model", "gpt-4o"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(
            ["run", "fix the auth bug", "--model", "gpt-4o"]
        )
        run_legacy.assert_not_called()

    def test_multi_token_prompt_with_run_flag_preserves_value(self):
        # An unquoted multi-word prompt with a value-taking run flag: the
        # positional tokens join into the target and the flag's value stays
        # with the flag rather than leaking into the prompt.
        sys.argv = ["praisonai", "build", "a", "weather", "agent", "-m", "gpt-4o"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(
            ["run", "build a weather agent", "-m", "gpt-4o"]
        )
        run_legacy.assert_not_called()

    def test_bare_prompt_with_dash_prefixed_value_routes_to_typer_run(self):
        # A value-taking run flag whose value begins with ``-`` must reach the
        # modern engine intact — the value is not mistaken for an unsupported
        # flag (Greptile P1 regression guard, full main() path).
        sys.argv = ["praisonai", "resume", "work", "--session", "-abc"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--session", "-s"}, {"--session", "-s"}),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(
            ["run", "resume work", "--session", "-abc"]
        )
        run_legacy.assert_not_called()

    def test_bare_prompt_with_boolean_run_flag_routes_to_typer_run(self):
        # A boolean run flag (no value) is forwarded intact.
        sys.argv = ["praisonai", "summarise this", "--continue"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--continue", "-c"}, set()),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(
            ["run", "summarise this", "--continue"]
        )
        run_legacy.assert_not_called()

    def test_bare_prompt_with_legacy_flag_routes_to_legacy_with_notice(self):
        # A prompt combined with a legacy-only flag stays on legacy — but now
        # prints a one-line notice so the fallback is never silent (#3462).
        sys.argv = ["praisonai", "Create a weather app", "--serve"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy, \
             mock.patch("builtins.print") as mock_print:
            dispatcher.main()
        run_legacy.assert_called_once()
        run_typer.assert_not_called()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("legacy engine", printed)
        self.assertIn("praisonai run", printed)

    def test_yaml_path_routes_to_typer_run(self):
        # A workflow YAML file now reaches the modern Typer `run` engine
        # (session continuity, --output modes, credential gate, permissions)
        # instead of the legacy path — forwarded as ``run agents.yaml`` (#3793).
        sys.argv = ["praisonai", "agents.yaml"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(["run", "agents.yaml"])
        run_legacy.assert_not_called()

    def test_yaml_path_with_run_flags_routes_to_typer_run(self):
        # A YAML workflow combined with run-supported flags (session
        # continuity + output mode) reaches the modern engine intact (#3793).
        sys.argv = ["praisonai", "agents.yaml", "--continue", "--output", "json"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=(
                {"--continue", "-c", "--output", "-o"},
                {"--output", "-o"},
            ),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(
            ["run", "agents.yaml", "--continue", "--output", "json"]
        )
        run_legacy.assert_not_called()

    def test_yaml_path_with_legacy_flag_routes_to_legacy_with_notice(self):
        # A YAML workflow carrying a legacy-only flag stays on legacy, with the
        # one-line fallback notice so the divert is never silent (#3793).
        sys.argv = ["praisonai", "agents.yaml", "--serve"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--model", "-m"}, {"--model", "-m"}),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy, \
             mock.patch("builtins.print") as mock_print:
            dispatcher.main()
        run_legacy.assert_called_once()
        run_typer.assert_not_called()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list)
        self.assertIn("legacy engine", printed)

    def test_leading_value_option_before_yaml_routes_to_typer_run(self):
        # Regression guard (CodeRabbit / Greptile P1): a leading value-taking
        # run option (``--session abc123``) must consume its value so the YAML
        # target after it is correctly identified as the first positional and
        # routed to the modern engine — not mistaken for the command token.
        sys.argv = ["praisonai", "--session", "abc123", "agents.yaml"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--session", "-s"}, {"--session", "-s"}),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(
            ["run", "--session", "abc123", "agents.yaml"]
        )
        run_legacy.assert_not_called()

    def test_leading_value_option_before_prompt_routes_to_typer_run(self):
        # Regression guard (CodeRabbit): a leading value-taking run option
        # (``--session abc123``) followed by an unquoted multi-token prompt must
        # consume its value, then the remaining positionals join into one
        # ``target`` — reaching the modern engine, not misrouted as free text.
        sys.argv = ["praisonai", "--session", "abc123", "build", "an", "agent"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat", "ui"}
        ), mock.patch.object(
            dispatcher,
            "_get_run_option_names",
            return_value=({"--session", "-s"}, {"--session", "-s"}),
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(
            ["run", "build an agent", "--session", "abc123"]
        )
        run_legacy.assert_not_called()

    def test_unknown_single_token_routes_to_typer_run(self):
        # A lone unknown token (no flags, not a YAML path) is treated as a bare
        # prompt and forwarded to the modern Typer `run` engine — matching the
        # prior legacy behaviour of running an unknown word as a one-shot prompt.
        sys.argv = ["praisonai", "totally-unknown"]
        with mock.patch.object(
            dispatcher, "_get_typer_commands", return_value={"chat"}
        ), mock.patch.object(dispatcher, "_run_typer") as run_typer, \
             mock.patch.object(dispatcher, "_run_legacy") as run_legacy:
            dispatcher.main()
        run_typer.assert_called_once_with(["run", "totally-unknown"])
        run_legacy.assert_not_called()


class TestBuildRunArgv(unittest.TestCase):
    """``_build_run_argv`` partitions a bare-prompt argv into a ``run`` call.

    Positional tokens join into a single ``target``; run flags (and the values
    of value-taking options) are appended after it.
    """

    VALUE_OPTS = {"--model", "-m", "--output", "-o"}

    def test_flagless_prompt(self):
        self.assertEqual(
            dispatcher._build_run_argv(["build", "a", "weather", "agent"], self.VALUE_OPTS),
            ["run", "build a weather agent"],
        )

    def test_value_flag_keeps_its_value(self):
        self.assertEqual(
            dispatcher._build_run_argv(
                ["fix", "the", "bug", "--model", "gpt-4o"], self.VALUE_OPTS
            ),
            ["run", "fix the bug", "--model", "gpt-4o"],
        )

    def test_boolean_flag_has_no_value(self):
        # ``--continue`` is not in VALUE_OPTS → the following positional is part
        # of the prompt, not the flag's value.
        self.assertEqual(
            dispatcher._build_run_argv(
                ["summarise", "--continue", "extra"], self.VALUE_OPTS
            ),
            ["run", "summarise extra", "--continue"],
        )

    def test_equals_form_needs_no_lookahead(self):
        self.assertEqual(
            dispatcher._build_run_argv(
                ["do", "it", "--model=gpt-4o"], self.VALUE_OPTS
            ),
            ["run", "do it", "--model=gpt-4o"],
        )

    def test_leading_flag_before_prompt(self):
        self.assertEqual(
            dispatcher._build_run_argv(
                ["-m", "gpt-4o", "fix", "bug"], self.VALUE_OPTS
            ),
            ["run", "fix bug", "-m", "gpt-4o"],
        )


class TestGetRunOptionNames(unittest.TestCase):
    """``_get_run_option_names`` introspects the real ``run`` command.

    The set must include the flags the issue lists (``--model``/``-m``,
    ``--continue``/``-c``, ``--session``/``-s``, ``--output``/``-o``,
    ``--stream``), so free-text prompts with those flags reach the modern
    engine. Value-taking options (``--model``) are distinguished from boolean
    flags (``--stream``).
    """

    def setUp(self):
        dispatcher._run_option_names_cache = None

    def tearDown(self):
        dispatcher._run_option_names_cache = None

    def test_includes_key_run_flags(self):
        result = dispatcher._get_run_option_names()
        self.assertIsNotNone(result)
        supported, value_opts = result
        for flag in ("--model", "-m", "--continue", "-c", "--session", "-s",
                     "--output", "-o", "--stream"):
            self.assertIn(flag, supported, f"{flag} missing from run option set")
        # Value-taking vs boolean discrimination.
        self.assertIn("--model", value_opts)
        self.assertNotIn("--stream", value_opts)

    def test_cached_after_first_call(self):
        first = dispatcher._get_run_option_names()
        self.assertIsNotNone(dispatcher._run_option_names_cache)
        second = dispatcher._get_run_option_names()
        self.assertEqual(first, second)

    def test_discovery_failure_returns_none_and_caches(self):
        with mock.patch(
            "typer.main.get_command", side_effect=RuntimeError("boom")
        ):
            result = dispatcher._get_run_option_names()
        self.assertIsNone(result)
        # Failure is cached as False so it isn't retried every dispatch.
        self.assertIs(dispatcher._run_option_names_cache, False)


class TestRunLegacyArgvRestoration(unittest.TestCase):
    """``_run_legacy`` must always restore ``sys.argv``, even on
    SystemExit, AND that restoration must have discriminating power."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_argv_restored_after_normal_exit(self):
        # NOTE: argv[0] differs from the dispatcher's rewrite ("praisonai")
        # so the assertion has discriminating power: if the ``finally``
        # clause were missing, ``sys.argv[0]`` would still be "praisonai"
        # after dispatch, and the equality check would fail.
        original = ["/usr/local/bin/some-launcher", "agents.yaml"]
        sys.argv = list(original)

        fake = mock.MagicMock()
        fake.main.return_value = None

        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit) as cm:
            dispatcher._run_legacy(["agents.yaml"])

        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(sys.argv, original)
        self.assertNotEqual(sys.argv[0], "praisonai")  # invariant pin

    def test_argv_restored_after_systemexit(self):
        original = ["/usr/local/bin/some-launcher", "topic"]
        sys.argv = list(original)

        fake = mock.MagicMock()
        fake.main.side_effect = SystemExit(2)

        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit) as cm:
            dispatcher._run_legacy(["topic"])

        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(sys.argv, original)
        self.assertNotEqual(sys.argv[0], "praisonai")

    def test_main_returning_false_translates_to_exit_code_1(self):
        sys.argv = ["/usr/local/bin/some-launcher", "topic"]
        fake = mock.MagicMock()
        fake.main.return_value = False
        with mock.patch("praisonai.cli.main.PraisonAI", return_value=fake), \
             self.assertRaises(SystemExit) as cm:
            dispatcher._run_legacy(["topic"])
        self.assertEqual(cm.exception.code, 1)


class TestRunTyperArgvRestoration(unittest.TestCase):
    """``_run_typer`` must restore argv even if the Typer app raises."""

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_argv_restored_after_systemexit(self):
        original = ["/usr/local/bin/some-launcher", "chat"]
        sys.argv = list(original)
        with mock.patch("praisonai.cli.app.register_commands"), \
             mock.patch("praisonai.cli.app.app", side_effect=SystemExit(0)), \
             self.assertRaises(SystemExit):
            dispatcher._run_typer(["chat"])
        self.assertEqual(sys.argv, original)
        self.assertNotEqual(sys.argv[0], "praisonai")


class TestTyperRegistrationFailureFailsLoud(unittest.TestCase):
    """``_run_typer`` must NOT swallow ``register_commands()`` exceptions.

    A registration failure (e.g. ``ImportError`` from a missing optional
    dependency) is a real misconfiguration: the user should see the
    underlying error rather than a silent fallback to "no commands
    registered". A future refactor that wraps ``register_commands()`` in a
    defensive try/except inside ``_run_typer`` would silently downgrade
    that to Typer's empty-app behaviour, so this test pins the invariant.
    """

    def setUp(self):
        self._saved_argv = sys.argv

    def tearDown(self):
        sys.argv = self._saved_argv

    def test_register_commands_importerror_propagates(self):
        sys.argv = ["praisonai", "chat"]
        with mock.patch(
            "praisonai.cli.app.register_commands",
            side_effect=ImportError("missing optional dep 'fakemod'"),
        ), self.assertRaises(ImportError) as cm:
            dispatcher._run_typer(["chat"])
        self.assertIn("fakemod", str(cm.exception))

    def test_register_commands_runtimeerror_propagates(self):
        sys.argv = ["praisonai", "chat"]
        with mock.patch(
            "praisonai.cli.app.register_commands",
            side_effect=RuntimeError("registration broke"),
        ), self.assertRaises(RuntimeError) as cm:
            dispatcher._run_typer(["chat"])
        self.assertIn("registration broke", str(cm.exception))


class TestCommandRegistryNoDrift(unittest.TestCase):
    """``get_command_names()`` must stay in sync with ``_LAZY_COMMANDS``.

    Regression guard for the duplicate-registry drift that misrouted six
    Typer commands (agent, auth, command, models, permissions, validate)
    to the legacy dispatcher. ``_LAZY_COMMANDS`` is the single source of
    truth (it also drives ``--help``); every command advertised there must
    be recognised by the routing decision in ``main()``.
    """

    def test_lazy_commands_subset_of_routing_names(self):
        from praisonai.cli import app as cli_app

        routing = cli_app.get_command_names()
        advertised = set(cli_app._LAZY_COMMANDS.keys())
        missing = advertised - routing
        self.assertEqual(
            missing,
            set(),
            f"Commands advertised in _LAZY_COMMANDS but not routed to Typer: {missing}",
        )

    def test_previously_drifted_commands_are_routed(self):
        from praisonai.cli import app as cli_app

        routing = cli_app.get_command_names()
        expected = {"agent", "auth", "command", "models", "permissions", "validate"}
        missing = expected - routing
        self.assertEqual(
            missing,
            set(),
            f"Previously-drifted commands not found in routing set: {missing}",
        )

    def test_flagless_operational_commands_are_typer_not_prompts(self):
        # Greptile P1 (flagless legacy-only commands) is a false positive:
        # ``serve``, ``call``, ``realtime``, ``debug``, ``lsp``, ``diag`` are all
        # registered Typer commands in ``_LAZY_COMMANDS`` and are therefore
        # recognised by ``get_command_names()`` — so ``main()`` routes them to
        # Typer at the command-membership check *before* ever reaching the
        # bare-prompt forwarder. Pin that so they never regress into prompts.
        from praisonai.cli import app as cli_app

        routing = cli_app.get_command_names()
        operational = {"serve", "call", "realtime", "debug", "lsp", "diag"}
        missing = operational - routing
        self.assertEqual(
            missing,
            set(),
            f"Operational commands not recognised as Typer commands "
            f"(would be misrouted to `run` as prompts): {missing}",
        )


class TestBotCommandRouting(unittest.TestCase):
    """Bot/channel commands route via C9 ``_BOT_RESIDENT_COMMANDS`` (C9).

    Bot-tier commands live in ``praisonai_bot.cli.commands.*`` and are loaded
    by ``get_command()`` when the bot package is installed. ``dashboard`` stays
    wrapper-resident via ``_WRAPPER_RESIDENT_COMMANDS`` →
    ``praisonai.cli.commands.dashboard``. All remain in ``_LAZY_COMMANDS`` so
    ``--help`` advertises them when the relevant package is available.
    """

    BOT_TIER_COMMANDS: ClassVar[FrozenSet[str]] = frozenset({
        "bot",
        "gateway",
        "onboard",
        "pairing",
        "identity",
        "kanban",
        "claw",
        "mint_link",
    })
    WRAPPER_ONLY: ClassVar[FrozenSet[str]] = frozenset({"dashboard"})
    ADVERTISED_COMMANDS: ClassVar[FrozenSet[str]] = BOT_TIER_COMMANDS | WRAPPER_ONLY

    def test_bot_commands_advertised(self):
        from praisonai.cli import app as cli_app

        routing = cli_app.get_command_names()
        missing = self.ADVERTISED_COMMANDS - routing
        self.assertEqual(
            missing,
            set(),
            f"Bot commands not advertised by get_command_names(): {missing}",
        )

    def test_bot_commands_in_bot_resident_registry(self):
        from praisonai.cli import app as cli_app

        missing = self.BOT_TIER_COMMANDS - set(cli_app._BOT_RESIDENT_COMMANDS)
        self.assertEqual(
            missing,
            set(),
            f"Bot commands missing from _BOT_RESIDENT_COMMANDS: {missing}",
        )

    def test_dashboard_in_wrapper_resident_registry(self):
        from praisonai.cli import app as cli_app

        missing = self.WRAPPER_ONLY - set(cli_app._WRAPPER_RESIDENT_COMMANDS)
        self.assertEqual(
            missing,
            set(),
            f"Wrapper commands missing from _WRAPPER_RESIDENT_COMMANDS: {missing}",
        )

    def test_bot_commands_present_in_lazy_registry(self):
        from praisonai.cli import app as cli_app

        missing = self.ADVERTISED_COMMANDS - set(cli_app._LAZY_COMMANDS.keys())
        self.assertEqual(
            missing,
            set(),
            f"Bot commands missing from _LAZY_COMMANDS (would not be advertised "
            f"in --help): {missing}",
        )

    def test_commands_reroute_to_correct_package_path(self):
        """``get_command`` must import bot-tier via ``praisonai_bot`` and
        wrapper-only via ``praisonai.cli.commands.*`` — never relative
        ``.commands.*`` inside ``praisonai_code``."""
        import importlib
        from unittest import mock
        from praisonai.cli import app as cli_app

        group = cli_app.LazyCommandGroup(name="praisonai")
        ctx = mock.MagicMock()
        real_import_module = importlib.import_module

        routing = [
            (name, f"praisonai_bot.cli.commands.{name}")
            for name in self.BOT_TIER_COMMANDS
        ] + [
            (name, f"praisonai.cli.commands.{name}")
            for name in self.WRAPPER_ONLY
        ]

        for name, expected_path in routing:
            imported = []

            def _spy(module_path, package=None, _imported=imported):
                _imported.append(module_path)
                return mock.MagicMock()

            with mock.patch.object(cli_app.TyperGroup, "get_command",
                                   return_value=None), \
                    mock.patch.object(cli_app, "typer_get_command",
                                      return_value=mock.MagicMock()), \
                    mock.patch.object(cli_app, "bot_package_available",
                                      return_value=True), \
                    mock.patch.object(cli_app, "wrapper_available",
                                      return_value=True), \
                    mock.patch.object(importlib, "import_module",
                                      side_effect=_spy), \
                    mock.patch.object(importlib.util, "find_spec",
                                      return_value=object()):
                cli_app.LazyCommandGroup.get_command(group, ctx, name)

            self.assertIn(
                expected_path,
                imported,
                f"Command '{name}' was not routed to '{expected_path}'; "
                f"imports seen: {imported}",
            )
            self.assertNotIn(
                f".commands.{name}",
                imported,
                f"Command '{name}' used relative '.commands.{name}' path.",
            )

        self.assertIs(importlib.import_module, real_import_module)


if __name__ == "__main__":
    unittest.main()
